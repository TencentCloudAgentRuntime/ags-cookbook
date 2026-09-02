import { randomUUID } from "node:crypto";
import { createServer, type IncomingMessage, type ServerResponse } from "node:http";

import { Context } from "@deepseek-ai/cordis";
import * as AgentSpine from "@deepseek-ai/dsh-agent-spine-demo";
import { createUserMessage } from "@deepseek-ai/dsh-llm";
import * as PiAi from "@deepseek-ai/dsh-llm-pi-ai";
import {
  SESSION_FORMAT_VERSION,
  SessionId,
  type Session,
  type SessionHeader,
} from "@deepseek-ai/dsh-session";
import { config as loadDotenv } from "dotenv";

import { HandsGateway, type HandsTarget } from "../hands/gateway.js";
import { DeploymentSandboxFactory } from "../hands/deployment-sandbox.js";
import { TencentCloudDeploymentTokenProvider } from "../hands/deployment-token.js";
import { MysqlSessionPersistence } from "../persistence/mysql-session-persistence.js";
import {
  MysqlRuntimeState,
  RuntimeStateConflictError,
  SessionBusyError,
  type WorkspaceBinding,
  type WorkspaceBindingKey,
  type WorkspaceBindingMode,
} from "../runtime/mysql-state.js";
import { TurnContext } from "../runtime/turn-context.js";
import { brainConfigFromEnv, type BrainConfig } from "./config.js";
import { ActiveTurnTargets, handsToolsPlugin } from "./hands-tools.js";

const MAX_JSON_BYTES = 1024 * 1024;

export const BRAIN_SPINE_CONFIG: AgentSpine.Config = {
  workspaceContext: false,
  skills: { enabled: false },
  toolBash: false,
  toolJobs: false,
  goals: false,
  maxParallelToolCalls: 1,
  tools: { mode: "native" },
  toolOrder: ["bash", "read", "write", "edit", "<unlisted-tools>"],
  persona: "You are the Brain. Use the provided Hands tools for all workspace operations.",
};

async function waitForServices(context: Context, names: readonly string[], timeoutMs = 5_000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const missing = names.filter((name) => context.get(name) === undefined);
    if (missing.length === 0) return;
    if (Date.now() >= deadline) {
      throw new Error(`Brain agent spine failed to start: missing ${missing.join(", ")}`);
    }
    await new Promise<void>((resolve) => setTimeout(resolve, 10));
  }
}

class HttpError extends Error {
  public constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly details?: Readonly<Record<string, string>>,
  ) {
    super(message);
    this.name = "HttpError";
  }
}

export class BrainRuntime {
  private readonly ctx = new Context();
  private readonly state: MysqlRuntimeState;
  private readonly turnContext = new TurnContext();
  private readonly targets = new ActiveTurnTargets();
  private readonly tokenProvider: TencentCloudDeploymentTokenProvider;
  private readonly gateway: HandsGateway;
  private ready = false;

  public constructor(private readonly config: BrainConfig) {
    this.state = new MysqlRuntimeState(config.mysql);
    this.tokenProvider = new TencentCloudDeploymentTokenProvider({
      deploymentId: config.hands.deploymentId,
      endpoint: config.hands.apiEndpoint,
      region: config.hands.region,
      secretId: config.hands.secretId,
      secretKey: config.hands.secretKey,
      ...(config.hands.sessionToken === undefined ? {} : { sessionToken: config.hands.sessionToken }),
    });
    const sandboxFactory = new DeploymentSandboxFactory({
      baseUrl: config.hands.baseUrl,
      deploymentId: config.hands.deploymentId,
      deploymentToken: this.tokenProvider,
    });
    this.gateway = new HandsGateway(sandboxFactory, this.state);
  }

