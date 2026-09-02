import { randomUUID } from "node:crypto";
import { isDeepStrictEqual } from "node:util";

import { type Context } from "@deepseek-ai/cordis";
import type {
  SessionEvent,
  SessionHeader,
  SessionId,
  SessionPreparation,
} from "@deepseek-ai/dsh-session";
import {
  DEFAULT_PREPARED_SESSION_CACHE_SIZE,
  DEFAULT_WRITE_BATCH_MAX_DELAY_MS,
  MAX_WRITE_BATCH_DELAY_MS,
  PersistenceCoordinator,
  SessionPersistence,
  SessionPersistenceRevision,
  type PersistenceBackend,
  type SessionInspection,
  type SessionLocation,
  type SessionPersistenceRevision as PersistenceRevision,
  type SessionPersistenceSnapshot,
  type StoredPrefix,
  type StoredSuffix,
} from "@deepseek-ai/dsh-session-persistence";
import {
  createPool,
  type Pool,
  type PoolConnection,
  type ResultSetHeader,
  type RowDataPacket,
} from "mysql2/promise";

import { mysqlPoolOptions, type MysqlConnectionConfig } from "../mysql/config.js";
import { runMigrations } from "../mysql/migrations.js";
import {
  workspaceClaimId,
  type TurnClaim,
} from "../runtime/mysql-state.js";
import { workspaceIdFromCwd } from "../web/workspace-path.js";

interface SessionRow extends RowDataPacket {
  readonly session_id: string;
  readonly header_json: string;
  readonly incarnation: string;
  readonly next_seq: string;
  readonly revision: string;
}

interface EventRow extends RowDataPacket {
  readonly event_json: string;
}

interface StoreRow extends RowDataPacket {
  readonly store_id: string;
}

interface ActiveClaimRow extends RowDataPacket {
  readonly state: "ACTIVE" | "COMPLETED" | "INTERRUPTED";
  readonly unexpired: number | string;
}

export interface MysqlSessionPersistenceConfig {
  readonly connection: MysqlConnectionConfig;
  readonly preparedSessionCacheSize?: number;
  readonly writeBatchMaxDelayMs?: number;
  readonly migrateOnStart?: boolean;
  /** Required by the Brain runtime so a stale replica cannot append after losing its lease. */
  readonly currentTurnClaim?: (
    sessionId: string,
    events: readonly SessionEvent[],
  ) => TurnClaim | null | undefined | Promise<TurnClaim | null | undefined>;
}

export class MysqlSessionConflictError extends Error {
  public constructor(message: string) {
    super(message);
    this.name = "MysqlSessionConflictError";
  }
}

function exactSeq(value: string, field: string): number {
  if (!/^(?:0|[1-9][0-9]*)$/u.test(value)) throw new Error(`Invalid stored ${field}`);
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed)) throw new Error(`Stored ${field} exceeds the safe integer range`);
  return parsed;
}

function parseJson<T>(text: string, description: string): T {
  try {
    return JSON.parse(text) as T;
  } catch (error) {
    throw new Error(`Invalid ${description} JSON`, { cause: error });
  }
}

function revision(storeId: string, row: SessionRow): PersistenceRevision {
  return SessionPersistenceRevision(
    `mysql:store:${storeId}:incarnation:${row.incarnation}:revision:${row.revision}`,
  );
}

function assertBatch(events: readonly SessionEvent[], expectedSeq: number): void {
  if (events.length === 0) throw new MysqlSessionConflictError("Cannot append an empty event batch");
  for (const [offset, event] of events.entries()) {
    if (event.seq !== expectedSeq + offset) {
      throw new MysqlSessionConflictError(
        `Expected event seq ${expectedSeq + offset}, received ${event.seq}`,
      );
    }
  }
}

async function rollback(connection: PoolConnection): Promise<void> {
  try {
    await connection.rollback();
  } catch {
    connection.destroy();
  }
}

/**
 * MySQL-backed DSH SessionPersistence for stateless Brain replicas.
 *
 * The official PersistenceCoordinator owns DSH validation, buffering, repair,
 * and live-session lifecycle. This class only implements the transactional SQL
 * primitives shared by every Brain replica.
 */
export class MysqlSessionPersistence extends SessionPersistence implements PersistenceBackend<never> {
  public static inject = ["sessions"];
  public override readonly supportsRawArtifacts = false;
  public override readonly name = "session-persistence-mysql";

