# DSH source patch and image build (dsh-v0.2.1-rc.2)

## 1. Why a source patch is required

The persistence plugin can detect conflicts and stop writing, but it cannot see the turn boundary and does not hold the capability that disposes a live generation:

- `session/event` is a post-commit notification; a listener failure does not stop the loop;
- `AgentHandle.dispose()` belongs to the owner of `ctx.agents.create/resume`;
- `session-controller` has no public per-session generation-invalidate entry point.

The patch adds the three missing pieces to `session-controller`.

## 2. Patch contents

### 2.1 Keep the `AgentHandle`

`ApiSessionAgentController` used to take only `.agent` from `ctx.agents.create/resume` and discard the handle. The patch stores it per Session on all three create/resume paths.

### 2.2 Invalidate and rebuild a generation

```ts
async invalidateGeneration(sessionId): Promise<void> {
  // wait for an in-flight resolve/claim first (it stores the handle)
  // idempotent: no live handle satisfies the postcondition
  // deletes handles / resumes / claims, then awaits handle.dispose()
}

async resumeGeneration(sessionId): Promise<Agent> {
  await this.invalidateGeneration(sessionId)
  // resolveAgent() -> ctx.agents.resume() re-reads durable state
}
```

`SessionController` exposes delegating methods with the same names for the integration plugin.

### 2.3 Pre-prompt hook

The call site is `SessionCommandController.prompt`, **after `resolveAgent` and before admission**:

```ts
let agent = await this.resolveAgent(request.sessionId)
if (hasPromptRequest(agent, request.requestId)) return { accepted: true }
if (request.mode !== 'steer') {
  const handoff = this.ctx.get('sessionHandoff')
  if (handoff !== undefined) {
    const decision = await handoff.beforePrompt(request.sessionId)
    if (decision.action === 'rebuilt') agent = await this.resolveAgent(request.sessionId)
  }
}
```

Why not earlier in `SessionController.prompt`:

- on the first prompt in a replica there is no writer handle yet, so `writerCursor()` is `undefined` and the check would fail;
- after `resolveAgent` the writer always exists and `invalidate` always has a real generation to dispose;
- a non-`RemoteError` from the hook is mapped to `session/agent-busy`.

`steer` must be skipped: it is inserted into the running turn, and a rebuild would tear that turn down.

The patch also declares `SessionHandoffService` and `SessionHandoffDecision`. When no such service is installed, behaviour is unchanged.

## 3. Source and version

Same approach as `deployment-cookbook/deepseek-harness/all-in-one/dockerfiles/Dockerfile`: clone a pinned tag from GitHub and verify the commit.

| Item | Value |
| --- | --- |
| tag | `dsh-v0.2.1-rc.2` |
| commit | `687f282e8625c6b8d11ff58211a90524be2e4317` |
| pnpm | `11.28.5` (the DSH root `package.json` `packageManager`) |

## 4. Build the image

The build context is this reference directory, not the repository root:

```bash
cd examples/session-cookbook/deepseek-harness/reference/dsh-0.2.1-rc.2-stateless-handoff
docker build -t ags-dsh-stateless-handoff -f dockerfiles/Dockerfile .
```

The image has two stages:

1. **build**: clone the tag, verify the commit, `git apply` the patch, `pnpm install --frozen-lockfile`;
2. run the session-controller `agent` / `commands-queue-attachment` / `controller` tests;
3. `pnpm run build:official`, then `release:pack` for the vendor and dsh tarballs;
4. **runtime**: install the tarballs and this plugin, link the `@deepseek-ai` peers to DSH's own copy, then add the Cordis config and entrypoint.

The first build compiles all of DSH and takes a while. If a release hoists the `@deepseek-ai` packages elsewhere, override `DSH_MODULES`:

```bash
docker build --build-arg DSH_MODULES=/usr/local/lib/node_modules/@deepseek-ai ...
```

## 5. Runtime wiring

[`agent-runtime-session.cordis.yml`](./agent-runtime-session.cordis.yml) adds one plugin to the base example:

```yaml
- id: dsh-stateless-handoff
  name: '@tencentcloud/ags-dsh-session-persistence/handoff'
```

It must load after `session-persistence-agent-runtime`. The integration plugin ([`../plugin/dsh-handoff-plugin.js`](../plugin/dsh-handoff-plugin.js)):

- calls `attachDshHandoff` and binds `localEventCount` to `writerCursor`;
- supplies liveness from `ctx.agents.get(id)?.status` and `ctx.sessionProjections.stateOf(session, 'turnBoundary')`;
- registers the `sessionHandoff` service the patched `prompt` calls;
- subscribes to `session-persistence/conflict` and runs `invalidateGeneration` → `releaseWriter` → `resumeGeneration`.

## 6. Verification

The build already runs three session-controller test files. After the image is built, verify at least these three flows by hand:

1. **A→B→A, no conflict**
   - A finishes a turn and flushes;
   - B finishes a turn on the same Session;
   - the next turn returns to A: `preflight` should report `stale` + `closed` and rebuild before any model call.
2. **Conflict recovery**
   - let A keep writing on a stale generation and trigger `ResourceInUse.EventIdDuplicate`;
   - the plugin should mark the handle conflicted, stop retrying, and emit `session-persistence/conflict`;
   - the integration plugin should rebuild and later writes should succeed.
3. **Open turn**
   - produce a log with no `turn/end`;
   - a new request must return busy instead of closing it automatically;
   - if a live Agent is driving that turn (`status === 'running'`), a followup on the same replica must still queue normally.

## 7. Compatibility

- The patch targets `dsh-v0.2.1-rc.2` / `687f282e...`; do not assume it applies to the latest version.
- On upgrade, clone the new tag and run `git apply --check` first. Conflicts usually appear in four places:
  - `ApiSessionAgentController` create/resume and handle storage;
  - the `SessionCommandController.prompt` admission path;
  - the `SessionController` delegating methods;
  - the Cordis `Context` service declarations.
- If upstream later provides a native pre-prompt / generation-invalidate hook, delete the patch and register the service directly.
- If the AGS deployment patch (`0001-support-ags-deployment-web.patch`) is also needed, apply it before this patch and re-run the tests.

## 8. Verification status

The patch passes `git apply --check`, and the Dockerfile follows the deployment cookbook build path; **the image has not been built and DSH has not been run from this repository**. Until the three flows above pass, this can only claim compile-time and unit-test coverage, not production readiness.
