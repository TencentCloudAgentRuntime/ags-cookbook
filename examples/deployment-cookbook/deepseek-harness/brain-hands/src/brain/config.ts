import { randomUUID } from "node:crypto";
import { hostname } from "node:os";

import { mysqlConfigFromEnv, type MysqlConnectionConfig } from "../mysql/config.js";

export interface BrainConfig {
  readonly port: number;
  readonly instanceId: string;
  readonly workspaceUserId: string;
  readonly mysql: MysqlConnectionConfig;
  readonly hands: {
    readonly deploymentId: string;
    readonly baseUrl: string;
    readonly apiEndpoint: string;
    readonly region: string;
    readonly secretId: string;
    readonly secretKey: string;
    readonly sessionToken?: string;
  };
  readonly llm: {
    readonly provider: "tokenhub";
    readonly model: string;
    readonly baseUrl: string;
    readonly apiKeyEnv: "TOKENHUB_API_KEY";
    readonly maxTokens: number;
  };
  readonly turnLeaseMs: number;
}

export function brainConfigFromEnv(env: NodeJS.ProcessEnv = process.env): BrainConfig {
  const region = required(env, "AGS_REGION");
  const deploymentId = required(env, "HANDS_DEPLOYMENT_ID");
  const dataPlaneDomain = optional(env, "AGS_DATA_PLANE_DOMAIN") ?? "tencentags.com";
  const sessionToken = optional(env, "TENCENTCLOUD_TOKEN");
  return {
    port: integer(env, "BRAIN_PORT", 8080, 1, 65_535),
    instanceId: optional(env, "BRAIN_INSTANCE_ID") ?? `${hostname()}-${process.pid}-${randomUUID()}`,
    workspaceUserId: required(env, "BRAIN_WORKSPACE_USER_ID"),
    mysql: mysqlConfigFromEnv(env),
    hands: {
      deploymentId,
      baseUrl: optional(env, "HANDS_BASE_URL")
        ?? `https://49983-${deploymentId}.${region}.agents.${dataPlaneDomain}`,
      apiEndpoint: optional(env, "AGS_API_ENDPOINT") ?? "ags.tencentcloudapi.com",
      region,
      secretId: required(env, "TENCENTCLOUD_SECRET_ID"),
      secretKey: required(env, "TENCENTCLOUD_SECRET_KEY"),
      ...(sessionToken === undefined ? {} : { sessionToken }),
    },
    llm: {
      provider: "tokenhub",
      model: optional(env, "TOKENHUB_MODEL") ?? "deepseek-v4-flash",
      baseUrl: optional(env, "TOKENHUB_BASE_URL") ?? "https://tokenhub.tencentmaas.com/v1",
      apiKeyEnv: "TOKENHUB_API_KEY",
      maxTokens: integer(env, "TOKENHUB_MAX_TOKENS", 16_384, 1, 131_072),
    },
    turnLeaseMs: integer(env, "BRAIN_TURN_LEASE_MS", 60_000, 5_000, 300_000),
  };
}

function required(env: NodeJS.ProcessEnv, name: string): string {
  const value = optional(env, name);
  if (value === undefined) throw new Error(`${name} is required`);
  return value;
}

function optional(env: NodeJS.ProcessEnv, name: string): string | undefined {
  const value = env[name]?.trim();
  if (value === undefined || value.length === 0) return undefined;
  if (/\r|\n/u.test(value)) throw new Error(`${name} is invalid`);
  return value;
}

function integer(
  env: NodeJS.ProcessEnv,
  name: string,
  fallback: number,
  minimum: number,
  maximum: number,
): number {
  const raw = optional(env, name);
  if (raw === undefined) return fallback;
  if (!/^[0-9]+$/u.test(raw)) throw new Error(`${name} must be an integer`);
  const value = Number(raw);
  if (!Number.isSafeInteger(value) || value < minimum || value > maximum) {
    throw new Error(`${name} must be between ${minimum} and ${maximum}`);
  }
  return value;
}
