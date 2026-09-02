import { createHash } from "node:crypto";
import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { createPool, type PoolConnection, type RowDataPacket } from "mysql2/promise";

import { mysqlPoolOptions, type MysqlConnectionConfig } from "./config.js";

const LOCK_NAME = "ags-cookbook-dsh-migrations";
const DEFAULT_LOCK_TIMEOUT_SECONDS = 30;

interface LockRow extends RowDataPacket {
  readonly acquired: number | string | null;
}

interface JournalRow extends RowDataPacket {
  readonly checksum: string;
}

export interface MigrationResult {
  readonly applied: readonly string[];
  readonly skipped: readonly string[];
}

export class MigrationLockTimeoutError extends Error {
  public constructor() {
    super("Timed out waiting for the MySQL migration lock");
    this.name = "MigrationLockTimeoutError";
  }
}

export function migrationChecksum(sql: string): string {
  return createHash("sha256").update(sql, "utf8").digest("hex");
}

export function defaultMigrationsDirectory(): string {
  return fileURLToPath(new URL("../../migrations", import.meta.url));
}

async function migrationFiles(directory: string): Promise<readonly { name: string; sql: string }[]> {
  const names = (await readdir(directory))
    .filter((name) => /^\d+[_-].+\.sql$/u.test(name))
    .sort((left, right) => left.localeCompare(right));
  if (names.length === 0) throw new Error(`No migrations found in ${path.resolve(directory)}`);
  return Promise.all(names.map(async (name) => ({
    name,
    sql: await readFile(path.join(directory, name), "utf8"),
  })));
}

async function acquireLock(connection: PoolConnection, timeoutSeconds: number): Promise<void> {
  const [rows] = await connection.execute<LockRow[]>("SELECT GET_LOCK(?, ?) AS acquired", [
    LOCK_NAME,
    timeoutSeconds,
  ]);
  const acquired = rows[0]?.acquired;
  if (acquired !== 1 && acquired !== "1") throw new MigrationLockTimeoutError();
}

async function releaseLock(connection: PoolConnection): Promise<void> {
  await connection.execute("SELECT RELEASE_LOCK(?)", [LOCK_NAME]);
}

export async function runMigrations(
  config: MysqlConnectionConfig,
  directory = defaultMigrationsDirectory(),
  lockTimeoutSeconds = DEFAULT_LOCK_TIMEOUT_SECONDS,
): Promise<MigrationResult> {
  const pool = createPool(mysqlPoolOptions(config, true));
  const connection = await pool.getConnection();
  let locked = false;
  try {
    await acquireLock(connection, lockTimeoutSeconds);
    locked = true;
    await connection.query(`
      CREATE TABLE IF NOT EXISTS dsh_schema_migrations (
        migration_id VARCHAR(255) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
        checksum CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
        applied_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
        PRIMARY KEY (migration_id)
      ) ENGINE=InnoDB
    `);

    const applied: string[] = [];
    const skipped: string[] = [];
    for (const migration of await migrationFiles(directory)) {
      const checksum = migrationChecksum(migration.sql);
      const [rows] = await connection.execute<JournalRow[]>(
        "SELECT checksum FROM dsh_schema_migrations WHERE migration_id = ?",
        [migration.name],
      );
      const recorded = rows[0]?.checksum;
      if (recorded === checksum) {
        skipped.push(migration.name);
        continue;
      }

      // Every statement in a migration is idempotent. MySQL DDL commits
      // implicitly, so the advisory lock and checksum journal provide startup
      // serialization while a rerun completes a partially applied migration.
      await connection.query(migration.sql);
      await connection.execute(`
        INSERT INTO dsh_schema_migrations (migration_id, checksum)
        VALUES (?, ?)
        ON DUPLICATE KEY UPDATE checksum = VALUES(checksum), applied_at = CURRENT_TIMESTAMP(6)
      `, [migration.name, checksum]);
      applied.push(migration.name);
    }
    return { applied, skipped };
  } finally {
    if (locked) await releaseLock(connection);
    connection.release();
    await pool.end();
  }
}
