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

`dsh-handoff.js` collapses the wiring into one generation port:

```js
const { controller, dispose } = attachDshHandoff(ctx, {
  generation: {
    invalidate: id => stopAndDisposeGeneration(id), // implement for DSH 0.2.1-rc.2
    resume: id => ctx.agents.resume({ resumeSessionId: id }),
    flush: id => flushSession(id), // optional
  },
})
```

- `localEventCount` is wired to `persistence.writerCursor`;
- `generation` is the only version-specific port;
- `attachDshHandoff` also subscribes to `session-persistence/conflict`.

Usage:

```js
const controller = createHandoffController({ persistence, host, logger })
const decision = await controller.preflight(sessionId)
// run | rebuilt | create | blocked; an open turn throws HandoffBusyError
```

`preflight` decisions:

| Check result | Action |
| --- | --- |
| `fresh` + `turnClosed` | `run` |
| `stale` + `turnClosed` | `invalidate` → `releaseWriter` → `resume`, then return `rebuilt` |
| any `turnClosed: false` | Throw `HandoffBusyError`; never append closers automatically |
| `local-ahead` | Flush and recheck when the host supports it, otherwise return `blocked` |
| `not-found` | `create` |

`recover(sessionId)` handles a conflict: it only rebuilds the generation and never reruns the turn. Concurrent calls share one rebuild; a failed `invalidate` or `releaseWriter` stops before `resume`.

Cordis integration can subscribe directly:

```js
const dispose = attachConflictRecovery(ctx, controller)
```

It listens for `session-persistence/conflict`, calls `recover(sessionId, 'conflict')`, and returns the disposer.

Integration points:

1. After a Session is created or resumed: call `attachDshHandoff`; it creates the controller and subscribes to conflicts.
2. Before each turn: `await controller.preflight(sessionId)`; continue only for `run` / `rebuilt` / `create`.
3. On a conflict: let `attachConflictRecovery` call `recover`; do not keep writing this turn.
4. After a turn: ensure `session/flush` succeeded so the next `preflight` sees the durable cursor.

`invalidate` and `resume` still need verification on DSH 0.2.1-rc.2; the controller itself covers the state machine, ordering, and failure paths with a fake host.

## 5. Pre-turn check

The integration can call `handoffCheck(id, localEventCount)` before each turn:

| State | Meaning | Suggested action |
| --- | --- | --- |
| `fresh` | Stored and locally persisted counts match | Run normally |
| `stale` | Storage is ahead; another writer advanced it | Rebuild the generation first |
| `local-ahead` | Local is ahead; events may be unflushed | Flush or rebuild; do not run |
| `not-found` | The Session does not exist yet | Treat it as a new Session |

`handoffCheck` also returns `turnClosed` and `lastEvent`. `turnClosed` looks only at the last `turn/start` / `turn/end` in the scanned tail:

- `true`: a `turn/end` was seen; apply the state above.
- `false`: return an explicit busy / interrupted status, do not append `interruptedTurnClosers` automatically, and use an explicit recovery policy.

Limits:

- This is not a lock. A writer can still append between the check and the write; the write-time EventId check is the last line of defense.
- `turnClosed` is not a liveness signal. It cannot tell a crashed execution from one still running on another replica, and it does not replace DSH's own interrupted-turn repair.
- "The previous turn is closed" also requires `turn/end` to be durably flushed; a written but unflushed `turn/end` does not count.
- Cost: `fresh` / `local-ahead` issue one `DescribeEvents` and read the local write handle's tail for `turnClosed`; only `stale` needs a second read for the cloud tail.

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

1. `ctx.agents.resume()` and `handle.dispose()` exist on 0.2.1-rc.2.
2. Session-controller generation retain/release semantics; whether `release` alone lets the next `retain` get a new generation, or an explicit invalidate is required.
3. Whether `session/disposed` dispatch awaits the listener's returned Promise. This reference returns `close()`'s Promise, but the dispatcher behavior needs verification.
4. Whether a successful `session/flush` is guaranteed after `turn/end`.
5. Whether inbox / queued prompts survive a resume; `agent/*` is live control state.

This directory includes a source patch for `dsh-v0.2.1-rc.2` (commit `687f282e8625c6b8d11ff58211a90524be2e4317`): [0001-stateless-handoff.patch](./dockerfiles/0001-stateless-handoff.patch). It follows the deployment cookbook all-in-one approach: clone the pinned tag, verify the commit, `git apply`, then build. The patch:

- keeps the `AgentHandle` returned by `ctx.agents.create/resume`;
- adds `invalidateGeneration(sessionId)` / `resumeGeneration(sessionId)`;
- calls `sessionHandoff.beforePrompt(sessionId)` in the non-`steer` path of `SessionController.prompt`.

The patch has only passed `git apply --check`; DSH has not been built or run in this repository. See [dockerfiles/README.md](./dockerfiles/README.md) for the full build, wiring, and verification steps. It targets a pinned tag; on upgrade, clone the new tag, run `git apply --check`, and re-check the three insertion points. Do not assume it applies to the latest version.

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
- `handoffCheck` reports `fresh` / `stale` / `local-ahead` / `not-found` and `turnClosed`;
- `handoffCheck` cost: one `DescribeEvents` for `fresh` / `local-ahead`, two for `stale`;
- a second replica takes over at a turn boundary and the stale writer stops on its next append;
- the controller's preflight decisions, recover ordering, concurrent rebuild coalescing, no-resume on `invalidate` / `releaseWriter` failure, and conflict-event routing;
- the DSH generation port: validation, `writerCursor` wiring, optional `flush` forwarding, and conflict-event wiring;
- end to end: a stale replica is rebuilt by the controller and continues after resume;
- end to end: a conflicted handle is recovered by the controller and continues after resume;
- transient errors still keep the batch for retry, as in the base plugin.

## 9. Files

| File | Purpose |
| --- | --- |
| [`plugin/index.js`](./plugin/index.js) | Reference plugin |
| [`plugin/constants.js`](./plugin/constants.js) | Shared event name |
| [`plugin/handoff-controller.js`](./plugin/handoff-controller.js) | Handoff state machine |
| [`plugin/dsh-handoff.js`](./plugin/dsh-handoff.js) | DSH generation port and Cordis wiring |
| [`plugin/index.test.js`](./plugin/index.test.js) | Plugin and end-to-end tests |
| [`plugin/handoff-controller.test.js`](./plugin/handoff-controller.test.js) | Controller tests |
| [`plugin/dsh-handoff.test.js`](./plugin/dsh-handoff.test.js) | Port and wiring tests |
| [`plugin/package.json`](./plugin/package.json) | Dependencies, same as the base example |
| [`stateless-handoff.patch`](./stateless-handoff.patch) | Delta against the base plugin |
| [`dockerfiles/0001-stateless-handoff.patch`](./dockerfiles/0001-stateless-handoff.patch) | DSH 0.2.1-rc.2 source patch |
| [`dockerfiles/README.md`](./dockerfiles/README.md) | Source acquisition, build, and plugin wiring |
| [`Makefile`](./Makefile) | `setup` / `check` |
