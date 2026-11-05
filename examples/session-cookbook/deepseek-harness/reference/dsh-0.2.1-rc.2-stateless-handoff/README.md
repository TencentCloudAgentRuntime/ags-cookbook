# Stateless session handoff reference (DSH 0.2.1-rc.2)

[中文](./README_zh.md)

This directory is a **reference implementation** of the persistence plugin in [dsh-0.2.1-rc.2](../../dsh-0.2.1-rc.2/README.md) for stateless session handoff across replicas. "Stateless" here means a replica does not stay bound to a conversation and another replica can take it over at a turn boundary; a live session is still required while a turn runs. It is not a new DSH version and not a standalone deployable example; the base example's plugin, image, and documentation stay unchanged.

This reference covers the plugin-side half of stateless handoff: detect an EventId conflict, stop retrying, release the write handle, and provide pre-turn and teardown helpers. It **does not introduce a lease** and **cannot rebuild the live session by itself**.

## 1. Relationship to the base example

| | Base example `dsh-0.2.1-rc.2` | This reference |
| --- | --- | --- |
| Normal write path | Same | Same |
| EventId conflict | The batch stays buffered and the next flush retries; the replica keeps failing and needs a restart | Marks the write handle conflicted, drops the uncommitted batch, rejects later writes, and emits `session-persistence/conflict` |
| Recovery | Restart the replica | The owner destroys and rebuilds the generation; this reference only detects and stops |
| Deployment | Buildable image | Reference plugin; integrate it into your DSH image and session lifecycle |

The delta is kept in [stateless-handoff.patch](./stateless-handoff.patch) for review against the base plugin. It uses the base plugin's paths; apply it from the repository root:

```bash
git apply examples/session-cookbook/deepseek-harness/reference/dsh-0.2.1-rc.2-stateless-handoff/stateless-handoff.patch
```

## 2. Plugin behavior

On `ResourceInUse.EventIdDuplicate`:

1. Throws `SessionPersistenceConflictError` with `sessionId`, `eventId`, and the original cause.
2. The write handle becomes permanently conflicted:
   - later `append` / `flush` calls reject with the same error;
   - `enqueueLive` stops buffering and reports through its failure callback;
   - the uncommitted local batch is dropped, not retried or renumbered.
3. Foreground conflicts reach the caller as the typed error. Background conflicts log at error level and emit:

   ```text
   session-persistence/conflict
   ```

   The listener receives `(session, error)`.
4. `close()` skips the drain when conflicted and releases the in-process write claim, so teardown can finish.
5. Four helpers are added:
   - `handoffCheck(id, localEventCount)` for the pre-turn state machine;
   - `eventCount(id)` for the stored event count;
   - `writerCursor(id)` for this replica's durable write cursor;
   - `releaseWriter(id)` to wait for the write handle to close before rebuilding the generation.

## 3. What the owner must do

The plugin cannot rebuild the live session or cancel a running turn. The integration must:

1. Listen for `session-persistence/conflict`, or catch `SessionPersistenceConflictError`.
2. Stop the generation from accepting input and cancel or await the current execution.
3. Destroy the current agent / generation.
4. `await releaseWriter(sessionId)` so the old writer is closed and the in-process claim is gone.
5. Reopen the session through DSH's resume path (expected to be `ctx.agents.resume({ resumeSessionId })`; verify on 0.2.1-rc.2).
6. Decide by execution state:
   - the turn had not started: bounded retry after rebuild;
   - the turn had started: report an uncertain result and do not auto-rerun;
   - external tool side effects cannot be rolled back by the session log; tools may need their own idempotency keys.

> `ctx.agents.resume()`, `handle.dispose()`, and the session-controller generation semantics come from the DSH repository documentation. Those packages are not in this repository. **Verify them on DSH 0.2.1-rc.2**; do not infer them from the plugin.

## 4. Controller (`handoff-controller.js`)

The plugin provides primitives. `handoff-controller.js` turns them into an explicit state machine for whoever owns the live session.

The integration provides a host:

