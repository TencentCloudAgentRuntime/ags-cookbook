import type { PoolOptions } from "mysql2/promise";

export interface MysqlConnectionConfig {
  readonly host: string;
  readonly port: number;
  readonly user: string;
  readonly password: string;
  readonly database: string;
}

function required(env: NodeJS.ProcessEnv, name: string): string {
  const value = env[name];
  if (value === undefined || value.length === 0) {
    throw new Error(`${name} is required`);
  }
  return value;
}

export function mysqlConfigFromEnv(env: NodeJS.ProcessEnv = process.env): MysqlConnectionConfig {
  const portText = env.MYSQL_PORT ?? "3306";
  if (!/^[0-9]+$/u.test(portText)) throw new Error("MYSQL_PORT must be an integer");
  const port = Number(portText);
  if (!Number.isSafeInteger(port) || port < 1 || port > 65_535) {
    throw new Error("MYSQL_PORT must be between 1 and 65535");
  }

  const database = required(env, "MYSQL_DATABASE");
  if (!/^[A-Za-z0-9_-]+$/u.test(database)) {
    throw new Error("MYSQL_DATABASE may contain only letters, digits, underscores, and hyphens");
  }

  return {
    host: required(env, "MYSQL_HOST"),
    port,
    user: required(env, "MYSQL_USER"),
    password: required(env, "MYSQL_PASSWORD"),
    database,
  };
}

export function mysqlPoolOptions(
  config: MysqlConnectionConfig,
  multipleStatements = false,
): PoolOptions {
  return {
    host: config.host,
    port: config.port,
    user: config.user,
    password: config.password,
    database: config.database,
    multipleStatements,
    waitForConnections: true,
    connectionLimit: 10,
    queueLimit: 0,
    connectTimeout: 10_000,
    enableKeepAlive: true,
    supportBigNumbers: true,
    bigNumberStrings: true,
    timezone: "Z",
  };
}
