import type { Context } from "@deepseek-ai/cordis";
import { isTrustedApiRequest } from "@deepseek-ai/dsh-client-connection";
import type { WebServer } from "@deepseek-ai/dsh-host-webserver";
import type { WorkspaceRegistry } from "@deepseek-ai/dsh-workspace";
import { randomUUID } from "node:crypto";
import { mkdir } from "node:fs/promises";
import type { IncomingMessage, ServerResponse } from "node:http";

import { brainConfigFromEnv } from "../brain/config.js";
import { MysqlRuntimeState } from "../runtime/mysql-state.js";
import { DSH_WORKSPACE_ROOT, workspacePath } from "./workspace-path.js";

declare module "@deepseek-ai/cordis" {
  interface Context {
    webServer: WebServer;
    workspaceRegistry: WorkspaceRegistry;
  }
}

interface CreateWorkspaceBody {
  readonly name: string;
  readonly os: string;
}

function sendJson(response: ServerResponse, status: number, body: unknown): void {
  response.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "cache-control": "no-store",
  });
  response.end(JSON.stringify(body));
}

async function readBody(request: IncomingMessage): Promise<CreateWorkspaceBody> {
  const chunks: Buffer[] = [];
  let size = 0;
  for await (const chunk of request) {
    const bytes = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
    size += bytes.byteLength;
    if (size > 8_192) throw new Error("Request body is too large");
    chunks.push(bytes);
  }
  const value = JSON.parse(Buffer.concat(chunks).toString("utf8")) as unknown;
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error("Request body must be an object");
  }
  const body = value as Record<string, unknown>;
  if (typeof body.name !== "string" || typeof body.os !== "string") {
    throw new Error("Workspace name and OS are required");
  }
  return { name: body.name, os: body.os };
}

export const inject = ["webServer", "webStartup", "workspaceRegistry"];

export function isTrustedWorkspaceRequest(
  request: IncomingMessage,
  trustedHosts: readonly string[],
): boolean {
  return isTrustedApiRequest(request, trustedHosts);
}

function requireTrustedRequest(
  request: IncomingMessage,
  response: ServerResponse,
  trustedHosts: readonly string[],
): boolean {
  if (isTrustedWorkspaceRequest(request, trustedHosts)) return true;
  response.writeHead(403, { "content-type": "text/plain; charset=utf-8" });
  response.end("forbidden");
  return false;
}

/** Adds the name-and-OS Workspace creation surface consumed by DSH Web. */
export async function apply(ctx: Context): Promise<void> {
  const config = brainConfigFromEnv();
  const state = new MysqlRuntimeState(config.mysql);
  const oses = new Map(config.hands.oses.map((os) => [os.id, os]));
  const reconcile = async (): Promise<void> => {
    const registeredByPath = new Map(ctx.workspaceRegistry.list().map((entry) => [entry.path, entry]));
    for (const workspace of await state.listWorkspaces()) {
      const logicalPath = workspacePath(workspace.id);
      await mkdir(logicalPath, { recursive: true });
      const registered = registeredByPath.get(logicalPath)
        ?? await ctx.workspaceRegistry.create(logicalPath, workspace.title);
      if (registered.title !== workspace.title) await registered.setTitle(workspace.title);
    }
  };
  try {
    await mkdir(DSH_WORKSPACE_ROOT, { recursive: true });
    await reconcile();
  } catch (error) {
    await state.close();
    throw error;
  }

  const disposeOptions = ctx.webServer.register({
    kind: "exact",
    path: "/api/ags/workspace-options",
    handler: (request, response) => {
      if (!requireTrustedRequest(request, response, ctx.webStartup.trustedHosts)) return;
      sendJson(response, 200, {
        oses: config.hands.oses.map((os) => ({ id: os.id, label: os.label })),
      });
    },
  });
  const disposeCreate = ctx.webServer.register({
    kind: "exact",
    path: "/api/ags/workspaces",
    handler: async (request, response) => {
      if (!requireTrustedRequest(request, response, ctx.webStartup.trustedHosts)) return;
      if (request.method !== "POST") {
        sendJson(response, 405, { error: "METHOD_NOT_ALLOWED" });
        return;
      }
      try {
        const body = await readBody(request);
        const name = body.name.trim();
        if (name.length === 0 || name.length > 80) throw new Error("Workspace name must be 1-80 characters");
        const os = oses.get(body.os);
        if (os === undefined) throw new Error("Select a configured OS");
        const workspaceId = randomUUID();
        const logicalPath = workspacePath(workspaceId);
        await state.createWorkspace(workspaceId, name, os.id, os.deploymentId);
        await mkdir(logicalPath, { recursive: true });
        const registered = await ctx.workspaceRegistry.create(logicalPath, name);
        if (registered.title !== name) await registered.setTitle(name);
        sendJson(response, 201, { path: logicalPath });
      } catch (error) {
        sendJson(response, 400, {
          error: "INVALID_WORKSPACE",
          message: error instanceof Error ? error.message : String(error),
        });
      }
    },
  });
  let reconciling = false;
  const timer = setInterval(() => {
    if (reconciling) return;
    reconciling = true;
    void reconcile().catch((error: unknown) => {
      ctx.logger.warn(`ags-workspace-api: reconciliation failed: ${String(error)}`);
    }).finally(() => {
      reconciling = false;
    });
  }, 1_000);
  timer.unref();

  ctx.effect(() => async () => {
    clearInterval(timer);
    disposeCreate();
    disposeOptions();
    await state.close();
  }, "close AGS Workspace API");
}