  private readonly pool: Pool;
  private readonly ready: Promise<string>;
  private readonly coordinator: PersistenceCoordinator<never>;
  private closed = false;

  public constructor(ctx: Context, public readonly config: MysqlSessionPersistenceConfig) {
    super(ctx);
    const preparedSessionCacheSize = config.preparedSessionCacheSize
      ?? DEFAULT_PREPARED_SESSION_CACHE_SIZE;
    const writeBatchMaxDelayMs = config.writeBatchMaxDelayMs
      ?? DEFAULT_WRITE_BATCH_MAX_DELAY_MS;
    if (!Number.isSafeInteger(preparedSessionCacheSize) || preparedSessionCacheSize < 1) {
      throw new Error("preparedSessionCacheSize must be a positive integer");
    }
    if (!Number.isSafeInteger(writeBatchMaxDelayMs)
      || writeBatchMaxDelayMs < 1
      || writeBatchMaxDelayMs > MAX_WRITE_BATCH_DELAY_MS) {
      throw new Error(`writeBatchMaxDelayMs must be between 1 and ${MAX_WRITE_BATCH_DELAY_MS}`);
    }

    this.pool = createPool(mysqlPoolOptions(config.connection));
    this.ready = this.initialize(config.migrateOnStart ?? true);
    this.ctx.effect(() => () => this.close(), "close MySQL SessionPersistence");
    this.coordinator = new PersistenceCoordinator<never>(this.ctx, this, {
      preparedSessionCacheSize,
      writeBatchMaxDelayMs,
    });
  }

  private async initialize(migrateOnStart: boolean): Promise<string> {
    if (migrateOnStart) await runMigrations(this.config.connection);
    const [rows] = await this.pool.execute<StoreRow[]>(
      "SELECT store_id FROM dsh_store_state WHERE singleton = 1",
    );
    const storeId = rows[0]?.store_id;
    if (storeId === undefined || storeId.length === 0) {
      throw new Error("MySQL DSH store identity is missing; run migrations first");
    }
    return storeId;
  }

  public locate(_meta: SessionHeader): SessionLocation | undefined {
    return undefined;
  }

  public create(meta: SessionHeader): Promise<void> {
    return this.coordinator.create(meta);
  }

  public append(id: SessionId, events: readonly SessionEvent[]): Promise<void> {
    return this.coordinator.append(id, events);
  }

  public override prepare(id: SessionId, signal?: AbortSignal): Promise<SessionPreparation> {
    return this.coordinator.prepare(id, signal);
  }

  public load(id: SessionId): Promise<SessionInspection> {
    return this.coordinator.load(id);
  }

  public inspect(id: SessionId, signal?: AbortSignal): Promise<SessionInspection> {
    return this.coordinator.inspect(id, signal);
  }

  public readFrom(
    id: SessionId,
    fromSeq: number,
    signal?: AbortSignal,
  ): Promise<{ meta: SessionHeader; events: SessionEvent[] }> {
    return this.coordinator.readFrom(id, fromSeq, signal);
  }

  private async sessionRow(connection: PoolConnection, id: SessionId): Promise<SessionRow | undefined> {
    const [rows] = await connection.execute<SessionRow[]>(`
      SELECT session_id, CAST(header_json AS CHAR) AS header_json,
             incarnation, next_seq, revision
      FROM dsh_sessions
      WHERE session_id = ?
    `, [id]);
    return rows[0];
  }

  private async readStored(
    id: SessionId,
    fromSeq: number | undefined,
    signal?: AbortSignal,
  ): Promise<{ row: SessionRow; meta: SessionHeader; events: SessionEvent[] } | undefined> {
    signal?.throwIfAborted();
    await this.ready;
    signal?.throwIfAborted();
    const connection = await this.pool.getConnection();
    try {
      await connection.query("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ");
      await connection.beginTransaction();
      const row = await this.sessionRow(connection, id);
      if (row === undefined) {
        await connection.commit();
        return undefined;
      }
      const [events] = fromSeq === undefined
        ? await connection.execute<EventRow[]>(`
            SELECT CAST(event_json AS CHAR) AS event_json
            FROM dsh_session_events WHERE session_id = ? ORDER BY seq
          `, [id])
        : await connection.execute<EventRow[]>(`
            SELECT CAST(event_json AS CHAR) AS event_json
            FROM dsh_session_events WHERE session_id = ? AND seq >= ? ORDER BY seq
          `, [id, fromSeq]);
      await connection.commit();
      signal?.throwIfAborted();
      return {
        row,
        meta: parseJson<SessionHeader>(row.header_json, "session header"),
        events: events.map((event) => parseJson<SessionEvent>(event.event_json, "session event")),
      };
    } catch (error) {
      await rollback(connection);
      throw error;
    } finally {
      connection.release();
    }
  }

