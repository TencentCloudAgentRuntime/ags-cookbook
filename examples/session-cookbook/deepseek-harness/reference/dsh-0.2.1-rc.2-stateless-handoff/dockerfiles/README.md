# DSH source patch (dsh-v0.2.1-rc.2)

This patch adds the two capabilities the stateless handoff needs to DSH's session-controller:

1. **Keep `AgentHandle`**: the handle returned by `ctx.agents.create/resume` is the only capability that can tear an agent down. The original code took `.agent` and dropped the handle; the patch keeps it in `ApiSessionAgentController.handles`.
2. **Generation invalidate/rebuild**: `invalidateGeneration(sessionId)` awaits `handle.dispose()`; `resumeGeneration(sessionId)` disposes and then `resolveAgent`, which resumes from durable state.
3. **Pre-prompt hook**: `SessionController.prompt` calls `ctx.get('sessionHandoff')?.beforePrompt(sessionId)` for non-`steer` prompts. The plugin runs `controller.preflight()` there.

## Source and version

This uses the same approach as `deployment-cookbook/deepseek-harness/all-in-one/dockerfiles/Dockerfile`: clone a pinned tag from GitHub and verify the commit.

```bash
git clone --depth 1 --branch dsh-v0.2.1-rc.2 \
  https://github.com/deepseek-ai/deepseek-harness.git
git -C deepseek-harness rev-parse HEAD
# must be 687f282e8625c6b8d11ff58211a90524be2e4317
```

| Item | Value |
| --- | --- |
| Tag | `dsh-v0.2.1-rc.2` |
| Commit | `687f282e8625c6b8d11ff58211a90524be2e4317` |
| pnpm | `11.28.5` (the root `package.json` `packageManager`) |

## Apply and build

```bash
cd deepseek-harness
git apply --check /path/to/0001-stateless-handoff.patch
git apply /path/to/0001-stateless-handoff.patch

pnpm install --frozen-lockfile
pnpm run build:official
pnpm release:pack --family vendor --out dist/npm-vendor
pnpm release:pack --family dsh --out dist/npm-dsh
```

After the build, install the plugin and link the `@deepseek-ai` modules as in the [base 0.2.1-rc.2 image](../../../dsh-0.2.1-rc.2/dockerfiles/Dockerfile); the `plugin/` here can replace that example's plugin.

At minimum, run:

```bash
pnpm exec vitest run packages/api/session-controller/tests/agent.host.spec.ts
```

## Plugin wiring

The patch only provides hooks. A small Cordis integration plugin calls `attachDshHandoff`:

```js
import { attachDshHandoff } from '@tencentcloud/ags-dsh-session-persistence'

export const name = 'dsh-stateless-handoff'
export const inject = ['sessionController', 'sessionPersistence']

export function apply(ctx) {
  attachDshHandoff(ctx, {
    generation: {
      invalidate: id => ctx.sessionController.invalidateGeneration(id),
      resume: id => ctx.sessionController.resumeGeneration(id),
    },
    logger: (message, fields) => ctx.logger.info(`${message} ${JSON.stringify(fields)}`),
  })
}
```

`attachDshHandoff`:

- wires `localEventCount` to `sessionPersistence.writerCursor`;
- registers the `sessionHandoff` service that the patched `prompt` calls;
- subscribes to `session-persistence/conflict` and routes it to `controller.recover`.

## Compatibility and maintenance

- The patch targets `dsh-v0.2.1-rc.2` / `687f282e...`; do not assume it applies to the latest version.
- On upgrade, clone the new tag and run `git apply --check` first. Conflicts normally appear only in three places:
  - `ApiSessionAgentController` create/resume;
  - `SessionController.prompt` admission;
  - the Cordis `Context` service declaration.
- Keep the patch minimal: handle retention, generation invalidate/resume, and one optional `sessionHandoff` hook. Without the service installed, behavior is unchanged.
- If upstream later provides a native pre-prompt/generation-invalidate hook, drop the patch and register the service directly.
- If the AGS deployment patch (`0001-support-ags-deployment-web.patch`) is also needed, apply it first, then this patch, and rerun the tests above.

## Verification status

The patch has only passed `git apply --check` and code review; **it has not been built or run in this repository**. To call it usable, you must:

1. build the image with the commands above;
2. run the session-controller tests;
3. run A→B→A on a real DSH process: after B writes, A's next prompt makes `preflight` see `stale`, then `invalidateGeneration` + `resumeGeneration` continue from the cloud log.