| Host method | Responsibility |
| --- | --- |
| `localEventCount(sessionId)` | Durable events this replica has written; use `persistence.writerCursor(sessionId)` |
| `invalidate(sessionId)` | Stop input, cancel or await the turn, dispose the agent, and await teardown |
| `resume(sessionId)` | Reopen through DSH's resume path (expected to be `ctx.agents.resume({ resumeSessionId })`) |
| `flush(sessionId)` (optional) | Flush first when the check reports `local-ahead` |
| `liveAgentStatus(sessionId)` (optional) | `ctx.agents.get(id)?.status`: `'idle' \| 'running' \| undefined` |
| `liveTurnState(sessionId)` (optional) | `'none' \| 'open' \| 'closed'` derived from `sessionProjections.stateOf(session, 'turnBoundary')` |

The last two are optional liveness ports. Without them the controller stays conservative: a `fresh` check with an open turn always returns busy. `attachDshHandoff` derives both from `ctx.agents` and `ctx.sessionProjections`, so callers do not hand-write them.

`dsh-handoff.js` collapses the wiring into one generation port:

```js
const { controller, dispose } = attachDshHandoff(ctx, {
  generation: {
    invalidate: id => ctx.sessionController.invalidateGeneration(id),
    resume: id => ctx.sessionController.resumeGeneration(id),
    flush: id => flushSession(id), // optional
  },
})
```

- `localEventCount` is wired to `persistence.writerCursor`;
- liveness comes from `ctx.agents` / `ctx.sessionProjections`;
- `generation` is the only version-specific port;
- `attachDshHandoff` also subscribes to `session-persistence/conflict` and registers the `sessionHandoff` service.

Usage:

```js
const controller = createHandoffController({ persistence, host, logger })
const decision = await controller.preflight(sessionId)
// run | rebuilt | create | blocked; an open turn throws HandoffBusyError
```

`preflight` decisions:

| Check result | Live agent | Turn boundary | Action |
| --- | --- | --- | --- |
| `not-found` | — | — | `create` |
| `local-ahead` | — | — | Flush and recheck when the host supports it, otherwise `blocked` |
| `stale` | `running` | — | Throw `HandoffBusyError` (`local-turn-running`); never rebuild under a running turn |
| `stale` | idle / none | `open` | Throw `HandoffBusyError`; never append closers automatically |
| `stale` | idle / none | `closed` | `invalidate` → `releaseWriter` → `resume`, then `rebuilt` |
| `fresh` | `running` | `open` | `run`: this replica is driving the turn; the followup queues normally |
| `fresh` | idle / none | `open` | Throw `HandoffBusyError`: an open turn with no driver is crash residue or a just-resumed turn |
| `fresh` | any | `closed` / `none` | `run` |

`recover(sessionId)` handles a conflict: it only rebuilds the generation and never reruns the turn. Concurrent calls share one rebuild; a failed `invalidate` or `releaseWriter` stops before `resume`. A `preflight` check also waits for an in-flight rebuild, so it never reads the writer cursor while the generation is half torn down.

Cordis integration can subscribe directly:

```js
const dispose = attachConflictRecovery(ctx, controller)
```

It listens for `session-persistence/conflict`, calls `recover(sessionId, 'conflict')`, and returns the disposer.

Integration points:

1. At deployment, load [`plugin/dsh-handoff-plugin.js`](./plugin/dsh-handoff-plugin.js) (Cordis name `@tencentcloud/ags-dsh-session-persistence/handoff`). It calls `attachDshHandoff`, creates the controller, registers the `sessionHandoff` service, and subscribes to conflicts.
2. The patch calls `sessionHandoff.beforePrompt(sessionId)` inside `SessionCommandController.prompt`, after `resolveAgent` and before admission; on `rebuilt` it resolves the Agent again. `steer` bypasses the check.
3. On a conflict: let `attachConflictRecovery` call `recover`; do not keep writing this turn.
4. After a turn: ensure `session/flush` succeeded so the next `preflight` sees the durable cursor.

`invalidate`, `resume`, and the liveness ports are all built on public 0.2.1-rc.2 APIs; the controller still covers the state machine, ordering, and failure paths with a fake host. See [dockerfiles/README.md](./dockerfiles/README.md) for the real build and A→B→A verification.

