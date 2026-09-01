import {
  createPool,
  type Pool,
  type PoolConnection,
  type ResultSetHeader,
  type RowDataPacket,
} from "mysql2/promise";
import { randomUUID } from "node:crypto";
import type { SessionHeader } from "@deepseek-ai/dsh-session";

import { mysqlPoolOptions, type MysqlConnectionConfig } from "../mysql/config.js";

export type WorkspaceBindingMode = "USER" | "SESSION";
export type WorkspaceBindingState = "PENDING" | "ACTIVE" | "FAILED";

export interface WorkspaceBindingKey {
  readonly mode: WorkspaceBindingMode;
  readonly identity: string;
}

export interface WorkspaceBinding extends WorkspaceBindingKey {
  readonly state: WorkspaceBindingState;
  readonly generation: string;
  readonly deploymentId?: string;
  readonly affinityId?: string;
  readonly failureCode?: string;
}

export interface BindingReservation {
  readonly binding: WorkspaceBinding;
  readonly owner: boolean;
}

interface BindingRow extends RowDataPacket {
  readonly binding_mode: WorkspaceBindingMode;
  readonly binding_identity: string;
  readonly state: WorkspaceBindingState;
  readonly generation: string;
  readonly deployment_id: string | null;
  readonly affinity_id: string | null;
  readonly failure_code: string | null;
}

interface ClaimRow extends RowDataPacket {
  readonly session_id: string;
  readonly holder_instance_id: string;
  readonly generation: string;
  readonly state: "ACTIVE" | "COMPLETED" | "INTERRUPTED";
  readonly unexpired: number | string;
}

interface StoreGenerationRow extends RowDataPacket {
  readonly generation: string;
}

export interface TurnClaim {
  readonly sessionId: string;
  readonly holderInstanceId: string;
  readonly generation: string;
}

export class RuntimeStateConflictError extends Error {
  public constructor(message: string) {
    super(message);
    this.name = "RuntimeStateConflictError";
  }
}

export class SessionBusyError extends Error {
  public constructor(readonly sessionId: string) {
    super(`Session ${sessionId} already has an active turn`);
    this.name = "SessionBusyError";
  }
}

export class StaleTurnClaimError extends Error {
  public constructor(readonly sessionId: string) {
    super(`Turn claim for session ${sessionId} is stale`);
    this.name = "StaleTurnClaimError";
  }
}

function binding(row: BindingRow): WorkspaceBinding {
  return {
    mode: row.binding_mode,
    identity: row.binding_identity,
    state: row.state,
    generation: row.generation,
    ...(row.deployment_id === null ? {} : { deploymentId: row.deployment_id }),
    ...(row.affinity_id === null ? {} : { affinityId: row.affinity_id }),
    ...(row.failure_code === null ? {} : { failureCode: row.failure_code }),
  };
}

function validateIdentity(value: string, field: string, maxLength = 191): void {
  if (value.length === 0 || value.length > maxLength) {
    throw new Error(`${field} must be between 1 and ${maxLength} characters`);
  }
}

async function inTransaction<T>(pool: Pool, work: (connection: PoolConnection) => Promise<T>): Promise<T> {
  const connection = await pool.getConnection();
  try {
    await connection.query("SET TRANSACTION ISOLATION LEVEL READ COMMITTED");
    await connection.beginTransaction();
    const result = await work(connection);
    await connection.commit();
    return result;
  } catch (error) {
    try {
      await connection.rollback();
    } catch {
      connection.destroy();
    }
    throw error;
  } finally {
    connection.release();
  }
}

/** MySQL authority for workspace identity and per-session turn fencing. */
export class MysqlRuntimeState {
  private readonly pool: Pool;

  public constructor(config: MysqlConnectionConfig) {
    this.pool = createPool(mysqlPoolOptions(config));
  }

  public async ping(): Promise<void> {
    await this.pool.query("SELECT 1");
  }

  public async getBinding(key: WorkspaceBindingKey): Promise<WorkspaceBinding | undefined> {
    const [rows] = await this.pool.execute<BindingRow[]>(`
      SELECT binding_mode, binding_identity, state, generation,
             deployment_id, affinity_id, failure_code
      FROM workspace_bindings
      WHERE binding_mode = ? AND binding_identity = ?
    `, [key.mode, key.identity]);
    return rows[0] === undefined ? undefined : binding(rows[0]);
  }

