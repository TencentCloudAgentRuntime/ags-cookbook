import path from "node:path";

export const DSH_WORKSPACE_ROOT = "/tmp/dsh-workspaces";

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/u;

export function workspacePath(workspaceId: string): string {
  if (!UUID_PATTERN.test(workspaceId)) throw new Error("workspace id must be a UUID");
  return path.join(DSH_WORKSPACE_ROOT, workspaceId);
}

export function workspaceIdFromCwd(cwd: string | undefined): string | undefined {
  if (cwd === undefined || path.dirname(cwd) !== DSH_WORKSPACE_ROOT) return undefined;
  const workspaceId = path.basename(cwd);
  return UUID_PATTERN.test(workspaceId) ? workspaceId : undefined;
}
