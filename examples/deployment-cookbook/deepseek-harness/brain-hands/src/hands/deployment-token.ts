import { CommonClient } from "tencentcloud-sdk-nodejs-common";

const AGS_API_VERSION = "2025-09-20";
const REFRESH_MARGIN_MS = 60_000;

export interface DeploymentTokenProvider {
  ensureValid(): Promise<void>;
  currentToken(): string;
  close(): void;
}

interface CommonClientLike {
  request(action: string, request: unknown): Promise<unknown>;
}

export interface TencentCloudDeploymentTokenConfig {
  readonly deploymentId: string;
  readonly endpoint: string;
  readonly region: string;
  readonly secretId: string;
  readonly secretKey: string;
  readonly sessionToken?: string;
}

interface TokenResponse {
  readonly token: string;
  readonly expiresAt: number;
}

export class TencentCloudDeploymentTokenProvider implements DeploymentTokenProvider {
  private readonly client: CommonClientLike;
  private readonly now: () => number;
  private token: string | undefined;
  private expiresAt = 0;
  private pending: Promise<void> | undefined;
  private closed = false;

  public constructor(
    private readonly config: TencentCloudDeploymentTokenConfig,
    dependencies: { readonly client?: CommonClientLike; readonly now?: () => number } = {},
  ) {
    this.now = dependencies.now ?? Date.now;
    this.client = dependencies.client ?? new CommonClient(config.endpoint, AGS_API_VERSION, {
      credential: {
        secretId: config.secretId,
        secretKey: config.secretKey,
        ...(config.sessionToken === undefined ? {} : { token: config.sessionToken }),
      },
      region: config.region,
      profile: {
        signMethod: "TC3-HMAC-SHA256",
        httpProfile: {
          endpoint: config.endpoint,
          protocol: "https://",
          reqMethod: "POST",
        },
      },
    });
  }

  public ensureValid(): Promise<void> {
    if (this.closed) return Promise.reject(new Error("Deployment token provider is closed"));
    if (this.token !== undefined && this.expiresAt - this.now() > REFRESH_MARGIN_MS) {
      return Promise.resolve();
    }
    if (this.pending !== undefined) return this.pending;
    const pending = this.acquire();
    this.pending = pending;
    void pending.finally(() => {
      if (this.pending === pending) this.pending = undefined;
    }).catch(() => undefined);
    return pending;
  }

  private async acquire(): Promise<void> {
    const response = await this.client.request("AcquireDeploymentToken", {
      DeploymentId: this.config.deploymentId,
    });
    const parsed = parseDeploymentTokenResponse(response, this.now());
    if (this.closed) throw new Error("Deployment token provider is closed");
    this.token = parsed.token;
    this.expiresAt = parsed.expiresAt;
  }

  public currentToken(): string {
    if (this.closed || this.token === undefined || this.expiresAt <= this.now()) {
      throw new Error("No valid Hands Deployment token is available");
    }
    return this.token;
  }

  public close(): void {
    this.closed = true;
    this.token = undefined;
    this.expiresAt = 0;
  }
}

export class StaticDeploymentTokenProvider implements DeploymentTokenProvider {
  private closed = false;

  public constructor(private readonly token: string) {
    validateHeaderValue(token, "Deployment token");
  }

  public ensureValid(): Promise<void> {
    return this.closed
      ? Promise.reject(new Error("Deployment token provider is closed"))
      : Promise.resolve();
  }

  public currentToken(): string {
    if (this.closed) throw new Error("Deployment token provider is closed");
    return this.token;
  }

  public close(): void {
    this.closed = true;
  }
}

export function parseDeploymentTokenResponse(response: unknown, now = Date.now()): TokenResponse {
  if (!isRecord(response)) throw new Error("AcquireDeploymentToken returned an invalid response");
  if (typeof response.Token !== "string") {
    throw new Error("AcquireDeploymentToken returned no usable Token");
  }
  validateHeaderValue(response.Token, "AcquireDeploymentToken Token");
  if (typeof response.ExpiresAt !== "string") {
    throw new Error("AcquireDeploymentToken returned no ExpiresAt");
  }
  const expiresAt = Date.parse(response.ExpiresAt);
  if (!Number.isFinite(expiresAt) || expiresAt <= now) {
    throw new Error("AcquireDeploymentToken returned an invalid ExpiresAt");
  }
  return { token: response.Token, expiresAt };
}

function validateHeaderValue(value: string, label: string): void {
  if (value.trim().length === 0 || /[\r\n]/u.test(value)) throw new Error(`${label} is invalid`);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