  /**
   * Reserve an identity before asking AGS for a Hands affinity. An existing
   * PENDING row is returned unchanged, so a crashed allocation is fail-closed
   * instead of silently allocating a second workspace.
   */
  public async beginBinding(key: WorkspaceBindingKey): Promise<WorkspaceBinding> {
    return (await this.reserveBinding(key)).binding;
  }

  public async reserveBinding(key: WorkspaceBindingKey): Promise<BindingReservation> {
    validateIdentity(key.identity, "binding identity");
    return inTransaction(this.pool, async (connection) => {
      const [rows] = await connection.execute<BindingRow[]>(`
        SELECT binding_mode, binding_identity, state, generation,
               deployment_id, affinity_id, failure_code
        FROM workspace_bindings
        WHERE binding_mode = ? AND binding_identity = ?
        FOR UPDATE
      `, [key.mode, key.identity]);
      const current = rows[0];
      if (current !== undefined) return { binding: binding(current), owner: false };
      await connection.execute<ResultSetHeader>(`
        INSERT INTO workspace_bindings
          (binding_mode, binding_identity, state, generation)
        VALUES (?, ?, 'PENDING', 1)
      `, [key.mode, key.identity]);
      return { binding: { ...key, state: "PENDING", generation: "1" }, owner: true };
    });
  }

  /** Publish a new DSH header against an already ACTIVE shared workspace. */
  public async provisionSession(
    meta: SessionHeader,
    bindingKey: WorkspaceBindingKey,
    generation: string,
  ): Promise<void> {
    await inTransaction(this.pool, async (connection) => {
      const [bindings] = await connection.execute<BindingRow[]>(`
        SELECT binding_mode, binding_identity, state, generation,
               deployment_id, affinity_id, failure_code
        FROM workspace_bindings
        WHERE binding_mode = ? AND binding_identity = ? FOR UPDATE
      `, [bindingKey.mode, bindingKey.identity]);
      const current = bindings[0];
      if (current?.state !== "ACTIVE" || current.generation !== generation) {
        throw new RuntimeStateConflictError("Workspace binding is not active");
      }
      await this.insertProvisionedSession(connection, meta, bindingKey);
    });
  }

  /** Atomically publish the allocated affinity and the first DSH Session header. */
  public async activateBindingAndProvisionSession(
    meta: SessionHeader,
    bindingKey: WorkspaceBindingKey,
    generation: string,
    deploymentId: string,
    affinityId: string,
  ): Promise<WorkspaceBinding> {
    validateIdentity(deploymentId, "deployment id");
    validateIdentity(affinityId, "affinity id", 1024);
    return inTransaction(this.pool, async (connection) => {
      const [updated] = await connection.execute<ResultSetHeader>(`
        UPDATE workspace_bindings
        SET state = 'ACTIVE', deployment_id = ?, affinity_id = ?, failure_code = NULL
        WHERE binding_mode = ? AND binding_identity = ?
          AND state = 'PENDING' AND generation = ?
      `, [deploymentId, affinityId, bindingKey.mode, bindingKey.identity, generation]);
      if (updated.affectedRows !== 1) throw new RuntimeStateConflictError("Workspace binding changed");
      await this.insertProvisionedSession(connection, meta, bindingKey);
      return {
        ...bindingKey,
        state: "ACTIVE",
        generation,
        deploymentId,
        affinityId,
      };
    });
  }

  private async insertProvisionedSession(
    connection: PoolConnection,
    meta: SessionHeader,
    bindingKey: WorkspaceBindingKey,
  ): Promise<void> {
    await connection.execute<ResultSetHeader>(`
      INSERT INTO dsh_sessions
        (session_id, header_json, incarnation, next_seq, revision)
      VALUES (?, CAST(? AS JSON), ?, 0, 0)
    `, [meta.id, JSON.stringify(meta), randomUUID()]);
    await connection.execute<ResultSetHeader>(`
      INSERT INTO dsh_session_workspaces (session_id, binding_mode, binding_identity)
      VALUES (?, ?, ?)
    `, [meta.id, bindingKey.mode, bindingKey.identity]);
  }