  public async start(): Promise<void> {
    const persistence = this.ctx.plugin(MysqlSessionPersistence, {
      connection: this.config.mysql,
      currentTurnClaim: (sessionId) => this.turnContext.current(sessionId),
    });
    const spine = this.ctx.plugin(AgentSpine, BRAIN_SPINE_CONFIG);
    const llm = this.ctx.plugin(PiAi, {
      providers: {
        [this.config.llm.provider]: {
          displayName: "Tencent Cloud TokenHub",
          apiKeyEnv: this.config.llm.apiKeyEnv,
          api: "openai-completions",
          baseURL: this.config.llm.baseUrl,
          compat: { thinkingFormat: "deepseek" },
          models: [{
            id: this.config.llm.model,
            contextWindow: 128_000,
            maxTokens: this.config.llm.maxTokens,
          }],
        },
      },
    });
    const tools = this.ctx.plugin(handsToolsPlugin, { gateway: this.gateway, targets: this.targets });
    await Promise.all([persistence.await(), spine.await(), llm.await(), tools.await()]);
    await waitForServices(this.ctx, ["systemPrompt", "tools", "agentLoop"]);
    await this.state.ping();
    this.ready = true;
  }

  public isReady(): boolean {
    return this.ready;
  }

  public async checkReady(): Promise<void> {
    if (!this.ready) throw new Error("Brain is starting");
    await this.state.ping();
  }

  public async createSession(workspaceMode: "user" | "session"): Promise<{ sessionId: string }> {
    const sessionId = randomUUID();
    const header = sessionHeader(sessionId);
    const key = this.bindingKey(workspaceMode, sessionId);
    const reservation = await this.state.reserveBinding(key);
    if (reservation.binding.state === "ACTIVE") {
      await this.state.provisionSession(header, key, reservation.binding.generation);
      return { sessionId };
    }
    if (!reservation.owner) {
      throw new HttpError(409, "WORKSPACE_RECOVERY_REQUIRED", "Workspace allocation needs explicit recovery", {
        sessionId,
      });
    }
    await this.allocateAndPublish(header, key, reservation.binding);
    return { sessionId };
  }

  public async recoverSession(sessionId: string): Promise<{ sessionId: string }> {
    assertIdentifier(sessionId, "session ID");
    const existing = await this.state.getSessionBinding(sessionId);
    if (existing?.state === "ACTIVE") return { sessionId };
    const header = sessionHeader(sessionId);
    let key: WorkspaceBindingKey = { mode: "SESSION", identity: sessionId };
    let binding = await this.state.getBinding(key);
    if (binding === undefined) {
      key = { mode: "USER", identity: this.config.workspaceUserId };
      binding = await this.state.getBinding(key);
    }
    if (binding === undefined) throw new HttpError(404, "SESSION_NOT_FOUND", "No recoverable workspace binding exists");
    if (binding.state === "ACTIVE") {
      await this.state.provisionSession(header, key, binding.generation);
      return { sessionId };
    }
    const retried = await this.state.retryBinding(key);
    await this.allocateAndPublish(header, key, retried);
    return { sessionId };
  }

