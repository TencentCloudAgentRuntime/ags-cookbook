# pi 1.4.0 replica handoff (reference implementation)

[中文](./README_zh.md) · [pi 1.4.0 file/RPC integration](../../README.md) · [Session examples overview](../../../README.md)

## Start here

**The problem.** You run two long-lived pi service replicas (A and B). One turn of a conversation is handled by A, the next by B, the next by A again — with no restarts, no shared disk, and no session affinity (you do not pin a conversation to one replica).

**How it is solved.** Every request reads the full history from the cloud Session, builds a brand-new in-memory session, and discards it when done. The cloud Session is the only source of history; a replica keeps no conversation state, so "switching replicas" needs no extra step.

**What you get:**

- after a completed turn, the next turn can go to any replica;
- when two replicas race for the same turn, only one runs it; the other is rejected **before** any model or tool call (HTTP 409);
- when a model call fails, the turn is closed normally and the conversation stays usable, with no manual step;
- when a replica crashes and leaves a turn unclosed, the next request takes it over and closes it off once the timeout (default 10 minutes) has passed;
- when a replica receives a stop signal (deploy, scale-in), it waits for running turns and, if needed, aborts them and closes them off.

**What you do not get:**

- another replica taking over a turn that is half-way through;
- tools that already ran being replayed or undone;
- workspace files or running processes moving with the conversation (a Session stores conversation history only);
- the full pi RPC or terminal UI. There is only `POST /prompt` and `GET /health`;
- a server-side lock or lease. This relies on the existing EventId uniqueness.

