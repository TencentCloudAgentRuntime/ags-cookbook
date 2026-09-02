import type { Session } from "@deepseek-ai/dsh-session";
import { describe, expect, it } from "vitest";

import { assistantResponse } from "../src/brain/server.js";

function sessionWithAssistant(seq: number, text: string): Session {
  return {
    id: "session-test",
    events: [{
      type: "assistant/message",
      seq,
      time: 1,
      data: {
        turn: 1,
        step: 1,
        message: {
          id: `message-${seq}`,
          role: "assistant",
          source: { kind: "model", provider: "test", model: "test" },
          content: [{ type: "text", text }],
        },
      },
    }],
  } as never;
}

describe("Brain turn response", () => {
  it("never reuses an assistant message from an earlier turn", () => {
    const session = sessionWithAssistant(3, "old answer");
    expect(() => assistantResponse(session, 4)).toThrow(/no assistant message/i);
  });

  it("returns an assistant message appended by the current turn", () => {
    const session = sessionWithAssistant(4, "new answer");
    expect(assistantResponse(session, 4)).toMatchObject({
      sessionId: "session-test",
      messageId: "message-4",
      text: "new answer",
    });
  });
});