  public async loadStored(id: SessionId, signal?: AbortSignal): Promise<StoredPrefix<never> | undefined> {
    const stored = await this.readStored(id, undefined, signal);
    if (stored === undefined) return undefined;
    return {
      meta: stored.meta,
      events: stored.events,
      revision: revision(await this.ready, stored.row),
    };
  }

  public async readStoredRevision(
    id: SessionId,
    signal?: AbortSignal,
  ): Promise<PersistenceRevision | undefined> {
    signal?.throwIfAborted();
    const storeId = await this.ready;
    signal?.throwIfAborted();
    const [rows] = await this.pool.execute<SessionRow[]>(`
      SELECT session_id, CAST(header_json AS CHAR) AS header_json,
             incarnation, next_seq, revision
      FROM dsh_sessions WHERE session_id = ?
    `, [id]);
    signal?.throwIfAborted();
    const row = rows[0];
    return row === undefined ? undefined : revision(storeId, row);
  }

  public async loadStoredFrom(
    id: SessionId,
    fromSeq: number,
    signal?: AbortSignal,
  ): Promise<StoredSuffix | undefined> {
    const stored = await this.readStored(id, fromSeq, signal);
    return stored === undefined ? undefined : { meta: stored.meta, events: stored.events };
  }

  public async appendBatch(
    meta: SessionHeader,
    events: readonly SessionEvent[],
    isMaterialized: boolean,
  ): Promise<void> {
    await this.ready;
    const connection = await this.pool.getConnection();
    try {
      await connection.query("SET TRANSACTION ISOLATION LEVEL READ COMMITTED");
      await connection.beginTransaction();
      await this.lockActiveTurnClaim(connection, meta.id, events);
      const [rows] = await connection.execute<SessionRow[]>(`
        SELECT session_id, CAST(header_json AS CHAR) AS header_json,
               incarnation, next_seq, revision
        FROM dsh_sessions WHERE session_id = ? FOR UPDATE
      `, [meta.id]);
      let row = rows[0];
      if (row === undefined) {
        if (isMaterialized) {
          throw new MysqlSessionConflictError(`Materialized session ${meta.id} is missing`);
        }
        assertBatch(events, 0);
        await connection.execute<ResultSetHeader>(`
          INSERT INTO dsh_sessions
            (session_id, header_json, incarnation, next_seq, revision)
          VALUES (?, CAST(? AS JSON), ?, 0, 0)
        `, [meta.id, JSON.stringify(meta), randomUUID()]);
        const [created] = await connection.execute<SessionRow[]>(`
          SELECT session_id, CAST(header_json AS CHAR) AS header_json,
                 incarnation, next_seq, revision
          FROM dsh_sessions WHERE session_id = ? FOR UPDATE
        `, [meta.id]);
        row = created[0];
      } else if (!isMaterialized) {
        const storedHeader = parseJson<SessionHeader>(row.header_json, "session header");
        if (exactSeq(row.next_seq, "next_seq") !== 0 || !isDeepStrictEqual(storedHeader, meta)) {
          throw new MysqlSessionConflictError(`Session ${meta.id} was concurrently materialized`);
        }
      }
      if (row === undefined) throw new Error(`Session ${meta.id} could not be materialized`);

      const expectedSeq = exactSeq(row.next_seq, "next_seq");
      assertBatch(events, expectedSeq);
      for (const event of events) {
        await connection.execute<ResultSetHeader>(`
          INSERT INTO dsh_session_events (session_id, seq, event_json)
          VALUES (?, ?, CAST(? AS JSON))
        `, [meta.id, event.seq, JSON.stringify(event)]);
      }
      const [updated] = await connection.execute<ResultSetHeader>(`
        UPDATE dsh_sessions
        SET next_seq = ?, revision = revision + 1
        WHERE session_id = ? AND next_seq = ?
      `, [expectedSeq + events.length, meta.id, expectedSeq]);
      if (updated.affectedRows !== 1) {
        throw new MysqlSessionConflictError(`Session ${meta.id} changed during append`);
      }
      await connection.commit();
    } catch (error) {
      await rollback(connection);
      throw error;
    } finally {
      connection.release();
    }
  }

