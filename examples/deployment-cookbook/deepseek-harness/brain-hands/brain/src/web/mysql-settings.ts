import { Service, type Context } from "@deepseek-ai/cordis";
import {
  deepEqualJson,
  SettingsConflictError,
  SettingsProvider,
  type SettingsNamespace,
} from "@deepseek-ai/dsh-settings";
import {
  createPool,
  type Pool,
  type ResultSetHeader,
  type RowDataPacket,
} from "mysql2/promise";

import { brainConfigFromEnv } from "../brain/config.js";
import { mysqlPoolOptions } from "../mysql/config.js";

interface SettingsRow extends RowDataPacket {
  readonly namespace: string;
  readonly section_json: string | Record<string, unknown>;
  readonly storage_revision: string | number;
}

/** Shared Settings provider for every stateless Brain replica. */
export class MysqlSettingsProvider extends SettingsProvider {
  public readonly writable = true;
  private readonly pool: Pool;
  private cachedDocument: Record<string, unknown> = {};
  private readonly storageRevisions = new Map<string, number>();
  private timer?: NodeJS.Timeout;

  public constructor(ctx: Context) {
    super(ctx);
    this.pool = createPool(mysqlPoolOptions(brainConfigFromEnv().mysql));
  }

  protected async load(): Promise<Record<string, unknown>> {
    const [rows] = await this.pool.execute<SettingsRow[]>(`
      SELECT namespace, CAST(section_json AS CHAR) AS section_json, storage_revision
      FROM dsh_settings
      ORDER BY namespace
    `);
    const revisions = new Map<string, number>();
    const document = Object.fromEntries(rows.map((row) => [
      row.namespace,
      (() => {
        revisions.set(row.namespace, storageRevision(row.storage_revision));
        return typeof row.section_json === "string" ? JSON.parse(row.section_json) : row.section_json;
      })(),
    ]));
    this.storageRevisions.clear();
    for (const [namespace, revision] of revisions) this.storageRevisions.set(namespace, revision);
    this.cachedDocument = document;
    return document;
  }

  protected async persist(ns: SettingsNamespace, section: Record<string, unknown>): Promise<void> {
    const expected = this.storageRevisions.get(ns);
    const serialized = JSON.stringify(section);
    let updated: ResultSetHeader;
    if (expected === undefined) {
      [updated] = await this.pool.execute<ResultSetHeader>(`
        INSERT IGNORE INTO dsh_settings (namespace, section_json, storage_revision)
        VALUES (?, CAST(? AS JSON), 1)
      `, [ns, serialized]);
    } else {
      [updated] = await this.pool.execute<ResultSetHeader>(`
        UPDATE dsh_settings
        SET section_json = CAST(? AS JSON), storage_revision = storage_revision + 1
        WHERE namespace = ? AND storage_revision = ?
      `, [serialized, ns, expected]);
    }
    if (updated.affectedRows !== 1) {
      await this.refresh();
      throw new SettingsConflictError(ns, expected ?? 0, this.storageRevisions.get(ns) ?? 0);
    }
    this.storageRevisions.set(ns, (expected ?? 0) + 1);
    this.cachedDocument = { ...this.cachedDocument, [ns]: structuredClone(section) };
  }

  public override async *[Service.init](): AsyncGenerator<() => Promise<void> | void, void, void> {
    yield* super[Service.init]();
    this.timer = setInterval(() => {
      void this.refresh().catch((error: unknown) => {
        this.ctx.logger.warn(`mysql-settings: refresh failed: ${String(error)}`);
      });
    }, 1_000);
    this.timer.unref();
    yield async () => {
      if (this.timer !== undefined) clearInterval(this.timer);
      await this.pool.end();
    };
  }

  private async refresh(): Promise<void> {
    const previous = this.cachedDocument;
    const current = await this.load();
    if (!deepEqualJson(previous, current)) this.publish(current);
  }
}

function storageRevision(value: string | number): number {
  const revision = typeof value === "number" ? value : Number.parseInt(value, 10);
  if (!Number.isSafeInteger(revision) || revision < 1) throw new Error("settings storage revision is invalid");
  return revision;
}

export default MysqlSettingsProvider;
