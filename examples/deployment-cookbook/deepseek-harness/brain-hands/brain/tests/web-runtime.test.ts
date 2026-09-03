import type { SessionEvent } from "@deepseek-ai/dsh-session";
import { describe, expect, it } from "vitest";

import type { TurnClaim } from "../src/runtime/mysql-state.js";
import { AgsWebRuntime, startsTurn } from "../src/web/runtime.js";

describe("DSH Web turn detection", () => {
  it("starts fencing only for a real turn", () => {
    const idleAppend = [{ type: "session/end-seed" }] as SessionEvent[];
    const turnAppend = [{ type: "turn/start" }] as SessionEvent[];

    expect(startsTurn(idleAppend)).toBe(false);
    expect(startsTurn(turnAppend)).toBe(true);
  });

  it("uses the closing lifecycle claim when its flush includes the next turn", async () => {
    const sessionId = "session-1";
    const closingClaim: TurnClaim = {
      sessionId,
      claimId: "workspace-user-example",
      holderInstanceId: "brain-a",
      generation: "1",
    };
    const runtime = Object.create(AgsWebRuntime.prototype) as AgsWebRuntime;
    Object.assign(runtime, {
      closing: new Map([[sessionId, [{
        startSeq: 0,
        boundarySeq: 4,
        started: true,
        acceptingWrites: true,
        ready: Promise.resolve({ claim: closingClaim }),
      }]]]),
      active: new Map([[sessionId, {
        ready: new Promise(() => undefined),
      }]]),
    });

    const claim = await runtime.currentTurnClaim(
      sessionId,
      [{ type: "turn/start" }] as SessionEvent[],
    );
    expect(claim).toBe(closingClaim);
  });

  it("starts a closing lifecycle when its queued turn reaches persistence", async () => {
    const sessionId = "session-1";
    const claim: TurnClaim = {
      sessionId,
      claimId: "workspace-user-example",
      holderInstanceId: "brain-a",
      generation: "1",
    };
    let started = false;
    const activity = {
      startSeq: 0,
      boundarySeq: 2,
      started: false,
      acceptingWrites: true,
      start(): void {
        this.started = true;
        started = true;
      },
      ready: Promise.resolve({ claim }),
    };
    const runtime = Object.create(AgsWebRuntime.prototype) as AgsWebRuntime;
    Object.assign(runtime, {
      closing: new Map([[sessionId, [activity]]]),
      active: new Map(),
    });

    await expect(runtime.currentTurnClaim(
      sessionId,
      [{ type: "turn/start", seq: 0 }] as SessionEvent[],
    )).resolves.toBe(claim);
    expect(started).toBe(true);
  });

  it("waits for claim completion after the closing flush stops routing writes", async () => {
    const sessionId = "session-1";
    const oldClaim: TurnClaim = {
      sessionId,
      claimId: "workspace-user-example",
      holderInstanceId: "brain-a",
      generation: "1",
    };
    const nextClaim: TurnClaim = { ...oldClaim, generation: "2" };
    let resolveClosing!: () => void;
    const closing = new Map<string, unknown[]>();
    const closed = new Promise<void>((resolve) => {
      resolveClosing = () => {
        closing.delete(sessionId);
        resolve();
      };
    });
    const nextActivity = {
      started: false,
      previous: closed,
      start(): void {
        this.started = true;
      },
      ready: Promise.resolve({ claim: nextClaim }),
    };
    closing.set(sessionId, [{
      startSeq: 0,
      boundarySeq: 4,
      started: true,
      acceptingWrites: false,
      closing: closed,
      ready: Promise.resolve({ claim: oldClaim }),
    }]);
    const runtime = Object.create(AgsWebRuntime.prototype) as AgsWebRuntime;
    Object.assign(runtime, {
      closing,
      active: new Map([[sessionId, nextActivity]]),
    });

    const selected = runtime.currentTurnClaim(
      sessionId,
      [{ type: "turn/start", seq: 4 }] as SessionEvent[],
    );
    let settled = false;
    void selected.then(() => { settled = true; });
    await Promise.resolve();
    expect(settled).toBe(false);

    resolveClosing();
    await expect(selected).resolves.toBe(nextClaim);
  });

  it("closes an unstarted lifecycle whose turn was flushed by its predecessor", async () => {
    const sessionId = "session-1";
    const activity = {
      agent: { id: sessionId, session: {} },
      previous: Promise.resolve(),
      started: false,
      acceptingWrites: true,
      hasTurn: true,
      ready: new Promise(() => undefined),
    };
    const closing = new Map([[sessionId, [activity]]]);
    const active = new Map([[sessionId, activity]]);
    const runtime = Object.create(AgsWebRuntime.prototype) as AgsWebRuntime;
    Object.assign(runtime, {
      ctx: { sessions: { flush: async () => undefined } },
      state: { completeTurn: async () => { throw new Error("No claim should be completed"); } },
      closing,
      active,
    });

    const closeTurn = (runtime as unknown as {
      closeTurn(candidate: unknown): Promise<void>;
    }).closeTurn.bind(runtime);
    await expect(closeTurn(activity)).resolves.toBeUndefined();
    expect(activity.acceptingWrites).toBe(false);
    expect(closing.has(sessionId)).toBe(false);
    expect(active.has(sessionId)).toBe(false);
  });
});
