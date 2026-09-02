import { spawn, type ChildProcess } from "node:child_process";
import { fileURLToPath } from "node:url";

const appRoot = fileURLToPath(new URL("../../", import.meta.url));
const server = spawn(process.execPath, [`${appRoot}/dist/brain/server.js`], {
  cwd: "/workspace",
  env: process.env,
  stdio: "inherit",
});
const web = spawn(process.execPath, [
  `${appRoot}/node_modules/@deepseek-ai/dsh/lib/bin.js`,
  "--profile",
  "web",
  "--patch",
  `${appRoot}/web/cordis.patch.yml`,
], {
  cwd: "/workspace",
  env: { ...process.env, DSH_HOME: "/tmp/dsh-home" },
  stdio: "inherit",
});

const children: readonly ChildProcess[] = [server, web];
let stopping = false;

function stop(signal: NodeJS.Signals): void {
  if (stopping) return;
  stopping = true;
  for (const child of children) child.kill(signal);
}

process.on("SIGTERM", () => stop("SIGTERM"));
process.on("SIGINT", () => stop("SIGINT"));

const exits = children.map((child) => new Promise<number>((resolve) => {
  child.once("error", (error) => {
    console.error(error);
    if (!stopping) stop("SIGTERM");
    resolve(1);
  });
  child.once("exit", (code, signal) => {
    if (!stopping) stop("SIGTERM");
    resolve(code ?? (signal === null ? 1 : 0));
  });
}));

const code = await Promise.race(exits);
await Promise.allSettled(exits);
process.exitCode = code;
