import type { Context } from "@deepseek-ai/cordis";

import {
  MysqlSessionPersistence,
  type MysqlSessionPersistenceConfig,
} from "../persistence/mysql-session-persistence.js";
import type { AgsWebRuntime } from "./runtime.js";

declare module "@deepseek-ai/cordis" {
  interface Context {
    agsWebRuntime: AgsWebRuntime;
  }
}

/** Native Web adapter that sources write fencing from the active Web turn. */
export class WebMysqlSessionPersistence extends MysqlSessionPersistence {
  public static override inject = ["sessions", "agsWebRuntime"];

  public constructor(ctx: Context, config: MysqlSessionPersistenceConfig) {
    super(ctx, {
      ...config,
      currentTurnClaim: (sessionId, events) => ctx.agsWebRuntime.currentTurnClaim(sessionId, events),
    });
  }
}

export default WebMysqlSessionPersistence;
