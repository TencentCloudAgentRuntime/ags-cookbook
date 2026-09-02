import { randomUUID } from "node:crypto";
import "dotenv/config";

import { Context } from "@deepseek-ai/cordis";
import * as AgentSpine from "@deepseek-ai/dsh-agent-spine-demo";
import { SettingsConflictError, settingsNamespace } from "@deepseek-ai/dsh-settings";
import SessionStore, {
  SESSION_FORMAT_VERSION,
  SessionId,
  type SessionEvent,
  type SessionHeader,
} from "@deepseek-ai/dsh-session";
import { createPool, type RowDataPacket } from "mysql2/promise";
import { afterEach, describe, expect, it } from "vitest";

import { mysqlConfigFromEnv, mysqlPoolOptions } from "../src/mysql/config.js";
import { runMigrations } from "../src/mysql/migrations.js";
import MysqlSessionPersistence from "../src/persistence/mysql-session-persistence.js";
import {
  MysqlRuntimeState,
  RuntimeStateConflictError,
  SessionBusyError,
  StaleTurnClaimError,
  workspaceClaimId,
  type HandsWorkspace,
  type TurnClaim,
} from "../src/runtime/mysql-state.js";
import { TurnContext } from "../src/runtime/turn-context.js";
import { workspacePath } from "../src/web/workspace-path.js";
import MysqlSettingsProvider from "../src/web/mysql-settings.js";

const enabled = process.env.RUN_MYSQL_INTEGRATION === "1";
const createdSessionIds: string[] = [];
const createdWorkspaceIds: string[] = [];
const createdSettingsNamespaces: string[] = [];

class TestMysqlSettingsProvider extends MysqlSettingsProvider {
  public loadForTest(): Promise<Record<string, unknown>> {
    return this.load();
  }

  public persistForTest(namespace: string, section: Record<string, unknown>): Promise<void> {
    return this.persist(settingsNamespace(namespace), section);
  }
}

function sessionId(): string {
  const id = `cookbook-test-${randomUUID()}`;
  createdSessionIds.push(id);
  return id;
}

function workspaceId(): string {
  const id = randomUUID();
  createdWorkspaceIds.push(id);
  return id;
}

function header(id: string, cwd = "/workspace"): SessionHeader {
  return {
    version: SESSION_FORMAT_VERSION,
    id: SessionId(id),
    createdAt: Date.now(),
    cwd,
  };
}

function completedTurn(): SessionEvent[] {
  return [
    { type: "turn/start", seq: 0, time: 1, data: { turn: 1 } },
    { type: "step/start", seq: 1, time: 2, data: { turn: 1, step: 1 } },
    { type: "step/end", seq: 2, time: 3, data: { turn: 1, step: 1 } },
    { type: "turn/end", seq: 3, time: 4, data: { turn: 1, reason: { kind: "completed" } } },
  ];
}

async function mount(): Promise<{
  readonly context: Context;
  readonly dispose: () => Promise<void>;
}> {
  const context = new Context();
  await context.plugin(SessionStore);
  const fiber = await context.plugin(MysqlSessionPersistence, {
    connection: mysqlConfigFromEnv(),
    writeBatchMaxDelayMs: 1,
  });
  return { context, dispose: () => fiber.dispose() };
}

async function activeWorkspace(
  state: MysqlRuntimeState,
  id = workspaceId(),
  osId = "ubuntu",
  deploymentId = "dpl-ubuntu",
): Promise<HandsWorkspace> {
  await state.createWorkspace(id, `Workspace ${id.slice(0, 8)}`, osId, deploymentId);
  const allocation = await state.claimWorkspaceAllocation(id);
  if (!allocation.owner || allocation.token === undefined) throw new Error("allocation claim missing");
  return state.activateWorkspace(id, allocation.token, allocation.workspace.generation, `affinity-${id}`);
}

afterEach(async () => {
  if (!enabled) return;
  const pool = createPool(mysqlPoolOptions(mysqlConfigFromEnv()));
  try {
    for (const id of createdSessionIds.splice(0)) {
      await pool.execute("DELETE FROM turn_claims WHERE session_id = ?", [id]);
      await pool.execute("DELETE FROM dsh_sessions WHERE session_id = ?", [id]);
    }
    for (const id of createdWorkspaceIds.splice(0)) {
      await pool.execute("DELETE FROM turn_claims WHERE session_id = ?", [workspaceClaimId(id)]);
      await pool.execute("DELETE FROM dsh_workspaces WHERE workspace_id = ?", [id]);
    }
    for (const namespace of createdSettingsNamespaces.splice(0)) {
      await pool.execute("DELETE FROM dsh_settings WHERE namespace = ?", [namespace]);
    }
  } finally {
    await pool.end();
  }
});

