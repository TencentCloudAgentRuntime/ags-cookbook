import { randomUUID } from "node:crypto";
import { hostname } from "node:os";

import { mysqlConfigFromEnv, type MysqlConnectionConfig } from "../mysql/config.js";

export interface BrainConfig {
  readonly port: number;
  readonly instanceId: string;
  readonly mysql: MysqlConnectionConfig;
  readonly hands: {
    readonly oses: readonly HandsOsConfig[];
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

export interface HandsOsConfig {
  readonly id: string;
  readonly label: string;
  readonly deploymentId: string;
  readonly baseUrl: string;
}

export function brainConfigFromEnv(env: NodeJS.ProcessEnv = process.env): BrainConfig {
  const region = required(env, "AGS_REGION");
  const dataPlaneDomain = optional(env, "AGS_DATA_PLANE_DOMAIN") ?? "tencentags.com";
  const oses = handsOsConfigs(env, region, dataPlaneDomain);
  const sessionToken = optional(env, "TENCENTCLOUD_TOKEN");
  return {
    port: integer(env, "BRAIN_PORT", 8080, 1, 65_535),
    instanceId: optional(env, "BRAIN_INSTANCE_ID") ?? `${hostname()}-${process.pid}-${randomUUID()}`,
    mysql: mysqlConfigFromEnv(env),
    hands: {
      oses,
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

function handsOsConfigs(
  env: NodeJS.ProcessEnv,
  region: string,
  dataPlaneDomain: string,
): readonly HandsOsConfig[] {
  const catalog = optional(env, "HANDS_OS_DEPLOYMENTS");
  if (catalog === undefined) {
    const deploymentId = required(env, "HANDS_DEPLOYMENT_ID");
    return [{
      id: "ubuntu",
      label: "Ubuntu",
      deploymentId,
      baseUrl: optional(env, "HANDS_BASE_URL")
        ?? `https://49983-${deploymentId}.${region}.agents.${dataPlaneDomain}`,
    }];
  }
  const seen = new Set<string>();
  return catalog.split(",").map((entry) => {
    const separator = entry.indexOf("=");
    if (separator <= 0) {
      throw new Error("HANDS_OS_DEPLOYMENTS must use os=deployment-id entries");
    }
    const id = entry.slice(0, separator).trim().toLowerCase();
    const deploymentId = entry.slice(separator + 1).trim();
    if (!/^[a-z0-9][a-z0-9._-]{0,63}$/u.test(id) || deploymentId.length === 0) {
      throw new Error("HANDS_OS_DEPLOYMENTS must use os=deployment-id entries");
    }
    if (seen.has(id)) throw new Error(`HANDS_OS_DEPLOYMENTS contains duplicate OS ${id}`);
    seen.add(id);
    return {
      id,
      label: id.split(/[._-]+/u)
        .map((part) => `${part.slice(0, 1).toUpperCase()}${part.slice(1)}`)
        .join(" "),
      deploymentId,
      baseUrl: `https://49983-${deploymentId}.${region}.agents.${dataPlaneDomain}`,
    };
  });
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
