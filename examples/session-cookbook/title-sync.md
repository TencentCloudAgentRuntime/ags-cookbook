# Session title synchronization

[中文](./title-sync_zh.md)

Applies to every session-cookbook example that stores a framework conversation in cloud Session: the DSH base and handoff implementations, and the pi file/RPC and handoff implementations. Each example's README only links here.

## The problem

A conversation was renamed in the framework, but the cloud Session's top-level `Title` did not change. As a result:

- the cloud console and other clients showed a different title from the framework;
- a freshly started DSH replica listed the conversation as "untitled", because it had no local title cache yet.

## Current behavior

**Writing.** When the framework produces a new rename event and `AppendEvent` stores it successfully, one `ModifySession` call sets `Title` to the same value. If the event was not stored, `Title` is not touched.

**Explicit clear.** pi can clear a name. A clear is treated as a rename to the empty string, and `Title` is set to empty explicitly. The cloud service derives a fallback title from the next user message; to keep the clear in effect, each user message appended after a clear triggers one more `ModifySession` that puts the title back to empty.

**Why a clear survives a restart.** Every rename event carries a `sessionTitleSync` marker in its `StateDelta` (version, event sequence, title). A new process that reads this marker knows the title was synchronized by us, and does not mistake an empty title for "never set".

**Reads never write.** Reading or listing Sessions never calls `ModifySession` and never backfills the title of an older Session. Sessions without a `sessionTitleSync` marker are left as they are; nothing is migrated.

**DSH cold lists.** When a new replica has no local title cache, the list shows the cloud list's `Title`. Whenever the framework already has a title (local cache or a live Session), the framework's title wins. This only reads fields the cloud already returns and never replays history.

## When something fails

| Situation | Behavior |
| --- | --- |
| `ModifySession` fails (for example the title service is briefly unavailable) | The current save reports an error **even though the event itself was stored**. The pending title is remembered and retried on the next save |
| A newer title is produced before the retry | The newer title replaces the older one; the older title is not written back |
| Another replica already wrote a newer title | After this replica reads the newer cloud `sessionTitleSync` marker, it drops its own pending older title |
| Two replicas rename at almost the same time | `ModifySession` has no version condition, so **the later write wins**. This window cannot be removed; the design only guarantees that a title already known to be older never overwrites a newer one |
| `CustomState` or `Extensions` is not valid JSON | Treated as "no marker"; reads and ordinary saves are unaffected |
| A rename event's `StateDelta` is not a JSON object | Rejected before sending with code `invalid-title-event`. It is **not retryable** (the same payload can never succeed) and nothing corrupt is written |

A title-service outage makes saves fail. This is deliberate: a failed synchronization is never swallowed silently. The cost is that if the title service stays down for a long time, saves for that Session keep failing until it recovers.

## Extra request cost

- Each rename: one extra `ModifySession`.
- Each user message after an explicit clear: one extra `ModifySession`.
- Reading or listing: no extra requests.

## Where it lives, and keeping copies in sync

The logic is in `session-titles.js`. So that every example directory builds on its own, **each directory carries an identical copy**:

- `pi/extension/session-titles.js`
- `pi/reference/pi-1.4.0-stateless-handoff/extension/session-titles.js`
- `deepseek-harness/dsh-0.2.1-rc.2/plugin/session-titles.js`
- `deepseek-harness/reference/dsh-0.2.1-rc.2-stateless-handoff/plugin/session-titles.js`

The two DSH directories also carry an identical `cloud-title-hints.js` (used for the list display).

Change one copy and you must change the others. A test in each directory's `session-titles.test.js` compares the copies and fails if they differ.

The per-Session state held in memory is released when the Session is disposed (DSH calls `forget` on `session/disposed`).
