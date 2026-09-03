import type { CommandResult } from "e2b";
import { randomUUID } from "node:crypto";

import type { TurnClaim } from "../runtime/mysql-state.js";

const WORKSPACE_ROOT = "/workspace";
const MAX_FILE_BYTES = 1024 * 1024;
const MAX_SCRIPT_BYTES = 64 * 1024;
const MAX_COMMAND_TIMEOUT_MS = 120_000;
const MAX_COMMAND_OUTPUT_BYTES = 1024 * 1024;

export interface HandsTarget {
  readonly deploymentId: string;
  readonly affinityId: string;
  readonly claim: TurnClaim;
}

export interface TurnFenceChecker {
  assertTurn(claim: TurnClaim): Promise<void>;
}

export interface HandsBashResult {
  readonly exitCode: number;
  readonly stdout: string;
  readonly stderr: string;
}

interface HandsSandbox {
  readonly files: {
    read(path: string, options: { readonly format: "stream"; readonly user: string }): Promise<ReadableStream<Uint8Array>>;
    write(path: string, contents: string, options: { readonly user: string }): Promise<unknown>;
  };
  readonly commands: {
    run(command: string, options?: {
      readonly cwd?: string;
      readonly timeoutMs?: number;
      readonly user?: string;
    }): Promise<CommandResult>;
  };
}

export interface HandsConnectionFactory {
  readonly deploymentId: string;
  allocateAffinity(signal?: AbortSignal): Promise<string>;
  health(affinityId: string, signal?: AbortSignal): Promise<Response>;
  connect(affinityId: string): Promise<HandsSandbox>;
}

/** Bounded bash/read/write/edit surface exposed by Brain to DSH. */
export class HandsGateway {
  private readonly factories: ReadonlyMap<string, HandsConnectionFactory>;

  public constructor(
    factory: HandsConnectionFactory | readonly HandsConnectionFactory[],
    private readonly fence: TurnFenceChecker,
  ) {
    const factories = Array.isArray(factory) ? factory : [factory];
    const byDeployment = new Map(factories.map((candidate) => [candidate.deploymentId, candidate]));
    if (byDeployment.size !== factories.length || byDeployment.size === 0) {
      throw new Error("Hands deployments must be non-empty and unique");
    }
    this.factories = byDeployment;
  }

  public allocateAffinity(deploymentId: string, signal?: AbortSignal): Promise<string> {
    return this.factoryFor(deploymentId).allocateAffinity(signal);
  }

  public async health(target: HandsTarget, signal?: AbortSignal): Promise<boolean> {
    this.assertTarget(target);
    await this.fence.assertTurn(target.claim);
    const response = await this.factoryFor(target.deploymentId).health(target.affinityId, signal);
    return response.ok;
  }

  public async bash(
    target: HandsTarget,
    script: string,
    cwd = WORKSPACE_ROOT,
    timeoutMs = 30_000,
  ): Promise<HandsBashResult> {
    assertWorkspacePath(cwd);
    assertByteLimit(script, MAX_SCRIPT_BYTES, "bash script");
    if (!Number.isSafeInteger(timeoutMs) || timeoutMs < 1 || timeoutMs > MAX_COMMAND_TIMEOUT_MS) {
      throw new Error(`timeoutMs must be between 1 and ${MAX_COMMAND_TIMEOUT_MS}`);
    }
    const sandbox = await this.sandbox(target);
    const operationId = randomUUID();
    const operationRoot = `/tmp/ags-dsh-${operationId}`;
    const scriptPath = `${operationRoot}/script.sh`;
    const stdoutPath = `${operationRoot}/stdout`;
    const stderrPath = `${operationRoot}/stderr`;
    await sandbox.commands.run(`mkdir -p ${operationRoot}`, { timeoutMs: 5_000, user: "root" });
    await sandbox.files.write(scriptPath, script, { user: "root" });
    try {
      const blocks = Math.ceil(MAX_COMMAND_OUTPUT_BYTES / 512);
      const wrapper = [
        `(ulimit -f ${blocks}; bash ${scriptPath} >${stdoutPath} 2>${stderrPath})`,
        "code=$?",
        "printf '%s' \"$code\"",
      ].join("; ");
      const result = await this.runFenced(target, sandbox, wrapper, { cwd, timeoutMs });
      const exitCode = Number.parseInt(result.stdout, 10);
      if (!Number.isSafeInteger(exitCode)) throw new Error("Hands command returned an invalid exit code");
      const [stdout, stderr] = await Promise.all([
        readBounded(sandbox, stdoutPath, MAX_COMMAND_OUTPUT_BYTES, "stdout"),
        readBounded(sandbox, stderrPath, MAX_COMMAND_OUTPUT_BYTES, "stderr"),
      ]);
      return { exitCode, stdout, stderr };
    } finally {
      await sandbox.commands.run(`rm -rf -- ${operationRoot}`, { timeoutMs: 5_000, user: "root" }).catch(() => undefined);
    }
  }