## 5. Pre-turn check

The integration can call `handoffCheck(id, localEventCount)` before each turn:

| State | Meaning | Suggested action |
| --- | --- | --- |
| `fresh` | Stored and locally persisted counts match | Run normally |
| `stale` | Storage is ahead; another writer advanced it | Rebuild the generation first |
| `local-ahead` | Local is ahead; events may be unflushed | Flush or rebuild; do not run |
| `not-found` | The Session does not exist yet | Treat it as a new Session |

`handoffCheck` also returns the tri-state `turnState`, the derived `turnClosed`, and `lastEvent`:

| `turnState` | Meaning |
| --- | --- |
| `none` | No event stored yet; the Session never started a turn |
| `closed` | The last turn boundary in the scanned tail is `turn/end` |
| `open` | The last boundary is `turn/start`, or a non-empty window has no boundary (a turn longer than the window) |

`turnState` is only a tail read of the persisted log and **is not a liveness signal**: `open` cannot distinguish a remote turn still running from crash residue. Liveness comes from the live Agent's `status` (see the decision table in section 4). Without live state the controller stays conservative and returns busy for `fresh + open`.

Limits:

- This is not a lock. A writer can still append between the check and the write; the write-time EventId check is the last line of defense.
- `turnState` is not a liveness signal. It cannot tell a crashed execution from one still running on another replica, and it does not replace DSH's own interrupted-turn repair.
- "The previous turn is closed" also requires `turn/end` to be durably flushed; a written but unflushed `turn/end` does not count.
- Cost: `fresh` / `local-ahead` issue one `DescribeEvents` and read the local write handle's tail for `turnState`; only `stale` needs a second read for the cloud tail.

## 6. Phase-one scope

**Supported**

- Turn-boundary handoff: A completes and flushes a turn, then B takes the next one.
- Conflict detection and stop-loss when an old generation is still alive but the cloud was already written by someone else.
- Rebuild the generation after a conflict and continue.

**Not supported**

- Overlapping execution of one conversation.
- Automatic rerun of a conflicted turn.
- Automatic continuation of an in-flight turn after a crash.
- Migration of workspace files, processes, or model connections.
- Telling from the log whether another replica is still running. The log cannot distinguish a crash from a live turn, so never close an open turn automatically.

## 7. DSH capabilities to verify

Confirmed on the `dsh-v0.2.1-rc.2` source:

1. `ctx.agents.resume()` / `ctx.agents.create()` return `AgentHandle`, and `handle.dispose()` exists; it is the only capability that disposes a live generation.
2. `Agent` exposes `status: 'idle' | 'running'` (mirrored on `agent/status`); this is the liveness signal for "is this replica still driving the turn".
3. `ctx.sessionProjections.stateOf(session, 'turnBoundary')` exposes `openTurnStartSeq` / `lastTurn`, which distinguishes `none` / `open` / `closed` without ambiguity.
4. 0.2.1-rc.2 has no automatic interrupted-turn repair, and `turn()` does not check for an existing open turn before appending `turn/start`. The owner must handle an open turn explicitly.
5. `session-controller` has no public retain/release generation semantics; the generation lives and dies with the handle in `ctx.agents`, so this reference invalidates it by keeping and disposing that handle.

Still to verify against a real build:

- whether `handle.dispose()` waits for the write handle to close (this reference calls `persistence.releaseWriter` afterwards as an explicit barrier);
- whether a successful `session/flush` is guaranteed after `turn/end`;
- whether inbox / queued prompts survive a resume; `agent/*` is live control state.

This directory includes a source patch for `dsh-v0.2.1-rc.2` (commit `687f282e8625c6b8d11ff58211a90524be2e4317`): [0001-stateless-handoff.patch](./dockerfiles/0001-stateless-handoff.patch). It follows the deployment cookbook all-in-one approach: clone the pinned tag, verify the commit, `git apply`, then build. The patch:

