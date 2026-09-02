import { Context, Service } from "@deepseek-ai/cordis";
import type { Agent, PreStepDecision } from "@deepseek-ai/dsh-agent";
import { SessionId, type SessionEvent, type SessionHeader } from "@deepseek-ai/dsh-session";

import { brainConfigFromEnv, type BrainConfig } from "../brain/config.js";
import { ActiveTurnTargets, handsToolDefinitions } from "../brain/hands-tools.js";
import { DeploymentSandboxFactory } from "../hands/deployment-sandbox.js";
import { TencentCloudDeploymentTokenProvider } from "../hands/deployment-token.js";
import { HandsGateway, type HandsTarget } from "../hands/gateway.js";
import {
  MysqlRuntimeState,
  type HandsWorkspace,
  type TurnClaim,
} from "../runtime/mysql-state.js";
import { workspaceIdFromCwd } from "./workspace-path.js";

interface OpenedTurn {
  readonly workspace: HandsWorkspace;
  readonly claim: TurnClaim;
  readonly target: HandsTarget;
  readonly release: () => void;
}

interface ActiveTurn {
  readonly agent: Agent;
  readonly previous: Promise<void>;
  readonly startSeq: number;
  readonly ready: Promise<OpenedTurn>;
  readonly start: () => void;
  started: boolean;
  acceptingWrites: boolean;
  boundarySeq?: number;
  hasTurn: boolean;
  closing?: Promise<void>;
}

declare module "@deepseek-ai/cordis" {
  interface Context {
    agsWebRuntime: AgsWebRuntime;
  }
}

export function startsTurn(events: readonly SessionEvent[]): boolean {
  return events.some((event) => event.type === "turn/start");
}

/** Connects native DSH Web turns to MySQL fencing and remote Hands. */
export class AgsWebRuntime extends Service {
  public static inject = ["agents", "sessions"];

  private readonly config: BrainConfig;
  private readonly state: MysqlRuntimeState;
  private readonly tokenProviders: readonly TencentCloudDeploymentTokenProvider[];
  private readonly gateway: HandsGateway;
  private readonly targets = new ActiveTurnTargets();
  private readonly active = new Map<string, ActiveTurn>();
  private readonly closing = new Map<string, ActiveTurn[]>();
  private readonly byAgent = new WeakMap<Agent, ActiveTurn>();
  private readonly tails = new Map<string, Promise<void>>();

  public constructor(ctx: Context) {
    super(ctx, "agsWebRuntime");
    this.config = brainConfigFromEnv();
    this.state = new MysqlRuntimeState(this.config.mysql);
    this.tokenProviders = this.config.hands.oses.map((os) => new TencentCloudDeploymentTokenProvider({
      deploymentId: os.deploymentId,
      endpoint: this.config.hands.apiEndpoint,
      region: this.config.hands.region,
      secretId: this.config.hands.secretId,
      secretKey: this.config.hands.secretKey,
      ...(this.config.hands.sessionToken === undefined
        ? {}
        : { sessionToken: this.config.hands.sessionToken }),
    }));
    this.gateway = new HandsGateway(this.config.hands.oses.map((os, index) => new DeploymentSandboxFactory({
      baseUrl: os.baseUrl,
      deploymentId: os.deploymentId,
      deploymentToken: this.tokenProviders[index]!,
    })), this.state);

    ctx.inject(["tools"], (toolsCtx) => {
      const definitions = handsToolDefinitions({ gateway: this.gateway, targets: this.targets });
      toolsCtx.effect(function* () {
        for (const definition of definitions) yield toolsCtx.tools.register(definition);
      }, "register AGS Hands tools");
    });

    ctx.on("agent/status", ({ agent, status }) => {
      if (status === "running") this.begin(agent);
      else this.finish(agent);
    });
    ctx.on("agent/pre-step", async ({ agent }, next): Promise<PreStepDecision> => {
      const activity = this.byAgent.get(agent);
      if (activity === undefined) throw new Error(`No AGS turn activity for session ${agent.id}`);
      if (!activity.started) {
        await this.ctx.sessions.flush(agent.session);
        if (!activity.started) {
          await activity.previous;
          activity.start();
        }
      }
      await activity.ready;
      return next();
    });
    ctx.effect(() => async () => {
      await Promise.allSettled([...this.active.values()].map((activity) => this.closeTurn(activity)));
      await Promise.allSettled([...this.tails.values()]);
      for (const provider of this.tokenProviders) provider.close();
      await this.state.close();
    }, "close AGS Web runtime");
  }