  private async lockActiveTurnClaim(
    connection: PoolConnection,
    sessionId: string,
    events: readonly SessionEvent[],
  ): Promise<void> {
    if (this.config.currentTurnClaim === undefined) return;
    const claim = await this.config.currentTurnClaim(sessionId, events);
    if (claim === null) {
      const [sessions] = await connection.execute<SessionRow[]>(`
        SELECT session_id, CAST(header_json AS CHAR) AS header_json,
               incarnation, next_seq, revision
        FROM dsh_sessions
        WHERE session_id = ?
      `, [sessionId]);
      const row = sessions[0];
      if (row === undefined) return;
      const workspaceId = workspaceIdFromCwd(
        parseJson<SessionHeader>(row.header_json, "session header").cwd,
      );
      if (workspaceId === undefined) return;

      const [workspaces] = await connection.execute<RowDataPacket[]>(`
        SELECT state
        FROM dsh_workspaces
        WHERE workspace_id = ?
        FOR UPDATE
      `, [workspaceId]);
      if (workspaces[0]?.state !== "ACTIVE") {
        throw new MysqlSessionConflictError("The workspace is not active");
      }

      const [claims] = await connection.execute<ActiveClaimRow[]>(`
        SELECT state, expires_at > CURRENT_TIMESTAMP(6) AS unexpired
        FROM turn_claims
        WHERE session_id = ?
        FOR SHARE
      `, [workspaceClaimId(workspaceId)]);
      const active = claims[0];
      if (active?.state === "ACTIVE" && (active.unexpired === 1 || active.unexpired === "1")) {
        throw new MysqlSessionConflictError("Workspace has an active turn claim");
      }
      return;
    }
    if (claim === undefined) throw new MysqlSessionConflictError("No active turn claim permits this write");
    if (claim.sessionId !== sessionId) {
      throw new MysqlSessionConflictError("The turn claim belongs to another session");
    }
    const [rows] = await connection.execute<RowDataPacket[]>(`
      SELECT generation
      FROM turn_claims
      WHERE session_id = ? AND holder_instance_id = ? AND generation = ?
        AND state = 'ACTIVE' AND expires_at > CURRENT_TIMESTAMP(6)
      FOR SHARE
    `, [claim.claimId, claim.holderInstanceId, claim.generation]);
    if (rows.length !== 1) throw new MysqlSessionConflictError("The turn claim no longer permits writes");
  }

  public async commitRepair(
    meta: SessionHeader,
    tornMarker: never | undefined,
    closers: readonly SessionEvent[],
  ): Promise<void> {
    if (tornMarker !== undefined) {
      throw new Error("MySQL transactions cannot produce a torn session tail");
    }
    if (closers.length > 0) await this.appendBatch(meta, closers, true);
  }

  public async list(signal?: AbortSignal): Promise<SessionHeader[]> {
    return (await this.listRows(signal)).map((row) =>
      parseJson<SessionHeader>(row.header_json, "session header"));
  }

  private async listRows(signal?: AbortSignal): Promise<SessionRow[]> {
    signal?.throwIfAborted();
    await this.ready;
    signal?.throwIfAborted();
    const [rows] = await this.pool.execute<SessionRow[]>(`
      SELECT session_id, CAST(header_json AS CHAR) AS header_json,
             incarnation, next_seq, revision
      FROM dsh_sessions ORDER BY created_at, session_id
    `);
    signal?.throwIfAborted();
    return rows;
  }

  public async listSnapshots(signal?: AbortSignal): Promise<SessionPersistenceSnapshot[]> {
    const storeId = await this.ready;
    return (await this.listRows(signal)).map((row) => ({
      header: parseJson<SessionHeader>(row.header_json, "session header"),
      revision: revision(storeId, row),
    }));
  }

  public async close(): Promise<void> {
    if (this.closed) return;
    this.closed = true;
    try {
      await this.ready;
    } finally {
      await this.pool.end();
    }
  }
}

export default MysqlSessionPersistence;
