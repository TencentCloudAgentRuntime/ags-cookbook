# DSH replica handoff (reference implementation)

[中文](./README_zh.md) · [DSH base persistence example](../../dsh-0.2.1-rc.2/README.md) · [Session examples overview](../../README.md)

## Start here

**The problem.** You run two long-lived DSH replicas (A and B). One turn of a conversation is handled by A, the next by B, the next by A again — with no restarts and no session affinity (you do not pin a conversation to one replica).

**What goes wrong without this.** In the base persistence example, A keeps the history it last saw in memory. After B writes new turns, a request that returns to A still continues from the old history, only discovers the conflict when it writes, and from then on that conversation keeps failing on A until A is restarted.

**How it is solved.** Before each new input, the replica checks whether the cloud history is newer than what it holds in memory. If so, it throws away its in-memory state for that conversation, reloads it from the cloud, and then runs.

**What you get:**

- after a completed turn, the next turn can go to any replica;
- when two replicas race for the same turn, only one runs it; the other is rejected **before** any model or tool call;
- when a replica crashes mid-turn and leaves a turn with no end record, the next request takes it over and closes it off once the timeout (default 10 minutes) has passed, with no manual step.

**What you do not get:**

- another replica taking over a turn that is half-way through;
- tools that already ran being replayed or undone;
- workspace files or running processes moving with the conversation (a Session stores conversation history only);
- a server-side lock or lease. This relies on the existing EventId uniqueness and adds no server capability.

**The cost:**