  public async read(target: HandsTarget, path: string): Promise<string> {
    assertWorkspacePath(path);
    const sandbox = await this.sandbox(target);
    const operationRoot = `/tmp/ags-dsh-${randomUUID()}`;
    const snapshotPath = `${operationRoot}/read`;
    await sandbox.commands.run(`mkdir -p ${operationRoot}`, { timeoutMs: 5_000, user: "root" });
    try {
      await this.runFenced(target, sandbox, `cp -- ${shellQuote(path)} ${shellQuote(snapshotPath)}`, {
        cwd: WORKSPACE_ROOT,
        timeoutMs: 30_000,
      });
      return await readBounded(sandbox, snapshotPath, MAX_FILE_BYTES, "read");
    } finally {
      await sandbox.commands.run(`rm -rf -- ${operationRoot}`, { timeoutMs: 5_000, user: "root" }).catch(() => undefined);
    }
  }

  public async write(target: HandsTarget, path: string, contents: string): Promise<void> {
    assertWorkspacePath(path);
    assertByteLimit(contents, MAX_FILE_BYTES, "write");
    const sandbox = await this.sandbox(target);
    const operationRoot = `/tmp/ags-dsh-${randomUUID()}`;
    const stagedPath = `${operationRoot}/write`;
    await sandbox.commands.run(`mkdir -p ${operationRoot}`, { timeoutMs: 5_000, user: "root" });
    await sandbox.files.write(stagedPath, contents, { user: "root" });
    try {
      await this.runFenced(target, sandbox, `cp -- ${shellQuote(stagedPath)} ${shellQuote(path)}`, {
        cwd: WORKSPACE_ROOT,
        timeoutMs: 30_000,
      });
    } finally {
      await sandbox.commands.run(`rm -rf -- ${operationRoot}`, { timeoutMs: 5_000, user: "root" }).catch(() => undefined);
    }
  }

  public async edit(
    target: HandsTarget,
    path: string,
    oldText: string,
    newText: string,
  ): Promise<void> {
    if (oldText.length === 0) throw new Error("edit oldText cannot be empty");
    const original = await this.read(target, path);
    const first = original.indexOf(oldText);
    if (first < 0) throw new Error("edit oldText was not found");
    if (original.indexOf(oldText, first + oldText.length) >= 0) {
      throw new Error("edit oldText must match exactly once");
    }
    const updated = `${original.slice(0, first)}${newText}${original.slice(first + oldText.length)}`;
    await this.write(target, path, updated);
  }

  private async sandbox(target: HandsTarget): Promise<HandsSandbox> {
    this.assertTarget(target);
    await this.fence.assertTurn(target.claim);
    return this.factoryFor(target.deploymentId).connect(target.affinityId);
  }

  private async runFenced(
    target: HandsTarget,
    sandbox: HandsSandbox,
    command: string,
    options: { readonly cwd: string; readonly timeoutMs: number },
  ): Promise<CommandResult> {
    await this.fence.assertTurn(target.claim);
    return sandbox.commands.run(`${generationGuard(target.claim.generation)} && { ${command}; }`, {
      ...options,
      user: "root",
    });
  }

  private assertTarget(target: HandsTarget): void {
    this.factoryFor(target.deploymentId);
    if (target.claim.sessionId.length === 0) throw new Error("Hands target session is missing");
  }

  private factoryFor(deploymentId: string): HandsConnectionFactory {
    const factory = this.factories.get(deploymentId);
    if (factory === undefined) throw new Error("Hands target does not match a configured Deployment");
    return factory;
  }
}

async function readBounded(
  sandbox: HandsSandbox,
  path: string,
  maximum: number,
  label: string,
): Promise<string> {
  const stream = await sandbox.files.read(path, { format: "stream", user: "root" });
  const reader = stream.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  try {
    while (true) {
      const next = await reader.read();
      if (next.done) break;
      size += next.value.byteLength;
      if (size > maximum) {
        await reader.cancel();
        throw new Error(`${label} exceeds ${maximum} bytes`);
      }
      chunks.push(next.value);
    }
  } finally {
    reader.releaseLock();
  }
  const bytes = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
}

function generationGuard(generation: string): string {
  if (!/^[1-9][0-9]*$/u.test(generation)) throw new Error("turn generation is invalid");
  return [
    "mkdir -p /workspace/.ags",
    "exec 9>/workspace/.ags/turn-generation.lock",
    "flock -x 9",
    "current=$(cat /workspace/.ags/turn-generation 2>/dev/null || printf 0)",
    `test "$current" -le ${generation} || exit 75`,
    `if test "$current" -lt ${generation}; then printf '%s\\n' ${generation} > /workspace/.ags/turn-generation.tmp && mv /workspace/.ags/turn-generation.tmp /workspace/.ags/turn-generation; fi`,
  ].join(" && ");
}

function shellQuote(value: string): string {
  return `'${value.replaceAll("'", `'"'"'`)}'`;
}

function assertWorkspacePath(path: string): void {
  let parsed: URL;
  try {
    parsed = new URL(`file://${path}`);
  } catch {
    throw new Error("path must be an absolute /workspace path");
  }
  if (parsed.pathname !== path || (path !== WORKSPACE_ROOT && !path.startsWith(`${WORKSPACE_ROOT}/`))) {
    throw new Error("path must be an absolute /workspace path");
  }
  if (path.split("/").some((segment) => segment === "." || segment === "..")) {
    throw new Error("path must not contain traversal segments");
  }
}

function assertByteLimit(value: string, maximum: number, label: string): void {
  if (Buffer.byteLength(value, "utf8") > maximum) throw new Error(`${label} exceeds ${maximum} bytes`);
}
