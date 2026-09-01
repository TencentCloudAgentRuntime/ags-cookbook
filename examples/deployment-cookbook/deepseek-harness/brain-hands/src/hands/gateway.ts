import type { CommandResult } from "e2b";

import type { TurnClaim } from "../runtime/mysql-state.js";

const WORKSPACE_ROOT = "/workspace";
const MAX_FILE_BYTES = 1024 * 1024;
const MAX_SCRIPT_BYTES = 64 * 1024;
const MAX_COMMAND_TIMEOUT_MS = 120_000;

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
    read(path: string, options: { readonly format: "bytes"; readonly user: string }): Promise<Uint8Array>;
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
  public constructor(
    private readonly factory: HandsConnectionFactory,
    private readonly fence: TurnFenceChecker,
  ) {}

  public allocateAffinity(signal?: AbortSignal): Promise<string> {
    return this.factory.allocateAffinity(signal);
  }

  public async health(target: HandsTarget, signal?: AbortSignal): Promise<boolean> {
    this.assertTarget(target);
    const response = await this.factory.health(target.affinityId, signal);
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
    const result = await sandbox.commands.run(script, { cwd, timeoutMs, user: "root" });
    return { exitCode: result.exitCode, stdout: result.stdout, stderr: result.stderr };
  }

  public async read(target: HandsTarget, path: string): Promise<string> {
    assertWorkspacePath(path);
    const sandbox = await this.sandbox(target);
    const bytes = await sandbox.files.read(path, { format: "bytes", user: "root" });
    if (bytes.byteLength > MAX_FILE_BYTES) throw new Error(`read exceeds ${MAX_FILE_BYTES} bytes`);
    return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  }

  public async write(target: HandsTarget, path: string, contents: string): Promise<void> {
    assertWorkspacePath(path);
    assertByteLimit(contents, MAX_FILE_BYTES, "write");
    const sandbox = await this.sandbox(target);
    await sandbox.files.write(path, contents, { user: "root" });
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
    const sandbox = await this.factory.connect(target.affinityId);
    await sandbox.commands.run(generationGuard(target.claim.generation), {
      cwd: WORKSPACE_ROOT,
      timeoutMs: 5_000,
      user: "root",
    });
    return sandbox;
  }

  private assertTarget(target: HandsTarget): void {
    if (target.deploymentId !== this.factory.deploymentId) {
      throw new Error("Hands target does not match the configured Deployment");
    }
    if (target.claim.sessionId.length === 0) throw new Error("Hands target session is missing");
  }
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