  /** MySQL persistence calls this before each durable append. */
  public async currentTurnClaim(
    sessionId: string,
    events: readonly SessionEvent[],
  ): Promise<TurnClaim | null | undefined> {
    const closing = this.closing.get(sessionId)?.[0];
    if (closing !== undefined) {
      const boundarySeq = closing.boundarySeq;
      const ownsTurnStart = boundarySeq !== undefined && events.some((event) =>
        event.type === "turn/start"
          && event.seq >= closing.startSeq
          && event.seq < boundarySeq);
      if (closing.acceptingWrites && (closing.started || ownsTurnStart)) {
        if (!closing.started) closing.start();
        return (await closing.ready).claim;
      }
      await closing.closing;
      return this.currentTurnClaim(sessionId, events);
    }

    let activity = this.active.get(sessionId);
    if (activity === undefined) {
      if (!startsTurn(events)) return null;
      const agent = this.ctx.agents.get(SessionId(sessionId));
      if (agent === undefined) return undefined;
      this.begin(agent);
      activity = this.byAgent.get(agent);
    }
    if (activity === undefined) return undefined;
    if (!activity.started) {
      if (!startsTurn(events)) return null;
      activity.start();
    }
    return (await activity.ready).claim;
  }

  private begin(agent: Agent): void {
    if (this.byAgent.has(agent)) return;
    const sessionId = agent.id;
    const previous = this.tails.get(sessionId) ?? Promise.resolve();
    let activity!: ActiveTurn;
    let resolveReady!: (opened: OpenedTurn) => void;
    let rejectReady!: (error: unknown) => void;
    const ready = new Promise<OpenedTurn>((resolve, reject) => {
      resolveReady = resolve;
      rejectReady = reject;
    });
    activity = {
      agent,
      previous,
      startSeq: agent.session.seq,
      ready,
      started: false,
      acceptingWrites: false,
      hasTurn: false,
      start: () => {
        if (activity.started) return;
        activity.started = true;
        void previous.then(() => this.openTurn(agent)).then(resolveReady, rejectReady);
      },
    };
    this.active.set(sessionId, activity);
    this.byAgent.set(agent, activity);
    void ready.catch((error: unknown) => {
      agent.cancel({ kind: "hook", reason: `AGS turn setup failed: ${String(error)}` });
    });
  }

  private finish(agent: Agent): void {
    const activity = this.byAgent.get(agent);
    if (activity === undefined) return;
    this.byAgent.delete(agent);
    activity.boundarySeq = agent.session.seq;
    activity.hasTurn = agent.session.events
      .slice(activity.startSeq, activity.boundarySeq)
      .some((event) => event.type === "turn/start");
    activity.acceptingWrites = true;
    const queue = this.closing.get(agent.id) ?? [];
    queue.push(activity);
    this.closing.set(agent.id, queue);
    const closing = this.closeTurn(activity);
    activity.closing = closing;
    const settled = closing.catch((error: unknown) => {
      this.ctx.logger.error(`AGS turn cleanup failed for session ${agent.id}: ${String(error)}`);
    });
    this.tails.set(agent.id, settled);
    void settled.finally(() => {
      if (this.tails.get(agent.id) === settled) this.tails.delete(agent.id);
    });
  }