- keeps the `AgentHandle` returned by `ctx.agents.create/resume`, stored per Session;
- adds idempotent `invalidateGeneration(sessionId)` / `resumeGeneration(sessionId)`;
- calls `sessionHandoff.beforePrompt(sessionId)` in `SessionCommandController.prompt`, after `resolveAgent` and before admission; on `rebuilt` it resolves the Agent again; `steer` bypasses it.

The patch passes `git apply --check`, and a source-build [Dockerfile](./dockerfiles/Dockerfile) is provided, but DSH has not been built or run in this repository. It targets a pinned tag; on upgrade, clone the new tag, run `git apply --check`, and re-check the insertion points. Do not assume it applies to the latest version.

## 8. Tests

```bash
make setup
make check
```

Coverage:

- a conflict makes the handle permanent and rejects later writes;
- a background drain conflict drops the uncommitted batch instead of retrying;
- `releaseWriter` closes the handle and releases the in-process claim;
- `writerCursor` reports this replica's durable write cursor;
- `handoffCheck` reports `fresh` / `stale` / `local-ahead` / `not-found` and the tri-state `turnState`;
- an empty log reports `turnState: 'none'` and is not mistaken for an open turn;
- `handoffCheck` cost: one `DescribeEvents` for `fresh` / `local-ahead`, two for `stale`;
- a second replica takes over at a turn boundary and the stale writer stops on its next append;
- controller decisions: every branch, including `fresh + open + running` (allow), `fresh + open + idle` (busy), and `stale + running` (no rebuild); plus recover ordering, concurrent rebuild coalescing, no-resume on `invalidate` / `releaseWriter` failure, and conflict-event routing;
- the DSH wiring: generation port validation, `writerCursor`, optional `flush`, liveness ports, turn state derived from `ctx.agents` / `ctx.sessionProjections`, and conflict-event wiring;
- the integration plugin: `apply` registers `sessionHandoff` and the conflict listener, and a conflict runs `invalidateGeneration` → `resumeGeneration`;
- end to end: a stale replica is rebuilt by the controller and continues after resume;
- end to end: a conflicted handle is recovered by the controller and continues after resume;
- transient errors still keep the batch for retry, as in the base plugin.

## 9. Files

| File | Purpose |
| --- | --- |
| [`plugin/index.js`](./plugin/index.js) | Reference plugin |
| [`plugin/constants.js`](./plugin/constants.js) | Shared event name |
| [`plugin/handoff-controller.js`](./plugin/handoff-controller.js) | Handoff state machine |
| [`plugin/dsh-handoff.js`](./plugin/dsh-handoff.js) | DSH generation port, liveness ports, and Cordis wiring |
| [`plugin/dsh-handoff-plugin.js`](./plugin/dsh-handoff-plugin.js) | Runtime integration plugin (`.../handoff` export) |
| [`plugin/index.test.js`](./plugin/index.test.js) | Plugin and end-to-end tests |
| [`plugin/handoff-controller.test.js`](./plugin/handoff-controller.test.js) | Controller tests |
| [`plugin/dsh-handoff.test.js`](./plugin/dsh-handoff.test.js) | Port, liveness, and integration-plugin tests |
| [`plugin/package.json`](./plugin/package.json) | Dependencies and the `./handoff` subpath export |
| [`stateless-handoff.patch`](./stateless-handoff.patch) | Delta against the base plugin |
| [`dockerfiles/0001-stateless-handoff.patch`](./dockerfiles/0001-stateless-handoff.patch) | DSH 0.2.1-rc.2 source patch |
| [`dockerfiles/Dockerfile`](./dockerfiles/Dockerfile) | Source build of the patched DSH image |
| [`dockerfiles/agent-runtime-session.cordis.yml`](./dockerfiles/agent-runtime-session.cordis.yml) | Loads both the persistence and handoff plugins |
| [`dockerfiles/entrypoint.sh`](./dockerfiles/entrypoint.sh) | Same entrypoint as the base example |
| [`.dockerignore`](./.dockerignore) | Keeps the `plugin/node_modules` link out of the build context |
| [`dockerfiles/README.md`](./dockerfiles/README.md) | Source acquisition, build, and verification |
| [`Makefile`](./Makefile) | `setup` / `check` |