- a few extra cloud reads before each new input (see [Cost](#cost));
- the DSH framework source must be patched and the image built yourself (see [Build and run](#build-and-run)).

## Terms

These words are used throughout; this is what they mean here.

| Term | Meaning |
| --- | --- |
| generation | The whole set of in-memory objects a replica holds for one conversation (the Agent, the history projection, the write handle). "Dropping and rebuilding the generation" means "refreshing this conversation's in-memory state on this replica" |
| writer (write handle) | The channel through which this replica appends events for a conversation. Within one process there is at most one per conversation |
| claim | At the start of every turn, `turn/start` is written to the cloud first, and only after that write succeeds are the model or tools called. When two replicas write the same position, the cloud lets only one succeed |
| EventId | A unique id per event, derived from its position in the conversation. The cloud answers "same EventId, different content" with a conflict; the whole scheme builds on that |
| open turn | The cloud history has a `turn/start` without a matching `turn/end` |
| fresh / stale | The cloud history matches the replica's memory / the cloud is newer (a rebuild is needed) |

## Build and run

### Prerequisites

- Docker, with a Docker VM of 8 GB or more;
- an existing SessionSpace and cloud credentials authorized for the Session APIs;
- a working model endpoint.

Prepare `.env` (credentials, SessionSpace, model) as described in the [base example](../../dsh-0.2.1-rc.2/README.md).

### Build the image

From this directory:

```sh
docker build --build-arg DSH_GATE_CONCURRENCY=1 -f dockerfiles/Dockerfile -t dsh-session-handoff:local .
```

`DSH_GATE_CONCURRENCY=1` makes DSH's build steps run one at a time. DSH defaults to one per CPU, which runs out of memory on a Docker VM of about 8 GB and aborts with `error reading from server: EOF`. With more memory you can omit it.

The first build compiles all of DSH and takes a while. Why the image must be built from source, and the problems you may meet while building, are in [dockerfiles/README.md](./dockerfiles/README.md).

### Start two replicas

Both replicas use the **same** SessionSpace, user, and agent filter, on different ports:

```sh
docker run -d --name dsh-a --env-file .env -p 18091:3080 dsh-session-handoff:local
docker run -d --name dsh-b --env-file .env -p 18092:3080 dsh-session-handoff:local
```

Each replica prints a `dsh web: http://…/?token=…` line at startup. Note both tokens; the next step needs them.

### Verify A → B → A

Create a conversation in either replica's web page and note its Session ID. Then:

```sh
scripts/verify-handoff.sh "http://127.0.0.1:18091/?token=<token of A>" \
                          "http://127.0.0.1:18092/?token=<token of B>" <session id>
```

The script sends three turns to A, B, A, pausing between turns so you can confirm the previous one has finished. **Expected result:**

1. all three requests return `{"ok":true,"value":{"accepted":true}}`;
2. the replies in the web page are `ACK`, `ALPHA-42`, `ALPHA-42`, which shows that B and the second A both saw the earlier content;
3. on the third turn (back on A), A's container log contains:

   ```text
   [dsh-stateless-handoff] handoff rebuild started   {"reason":"preflight-stale"}
   [dsh-stateless-handoff] handoff rebuild finished  {"reason":"preflight-stale"}
   ```

   These two lines are the evidence that "A noticed its memory was behind, dropped it, and rebuilt". View them with `docker logs dsh-a`.

> The sample service has no authentication. Run it only on your machine or a trusted network; do not expose it directly to the internet.

### Run the unit tests

```sh
make setup   # install dependencies
make check   # syntax checks and unit tests
```

Unit tests do not replace the real verification above: they do not call the real cloud or model.

## How it works

### Before every new input

```text
Is this replica's Agent running a turn right now?
├─ yes → let it through (the input queues into that turn). This replica already holds the claim, so no other replica can be running one
└─ no  → read the cloud history and compare it with this replica's memory
        ├─ the cloud has no such conversation → create it as new
        ├─ match (fresh)
        │    ├─ the last turn has no end         → refuse if it was active recently; take it over as crashed if quiet past the timeout (see "Unfinished turns")
        │    └─ otherwise                         → let it through
        ├─ the cloud is newer (stale)
        │    ├─ the last turn has no end         → same: refuse if active, take over if quiet past the timeout
        │    └─ otherwise                         → drop the generation, release the writer, rebuild from the cloud, then let it through
        └─ local is ahead of the cloud            → refuse (should not happen: this replica's buffer is written out before the check)
```

"Match" compares both the number of events and their content. Equal counts do not mean equal content: two replicas may each have written a different event at the same position.

### Claiming: why two replicas cannot run the same turn

At the start of a turn, `turn/start` is written first, and **the model or tools are called only after it is written successfully**. When two replicas write the same position, the cloud accepts only one by EventId; the other gets a conflict **before** it calls a model or runs a tool, so it has no side effects.

The `turn/start` events of two replicas can be byte-for-byte identical (same timestamp, same turn number), and the cloud would treat that as a retry of the same event and accept both. To prevent this, `turn/start` also carries a per-replica `dshWriter` id so the two always differ.

This needs a change in DSH's agent loop (see "Changes to DSH" below).

### After a conflict

The replica that lost the claim:

1. stops writing and drops the local tail that was not yet in the cloud;
2. emits a `session-persistence/conflict` event;
3. drops the failed generation and releases the writer;
4. rebuilds from the cloud if the winning turn has finished; if it has not, it stays unavailable for now and **waits for a later request** to load again.

It never reruns the failed input, and never renumbers an answer generated from the old history and writes it in.

### Changes to DSH

The patch [`dockerfiles/0001-stateless-handoff.patch`](./dockerfiles/0001-stateless-handoff.patch) targets DSH `dsh-v0.2.1-rc.2` (commit `687f282e8625c6b8d11ff58211a90524be2e4317`):

| Where | Change | Why it is needed |
| --- | --- | --- |
| `session-controller` `agent.ts` | Keep the `AgentHandle` returned by create/resume; add idempotent `invalidateGeneration` / `resumeGeneration` | Only the holder of the handle can tear down a running Agent. The framework used to discard it |
| `session-controller` `commands.ts` | Before a new input is admitted, and after the Agent is resolved, call `sessionHandoff.beforePrompt`; re-resolve the Agent if it reports a rebuild; `steer` is not checked | The lag must be found before writing. It runs after the Agent is resolved because this replica's writer exists by then |
| `session-controller` `index.ts` | Declare the optional `sessionHandoff` service and `invalidateGeneration` and related methods | With no plugin installed, behavior is identical to before |
| `agent-loop` `agent.ts` | Before the first step, wait for `turn/start` to be persisted | A lost claim must surface before any model or tool call |
| `agent-loop` `tests/claim-barrier.spec.ts` | New tests: a lost claim never calls the model; `turn/start` is still appended synchronously | Guards the previous row (see below) |

About "before the first step": DSH's contract is that when `steer()` / `followup()` wakes an idle Agent, `turn/start` is appended **synchronously** in the same call, and existing tests depend on it. So the barrier sits after `turn/start` and before the first `step/start`, rather than directly after `turn/start`.

DSH's whole `agent-loop` suite (452 tests, including the 2 this patch adds) and the relevant `session-controller` tests (40) pass with the patch. Building the image runs both groups again.

### Changes to the persistence plugin

The main differences of [`plugin/index.js`](./plugin/index.js) from the base example:

- `ResourceInUse.EventIdDuplicate` becomes a `SessionPersistenceConflictError` that keeps the original cause; after a conflict the write handle stops writing permanently;
- `handoffCheck` compares the cloud and local history (count and content);
- opening a write handle refuses when the last turn has no end (see the next section);
- `turn/start` carries the `dshWriter` id;
- a conflict is reported to the owner through the `session-persistence/conflict` event.

## Unfinished turns

A cloud history with a `turn/start` but no `turn/end` has two possible causes: another replica is **still running** it, or the replica that ran it **crashed** (killed hard, OOM, scaled in). The cloud history cannot tell them apart, so this scheme looks at **whether anything is still happening**:

| Time since the turn's last event | Verdict | What happens |
| --- | --- | --- |
| Less than the timeout | May still be running | Refused with `session/agent-busy`, with `retryAfterMs` saying how long to wait |
| More than the timeout | The executor has crashed | **Taken over automatically**: this replica drops its in-memory state, reopens the conversation, DSH's own crash repair appends the "interrupted" end record, and the request then runs normally |

So a crashed turn needs no manual step: once the timeout has passed, the next request closes it off.

### The timeout

The default is **10 minutes**, set with the environment variable `OPEN_TURN_TIMEOUT_MS` (milliseconds), for example `OPEN_TURN_TIMEOUT_MS=120000` for 2 minutes. Add it to `.env`, or pass it to the container with `docker run -e OPEN_TURN_TIMEOUT_MS=120000 …`. A non-positive or non-numeric value fails at startup instead of silently using the default.

How to choose: **it must be longer than the longest quiet stretch of a healthy turn.** During a model call or a tool run a turn can go a long time without producing a new event:

- too short, and a turn that is merely slow is taken over as if it had crashed;
- too long, and after a real crash the conversation stays unavailable that long.

If your tool calls can run longer than 10 minutes, raise it accordingly.

### The risk this design accepts

The timeout is an **inference** that the executor died, not a confirmation. Therefore:

- **A misjudged turn fails.** If the old executor was only slow, its later write collides with the closing record the new owner already wrote (same position, same EventId) and the cloud rejects it, so that turn fails with a conflict. **The cloud history is not corrupted.**
- **Tools it already started are not stopped.** The takeover can keep it from writing to the log; it cannot stop what it is already doing. Its side effects may overlap with the new turn. Tools still need to be idempotent, and the timeout should not be set aggressively.
- **It assumes the replicas' clocks roughly agree.** The decision uses the write time recorded in the event, so clock skew close to the timeout causes misjudgments.

This scheme has no heartbeat. A heartbeat would let the timeout drop to tens of seconds and avoid misjudging slow tools, but it needs an additional write channel and is outside this reference.

### Why not just let DSH repair it

DSH has its own crash repair: when it reopens a conversation with an unfinished turn it appends an "interrupted" record at once. Left unrestricted, a turn that is merely slow and still running would be closed immediately. So this plugin looks at activity **when the write handle is opened**: before the timeout it refuses, and only after the timeout does it let DSH repair.

## What has been verified

These scenarios were actually run on 2026-11-06 with DSH `dsh-v0.2.1-rc.2`, an image built from this directory's Dockerfile, two resident replicas, a real cloud Session, and a real model.

| Scenario | Result |
| --- | --- |
| Image build (including build-time tests) | Succeeded. `agent-loop` 452 and `session-controller` 40 tests pass |
| A → B → A | All three turns completed; replies were `ACK`, `ALPHA-42`, `ALPHA-42`; on returning to A the log shows `handoff rebuild started/finished` |
| One replica is running a turn and the other receives a request for the same conversation | Returns `session/agent-busy` with `retryAfterMs`; no longer `gateway/internal` |
| A replica is killed hard while running a tool | Before the timeout the other replica returns busy; after it, DSH appends a `turn/end` (`reason.kind: interrupted`) and a new turn then completes normally. The test set `OPEN_TURN_TIMEOUT_MS` to 15000; the default is still 10 minutes |

**Not covered:**

- Two replicas receiving a request for the same conversation **at the same moment** from idle and racing for the claim. That the losing side is rejected before any model or tool call is guaranteed by unit tests and the new regression test in `agent-loop`; it was not run as a simultaneous test against the image;
- What happens when the old executor was only slow and is misjudged by the timeout: unit tests only (its write is blocked by the EventId conflict);
- The default 10-minute timeout, and request volume with long histories.

## Known limits

| Situation | Current behavior | What you do |
| --- | --- | --- |
| Two replicas race for the same turn | One runs; the other is rejected before any model/tool call (`session/agent-busy`) | The client retries later |
| A replica crashes, is scaled in, or restarts while a turn is running | An unfinished turn is left. Before the timeout other replicas refuse; after it, one takes over and closes it off automatically | Nothing; the wait is set by `OPEN_TURN_TIMEOUT_MS` |
| The old executor was only slow and is misjudged by the timeout | Its next write fails with a conflict; tools it already started are not stopped | Make tools idempotent; set the timeout above the longest quiet stretch |
| A tool already ran, then saving failed | The tool's side effects cannot be undone and are not replayed | Make the tool idempotent |
| Long cloud history | The number of cloud reads per new input grows with the history | See [Cost](#cost) |
| An idle replica's memory lags the cloud | Allowed. Nothing refreshes it in the background; it is checked and updated on the next input | Nothing |
| Title service outage | The current save fails and is retried on the next save | See [Title synchronization](../../../title-sync.md) |
| A writer that does not follow this convention (an external client, a base-example replica) | Not protected; may corrupt the history | Let only replicas of this scheme write a given conversation |

On the scope of protection: this scheme relies on every writer following the same EventId and append-only convention. It is not a lock or a lease: whether an executor is alive is inferred from a timeout, not confirmed. External writers, deleting a Session, or editing history in place are outside what it protects.

## Cost

Before each new input, when this replica is not currently running a turn:

- one read of the total event count;
- when the in-memory and cloud counts are equal, **a full read of the cloud history** and an event-by-event content comparison, about `ceil(events / 100)` paged requests. 1000 events cost about one count request plus ten pages;
- waiting for this replica's own pending buffer to be written out.

Comparing only the tail would miss "same count but different content at an earlier position", so the full comparison stays. **This is not a low-request-cost design**; for long conversations the read volume is clearly higher than the base example. Reducing it needs a version cursor or a digest from the server, which is outside this example (the Session service is unchanged).

## Differences from the base example

| Aspect | Base example | This example |
| --- | --- | --- |
| In-memory cache | A resident Agent is reused whether or not the cloud changed | The cache is kept, but validated before each new input |
| Cloud is newer than memory | Continues on the old history and conflicts at write time | Drops the generation and rebuilds from the cloud |
| Consistency check | None | Compares count and content |
| Tearing down a running Agent | The framework has no public interface | Keeps the `AgentHandle`; waits for cleanup and writer release before rebuilding |
| Unfinished turns | The framework appends "interrupted" at once on recovery, possibly closing a turn that is still running | Refuses while there is activity; takes over and lets the framework repair only after the timeout |
| Claiming | Found only when a write fails, by which time the model may already have been called | The turn runs only after `turn/start` is written |
| After a conflict | The old writer keeps failing | Dropped and released; recovers once the remote turn ends |
| Build | Installs the published DSH package | Builds from pinned DSH source with a patch applied |
| Use case | One writer; restore history in a new process | Resident replicas switching between completed turns |

## Files

| File | Purpose |
| --- | --- |
| `plugin/index.js` | Cloud persistence, history comparison, conflict detection, judging unfinished turns by timeout when a write handle is opened |
| `plugin/handoff-controller.js` | The decision before each new input (the flow above) |
| `plugin/dsh-handoff.js`, `plugin/dsh-handoff-plugin.js` | Wire the controller into DSH: tear down/rebuild a generation, read Agent state, register the `sessionHandoff` service |
| `plugin/session-titles.js`, `plugin/cloud-title-hints.js` | Title synchronization, see [Title synchronization](../../../title-sync.md) |
| `dockerfiles/0001-stateless-handoff.patch` | The DSH source patch |
| `dockerfiles/Dockerfile`, `dockerfiles/agent-runtime-session.cordis.yml`, `dockerfiles/entrypoint.sh` | Image build and startup configuration |
| `scripts/verify-handoff.sh` | The script used in "Verify A → B → A" |
| `stateless-handoff.patch` | This directory's plugin relative to the base plugin, for review |
| `Makefile` | `setup` / `check` |

A late writer conflict disposes the losing generation. Conflict recovery never reopens an open winner, even if its quiet timeout has elapsed; only a new explicit prompt may initiate another timeout takeover.