**The cost:** every request cold-loads the full history, so cloud read volume is higher than in the file/RPC implementation; longer conversations make it more noticeable (see [Cost](#cost)).

## Terms

| Term | Meaning |
| --- | --- |
| turn | The whole of one `POST /prompt`: the user input, the model's answer, and any tool calls in between |
| claim | At the start of every turn, a boundary record with `state: open` is written to the cloud first, and only after that write succeeds are the model or tools called. When two replicas write the same position, the cloud lets only one succeed |
| open / closed boundary | The `ags-turn-boundary` records in the cloud history. If the last one is `open`, the turn has not ended |
| EventId | A unique id per event, derived from its position in the conversation. The cloud answers "same EventId, different content" with a conflict; the whole scheme builds on that |

## Comparison with the file/RPC implementation

The baseline is the [pi 1.4.0 file/RPC example](../../README.md), not a different pi release; both pin `@earendil-works/pi-coding-agent@1.4.0`.

| Aspect | File/RPC example | This directory (SDK/HTTP) |
| --- | --- | --- |
| Entry point | The official pi executable in RPC mode | A small HTTP service calling the official pi SDK |
| pi source changed | No | No; the addition is application code around the SDK |
| Conversation lifecycle | `SessionManager` keeps entries in memory and writes local JSONL; the process keeps using the loaded session | A new `SessionManager.inMemory` and Agent per request, released afterwards |
| Cloud restoration | Restored at startup; skipped if a local file exists | Every request reads the cloud header and history, including requests returning to the same replica |
| Concurrency | Route each conversation to one replica; a conflict can leave the old process failing | An `open` claim is written before execution; a lost claim is rejected; later requests reload |
| Unfinished turns | No equivalent protocol | Refuse to take over; history untouched; nothing replayed |
| Model error | Depends | The turn is closed as `closed` (`outcome: "error"`); the conversation continues |
| Interaction surface | pi RPC, terminal, `/fork`, `/resume`, … | Only `POST /prompt` and `GET /health` |
| Local state | Conversation files and live session objects | Model config and working directory may be local; the history is in the cloud |

## Build and run

### Prerequisites

- Docker;
- an existing SessionSpace and cloud credentials authorized for the Session APIs;
- a working model endpoint;
- for local checks, Node.js 24 and npm.

> **Security.** The sample service has **no authentication**, and the agent is equipped by default with tools that can run commands. Run it only on your machine or behind a trusted authenticated gateway; do not expose it directly to a network.

### Configure

```sh
cp .env.example .env
# Fill in .env. Do not copy a real credential file into an image.
```

Fill in `AGR_REGION`, `SESSION_SPACE_ID`, `SESSION_USER_ID`, `TENCENTCLOUD_SECRET_ID`, `TENCENTCLOUD_SECRET_KEY`, `LLM_BASE_URL`, `LLM_MODEL`, and `LLM_API_KEY`. Set `SESSION_API_ENDPOINT` for your environment; `SESSION_AGENT_ID` and the temporary credential `TENCENTCLOUD_SESSION_TOKEN` are optional. Both replicas must use the **same** Session identity and agent filter. The cloud API must return `ResourceInUse.EventIdDuplicate`, `ResourceInUse.SessionIdDuplicate`, and `ResourceNotFound.SessionNotExist` unchanged; other errors propagate as they are and are never re-read and reclassified as conflicts.

### Build and check

```sh
make setup   # install dependencies
make check   # syntax checks and unit tests
make build   # build the image
# On an ARM host: make build PLATFORM=linux/arm64
```

### Start two replicas

Start the same image in two terminals, **without** sharing a conversation volume:

```sh
make run PORT=18081
make run PORT=18082
```

### Verify A → B → A

After each request returns, send the next one to the other replica with the same `sessionId`:

```sh
curl -sS http://127.0.0.1:18081/prompt -H 'Content-Type: application/json' \
  -d '{"sessionId":"handoff-demo","text":"Remember marker ALPHA-42. Reply only ACK."}'
curl -sS http://127.0.0.1:18082/prompt -H 'Content-Type: application/json' \
  -d '{"sessionId":"handoff-demo","text":"Reply only with the earlier marker."}'
curl -sS http://127.0.0.1:18081/prompt -H 'Content-Type: application/json' \
  -d '{"sessionId":"handoff-demo","text":"Reply only with the earlier marker."}'
```

**Expected:** the replies are `ACK`, `ALPHA-42`, `ALPHA-42`; `eventCount` in the responses increases each time; no replica restarts. The third request returns to A, which holds nothing in memory and reloads from the cloud, so it can still answer with what B saw.

`GET /health` only says the process is alive; it does not say the cloud and model are reachable.

### API and error codes

| Request | Response |
| --- | --- |
| `POST /prompt` with `{"sessionId": "...", "text": "..."}` | `200`, `{"reply": "...", "eventCount": N}` |
| Body is not valid JSON, or `sessionId` / `text` is missing or malformed | `400 invalid-request` |
| The previous turn has not ended and was active recently, or this replica is already running this conversation | `409 session/agent-busy`; retry after `Retry-After` seconds |
| Another replica wrote first (same turn, or same new conversation) | `409 ResourceInUse.EventIdDuplicate` or `ResourceInUse.SessionIdDuplicate`; retry later |
| This replica is stopping | `503 session/shutting-down`; retry on another replica |
| Anything else | `500 internal-error`. Details go to the server log only, not to the client |

`sessionId` allows letters, digits, `_`, `.`, and `-`, must start with a letter or digit, and is at most 128 characters. The request body is limited to 1 MiB.

## How a request runs

1. Read the conversation with `DescribeSession` and `DescribeEvents`. A new conversation starts empty; if the history is not contiguous the request is refused. If the last turn is `open`: it is refused when there was recent activity, and closed off first when it has been quiet longer than the timeout (see below).
2. Build a brand-new in-memory `SessionManager` and Agent with the official SDK.
3. Append a boundary record with `state: open` and a random request id, and **call the model only after that write succeeds**. The random id makes two simultaneous requests differ, so the cloud treats the later one as a conflict rather than as a retry of the same request.
4. Run the prompt. Save checkpoints in order on `message_end`, `turn_end`, and `tool_execution_end`; if saving fails, execution is aborted where possible.
5. On success, append a boundary record with `state: closed`, return `reply` and `eventCount`, and release the Agent.

After the claim, this replica is the only writer at that position (another replica writing the next position gets an EventId conflict), so checkpoints **do not re-read the whole history**; it is validated once at the start of the request.

### What happens on failure

| Failure happens | What the cloud keeps | Afterwards |
| --- | --- | --- |
| Before the claim (reading history, or the claim write fails) | Nothing changed | Retry directly |
| The claim is won by another replica | The other replica's `open` | You get a 409. It **never** closes someone else's turn |
| After the claim, the model or a tool fails, and cloud writes still work | The turn is closed as `closed`, `outcome: "error"` | The conversation is usable at once; retry |
| After the claim, cloud writes fail too | The `open` is left as it was | After the timeout the next request takes over and closes it off |
| The replica is stopped (SIGTERM) | See the next section | See the next section |

A failed turn is never replayed automatically. The caller decides whether to retry; if tools already ran in that turn, a retry runs them again, so tools must be idempotent.

### When a replica is stopped

On `SIGTERM` / `SIGINT` the replica:

1. closes the listener to new connections; requests that reach the host during shutdown get `503 session/shutting-down`, while new connections may be refused;
2. lets running turns finish on their own, for at most `SHUTDOWN_GRACE_MS` (default 20000 ms);
3. requests cancellation and attempts to close off those still running, then waits at most `SHUTDOWN_ABORT_MS` (default 5000 ms);
4. exits. If any turn was not closed off, the exit code is 1 and the log lists those conversations.

The termination grace period of your orchestrator (Kubernetes, etc.) must be **longer** than the sum of these two values; otherwise the process is killed outright and leaves unfinished turns. The defaults add up to 25 seconds, which fits inside Kubernetes' default 30-second termination grace period; if you raise either value, raise `terminationGracePeriodSeconds` with it.

Cloud writes must also finish within the shutdown window. Size `SHUTDOWN_ABORT_MS` for tool cancellation and pending Session API writes, not just model cancellation. If the window expires, exit code 1 and an open boundary are possible even when cancellation works; use the recovery procedure below only after the executor has stopped.

## Unfinished turns left by a crash

The last record in the cloud history is `open`. Either another replica is **still running** the turn, or the replica that ran it **crashed** (killed hard, OOM, scaled in). The cloud history cannot tell them apart, so this scheme looks at **whether anything is still happening**:

| Time since the turn's last record | Verdict | What happens |
| --- | --- | --- |
| Less than the timeout | May still be running | Refused with `409 session/agent-busy`, plus a `Retry-After` header saying how long to wait |
| More than the timeout | The executor has crashed | **Taken over automatically**: a `closed` boundary (`outcome: "abandoned"`) is written to close it off, then the current request runs |

A crashed turn needs no manual step: once the timeout has passed, the next request closes it off and carries on.

### The timeout

The default is **10 minutes**, set with the environment variable `OPEN_TURN_TIMEOUT_MS` (milliseconds). A non-positive or non-numeric value fails at startup instead of silently using the default.

**It must be longer than the longest quiet stretch of a healthy turn.** During a model call or a tool run a turn can go a long time without a new record: too short, and a turn that is merely slow is taken over as if it had crashed; too long, and after a real crash the conversation stays unavailable that long. If your tools can run longer than 10 minutes, raise it.

### The risk this design accepts

The timeout is an **inference** that the executor died, not a confirmation:

- **A misjudged turn fails.** If the old executor was only slow, its later write collides with the `closed` boundary the new owner already wrote (same position, same EventId) and the cloud rejects it, so that turn fails with a 409. **The cloud history is not corrupted, and the new owner's turn is not closed by it.**
- **Tools it already started are not stopped.** The takeover can keep it from writing to the log; it cannot stop what it is already doing, so side effects may overlap with the new turn. Tools still need to be idempotent.
- **It assumes the replicas' clocks roughly agree.** The decision uses the timestamps in the records.

This scheme has no heartbeat.

If no timeout is configured (only when `StatelessPiHost` is used directly without `openTurnTimeoutMs`), nothing is ever taken over and every unfinished turn is refused.

## What has been verified

The behavior of this directory is covered by unit tests (the adapter and the HTTP host; they do not call the real cloud or model), including: a failed claim, closing off after a model error, not closing someone else's turn when the claim is lost, automatic takeover after the timeout, the old executor being blocked by the EventId conflict, simultaneous creation of a new conversation, and the stop signal.

On a real cloud and a real model, the basic scenarios — A → B → A, tool results recovered across replicas, simultaneous racing, and refusing unfinished history — were verified on an earlier version. **Automatic takeover of a crashed turn, closing off after a model error, and stop-signal handling were added later and currently have unit tests only; they have not been run in a real environment.** Before delivering, run these in a real environment.

## Known limits

| Situation | Current behavior | What you do |
| --- | --- | --- |
| Two replicas race for the same turn | One runs; the other is rejected before any model/tool call (409) | The client retries later |
| Two replicas create the same new conversation at once | One succeeds; the other gets 409 | Same |
| Model error | The turn is closed as `closed` (`outcome: "error"`); the conversation continues | The caller decides whether to retry |
| A replica is killed hard while a turn is running | An `open` is left. Before the timeout other replicas refuse; after it, one takes over and closes it off automatically | Nothing; the wait is set by `OPEN_TURN_TIMEOUT_MS` |
| The old executor was only slow and is misjudged by the timeout | Its next write fails with a conflict; tools it already started are not stopped | Make tools idempotent; set the timeout above the longest quiet stretch |
| A tool already ran, then saving failed | The side effects cannot be undone and are not replayed | Make the tool idempotent |
| Long history | Every request cold-loads the full history | See "Cost" |
| A writer that does not follow this convention (the file/RPC implementation, an external client) | Not protected; may corrupt the history | Let only replicas of this scheme write a given conversation |
| Title service outage | The current save fails and is retried on the next save | See [Title synchronization](../../../title-sync.md) |

On the scope of protection: this scheme relies on every writer following the same EventId and append-only convention. It is not a lock or a lease: whether an executor is alive is inferred from a timeout, not confirmed. A Session stores conversation history, not workspace files or running processes, and a crashed tool is never resumed automatically.

## Cost

- **Per request:** one read of the conversation header, then the whole event list in pages (about `ceil(events / 100)` requests), before execution starts. The same is true for a request returning to the same replica, because a replica keeps no conversation.
- **Per checkpoint:** only the new events are appended; the whole history is not re-read.

Read volume is higher than in the file/RPC implementation, and more noticeable for long conversations. Reducing it needs a version cursor or a digest from the server, which is outside this example (the Session service is unchanged). **Do not treat this reference as a low-request-cost design.**

## Files in this directory

| File | Purpose |
| --- | --- |
| `stateless/server.mjs` | HTTP entry point, error-code mapping, stop-signal handling; builds pi SDK sessions |
| `stateless/host.js` | The full flow of one request: read history, take over a crashed turn, claim, save checkpoints, close off |
| `extension/session-sync.js` | Appends pi entries to the cloud; validates sequence and content; keeps stable EventIds |
| `extension/session-restore.js`, `session-client.js`, `session-codec.js` | Reading cloud history, the Session API client, entry/event conversion |
| `extension/session-titles.js` | Title synchronization, see [Title synchronization](../../../title-sync.md) |
| `extension/prepare.mjs` | Only writes the model configuration; it no longer restores history into a local session file |
| `minimal/run-once.mjs` | A one-shot SDK entry that uses the same flow, handy to call from scripts |
| `dockerfiles/` | An independent image and entry point that always starts the HTTP service |

This directory imports no runtime file from the file/RPC directory: the codec, client, and tests are independent copies. The HTTP service does not load `extension/index.js` (that is the file/RPC entry point).
