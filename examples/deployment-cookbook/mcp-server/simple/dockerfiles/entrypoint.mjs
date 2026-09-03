import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { connect } from "node:net";

const mcpPort = Number(process.env.PORT ?? "3001");
const healthPort = Number(process.env.HEALTH_PORT ?? "3000");
const child = spawn(
  process.execPath,
  ["node_modules/@modelcontextprotocol/server-everything/dist/index.js", "streamableHttp"],
  {
    stdio: "inherit",
    env: { ...process.env, PORT: String(mcpPort) },
  },
);

let healthServer;
let stopping = false;

function waitUntilReady(deadline = Date.now() + 30_000) {
  return new Promise((resolve, reject) => {
    const probe = () => {
      const socket = connect({ host: "127.0.0.1", port: mcpPort });
      socket.once("connect", () => {
        socket.destroy();
        resolve();
      });
      socket.once("error", () => {
        socket.destroy();
        if (Date.now() >= deadline) {
          reject(new Error(`MCP port ${mcpPort} did not become ready`));
          return;
        }
        setTimeout(probe, 100);
      });
    };
    probe();
  });
}

async function stop(signal) {
  if (stopping) return;
  stopping = true;
  if (healthServer) {
    await new Promise((resolve) => healthServer.close(resolve));
  }
  child.kill(signal);
}

for (const signal of ["SIGTERM", "SIGINT"]) {
  process.on(signal, () => void stop(signal));
}

child.once("error", async (error) => {
  console.error(error);
  await stop("SIGTERM");
});

child.once("exit", (code, signal) => {
  if (healthServer) healthServer.close();
  if (signal) process.kill(process.pid, signal);
  else process.exit(code ?? 1);
});

try {
  await waitUntilReady();
  healthServer = createServer((request, response) => {
    if (request.method === "GET" && request.url === "/healthz") {
      response.writeHead(200, { "content-type": "text/plain; charset=utf-8" });
      response.end("ok\n");
      return;
    }
    response.writeHead(404);
    response.end();
  });
  healthServer.listen(healthPort, "0.0.0.0");
} catch (error) {
  console.error(error);
  await stop("SIGTERM");
}