describe.skipIf(!enabled)("MySQL SessionPersistence", () => {
  it("runs the convergent schema migration idempotently", async () => {
    const first = await runMigrations(mysqlConfigFromEnv());
    const second = await runMigrations(mysqlConfigFromEnv());
    expect(first.applied.length + first.skipped.length).toBeGreaterThan(0);
    expect(second.applied).toEqual([]);
    expect(second.skipped.length).toBeGreaterThan(0);
  });

  it("lazily materializes and round-trips a DSH session", async () => {
    const mounted = await mount();
    const meta = header(sessionId());
    try {
      await mounted.context.sessionPersistence.create(meta);
      expect((await mounted.context.sessionPersistence.list()).some((item) => item.id === meta.id)).toBe(false);
      await mounted.context.sessionPersistence.append(meta.id, completedTurn());
      const loaded = await mounted.context.sessionPersistence.load(meta.id);
      expect(loaded.meta).toEqual(meta);
      expect(loaded.events).toEqual(completedTurn());
      expect((await mounted.context.sessionPersistence.readFrom(meta.id, 2)).events.map((event) => event.seq))
        .toEqual([2, 3]);
    } finally {
      await mounted.dispose();
    }
  });

  it("lets only one stale Brain replica materialize the same session id", async () => {
    const left = await mount();
    const right = await mount();
    const meta = header(sessionId());
    try {
      await Promise.all([
        left.context.sessionPersistence.create(meta),
        right.context.sessionPersistence.create(meta),
      ]);
      const results = await Promise.allSettled([
        left.context.sessionPersistence.append(meta.id, completedTurn()),
        right.context.sessionPersistence.append(meta.id, completedTurn()),
      ]);
      expect(results.filter((result) => result.status === "fulfilled")).toHaveLength(1);
      expect(results.filter((result) => result.status === "rejected")).toHaveLength(1);
    } finally {
      await Promise.all([left.dispose(), right.dispose()]);
    }
  });

  it("creates a named PENDING Workspace with an internal OS Deployment mapping", async () => {
    await runMigrations(mysqlConfigFromEnv());
    const state = new MysqlRuntimeState(mysqlConfigFromEnv());
    const id = workspaceId();
    try {
      const created = await state.createWorkspace(id, "Data science", "alpine", "dpl-alpine");
      expect(created).toEqual({
        id,
        title: "Data science",
        osId: "alpine",
        deploymentId: "dpl-alpine",
        state: "PENDING",
        generation: "1",
      });
      expect(created.affinityId).toBeUndefined();
    } finally {
      await state.close();
    }
  });

  it("grants exactly one owner for concurrent first-use allocation", async () => {
    await runMigrations(mysqlConfigFromEnv());
    const left = new MysqlRuntimeState(mysqlConfigFromEnv());
    const right = new MysqlRuntimeState(mysqlConfigFromEnv());
    const id = workspaceId();
    try {
      await left.createWorkspace(id, "Ubuntu work", "ubuntu", "dpl-ubuntu");
      const claims = await Promise.all([
        left.claimWorkspaceAllocation(id),
        right.claimWorkspaceAllocation(id),
      ]);
      expect(claims.filter((claim) => claim.owner)).toHaveLength(1);
      const owner = claims.find((claim) => claim.owner);
      if (owner?.token === undefined) throw new Error("owner token missing");
      await left.activateWorkspace(id, owner.token, owner.workspace.generation, "affinity-ubuntu");
      await expect(right.getWorkspace(id)).resolves.toMatchObject({
        state: "ACTIVE",
        deploymentId: "dpl-ubuntu",
        affinityId: "affinity-ubuntu",
      });
    } finally {
      await Promise.all([left.close(), right.close()]);
    }
  });

  it("retries a failed first-use allocation with a new generation", async () => {
    await runMigrations(mysqlConfigFromEnv());
    const state = new MysqlRuntimeState(mysqlConfigFromEnv());
    const id = workspaceId();
    try {
      await state.createWorkspace(id, "Retry work", "ubuntu", "dpl-ubuntu");
      const first = await state.claimWorkspaceAllocation(id);
      if (first.token === undefined) throw new Error("first allocation token missing");
      await state.failWorkspaceAllocation(id, first.token, first.workspace.generation, "UNAVAILABLE");

      const retry = await state.claimWorkspaceAllocation(id);
      expect(retry).toMatchObject({ owner: true, workspace: { state: "PENDING", generation: "2" } });
      if (retry.token === undefined) throw new Error("retry allocation token missing");
      await state.activateWorkspace(id, retry.token, retry.workspace.generation, "affinity-retry");
      await expect(state.getWorkspace(id)).resolves.toMatchObject({
        state: "ACTIVE",
        generation: "2",
        affinityId: "affinity-retry",
      });
    } finally {
      await state.close();
    }
  });

  it("fences stale activation after reclaiming an abandoned allocation", async () => {
    await runMigrations(mysqlConfigFromEnv());
    const state = new MysqlRuntimeState(mysqlConfigFromEnv());
    const pool = createPool(mysqlPoolOptions(mysqlConfigFromEnv()));
    const id = workspaceId();
    try {
      await state.createWorkspace(id, "Recovered work", "ubuntu", "dpl-ubuntu");
      const abandoned = await state.claimWorkspaceAllocation(id);
      expect(abandoned.owner).toBe(true);
      await pool.execute(`
        UPDATE dsh_workspaces
        SET allocation_started_at = DATE_SUB(CURRENT_TIMESTAMP(6), INTERVAL 121 SECOND)
        WHERE workspace_id = ?
      `, [id]);
      const recovered = await state.claimWorkspaceAllocation(id);
      expect(recovered.owner).toBe(true);
      expect(recovered.token).not.toBe(abandoned.token);
      if (recovered.token === undefined) throw new Error("recovered allocation token missing");
      await state.activateWorkspace(id, recovered.token, recovered.workspace.generation, `dsh-${id}`);
      if (abandoned.token === undefined) throw new Error("abandoned allocation token missing");
      await expect(state.activateWorkspace(
        id,
        abandoned.token,
        abandoned.workspace.generation,
        `dsh-${id}`,
      )).rejects.toBeInstanceOf(RuntimeStateConflictError);
    } finally {
      await pool.end();
      await state.close();
    }
  });

  it("keeps a live Workspace allocation lease from being reclaimed", async () => {
    await runMigrations(mysqlConfigFromEnv());
    const state = new MysqlRuntimeState(mysqlConfigFromEnv());
    const pool = createPool(mysqlPoolOptions(mysqlConfigFromEnv()));
    const id = workspaceId();
    try {
      await state.createWorkspace(id, "Slow allocation", "ubuntu", "dpl-ubuntu");
      const owner = await state.claimWorkspaceAllocation(id);
      if (owner.token === undefined) throw new Error("allocation token missing");
      await pool.execute(`
        UPDATE dsh_workspaces
        SET allocation_started_at = DATE_SUB(CURRENT_TIMESTAMP(6), INTERVAL 121 SECOND)
        WHERE workspace_id = ?
      `, [id]);
      await state.heartbeatWorkspaceAllocation(id, owner.token, owner.workspace.generation);
      await expect(state.claimWorkspaceAllocation(id)).resolves.toMatchObject({ owner: false });
    } finally {
      await pool.end();
      await state.close();
    }
  });

  it("rejects a stale cross-replica Settings write instead of losing an update", async () => {
    await runMigrations(mysqlConfigFromEnv());
    const namespace = `test-${randomUUID().replaceAll("-", "")}`;
    createdSettingsNamespaces.push(namespace);
    const leftContext = new Context();
    const rightContext = new Context();
    const leftFiber = leftContext.plugin(TestMysqlSettingsProvider);
    const rightFiber = rightContext.plugin(TestMysqlSettingsProvider);
    try {
      await Promise.all([leftFiber.await(), rightFiber.await()]);
      const left = leftContext.settings as TestMysqlSettingsProvider;
      const right = rightContext.settings as TestMysqlSettingsProvider;
      await left.persistForTest(namespace, { model: "first" });
      await Promise.all([left.loadForTest(), right.loadForTest()]);
      await left.persistForTest(namespace, { model: "second" });
      await expect(right.persistForTest(namespace, { model: "stale" }))
        .rejects.toBeInstanceOf(SettingsConflictError);

      const pool = createPool(mysqlPoolOptions(mysqlConfigFromEnv()));
      try {
        const [rows] = await pool.execute<Array<{ section_json: string } & RowDataPacket>>(
          "SELECT CAST(section_json AS CHAR) AS section_json FROM dsh_settings WHERE namespace = ?",
          [namespace],
        );
        expect(JSON.parse(rows[0]?.section_json ?? "null")).toEqual({ model: "second" });
      } finally {
        await pool.end();
      }
    } finally {
      await Promise.all([leftFiber.dispose(), rightFiber.dispose()]);
    }
  });

  it("materializes a first Web session while claiming its Workspace turn", async () => {
    await runMigrations(mysqlConfigFromEnv());
    const state = new MysqlRuntimeState(mysqlConfigFromEnv());
    const pool = createPool(mysqlPoolOptions(mysqlConfigFromEnv()));
    const workspace = await activeWorkspace(state);
    const id = sessionId();
    const meta = header(id, workspacePath(workspace.id));
    let claim: TurnClaim | undefined;
    try {
      claim = await state.claimTurn(id, "brain-a", 10_000, workspace.id, meta);
      const [rows] = await pool.execute<Array<{ header_json: string } & RowDataPacket>>(
        "SELECT CAST(header_json AS CHAR) AS header_json FROM dsh_sessions WHERE session_id = ?",
        [id],
      );
      expect(JSON.parse(rows[0]?.header_json ?? "null")).toEqual(meta);
    } finally {
      if (claim !== undefined) await state.completeTurn(claim);
      await pool.end();
      await state.close();
    }
  });

  it("serializes sessions in one Workspace while allowing different Workspaces", async () => {
    await runMigrations(mysqlConfigFromEnv());
    const state = new MysqlRuntimeState(mysqlConfigFromEnv());
    const firstWorkspace = await activeWorkspace(state);
    const secondWorkspace = await activeWorkspace(state, workspaceId(), "alpine", "dpl-alpine");
    const firstId = sessionId();
    const secondId = sessionId();
    const thirdId = sessionId();
    let first: TurnClaim | undefined;
    let third: TurnClaim | undefined;
    try {
      first = await state.claimTurn(firstId, "brain-a", 10_000, firstWorkspace.id);
      await expect(state.claimTurn(secondId, "brain-b", 10_000, firstWorkspace.id))
        .rejects.toBeInstanceOf(SessionBusyError);
      third = await state.claimTurn(thirdId, "brain-c", 10_000, secondWorkspace.id);
      expect(third.claimId).not.toBe(first.claimId);
    } finally {
      if (first !== undefined) await state.completeTurn(first);
      if (third !== undefined) await state.completeTurn(third);
      await state.close();
    }
  });

  it("fences concurrent and stale turns with a monotonic generation", async () => {
    await runMigrations(mysqlConfigFromEnv());
    const state = new MysqlRuntimeState(mysqlConfigFromEnv());
    const id = sessionId();
    try {
      const first = await state.claimTurn(id, "brain-a", 10_000);
      await expect(state.claimTurn(id, "brain-b", 10_000)).rejects.toBeInstanceOf(SessionBusyError);
      await state.heartbeatTurn(first, 10_000);
      await state.completeTurn(first);
      const second = await state.claimTurn(id, "brain-b", 10_000);
      expect(BigInt(second.generation)).toBeGreaterThan(BigInt(first.generation));
      await expect(state.assertTurn(first)).rejects.toBeInstanceOf(StaleTurnClaimError);
      await state.assertTurn(second);
      await state.completeTurn(second);
    } finally {
      await state.close();
    }
  });

  it("resumes an empty session provisioned by its first Workspace turn", async () => {
    await runMigrations(mysqlConfigFromEnv());
    const state = new MysqlRuntimeState(mysqlConfigFromEnv());
    const workspace = await activeWorkspace(state);
    const context = new Context();
    const turnContext = new TurnContext();
    const id = sessionId();
    const meta = header(id, workspacePath(workspace.id));
    const claim = await state.claimTurn(id, "brain-a", 10_000, workspace.id, meta);
    const persistence = context.plugin(MysqlSessionPersistence, {
      connection: mysqlConfigFromEnv(),
      currentTurnClaim: (candidate) => turnContext.current(candidate),
    });
    const spine = context.plugin(AgentSpine, {
      workspaceContext: false,
      skills: { enabled: false },
      toolBash: false,
      toolJobs: false,
      goals: false,
      maxParallelToolCalls: 1,
      tools: { mode: "native" },
    });
    try {
      await Promise.all([persistence.await(), spine.await()]);
      const handle = await turnContext.run(claim, () => context.agents.resume({
        resumeSessionId: SessionId(id),
      }));
      expect(handle.agent.session.id).toBe(id);
      expect(handle.agent.session.events.map((event) => event.type)).toEqual(["session/end-seed"]);
      await turnContext.run(claim, () => handle.dispose());
      await state.completeTurn(claim);
    } finally {
      await Promise.all([persistence.dispose(), spine.dispose()]);
      await state.close();
    }
  });
});
