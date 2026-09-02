import type { CommandResult } from "e2b";
import { describe, expect, it, vi } from "vitest";

import { DeploymentSandboxFactory } from "../src/hands/deployment-sandbox.js";
import {
  parseDeploymentTokenResponse,
  StaticDeploymentTokenProvider,
  TencentCloudDeploymentTokenProvider,
} from "../src/hands/deployment-token.js";
import { HandsGateway, type HandsConnectionFactory, type HandsTarget } from "../src/hands/gateway.js";
import { ActiveTurnTargets, handsToolDefinitions } from "../src/brain/hands-tools.js";

const target: HandsTarget = {
  deploymentId: "dpl-test",
  affinityId: "affinity-test",
  claim: { sessionId: "session-test", holderInstanceId: "brain-a", generation: "7" },
};

function commandResult(stdout = ""): CommandResult {
  return { exitCode: 0, stdout, stderr: "" };
}

function fakeGateway(): {
  readonly gateway: HandsGateway;
  readonly files: Map<string, string>;
  readonly commands: string[];
  readonly asserted: string[];
} {
  const files = new Map<string, string>();
  const commands: string[] = [];
  const asserted: string[] = [];
  const sandbox = {
    files: {
      read: async (path: string) => new TextEncoder().encode(files.get(path) ?? ""),
      write: async (path: string, contents: string) => { files.set(path, contents); },
    },
    commands: {
      run: async (command: string) => {
        commands.push(command);
        return command.includes("turn-generation") ? commandResult() : commandResult("done\n");
      },
    },
  };
  const factory: HandsConnectionFactory = {
    deploymentId: "dpl-test",
    allocateAffinity: async () => "affinity-test",
    health: async () => new Response(null, { status: 200 }),
    connect: async () => sandbox,
  };
  const gateway = new HandsGateway(factory, {
    assertTurn: async (claim) => { asserted.push(claim.generation); },
  });
  return { gateway, files, commands, asserted };
}

describe("Hands gateway", () => {
  it("fences every operation before using envd", async () => {
    const fixture = fakeGateway();
    const result = await fixture.gateway.bash(target, "printf done");
    expect(result.stdout).toBe("done\n");
    expect(fixture.asserted).toEqual(["7"]);
    expect(fixture.commands[0]).toContain("turn-generation");
    expect(fixture.commands[1]).toBe("printf done");
  });

  it("provides exact-match edit over the retained workspace", async () => {
    const fixture = fakeGateway();
    fixture.files.set("/workspace/file.txt", "alpha beta gamma");
    await fixture.gateway.edit(target, "/workspace/file.txt", "beta", "delta");
    expect(fixture.files.get("/workspace/file.txt")).toBe("alpha delta gamma");
  });

  it("rejects traversal outside /workspace", async () => {
    const fixture = fakeGateway();
    await expect(fixture.gateway.write(target, "/workspace/../etc/passwd", "x"))
      .rejects.toThrow(/workspace/);
    expect(fixture.asserted).toEqual([]);
  });

  it("routes a DSH tool only through the active session target", async () => {
    const fixture = fakeGateway();
    const targets = new ActiveTurnTargets();
    const release = targets.bind("session-test", target);
    const read = handsToolDefinitions({ gateway: fixture.gateway, targets })
      .find((tool) => tool.name === "read");
    expect(read).toBeDefined();
    fixture.files.set("/workspace/file.txt", "tool-ok");
    const exec = {
      agent: { session: { id: "session-test" } },
    } as never;
    await expect(read?.execute({ path: "/workspace/file.txt" }, exec)).resolves.toBe("tool-ok");
    release();
    await expect(read?.execute({ path: "/workspace/file.txt" }, exec))
      .rejects.toThrow(/active fenced turn/);
  });
});

describe("AGS Deployment token and E2B routing", () => {
  it("parses a non-expired token response", () => {
    const now = Date.parse("2026-09-01T00:00:00Z");
    expect(parseDeploymentTokenResponse({
      Token: "token-value",
      ExpiresAt: "2026-09-01T01:00:00Z",
    }, now)).toEqual({ token: "token-value", expiresAt: Date.parse("2026-09-01T01:00:00Z") });
  });

  it("coalesces concurrent AcquireDeploymentToken calls", async () => {
    const request = vi.fn(async () => ({
      Token: "token-value",
      ExpiresAt: "2026-09-01T01:00:00Z",
    }));
    const provider = new TencentCloudDeploymentTokenProvider({
      deploymentId: "dpl-test",
      endpoint: "ags.tencentcloudapi.com",
      region: "ap-shanghai",
      secretId: "id",
      secretKey: "key",
    }, { client: { request }, now: () => Date.parse("2026-09-01T00:00:00Z") });
    await Promise.all([provider.ensureValid(), provider.ensureValid()]);
    expect(request).toHaveBeenCalledTimes(1);
    expect(provider.currentToken()).toBe("token-value");
  });

  it("allocates affinity through envd health with AGS headers", async () => {
    const provider = new StaticDeploymentTokenProvider("deployment-token");
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      const headers = new Headers(init?.headers);
      expect(headers.get("X-Access-Token")).toBe("deployment-token");
      expect(headers.get("E2b-Sandbox-Port")).toBe("49983");
      return new Response(null, {
        status: 200,
        headers: { "X-Tencent-Agr-Affinity-Id": "affinity-returned" },
      });
    });
    const factory = new DeploymentSandboxFactory({
      baseUrl: "https://49983-dpl-test.ap-shanghai.agents.tencentags.com",
      deploymentId: "dpl-test",
      deploymentToken: provider,
    }, fetchMock as typeof fetch);
    expect(await factory.allocateAffinity()).toBe("affinity-returned");
  });
});
