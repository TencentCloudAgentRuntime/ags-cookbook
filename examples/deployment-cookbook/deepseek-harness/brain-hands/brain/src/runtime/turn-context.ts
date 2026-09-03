import { AsyncLocalStorage } from "node:async_hooks";

import type { TurnClaim } from "./mysql-state.js";

/** Carries the MySQL-issued write capability through one Brain request. */
export class TurnContext {
  private readonly storage = new AsyncLocalStorage<TurnClaim>();

  public run<T>(claim: TurnClaim, operation: () => T): T {
    return this.storage.run(claim, operation);
  }

  public current(sessionId: string): TurnClaim | undefined {
    const claim = this.storage.getStore();
    return claim?.sessionId === sessionId ? claim : undefined;
  }
}
