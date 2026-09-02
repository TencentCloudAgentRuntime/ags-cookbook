import { Context } from "@deepseek-ai/cordis";
import * as AgentSpine from "@deepseek-ai/dsh-agent-spine-demo";
import { describe, expect, it } from "vitest";

import { BRAIN_SPINE_CONFIG } from "../src/brain/server.js";

describe("Brain agent spine", () => {
  it("mounts the concrete agent loop and model-facing tool registry", async () => {
    const context = new Context();
    const spine = context.plugin(AgentSpine, BRAIN_SPINE_CONFIG);
    try {
      await spine.await();
      await new Promise((resolve) => setTimeout(resolve, 50));
      expect(context.get("systemPrompt")).toBeDefined();
      expect(context.get("tools")).toBeDefined();
      expect(context.get("agentLoop")).toBeDefined();
    } finally {
      await context.fiber.dispose();
    }
  });
});