  public async getSessionBinding(sessionId: string): Promise<WorkspaceBinding | undefined> {
    const [rows] = await this.pool.execute<BindingRow[]>(`
      SELECT b.binding_mode, b.binding_identity, b.state, b.generation,
             b.deployment_id, b.affinity_id, b.failure_code
      FROM dsh_session_workspaces s
      JOIN workspace_bindings b
        ON b.binding_mode = s.binding_mode AND b.binding_identity = s.binding_identity
      WHERE s.session_id = ?
    `, [sessionId]);
    return rows[0] === undefined ? undefined : binding(rows[0]);
  }

  public async activateBinding(
    key: WorkspaceBindingKey,
    generation: string,
    deploymentId: string,
    affinityId: string,
  ): Promise<WorkspaceBinding> {
    validateIdentity(deploymentId, "deployment id");
    validateIdentity(affinityId, "affinity id", 1024);
    const [result] = await this.pool.execute<ResultSetHeader>(`
      UPDATE workspace_bindings
      SET state = 'ACTIVE', deployment_id = ?, affinity_id = ?, failure_code = NULL
      WHERE binding_mode = ? AND binding_identity = ?
        AND state = 'PENDING' AND generation = ?
    `, [deploymentId, affinityId, key.mode, key.identity, generation]);
    if (result.affectedRows !== 1) throw new RuntimeStateConflictError("Workspace binding changed");
    return {
      ...key,
      state: "ACTIVE",
      generation,
      deploymentId,
      affinityId,
    };
  }

  public async failBinding(
    key: WorkspaceBindingKey,
    generation: string,
    failureCode: string,
  ): Promise<void> {
    validateIdentity(failureCode, "failure code", 64);
    const [result] = await this.pool.execute<ResultSetHeader>(`
      UPDATE workspace_bindings
      SET state = 'FAILED', failure_code = ?
      WHERE binding_mode = ? AND binding_identity = ?
        AND state = 'PENDING' AND generation = ?
    `, [failureCode, key.mode, key.identity, generation]);
    if (result.affectedRows !== 1) throw new RuntimeStateConflictError("Workspace binding changed");
  }

  /** Explicit operator recovery for a failed or abandoned binding. */
  public async retryBinding(key: WorkspaceBindingKey): Promise<WorkspaceBinding> {
    return inTransaction(this.pool, async (connection) => {
      const [rows] = await connection.execute<BindingRow[]>(`
        SELECT binding_mode, binding_identity, state, generation,
               deployment_id, affinity_id, failure_code
        FROM workspace_bindings
        WHERE binding_mode = ? AND binding_identity = ?
        FOR UPDATE
      `, [key.mode, key.identity]);
      const current = rows[0];
      if (current === undefined || current.state === "ACTIVE") {
        throw new RuntimeStateConflictError("Only a PENDING or FAILED binding can be retried explicitly");
      }
      const nextGeneration = (BigInt(current.generation) + 1n).toString();
      await connection.execute<ResultSetHeader>(`
        UPDATE workspace_bindings
        SET state = 'PENDING', generation = ?, deployment_id = NULL,
            affinity_id = NULL, failure_code = NULL
        WHERE binding_mode = ? AND binding_identity = ? AND generation = ?
      `, [nextGeneration, key.mode, key.identity, current.generation]);
      return { ...key, state: "PENDING", generation: nextGeneration };
    });
  }

