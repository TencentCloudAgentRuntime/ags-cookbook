import type { Context } from "@deepseek-ai/cordis";
import { defineTool, type ToolDefinition } from "@deepseek-ai/dsh-tools";

import { HandsGateway, type HandsTarget } from "../hands/gateway.js";

export class ActiveTurnTargets {
  private readonly targets = new Map<string, HandsTarget>();

  public bind(sessionId: string, target: HandsTarget): () => void {
    if (sessionId.length === 0) throw new Error("session ID is required");
    if (target.claim.sessionId !== sessionId) throw new Error("Hands target belongs to another session");
    if (this.targets.has(sessionId)) throw new Error(`Session ${sessionId} already has an active target`);
    this.targets.set(sessionId, target);
    return () => {
      if (this.targets.get(sessionId) === target) this.targets.delete(sessionId);
    };
  }

  public resolve(sessionId: string): HandsTarget {
    const target = this.targets.get(sessionId);
    if (target === undefined) throw new Error("Hands tool called outside an active fenced turn");
    return target;
  }
}

export interface HandsToolsConfig {
  readonly gateway: HandsGateway;
  readonly targets: ActiveTurnTargets;
}

const textOutput = {
  schema: { type: "string" as const },
  render: (_args: unknown, value: string) => [{ type: "text" as const, text: value }],
};

function targetFor(config: HandsToolsConfig, exec: { readonly agent?: { readonly session: { readonly id: string } } }): HandsTarget {
  const sessionId = exec.agent?.session.id;
  if (sessionId === undefined) throw new Error("Hands tools require an agent session");
  return config.targets.resolve(sessionId);
}

export function handsToolDefinitions(config: HandsToolsConfig): readonly ToolDefinition[] {
  return [
    defineTool({
      name: "bash",
      description: "Run a bounded shell script inside the session's persistent /workspace.",
      parameters: {
        script: { type: "string", required: true, description: "Shell script to execute." },
        cwd: { type: "string", description: "Absolute working directory under /workspace." },
        timeoutMs: { type: "integer", description: "Timeout in milliseconds, at most 120000." },
      },
      output: {
        schema: {
          type: "object",
          properties: {
            exitCode: { type: "integer", required: true },
            stdout: { type: "string", required: true },
            stderr: { type: "string", required: true },
          },
          additionalProperties: false,
        },
        render: (_args, value) => [{
          type: "text",
          text: JSON.stringify(value),
        }],
      },
      execute: async (args, exec) => config.gateway.bash(
        targetFor(config, exec),
        args.script,
        args.cwd,
        args.timeoutMs,
      ),
    }),
    defineTool({
      name: "read",
      description: "Read one UTF-8 file under /workspace (maximum 1 MiB).",
      parameters: {
        path: { type: "string", required: true, description: "Absolute file path under /workspace." },
      },
      output: textOutput,
      execute: async (args, exec) => config.gateway.read(targetFor(config, exec), args.path),
      isConcurrencySafe: () => true,
    }),
    defineTool({
      name: "write",
      description: "Write one UTF-8 file under /workspace (maximum 1 MiB).",
      parameters: {
        path: { type: "string", required: true, description: "Absolute file path under /workspace." },
        contents: { type: "string", required: true, description: "Complete replacement contents." },
      },
      output: textOutput,
      execute: async (args, exec) => {
        await config.gateway.write(targetFor(config, exec), args.path, args.contents);
        return `wrote ${Buffer.byteLength(args.contents, "utf8")} bytes to ${args.path}`;
      },
    }),
    defineTool({
      name: "edit",
      description: "Replace one exact occurrence in a UTF-8 file under /workspace.",
      parameters: {
        path: { type: "string", required: true, description: "Absolute file path under /workspace." },
        oldText: { type: "string", required: true, description: "Text that must occur exactly once." },
        newText: { type: "string", required: true, description: "Replacement text." },
      },
      output: textOutput,
      execute: async (args, exec) => {
        await config.gateway.edit(targetFor(config, exec), args.path, args.oldText, args.newText);
        return `edited ${args.path}`;
      },
    }),
  ];
}

export const handsToolsPlugin = {
  name: "ags-hands-tools",
  inject: ["tools"],
  apply(ctx: Context, config: HandsToolsConfig): Iterable<() => void> {
    return handsToolDefinitions(config).map((definition) => ctx.tools.register(definition));
  },
};