  public async runTurn(sessionId: string, message: string): Promise<Readonly<Record<string, unknown>>> {
    assertIdentifier(sessionId, "session ID");
    if (message.length === 0 || Buffer.byteLength(message, "utf8") > MAX_JSON_BYTES) {
      throw new HttpError(400, "INVALID_MESSAGE", "message must be non-empty and at most 1 MiB");
    }
    const binding = await this.state.getSessionBinding(sessionId);
    if (binding?.state !== "ACTIVE" || binding.deploymentId === undefined || binding.affinityId === undefined) {
      throw new HttpError(404, "SESSION_NOT_FOUND", "Session has no active Hands workspace");
    }
    let claim;
    try {
      claim = await this.state.claimTurn(
        sessionId,
        this.config.instanceId,
        this.config.turnLeaseMs,
        binding,
      );
    } catch (error) {
      if (error instanceof SessionBusyError) throw new HttpError(409, "SESSION_BUSY", error.message);
      throw error;
    }
    const target: HandsTarget = {
      deploymentId: binding.deploymentId,
      affinityId: binding.affinityId,
      claim,
    };

    return this.turnContext.run(claim, async () => {
      const handle = await this.ctx.agents.resume({
        resumeSessionId: SessionId(sessionId),
        agentOptions: {
          provider: this.config.llm.provider,
          model: this.config.llm.model,
          maxTokens: this.config.llm.maxTokens,
        },
      });
      const responseStartSeq = handle.agent.session.seq;
      let unbind: (() => void) | undefined;
      let heartbeatFailure: unknown;
      let heartbeatRunning = false;
      let heartbeat: NodeJS.Timeout | undefined;
      try {
        unbind = this.targets.bind(sessionId, target);
        heartbeat = setInterval(() => {
          if (heartbeatRunning || heartbeatFailure !== undefined) return;
          heartbeatRunning = true;
          void this.state.heartbeatTurn(claim, this.config.turnLeaseMs).catch((error: unknown) => {
            heartbeatFailure = error;
            handle.agent.cancel({ kind: "hook", reason: "turn lease lost" });
          }).finally(() => {
            heartbeatRunning = false;
          });
        }, Math.max(1_000, Math.floor(this.config.turnLeaseMs / 3)));
        heartbeat.unref();
        handle.agent.followup(createUserMessage({
          source: { kind: "user" },
          content: [{ type: "text", text: message }],
        }));
        await handle.agent.whenIdle();
        if (heartbeatFailure !== undefined) throw heartbeatFailure;
        await this.ctx.sessions.flush(handle.agent.session);
        const response = assistantResponse(handle.agent.session, responseStartSeq);
        await handle.dispose();
        await this.state.completeTurn(claim);
        return response;
      } finally {
        if (heartbeat !== undefined) clearInterval(heartbeat);
        unbind?.();
        if (this.ctx.agents.get(SessionId(sessionId)) !== undefined) {
          await handle.dispose().catch(() => undefined);
        }
      }
    });
  }

  private bindingKey(mode: "user" | "session", sessionId: string): WorkspaceBindingKey {
    const bindingMode: WorkspaceBindingMode = mode === "user" ? "USER" : "SESSION";
    return {
      mode: bindingMode,
      identity: bindingMode === "USER" ? this.config.workspaceUserId : sessionId,
    };
  }

  private async allocateAndPublish(
    header: SessionHeader,
    key: WorkspaceBindingKey,
    binding: WorkspaceBinding,
  ): Promise<void> {
    try {
      const affinityId = await this.gateway.allocateAffinity();
      await this.state.activateBindingAndProvisionSession(
        header,
        key,
        binding.generation,
        this.config.hands.deploymentId,
        affinityId,
      );
    } catch (error) {
      throw new HttpError(503, "WORKSPACE_RECOVERY_REQUIRED", "Workspace allocation needs explicit recovery", {
        sessionId: header.id,
      });
    }
  }

  public async close(): Promise<void> {
    this.ready = false;
    try {
      await this.ctx.fiber.dispose();
    } finally {
      this.tokenProvider.close();
      await this.state.close();
    }
  }
}

function sessionHeader(id: string): SessionHeader {
  assertIdentifier(id, "session ID");
  return {
    version: SESSION_FORMAT_VERSION,
    id: SessionId(id),
    createdAt: Date.now(),
    cwd: "/workspace",
  };
}

export function assistantResponse(session: Session, fromSeq: number): Readonly<Record<string, unknown>> {
  const event = [...session.events].reverse().find((candidate) =>
    candidate.seq >= fromSeq && candidate.type === "assistant/message");
  if (event?.type !== "assistant/message") {
    throw new HttpError(502, "NO_ASSISTANT_RESPONSE", "The model produced no assistant message");
  }
  const content = event.data.message.content;
  return {
    sessionId: session.id,
    messageId: event.data.message.id,
    content,
    text: content.flatMap((block) => block.type === "text" ? [block.text] : []).join(""),
  };
}

function assertIdentifier(value: string, label: string): void {
  if (value.length === 0 || value.length > 191 || /[\u0000-\u001f]/u.test(value)) {
    throw new HttpError(400, "INVALID_ID", `${label} is invalid`);
  }
}