  public async claimTurn(
    sessionId: string,
    holderInstanceId: string,
    leaseMs: number,
  ): Promise<TurnClaim> {
    validateIdentity(sessionId, "session id");
    validateIdentity(holderInstanceId, "holder instance id");
    if (!Number.isSafeInteger(leaseMs) || leaseMs < 1_000 || leaseMs > 300_000) {
      throw new Error("leaseMs must be between 1000 and 300000");
    }
    const leaseMicros = leaseMs * 1_000;
    return inTransaction(this.pool, async (connection) => {
      const [rows] = await connection.execute<ClaimRow[]>(`
        SELECT session_id, holder_instance_id, generation, state,
               expires_at > CURRENT_TIMESTAMP(6) AS unexpired
        FROM turn_claims WHERE session_id = ? FOR UPDATE
      `, [sessionId]);
      const current = rows[0];
      if (current?.state === "ACTIVE" && (current.unexpired === 1 || current.unexpired === "1")) {
        throw new SessionBusyError(sessionId);
      }
      const [storeRows] = await connection.execute<StoreGenerationRow[]>(`
        SELECT generation FROM dsh_turn_generation WHERE singleton = 1 FOR UPDATE
      `);
      const storedGeneration = storeRows[0]?.generation;
      if (storedGeneration === undefined) throw new Error("MySQL turn generation state is missing");
      const generation = (BigInt(storedGeneration) + 1n).toString();
      await connection.execute<ResultSetHeader>(`
        UPDATE dsh_turn_generation SET generation = ? WHERE singleton = 1
      `, [generation]);
      if (current === undefined) {
        await connection.execute<ResultSetHeader>(`
          INSERT INTO turn_claims
            (session_id, holder_instance_id, generation, state, expires_at, heartbeat_at)
          VALUES (?, ?, ?, 'ACTIVE',
                  DATE_ADD(CURRENT_TIMESTAMP(6), INTERVAL ? MICROSECOND), CURRENT_TIMESTAMP(6))
        `, [sessionId, holderInstanceId, generation, leaseMicros]);
      } else {
        await connection.execute<ResultSetHeader>(`
          UPDATE turn_claims
          SET holder_instance_id = ?, generation = ?, state = 'ACTIVE',
              expires_at = DATE_ADD(CURRENT_TIMESTAMP(6), INTERVAL ? MICROSECOND),
              heartbeat_at = CURRENT_TIMESTAMP(6)
          WHERE session_id = ? AND generation = ?
        `, [holderInstanceId, generation, leaseMicros, sessionId, current.generation]);
      }
      return { sessionId, holderInstanceId, generation };
    });
  }

  public async heartbeatTurn(claim: TurnClaim, leaseMs: number): Promise<void> {
    if (!Number.isSafeInteger(leaseMs) || leaseMs < 1_000 || leaseMs > 300_000) {
      throw new Error("leaseMs must be between 1000 and 300000");
    }
    const [result] = await this.pool.execute<ResultSetHeader>(`
      UPDATE turn_claims
      SET heartbeat_at = CURRENT_TIMESTAMP(6),
          expires_at = DATE_ADD(CURRENT_TIMESTAMP(6), INTERVAL ? MICROSECOND)
      WHERE session_id = ? AND holder_instance_id = ? AND generation = ?
        AND state = 'ACTIVE' AND expires_at > CURRENT_TIMESTAMP(6)
    `, [leaseMs * 1_000, claim.sessionId, claim.holderInstanceId, claim.generation]);
    if (result.affectedRows !== 1) throw new StaleTurnClaimError(claim.sessionId);
  }

  /** Fencing check performed immediately before each new Hands operation. */
  public async assertTurn(claim: TurnClaim): Promise<void> {
    const [rows] = await this.pool.execute<ClaimRow[]>(`
      SELECT session_id, holder_instance_id, generation, state,
             expires_at > CURRENT_TIMESTAMP(6) AS unexpired
      FROM turn_claims
      WHERE session_id = ? AND holder_instance_id = ? AND generation = ?
    `, [claim.sessionId, claim.holderInstanceId, claim.generation]);
    const row = rows[0];
    if (row?.state !== "ACTIVE" || (row.unexpired !== 1 && row.unexpired !== "1")) {
      throw new StaleTurnClaimError(claim.sessionId);
    }
  }

  public async completeTurn(claim: TurnClaim): Promise<void> {
    const [result] = await this.pool.execute<ResultSetHeader>(`
      UPDATE turn_claims
      SET state = 'COMPLETED', expires_at = CURRENT_TIMESTAMP(6)
      WHERE session_id = ? AND holder_instance_id = ? AND generation = ?
        AND state = 'ACTIVE'
    `, [claim.sessionId, claim.holderInstanceId, claim.generation]);
    if (result.affectedRows !== 1) throw new StaleTurnClaimError(claim.sessionId);
  }

  public close(): Promise<void> {
    return this.pool.end();
  }
}
