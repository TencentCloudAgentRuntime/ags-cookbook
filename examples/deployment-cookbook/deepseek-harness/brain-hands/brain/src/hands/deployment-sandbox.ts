import { Sandbox, type SandboxConnectOpts } from "e2b";

import type { DeploymentTokenProvider } from "./deployment-token.js";

export const ENVD_PORT = 49_983;
export const ENVD_VERSION = "0.6.13";
export const DEFAULT_AFFINITY_HEADER = "X-Tencent-Agr-Affinity-Id";

export interface DeploymentSandboxConfig {
  readonly baseUrl: string;
  readonly deploymentId: string;
  readonly deploymentToken: DeploymentTokenProvider;
  readonly affinityHeader?: string;
  readonly envdUser?: string;
  readonly requestTimeoutMs?: number;
}

type ConnectedSandboxOptions = SandboxConnectOpts & {
  readonly sandboxId: string;
  readonly sandboxUrl: string;
  readonly envdVersion: string;
};

class ConnectedDeploymentSandbox extends Sandbox {
  public constructor(options: ConnectedSandboxOptions) {
    super(options);
  }
}

export interface EnvdSandboxFactory {
  readonly deploymentId: string;
  allocateAffinity(signal?: AbortSignal): Promise<string>;
  health(affinityId: string, signal?: AbortSignal): Promise<Response>;
  connect(affinityId: string): Promise<Sandbox>;
}

/** Connects the E2B 2.29.1 client to one AGS Hands Deployment. */
export class DeploymentSandboxFactory implements EnvdSandboxFactory {
  public readonly deploymentId: string;
  private readonly baseUrl: string;
  private readonly deploymentToken: DeploymentTokenProvider;
  private readonly affinityHeader: string;
  private readonly envdUser: string;
  private readonly requestTimeoutMs: number;
  private readonly fetchImpl: typeof fetch;

  public constructor(config: DeploymentSandboxConfig, fetchImpl: typeof fetch = fetch) {
    this.deploymentId = config.deploymentId;
    this.baseUrl = config.baseUrl.replace(/\/+$/u, "");
    this.deploymentToken = config.deploymentToken;
    this.affinityHeader = config.affinityHeader ?? DEFAULT_AFFINITY_HEADER;
    this.envdUser = config.envdUser ?? "root";
    this.requestTimeoutMs = config.requestTimeoutMs ?? 30_000;
    this.fetchImpl = fetchImpl;
    if (!isHttpUrl(this.baseUrl)) throw new Error("Hands Deployment URL must be HTTP or HTTPS");
    validateHeaderValue(this.deploymentId, "Deployment ID");
    validateHeaderName(this.affinityHeader, "affinity header name");
    validateHeaderValue(this.envdUser, "envd user");
  }

  public async allocateAffinity(signal?: AbortSignal): Promise<string> {
    await this.deploymentToken.ensureValid();
    const response = await this.fetchImpl(`${this.baseUrl}/health`, {
      method: "GET",
      headers: this.directHeaders(),
      signal: requestSignal(signal, this.requestTimeoutMs),
      redirect: "error",
    });
    if (!response.ok) throw new Error(`envd health returned HTTP ${response.status}`);
    const affinity = response.headers.get(this.affinityHeader);
    if (affinity === null) throw new Error("envd health returned no affinity ID");
    validateAffinity(affinity);
    return affinity;
  }

  public async health(affinityId: string, signal?: AbortSignal): Promise<Response> {
    validateAffinity(affinityId);
    await this.deploymentToken.ensureValid();
    return this.fetchImpl(`${this.baseUrl}/health`, {
      method: "GET",
      headers: { ...this.directHeaders(), [this.affinityHeader]: affinityId },
      signal: requestSignal(signal, this.requestTimeoutMs),
      redirect: "error",
    });
  }

