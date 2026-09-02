import { randomUUID } from "node:crypto";
import "dotenv/config";

import { Context } from "@deepseek-ai/cordis";
import SessionStore, {
  SESSION_FORMAT_VERSION,
  SessionId,
  type SessionEvent,
  type SessionHeader,
} from "@deepseek-ai/dsh-session";
import * as AgentSpine from "@deepseek-ai/dsh-agent-spine-demo";
import { createPool } from "mysql2/promise";
import { afterEach, describe, expect, it } from "vitest";

import { mysqlConfigFromEnv, mysqlPoolOptions } from "../src/mysql/config.js";
import { runMigrations } from "../src/mysql/migrations.js";
import MysqlSessionPersistence from "../src/persistence/mysql-session-persistence.js";
import {
  MysqlRuntimeState,
  SessionBusyError,
  StaleTurnClaimError,
  workspaceClaimId,
  type TurnClaim,
} from "../src/runtime/mysql-state.js";
import { TurnContext } from "../src/runtime/turn-context.js";

const enabled = process.env.RUN_MYSQL_INTEGRATION === "1";
const createdIds: string[] = [];

function sessionId(): string {
  const id = `cookbook-test-${randomUUID()}`;
  createdIds.push(id);
  return id;
}

function header(id: string): SessionHeader {
  return {
    version: SESSION_FORMAT_VERSION,
    id: SessionId(id),
    createdAt: Date.now(),
    cwd: "/workspace",
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

afterEach(async () => {
  if (!enabled || createdIds.length === 0) return;
  const pool = createPool(mysqlPoolOptions(mysqlConfigFromEnv()));
  try {
    for (const id of createdIds.splice(0)) {
      await pool.execute("DELETE FROM turn_claims WHERE session_id = ?", [id]);
      await pool.execute("DELETE FROM dsh_sessions WHERE session_id = ?", [id]);
      await pool.execute("DELETE FROM workspace_bindings WHERE binding_identity = ?", [id]);
    }
  } finally {
    await pool.end();
  }
});

describe.skipIf(!enabled)("MySQL SessionPersistence", () => {
  it("runs checksum migrations idempotently", async () => {
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

  it("binds one identity once and requires explicit recovery", async () => {
    await runMigrations(mysqlConfigFromEnv());
    const state = new MysqlRuntimeState(mysqlConfigFromEnv());
    const identity = sessionId();
    const key = { mode: "SESSION" as const, identity };
    try {
      const pending = await state.beginBinding(key);
      expect(pending).toMatchObject({ state: "PENDING", generation: "1" });
      expect(await state.beginBinding(key)).toEqual(pending);

      await state.failBinding(key, pending.generation, "ALLOCATION_UNCERTAIN");
      expect(await state.getBinding(key)).toMatchObject({ state: "FAILED" });
      const retried = await state.retryBinding(key);
      expect(retried).toMatchObject({ state: "PENDING", generation: "2" });
      await state.activateBinding(key, retried.generation, "dpl-example", "affinity-secret");
      expect(await state.getBinding(key)).toMatchObject({
        state: "ACTIVE",
        generation: "2",
        deploymentId: "dpl-example",
        affinityId: "affinity-secret",
      });
    } finally {
      await state.close();
    }
  });

  it("atomically publishes the affinity and first DSH Session header", async () => {
    await runMigrations(mysqlConfigFromEnv());
    const state = new MysqlRuntimeState(mysqlConfigFromEnv());
    const id = sessionId();
    const key = { mode: "SESSION" as const, identity: id };
    try {
      const reservation = await state.reserveBinding(key);
      expect(reservation.owner).toBe(true);
      const active = await state.activateBindingAndProvisionSession(
        header(id),
        key,
        reservation.binding.generation,
        "dpl-example",
        "affinity-secret",
      );
      expect(active.state).toBe("ACTIVE");
      expect(await state.getSessionBinding(id)).toMatchObject({
        mode: "SESSION",
        identity: id,
        state: "ACTIVE",
      });
    } finally {
      await state.close();
    }
  });

  it("links an already materialized Web session to an active Hands workspace", async () => {
    await runMigrations(mysqlConfigFromEnv());
    const mounted = await mount();
    const state = new MysqlRuntimeState(mysqlConfigFromEnv());
    const id = sessionId();
    const workspaceId = sessionId();
    const key = { mode: "USER" as const, identity: workspaceId };
    try {
      const meta = header(id);
      const reservation = await state.reserveBinding(key);
      await state.activateBinding(key, reservation.binding.generation, "dpl-example", "affinity-secret");
      await expect(state.linkSession(meta, key, reservation.binding.generation))
        .rejects.toThrow(/not materialized/);
      expect(await state.getSessionBinding(id)).toBeUndefined();

      await mounted.context.sessionPersistence.create(meta);
      await mounted.context.sessionPersistence.append(meta.id, completedTurn());

      await state.linkSession(meta, key, reservation.binding.generation);

      expect(await state.getSessionBinding(id)).toMatchObject({
        mode: "USER",
        identity: workspaceId,
        state: "ACTIVE",
        deploymentId: "dpl-example",
        affinityId: "affinity-secret",
      });
    } finally {
      await mounted.dispose();
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
    } finally {
      await state.close();
    }
  });

  it("serializes sessions sharing one Hands workspace", async () => {
    await runMigrations(mysqlConfigFromEnv());
    const state = new MysqlRuntimeState(mysqlConfigFromEnv());
    const firstId = sessionId();
    const secondId = sessionId();
    const key = { mode: "USER" as const, identity: sessionId() };
    createdIds.push(workspaceClaimId(key));
    try {
      const reservation = await state.reserveBinding(key);
      await state.activateBinding(key, reservation.binding.generation, "dpl-example", "affinity-secret");

      const first = await state.claimTurn(firstId, "brain-a", 10_000, key);
      await expect(state.claimTurn(secondId, "brain-b", 10_000, key))
        .rejects.toBeInstanceOf(SessionBusyError);
      await state.completeTurn(first);
      const second = await state.claimTurn(secondId, "brain-b", 10_000, key);
      expect(BigInt(second.generation)).toBeGreaterThan(BigInt(first.generation));
      await state.completeTurn(second);
    } finally {
      await state.close();
    }
  });

  it("atomically links a new Web session before its workspace turn becomes active", async () => {
    await runMigrations(mysqlConfigFromEnv());
    const context = new Context();
    await context.plugin(SessionStore);
    const persistence = await context.plugin(MysqlSessionPersistence, {
      connection: mysqlConfigFromEnv(),
      writeBatchMaxDelayMs: 1,
      currentTurnClaim: async () => null,
    });
    const state = new MysqlRuntimeState(mysqlConfigFromEnv());
    const id = sessionId();
    const key = { mode: "USER" as const, identity: sessionId() };
    createdIds.push(workspaceClaimId(key));
    const meta = header(id);
    try {
      await context.sessionPersistence.create(meta);
      const reservation = await state.reserveBinding(key);
      await state.activateBinding(key, reservation.binding.generation, "dpl-example", "affinity-secret");

      const claim = await state.claimTurn(id, "brain-a", 10_000, key, meta);
      expect(await state.getSessionBinding(id)).toMatchObject(key);
      const titleEvent = {
        type: "session/title",
        seq: 0,
        time: 5,
        data: { title: "renamed", source: { kind: "fallback" }, messageSeqs: [] },
      } as SessionEvent;
      await expect(context.sessionPersistence.append(meta.id, [titleEvent]))
        .rejects.toThrow(/active turn claim/);

      await state.completeTurn(claim);
      await expect(context.sessionPersistence.append(meta.id, [titleEvent])).resolves.toBeUndefined();
    } finally {
      await persistence.dispose();
      await state.close();
    }
  });

  it("waits for live session initialization before claiming its first Web turn", async () => {
    await runMigrations(mysqlConfigFromEnv());
    const context = new Context();
    await context.plugin(SessionStore);
    const state = new MysqlRuntimeState(mysqlConfigFromEnv());
    const id = sessionId();
    const key = { mode: "USER" as const, identity: sessionId() };
    createdIds.push(workspaceClaimId(key));
    let claim: TurnClaim | undefined;
    const persistence = await context.plugin(MysqlSessionPersistence, {
      connection: mysqlConfigFromEnv(),
      writeBatchMaxDelayMs: 1,
      currentTurnClaim: async (candidate, events) => {
        if (!events.some((event) => event.type === "turn/start")) return null;
        const live = context.sessions.get(SessionId(candidate));
        if (live === undefined) return undefined;
        claim = await state.claimTurn(candidate, "brain-a", 10_000, key, live.header);
        return claim;
      },
    });
    try {
      const reservation = await state.reserveBinding(key);
      await state.activateBinding(key, reservation.binding.generation, "dpl-example", "affinity-secret");

      const live = context.sessions.create(SessionId(id), { meta: { cwd: "/workspace" } });
      live.append("turn/start", { turn: 1 });
      await context.sessions.flush(live);

      expect(claim).toBeDefined();
      expect(await state.getSessionBinding(id)).toMatchObject(key);
      if (claim === undefined) throw new Error("The first Web turn was not claimed");
      await state.completeTurn(claim);
      claim = undefined;
    } finally {
      if (claim !== undefined) await state.completeTurn(claim);
      await persistence.dispose();
      await state.close();
    }
  });

  it("rejects a session append after another Brain owns the turn generation", async () => {
    await runMigrations(mysqlConfigFromEnv());
    const context = new Context();
    await context.plugin(SessionStore);
    const state = new MysqlRuntimeState(mysqlConfigFromEnv());
    const id = sessionId();
    let activeClaim = await state.claimTurn(id, "brain-a", 10_000);
    const persistence = await context.plugin(MysqlSessionPersistence, {
      connection: mysqlConfigFromEnv(),
      currentTurnClaim: async (candidate) => candidate === id ? activeClaim : undefined,
    });
    try {
      const meta = header(id);
      await context.sessionPersistence.create(meta);
      await state.completeTurn(activeClaim);
      await state.claimTurn(id, "brain-b", 10_000);
      await expect(context.sessionPersistence.append(meta.id, completedTurn()))
        .rejects.toThrow(/claim no longer permits writes/);
    } finally {
      await persistence.dispose();
      await state.close();
    }
  });

  it("resumes an atomically provisioned empty DSH session", async () => {
    await runMigrations(mysqlConfigFromEnv());
    const state = new MysqlRuntimeState(mysqlConfigFromEnv());
    const context = new Context();
    const turnContext = new TurnContext();
    const id = sessionId();
    const key = { mode: "SESSION" as const, identity: id };
    const reservation = await state.reserveBinding(key);
    await state.activateBindingAndProvisionSession(
      header(id),
      key,
      reservation.binding.generation,
      "dpl-example",
      "affinity-secret",
    );
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
      const claim = await state.claimTurn(id, "brain-a", 10_000);
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
