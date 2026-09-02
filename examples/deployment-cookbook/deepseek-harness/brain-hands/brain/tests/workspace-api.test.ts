import type { IncomingMessage } from "node:http";
import { describe, expect, it } from "vitest";

import { isTrustedWorkspaceRequest } from "../src/web/workspace-api.js";

const trustedHosts = ["*.ap-shanghai.agents.tencentags.com"];

function request(headers: Record<string, string>): IncomingMessage {
  return { headers } as IncomingMessage;
}

describe("Workspace API request trust", () => {
  it("accepts the AGS Host forwarded by a loopback proxy Origin", () => {
    expect(isTrustedWorkspaceRequest(request({
      host: "3080-instance.ap-shanghai.agents.tencentags.com",
      origin: "http://127.0.0.1:18082",
      "sec-fetch-site": "cross-site",
    }), trustedHosts)).toBe(false);

    expect(isTrustedWorkspaceRequest(request({
      host: "3080-instance.ap-shanghai.agents.tencentags.com",
      origin: "http://127.0.0.1:18082",
      "sec-fetch-site": "same-site",
    }), trustedHosts)).toBe(true);
  });

  it("rejects arbitrary and cross-site authorities", () => {
    expect(isTrustedWorkspaceRequest(request({ host: "attacker.example" }), trustedHosts)).toBe(false);
    expect(isTrustedWorkspaceRequest(request({
      host: "3080-instance.ap-shanghai.agents.tencentags.com",
      origin: "https://attacker.example",
    }), trustedHosts)).toBe(false);
  });
});
