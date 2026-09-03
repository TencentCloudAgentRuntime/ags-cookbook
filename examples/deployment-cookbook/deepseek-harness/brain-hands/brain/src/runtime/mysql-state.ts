import type { SessionHeader } from "@deepseek-ai/dsh-session";
import { createHash, randomUUID } from "node:crypto";
import {
  createPool,
  type Pool,
  type PoolConnection,
  type ResultSetHeader,
  type RowDataPacket,
} from "mysql2/promise";

import { mysqlPoolOptions, type MysqlConnectionConfig } from "../mysql/config.js";

export type WorkspaceState = "PENDING" | "ACTIVE" | "FAILED";
const WORKSPACE_ALLOCATION_LEASE_SECONDS = 120;

export interface HandsWorkspace {
  readonly id: string;
  readonly title: string;
  readonly osId: string;
  readonly deploymentId: string;
  readonly state: WorkspaceState;
  readonly generation: string;
  readonly affinityId?: string;
  readonly failureCode?: string;
}

export interface WorkspaceAllocation {
  readonly workspace: HandsWorkspace;
  readonly owner: boolean;
  readonly token?: string;
}

export interface TurnClaim {
  readonly sessionId: string;
  readonly claimId: string;
  readonly holderInstanceId: string;
  readonly generation: string;
}

interface WorkspaceRow extends RowDataPacket {
  readonly workspace_id: string;
  readonly title: string;
  readonly os_id: string;
  readonly deployment_id: string;
  readonly state: WorkspaceState;
  readonly generation: string;
  readonly affinity_id: string | null;
  readonly allocation_token: string | null;
  readonly allocation_started_at: Date | null;
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

export function workspaceClaimId(workspaceId: string): string {
  const digest = createHash("sha256").update(workspaceId).digest("hex");
  return `workspace-${digest}`;
}

function workspace(row: WorkspaceRow): HandsWorkspace {
  return {
    id: row.workspace_id,
    title: row.title,
    osId: row.os_id,
    deploymentId: row.deployment_id,
    state: row.state,
    generation: row.generation,
    ...(row.affinity_id === null ? {} : { affinityId: row.affinity_id }),
    ...(row.failure_code === null ? {} : { failureCode: row.failure_code }),
  };
}

function validateText(value: string, field: string, maxLength = 191): void {
  if (value.length === 0 || value.length > maxLength || /[\u0000-\u001f]/u.test(value)) {
    throw new Error(`${field} must be between 1 and ${maxLength} printable characters`);
  }
}

function validateWorkspaceId(value: string): void {
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/u.test(value)) {
    throw new Error("workspace id must be a UUID");
  }
}