  private async openTurn(agent: Agent): Promise<{
    readonly workspace: HandsWorkspace;
    readonly claim: TurnClaim;
    readonly target: HandsTarget;
    readonly release: () => void;
  }> {
    const workspace = await this.ensureWorkspace(agent.session.header);
    if (workspace.affinityId === undefined) {
      throw new Error(`Session ${agent.id} has no active Hands target`);
    }
    const claim = await this.state.claimTurn(
      agent.id,
      this.config.instanceId,
      this.config.turnLeaseMs,
      workspace.id,
      agent.session.header,
    );
    try {
      const target: HandsTarget = {
        deploymentId: workspace.deploymentId,
        affinityId: workspace.affinityId,
        claim,
      };
      const unbind = this.targets.bind(agent.id, target);
      const heartbeat = setInterval(() => {
        void this.state.heartbeatTurn(claim, this.config.turnLeaseMs).catch((error: unknown) => {
          agent.cancel({ kind: "hook", reason: `AGS turn lease lost: ${String(error)}` });
        });
      }, Math.max(1_000, Math.floor(this.config.turnLeaseMs / 3)));
      heartbeat.unref();
      let released = false;
      const release = (): void => {
        if (released) return;
        released = true;
        clearInterval(heartbeat);
        unbind();
      };
      return { workspace, claim, target, release };
    } catch (error) {
      await this.state.completeTurn(claim);
      throw error;
    }
  }

  private async closeTurn(activity: ActiveTurn): Promise<void> {
    if (activity.closing !== undefined) return activity.closing;
    let release: (() => void) | undefined;
    try {
      await activity.previous;
      if (!activity.started && !activity.hasTurn) return;
      await this.ctx.sessions.flush(activity.agent.session);
      activity.acceptingWrites = false;
      if (!activity.started) return;
      const opened = await activity.ready;
      release = opened.release;
      await this.state.completeTurn(opened.claim);
    } finally {
      activity.acceptingWrites = false;
      release?.();
      const queue = this.closing.get(activity.agent.id);
      if (queue?.[0] === activity) queue.shift();
      else if (queue !== undefined) {
        const index = queue.indexOf(activity);
        if (index >= 0) queue.splice(index, 1);
      }
      if (queue?.length === 0) this.closing.delete(activity.agent.id);
      if (this.active.get(activity.agent.id) === activity) this.active.delete(activity.agent.id);
    }
  }

  private async ensureWorkspace(meta: SessionHeader): Promise<HandsWorkspace> {
    const workspaceId = workspaceIdFromCwd(meta.cwd);
    if (workspaceId === undefined) throw new Error("Session does not belong to a managed Workspace");
    const existing = await this.state.getWorkspace(workspaceId);
    if (existing?.state === "ACTIVE") return existing;
    const allocation = await this.state.claimWorkspaceAllocation(workspaceId);
    if (allocation.workspace.state === "ACTIVE") return allocation.workspace;
    if (allocation.owner) {
      if (allocation.token === undefined) throw new Error("Workspace allocation token is missing");
      const allocationToken = allocation.token;
      const abort = new AbortController();
      let leaseFailure: unknown;
      const heartbeat = setInterval(() => {
        void this.state.heartbeatWorkspaceAllocation(
          workspaceId,
          allocationToken,
          allocation.workspace.generation,
        ).catch((error: unknown) => {
          leaseFailure = error;
          abort.abort(error);
        });
      }, 10_000);
      heartbeat.unref();
      try {
        const affinityId = await this.gateway.allocateAffinity(
          allocation.workspace.deploymentId,
          abort.signal,
        );
        if (leaseFailure !== undefined) throw leaseFailure;
        return await this.state.activateWorkspace(
          workspaceId,
          allocationToken,
          allocation.workspace.generation,
          affinityId,
        );
      } catch (error) {
        await this.state.failWorkspaceAllocation(
          workspaceId,
          allocationToken,
          allocation.workspace.generation,
          "ALLOCATION_FAILED",
        ).catch(() => undefined);
        throw error;
      } finally {
        clearInterval(heartbeat);
      }
    }

    for (let attempt = 0; attempt < 300; attempt += 1) {
      await new Promise<void>((resolve) => setTimeout(resolve, 200));
      const workspace = await this.state.getWorkspace(workspaceId);
      if (workspace?.state === "ACTIVE") return workspace;
      if (attempt > 0 && attempt % 25 === 0) return this.ensureWorkspace(meta);
    }
    throw new Error("Workspace allocation did not become active");
  }
}

export default AgsWebRuntime;
