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
  type TurnClaim,
  type WorkspaceBinding,
  type WorkspaceBindingKey,
} from "../runtime/mysql-state.js";

interface OpenedTurn {
  readonly binding: WorkspaceBinding;
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
  private readonly tokenProvider: TencentCloudDeploymentTokenProvider;
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
    this.tokenProvider = new TencentCloudDeploymentTokenProvider({
      deploymentId: this.config.hands.deploymentId,
      endpoint: this.config.hands.apiEndpoint,
      region: this.config.hands.region,
      secretId: this.config.hands.secretId,
      secretKey: this.config.hands.secretKey,
      ...(this.config.hands.sessionToken === undefined
        ? {}
        : { sessionToken: this.config.hands.sessionToken }),
    });
    this.gateway = new HandsGateway(new DeploymentSandboxFactory({
      baseUrl: this.config.hands.baseUrl,
      deploymentId: this.config.hands.deploymentId,
      deploymentToken: this.tokenProvider,
    }), this.state);

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
      this.tokenProvider.close();
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
    readonly binding: WorkspaceBinding;
    readonly claim: TurnClaim;
    readonly target: HandsTarget;
    readonly release: () => void;
  }> {
    const binding = await this.ensureBinding(agent.session.header);
    if (binding.deploymentId === undefined || binding.affinityId === undefined) {
      throw new Error(`Session ${agent.id} has no active Hands target`);
    }
    const claim = await this.state.claimTurn(
      agent.id,
      this.config.instanceId,
      this.config.turnLeaseMs,
      binding,
      agent.session.header,
    );
    try {
      const target: HandsTarget = {
        deploymentId: binding.deploymentId,
        affinityId: binding.affinityId,
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
      return { binding, claim, target, release };
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

  private async ensureBinding(meta: SessionHeader): Promise<WorkspaceBinding> {
    const existing = await this.state.getSessionBinding(meta.id);
    if (existing?.state === "ACTIVE") return existing;

    const key: WorkspaceBindingKey = {
      mode: "USER",
      identity: this.config.workspaceUserId,
    };
    const reservation = await this.state.reserveBinding(key);
    if (reservation.binding.state === "ACTIVE") return reservation.binding;
    if (reservation.owner) {
      const affinityId = await this.gateway.allocateAffinity();
      return this.state.activateBinding(
        key,
        reservation.binding.generation,
        this.config.hands.deploymentId,
        affinityId,
      );
    }

    for (let attempt = 0; attempt < 150; attempt += 1) {
      await new Promise<void>((resolve) => setTimeout(resolve, 200));
      const binding = await this.state.getBinding(key);
      if (binding?.state === "ACTIVE") return binding;
    }
    throw new Error("Hands workspace allocation did not become active");
  }
}

export default AgsWebRuntime;