  public async connect(affinityId: string): Promise<Sandbox> {
    validateAffinity(affinityId);
    await this.deploymentToken.ensureValid();
    const sandbox = new ConnectedDeploymentSandbox({
      sandboxId: this.deploymentId,
      sandboxUrl: this.baseUrl,
      envdVersion: ENVD_VERSION,
      requestTimeoutMs: this.requestTimeoutMs,
    });
    installRequestHeaders(sandbox, {
      Authorization: basicAuthorization(this.envdUser),
      [this.affinityHeader]: affinityId,
    }, this.deploymentToken);
    return sandbox;
  }

  private directHeaders(): Record<string, string> {
    return {
      Authorization: basicAuthorization(this.envdUser),
      "E2b-Sandbox-Id": this.deploymentId,
      "E2b-Sandbox-Port": String(ENVD_PORT),
      "X-Access-Token": this.deploymentToken.currentToken(),
    };
  }
}

function installRequestHeaders(
  sandbox: Sandbox,
  fixedHeaders: Readonly<Record<string, string>>,
  deploymentToken: DeploymentTokenProvider,
): void {
  for (const owner of [sandbox.files, sandbox.commands, sandbox.pty]) {
    const rpc = privateObject(owner, "rpc");
    privateSet(owner, "rpc", withRequestHeaders(rpc, fixedHeaders, deploymentToken));
  }
  const envdApi = privateObject(sandbox, "envdApi");
  const api = privateObject(envdApi, "api");
  privateSet(envdApi, "api", withRequestHeaders(api, fixedHeaders, deploymentToken));
}

function withRequestHeaders<T extends object>(
  target: T,
  fixedHeaders: Readonly<Record<string, string>>,
  deploymentToken: DeploymentTokenProvider,
): T {
  return new Proxy(target, {
    get(original, property, receiver) {
      const value = Reflect.get(original, property, receiver);
      if (typeof value !== "function") return value;
      return (...args: unknown[]) => {
        const callArgs = [...args];
        const options = isRecord(callArgs[1]) ? { ...callArgs[1] } : {};
        const headers = new Headers(options.headers as HeadersInit | undefined);
        for (const [name, headerValue] of Object.entries(fixedHeaders)) headers.set(name, headerValue);
        headers.set("X-Access-Token", deploymentToken.currentToken());
        options.headers = headers;
        callArgs[1] = options;
        return Reflect.apply(value, original, callArgs);
      };
    },
  });
}

function privateObject(target: object, property: string): Record<PropertyKey, unknown> {
  const value = Reflect.get(target, property);
  if (typeof value !== "object" || value === null) {
    throw new Error(`E2B 2.29.1 transport contract changed: ${property} is unavailable`);
  }
  return value as Record<PropertyKey, unknown>;
}

function privateSet(target: object, property: string, value: unknown): void {
  if (!Reflect.set(target, property, value)) {
    throw new Error(`E2B 2.29.1 transport contract changed: ${property} cannot be wrapped`);
  }
}

function requestSignal(signal: AbortSignal | undefined, timeoutMs: number): AbortSignal {
  const timeout = AbortSignal.timeout(timeoutMs);
  return signal === undefined ? timeout : AbortSignal.any([signal, timeout]);
}

function basicAuthorization(user: string): string {
  return `Basic ${Buffer.from(`${user}:`, "utf8").toString("base64")}`;
}

function isHttpUrl(value: string): boolean {
  try {
    return ["http:", "https:"].includes(new URL(value).protocol);
  } catch {
    return false;
  }
}

function validateHeaderName(value: string, label: string): void {
  if (!/^[!#$%&'*+.^_`|~0-9A-Za-z-]+$/u.test(value)) throw new Error(`${label} is invalid`);
}

function validateHeaderValue(value: string, label: string): void {
  if (value.trim().length === 0 || /[\r\n]/u.test(value)) throw new Error(`${label} is invalid`);
}

function validateAffinity(value: string): void {
  validateHeaderValue(value, "affinity ID");
  if (!/^[\x20-\x7e]+$/u.test(value) || Buffer.byteLength(value, "utf8") > 1024) {
    throw new Error("affinity ID is invalid");
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
