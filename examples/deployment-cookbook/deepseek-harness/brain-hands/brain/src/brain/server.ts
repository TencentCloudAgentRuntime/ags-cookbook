import { createServer, type ServerResponse } from "node:http";

import { config as loadDotenv } from "dotenv";

import { MysqlRuntimeState } from "../runtime/mysql-state.js";
import { brainConfigFromEnv } from "./config.js";

function sendJson(response: ServerResponse, status: number, body: unknown): void {
  response.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "cache-control": "no-store",
  });
  response.end(`${JSON.stringify(body)}\n`);
}

export async function main(): Promise<void> {
  loadDotenv();
  const config = brainConfigFromEnv();
  const state = new MysqlRuntimeState(config.mysql);
  const server = createServer((request, response) => {
    void (async () => {
      const url = new URL(request.url ?? "/", "http://brain.invalid");
      if (request.method === "GET" && url.pathname === "/healthz") {
        sendJson(response, 200, { ok: true });
        return;
      }
      if (request.method === "GET" && url.pathname === "/readyz") {
        await state.ping();
        const web = await fetch("http://127.0.0.1:3080/");
        if (!web.ok) throw new Error("DSH Web is not ready");
        sendJson(response, 200, { ok: true });
        return;
      }
      sendJson(response, 404, { error: "NOT_FOUND" });
    })().catch(() => {
      sendJson(response, 503, { error: "NOT_READY" });
    });
  });
  await new Promise<void>((resolve, reject) => {
    server.once("error", reject);
    server.listen(config.port, "0.0.0.0", resolve);
  });

  let stopping: Promise<void> | undefined;
  const stop = (): Promise<void> => {
    stopping ??= (async () => {
      await new Promise<void>((resolve, reject) => {
        server.close((error) => error === undefined ? resolve() : reject(error));
      });
      await state.close();
    })();
    return stopping;
  };
  process.once("SIGTERM", () => void stop());
  process.once("SIGINT", () => void stop());
}

if (import.meta.url === `file://${process.argv[1]}`) {
  await main();
}
