import { spawn, type ChildProcess } from "node:child_process";
import { mkdir, symlink } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { config as loadDotenv } from "dotenv";

import { runMigrations } from "../mysql/migrations.js";
import { brainConfigFromEnv } from "./config.js";

const appRoot = fileURLToPath(new URL("../../", import.meta.url));
loadDotenv();
const config = brainConfigFromEnv();
await runMigrations(config.mysql);
await mkdir("/tmp/dsh-home", { recursive: true });
await symlink("/app/node_modules", "/tmp/dsh-home/node_modules", "dir").catch((error: unknown) => {
  if (!(error instanceof Error && "code" in error && error.code === "EEXIST")) throw error;
});
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