async function readJson(request: IncomingMessage): Promise<unknown> {
  const chunks: Buffer[] = [];
  let length = 0;
  for await (const chunk of request) {
    const bytes = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
    length += bytes.byteLength;
    if (length > MAX_JSON_BYTES) throw new HttpError(413, "BODY_TOO_LARGE", "JSON body exceeds 1 MiB");
    chunks.push(bytes);
  }
  try {
    return JSON.parse(Buffer.concat(chunks).toString("utf8")) as unknown;
  } catch {
    throw new HttpError(400, "INVALID_JSON", "Request body must be valid JSON");
  }
}

function objectBody(value: unknown): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new HttpError(400, "INVALID_BODY", "Request body must be a JSON object");
  }
  return value as Record<string, unknown>;
}

function sendJson(response: ServerResponse, status: number, body: unknown): void {
  response.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "cache-control": "no-store",
  });
  response.end(`${JSON.stringify(body)}\n`);
}

async function route(runtime: BrainRuntime, request: IncomingMessage, response: ServerResponse): Promise<void> {
  const url = new URL(request.url ?? "/", "http://brain.invalid");
  if (request.method === "GET" && url.pathname === "/healthz") {
    sendJson(response, 200, { ok: true });
    return;
  }
  if (request.method === "GET" && url.pathname === "/readyz") {
    await runtime.checkReady();
    sendJson(response, 200, { ok: true });
    return;
  }
  if (request.method === "POST" && url.pathname === "/v1/sessions") {
    const body = objectBody(await readJson(request));
    if (body.workspaceMode !== "user" && body.workspaceMode !== "session") {
      throw new HttpError(400, "INVALID_WORKSPACE_MODE", "workspaceMode must be user or session");
    }
    sendJson(response, 201, await runtime.createSession(body.workspaceMode));
    return;
  }
  const turn = /^\/v1\/sessions\/([^/]+)\/turns$/u.exec(url.pathname);
  if (request.method === "POST" && turn !== null) {
    const body = objectBody(await readJson(request));
    if (typeof body.message !== "string") throw new HttpError(400, "INVALID_MESSAGE", "message must be a string");
    sendJson(response, 200, await runtime.runTurn(decodeURIComponent(turn[1] ?? ""), body.message));
    return;
  }
  const recovery = /^\/v1\/sessions\/([^/]+)\/recover$/u.exec(url.pathname);
  if (request.method === "POST" && recovery !== null) {
    sendJson(response, 200, await runtime.recoverSession(decodeURIComponent(recovery[1] ?? "")));
    return;
  }
  throw new HttpError(404, "NOT_FOUND", "Route not found");
}

export async function main(): Promise<void> {
  loadDotenv();
  const config = brainConfigFromEnv();
  const runtime = new BrainRuntime(config);
  await runtime.start();
  const server = createServer((request, response) => {
    void route(runtime, request, response).catch((error: unknown) => {
      const failure = error instanceof HttpError
        ? error
        : error instanceof RuntimeStateConflictError
          ? new HttpError(409, "STATE_CONFLICT", error.message)
          : new HttpError(500, "INTERNAL", "Internal Brain error");
      sendJson(response, failure.status, {
        error: failure.code,
        message: failure.message,
        ...(failure.details === undefined ? {} : failure.details),
      });
    });
  });
  await new Promise<void>((resolve, reject) => {
    server.once("error", reject);
    server.listen(config.port, "0.0.0.0", resolve);
  });
  let stopping: Promise<void> | undefined;
  const stop = (): Promise<void> => {
    stopping ??= (async () => {
      await new Promise<void>((resolve, reject) => {
        server.close((error) => error === undefined ? resolve() : reject(error));
      });
      await runtime.close();
    })();
    return stopping;
  };
  process.once("SIGTERM", () => void stop());
  process.once("SIGINT", () => void stop());
}

if (import.meta.url === `file://${process.argv[1]}`) {
  await main();
}