function validateOsId(value: string): void {
  if (!/^[a-z0-9][a-z0-9._-]{0,63}$/u.test(value)) {
    throw new Error("os id is invalid");
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

/** MySQL authority for DSH Workspaces, Hands affinity, and turn fencing. */
export class MysqlRuntimeState {
  private readonly pool: Pool;

  public constructor(config: MysqlConnectionConfig) {
    this.pool = createPool(mysqlPoolOptions(config));
  }

  public async ping(): Promise<void> {
    await this.pool.query("SELECT 1");
  }

  public async createWorkspace(
    workspaceId: string,
    title: string,
    osId: string,
    deploymentId: string,
  ): Promise<HandsWorkspace> {
    validateWorkspaceId(workspaceId);
    validateText(title, "workspace title");
    validateOsId(osId);
    validateText(deploymentId, "deployment id");
    return inTransaction(this.pool, async (connection) => {
      const [rows] = await connection.execute<WorkspaceRow[]>(`
        SELECT workspace_id, title, os_id, deployment_id, state, generation,
               affinity_id, allocation_token, failure_code
        FROM dsh_workspaces
        WHERE workspace_id = ?
        FOR UPDATE
      `, [workspaceId]);
      const current = rows[0];
      if (current !== undefined) {
        if (current.title !== title || current.os_id !== osId || current.deployment_id !== deploymentId) {
          throw new RuntimeStateConflictError("Workspace id already has different metadata");
        }
        return workspace(current);
      }
      await connection.execute<ResultSetHeader>(`
        INSERT INTO dsh_workspaces
          (workspace_id, title, os_id, deployment_id, state, generation)
        VALUES (?, ?, ?, ?, 'PENDING', 1)
      `, [workspaceId, title, osId, deploymentId]);
      return {
        id: workspaceId,
        title,
        osId,
        deploymentId,
        state: "PENDING",
        generation: "1",
      };
    });
  }

  public async listWorkspaces(): Promise<readonly HandsWorkspace[]> {
    const [rows] = await this.pool.execute<WorkspaceRow[]>(`
      SELECT workspace_id, title, os_id, deployment_id, state, generation,
             affinity_id, allocation_token, failure_code
      FROM dsh_workspaces
      ORDER BY created_at ASC
    `);
    return rows.map(workspace);
  }

  public async getWorkspace(workspaceId: string): Promise<HandsWorkspace | undefined> {
    validateWorkspaceId(workspaceId);
    const [rows] = await this.pool.execute<WorkspaceRow[]>(`
      SELECT workspace_id, title, os_id, deployment_id, state, generation,
             affinity_id, allocation_token, failure_code
      FROM dsh_workspaces
      WHERE workspace_id = ?
    `, [workspaceId]);
    return rows[0] === undefined ? undefined : workspace(rows[0]);
  }

  public async claimWorkspaceAllocation(workspaceId: string): Promise<WorkspaceAllocation> {
    validateWorkspaceId(workspaceId);
    return inTransaction(this.pool, async (connection) => {
      const [rows] = await connection.execute<WorkspaceRow[]>(`
        SELECT workspace_id, title, os_id, deployment_id, state, generation,
               affinity_id, allocation_token, allocation_started_at, failure_code
        FROM dsh_workspaces
        WHERE workspace_id = ?
        FOR UPDATE
      `, [workspaceId]);
      const current = rows[0];
      if (current === undefined) throw new RuntimeStateConflictError("Workspace does not exist");
      const selected = workspace(current);
      if (selected.state === "ACTIVE") return { workspace: selected, owner: false };
      if (selected.state === "FAILED") {
        const token = randomUUID();
        const generation = String(BigInt(selected.generation) + 1n);
        const [updated] = await connection.execute<ResultSetHeader>(`
          UPDATE dsh_workspaces
          SET state = 'PENDING', generation = ?, allocation_token = ?,
              allocation_started_at = CURRENT_TIMESTAMP(6), failure_code = NULL
          WHERE workspace_id = ? AND state = 'FAILED' AND generation = ?
        `, [generation, token, workspaceId, selected.generation]);
        if (updated.affectedRows !== 1) {
          throw new RuntimeStateConflictError("Workspace allocation changed");
        }
        return {
          workspace: {
            id: selected.id,
            title: selected.title,
            osId: selected.osId,
            deploymentId: selected.deploymentId,
            state: "PENDING",
            generation,
          },
          owner: true,
          token,
        };
      }
      if (selected.state !== "PENDING") {
        throw new RuntimeStateConflictError("Workspace cannot be allocated");
      }
      if (current.allocation_token !== null) {
        const token = randomUUID();
        const [reclaimed] = await connection.execute<ResultSetHeader>(`
          UPDATE dsh_workspaces
          SET allocation_token = ?, allocation_started_at = CURRENT_TIMESTAMP(6)
          WHERE workspace_id = ? AND state = 'PENDING'
            AND allocation_token = ?
            AND allocation_started_at <= DATE_SUB(
              CURRENT_TIMESTAMP(6), INTERVAL ${WORKSPACE_ALLOCATION_LEASE_SECONDS} SECOND
            )
        `, [token, workspaceId, current.allocation_token]);
        return reclaimed.affectedRows === 1
          ? { workspace: selected, owner: true, token }
          : { workspace: selected, owner: false };
      }
      const token = randomUUID();
      const [updated] = await connection.execute<ResultSetHeader>(`
        UPDATE dsh_workspaces
        SET allocation_token = ?, allocation_started_at = CURRENT_TIMESTAMP(6)
        WHERE workspace_id = ? AND state = 'PENDING' AND allocation_token IS NULL
      `, [token, workspaceId]);
      if (updated.affectedRows !== 1) throw new RuntimeStateConflictError("Workspace allocation changed");
      return { workspace: selected, owner: true, token };
    });
  }

  public async heartbeatWorkspaceAllocation(
    workspaceId: string,
    token: string,
    generation: string,
  ): Promise<void> {
    validateWorkspaceId(workspaceId);
    validateText(token, "allocation token");
    const [updated] = await this.pool.execute<ResultSetHeader>(`
      UPDATE dsh_workspaces
      SET allocation_started_at = CURRENT_TIMESTAMP(6)
      WHERE workspace_id = ? AND state = 'PENDING'
        AND generation = ? AND allocation_token = ?
    `, [workspaceId, generation, token]);
    if (updated.affectedRows !== 1) throw new RuntimeStateConflictError("Workspace allocation changed");
  }

  public async activateWorkspace(
    workspaceId: string,
    token: string,
    generation: string,
    affinityId: string,
  ): Promise<HandsWorkspace> {
    validateWorkspaceId(workspaceId);
    validateText(token, "allocation token");
    validateText(affinityId, "affinity id", 1024);
    const [updated] = await this.pool.execute<ResultSetHeader>(`
      UPDATE dsh_workspaces
      SET state = 'ACTIVE', affinity_id = ?, allocation_token = NULL,
          allocation_started_at = NULL, failure_code = NULL
      WHERE workspace_id = ? AND state = 'PENDING'
        AND generation = ? AND allocation_token = ?
    `, [affinityId, workspaceId, generation, token]);
    if (updated.affectedRows !== 1) throw new RuntimeStateConflictError("Workspace allocation changed");
    const active = await this.getWorkspace(workspaceId);
    if (active === undefined) throw new RuntimeStateConflictError("Workspace disappeared");
    return active;
  }

  public async failWorkspaceAllocation(
    workspaceId: string,
    token: string,
    generation: string,
    failureCode: string,
  ): Promise<void> {
    validateWorkspaceId(workspaceId);
    validateText(token, "allocation token");
    validateText(failureCode, "failure code", 64);
    const [updated] = await this.pool.execute<ResultSetHeader>(`
      UPDATE dsh_workspaces
      SET state = 'FAILED', failure_code = ?, allocation_token = NULL,
          allocation_started_at = NULL
      WHERE workspace_id = ? AND state = 'PENDING'
        AND generation = ? AND allocation_token = ?
    `, [failureCode, workspaceId, generation, token]);
    if (updated.affectedRows !== 1) throw new RuntimeStateConflictError("Workspace allocation changed");
  }

  private async materializeSession(
    connection: PoolConnection,
    meta: SessionHeader,
    provisionIfMissing: boolean,
  ): Promise<void> {
    const [sessions] = await connection.execute<RowDataPacket[]>(`
      SELECT CAST(header_json AS CHAR) AS header_json
      FROM dsh_sessions WHERE session_id = ? FOR UPDATE
    `, [meta.id]);
    const storedHeader = sessions[0]?.header_json;
    if (typeof storedHeader !== "string") {
      if (!provisionIfMissing) throw new RuntimeStateConflictError("Session is not materialized");
      await connection.execute<ResultSetHeader>(`
        INSERT INTO dsh_sessions
          (session_id, header_json, incarnation, next_seq, revision)
        VALUES (?, CAST(? AS JSON), ?, 0, 0)
      `, [meta.id, JSON.stringify(meta), randomUUID()]);
    } else {
      const parsed = JSON.parse(storedHeader) as SessionHeader;
      if (parsed.id !== meta.id || parsed.cwd !== meta.cwd) {
        throw new RuntimeStateConflictError("Stored session header does not match the live session");
      }
    }

  }

  public async claimTurn(
    sessionId: string,
    holderInstanceId: string,
    leaseMs: number,
    workspaceId?: string,
    sessionHeader?: SessionHeader,
  ): Promise<TurnClaim> {
    validateText(sessionId, "session id");
    validateText(holderInstanceId, "holder instance id");
    if (sessionHeader !== undefined && sessionHeader.id !== sessionId) {
      throw new Error("Session header does not match the claimed session");
    }
    if (sessionHeader !== undefined && workspaceId === undefined) {
      throw new Error("A session header requires a workspace");
    }
    if (workspaceId !== undefined) validateWorkspaceId(workspaceId);
    if (!Number.isSafeInteger(leaseMs) || leaseMs < 1_000 || leaseMs > 300_000) {
      throw new Error("leaseMs must be between 1000 and 300000");
    }
    const claimId = workspaceId === undefined ? sessionId : workspaceClaimId(workspaceId);
    validateText(claimId, "claim id");
    const leaseMicros = leaseMs * 1_000;
    return inTransaction(this.pool, async (connection) => {
      if (workspaceId !== undefined) {
        const [workspaces] = await connection.execute<WorkspaceRow[]>(`
          SELECT workspace_id, title, os_id, deployment_id, state, generation,
                 affinity_id, allocation_token, failure_code
          FROM dsh_workspaces
          WHERE workspace_id = ?
          FOR UPDATE
        `, [workspaceId]);
        if (workspaces[0]?.state !== "ACTIVE") {
          throw new RuntimeStateConflictError("Workspace is not active");
        }
      }
      const [rows] = await connection.execute<ClaimRow[]>(`
        SELECT session_id, holder_instance_id, generation, state,
               expires_at > CURRENT_TIMESTAMP(6) AS unexpired
        FROM turn_claims WHERE session_id = ? FOR UPDATE
      `, [claimId]);
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
        `, [claimId, holderInstanceId, generation, leaseMicros]);
      } else {
        await connection.execute<ResultSetHeader>(`
          UPDATE turn_claims
          SET holder_instance_id = ?, generation = ?, state = 'ACTIVE',
              expires_at = DATE_ADD(CURRENT_TIMESTAMP(6), INTERVAL ? MICROSECOND),
              heartbeat_at = CURRENT_TIMESTAMP(6)
          WHERE session_id = ? AND generation = ?
        `, [holderInstanceId, generation, leaseMicros, claimId, current.generation]);
      }
      if (sessionHeader !== undefined && workspaceId !== undefined) {
        await this.materializeSession(connection, sessionHeader, true);
      }
      return { sessionId, claimId, holderInstanceId, generation };
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
    `, [leaseMs * 1_000, claim.claimId, claim.holderInstanceId, claim.generation]);
    if (result.affectedRows !== 1) throw new StaleTurnClaimError(claim.sessionId);
  }

  /** Fencing check performed immediately before each new Hands operation. */
  public async assertTurn(claim: TurnClaim): Promise<void> {
    const [rows] = await this.pool.execute<ClaimRow[]>(`
      SELECT session_id, holder_instance_id, generation, state,
             expires_at > CURRENT_TIMESTAMP(6) AS unexpired
      FROM turn_claims
      WHERE session_id = ? AND holder_instance_id = ? AND generation = ?
    `, [claim.claimId, claim.holderInstanceId, claim.generation]);
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
    `, [claim.claimId, claim.holderInstanceId, claim.generation]);
    if (result.affectedRows !== 1) throw new StaleTurnClaimError(claim.sessionId);
  }

  public close(): Promise<void> {
    return this.pool.end();
  }
}
