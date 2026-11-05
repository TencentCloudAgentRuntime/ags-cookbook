# Persist pi conversations with Agent Runtime Session

[中文](./README_zh.md)

[pi](https://github.com/earendil-works/pi) is a terminal coding agent. It stores each conversation in a JSONL file on local disk, so deleting the container also deletes the conversation. This example adds a pi extension that copies every conversation entry to Agent Runtime Session in the cloud, and a start-up step that writes a conversation back to disk before pi starts. After you delete the container and start a fresh one, pi opens the original conversation and you keep talking.

The container runs the official `pi` binary. pi's own session commands (`/resume`, `/fork`, `/tree`, `/compact`) keep working because pi still reads and writes its normal session files.

## Quick start

pi 1.4.0 is not in a pre-built image; build the image from this directory. You need Docker, Python 3, and the `agr` CLI v0.7.0 or later, initialized as described in the [AGR CLI credential setup](https://github.com/TencentCloudAgentRuntime/ags-cli#initialize-cli-credentials).

```bash
cp .env.example .env            # fill in credentials and the model API key; see section 3
set -a; . ./.env; set +a
agr session space create \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --name pi-session-demo \
  --output json \
  --jq '.Data.SessionSpace.SpaceId'
# Put the printed SpaceId into SESSION_SPACE_ID in .env, then reload:
set -a; . ./.env; set +a

make build                      # build pi-session:local
make seed                       # start a container, save one turn carrying a marker, remove the container
make resume                     # start a fresh container; success when the model returns the marker
```

`make seed` and `make resume` each start their own container with `docker run --rm`, so the container is gone when the command returns and nothing on its disk survives. Clean up with [section 8](#8-clean-up) when you are done.

## 1. How the integration works

### Integration point

**The problem.** pi keeps a conversation in a JSONL file on local disk and offers no storage plug-in to change that. Delete the container and the file goes with it.

**The idea.** Let pi keep using its file, and treat the cloud Session as the copy that survives. Two small pieces do the work, one before pi starts and one while it runs:

| Piece | When it runs | What it does |
| --- | --- | --- |
| `prepare.mjs` | Once, in the container entrypoint, before pi starts | Reads the Session from the cloud and writes it to disk as pi's session file |
| `ags-pi-session` extension | Inside the pi process, while it runs | Copies each new conversation entry from pi to the Session |

pi itself is the official binary, started with the same session ID. It finds the file `prepare.mjs` wrote and carries on as if it had always been there.

```text
 first container                                    new container (after delete)
 ───────────────                                    ────────────────────────────
 pi writes entries to its file                      prepare.mjs reads the Session from the cloud
        │                                           and writes the session file
        ▼                                                   │
 extension copies new entries ──► cloud Session ──────────►│
                                  (survives)                ▼
                                                    pi opens the file and continues
```

**What "sync point" means.** The extension needs to know when pi has added entries. pi has no event that fires for each new entry, so the extension does it a different way. At certain moments it counts the entries pi holds and the entries already in the cloud, and sends the ones the cloud lacks, in order, one `AppendEvent` each. Those moments are the sync points: the end of each message (`message_end`), turn (`turn_end`) and run (`agent_end`), just before pi settles (`agent_before_settle`), after a compaction or tree change (`session_compact`, `session_tree`), when the session name changes (`session_info_changed`), and when pi shuts down (`session_shutdown`). A sync point that finds nothing new does nothing, so being called often is harmless.

pi's model calls, tools, skills and RPC protocol are unchanged.

### Conversation lifecycle

| Stage | What happens |
| --- | --- |
| New conversation | pi creates the session in memory. Nothing reaches the cloud until the session holds a user or assistant message, the same rule pi uses before it writes a file. |
| First write | The extension calls `CreateSession` with pi's session ID as the Session ID and stores pi's session header in `State.CustomState`, then appends every entry so far. |
| Later writes | At each sync point the extension appends only the entries beyond the count already saved. A failed append leaves the count where the last entry landed, and the next sync point continues from there. |
| Container start with an existing session | `prepare.mjs` reads the header and every Event, checks that the sequence numbers are contiguous, and writes `<timestamp>_<id>.jsonl` into the session directory. A file that already exists is left alone. |
| Shutdown | Closing pi's stdin triggers `session_shutdown`, which sends the last entries before pi exits. |

### Data layout

An entry's content is stored once. Content that a Part can express goes to `Content.Parts`, where other systems can read it. Everything else goes to `Extensions`, as the same entry with that content removed. Restoring puts the two back together, so the restored session file holds exactly the entries pi wrote.

| Data | Location |
| --- | --- |
| pi session header | `State.CustomState.piHeader` on the Session |
| Message text, reasoning, tool call name and arguments, tool result, compaction and branch summaries | `Content.Parts` on the Event |
| Entry id and parent, type, timestamp, signatures, usage, model, tool call id, `details` and any other field | `Extensions.pi.entry` on the Event, with the content above removed |
| Entries without conversational content: model and thinking changes, system prompt, labels, custom entries | Whole in `Extensions.pi.entry`; the Event has no `Content` |
| Image data | `InlineData` (`MimeType`, `Data`) on the Event, with the base64 data removed from `Extensions.pi.entry` |
| Event ID | `pi-<session id>-<sequence number>`; on a retried write the Session service uses it to recognize a duplicate |
| Author, role, error | `Author` is `user`, `assistant`, `tool` or `pi`; failed tool calls and model calls set `ErrorCode` and `ErrorMessage` |

Both `State.CustomState.piHeader` and `Extensions.pi` are defined by this extension. The Session service stores them as they are and does not interpret them.

### Before you integrate

- The extension depends on pi's session file format (version 3) and its extension events, so pi is pinned to an exact version. See [section 2](#2-versions-and-dependencies).
- One session must have one writer at a time. See [section 9](#9-limits).
- Every entry is sent to the cloud, including tool output and the system prompt. Use a SessionSpace and credentials you are allowed to put that data in.

## 2. Versions and dependencies

| Component | Version | Why |
| --- | --- | --- |
| pi | `@earendil-works/pi-coding-agent@1.4.0` | The extension was written and verified against this release. The older `@mariozechner/pi-coding-agent` package is deprecated and is not used. |
| Node.js | 24.8.0 in the image; 24 locally | The image base; `make check` was run with Node 24 |
| `tencentcloud-sdk-nodejs-ags` | 4.1.332 | Session API client used by the extension, pinned by `package-lock.json` |

pi 1.4.0 session files are format version 3. pi migrates older formats when it loads them, and the extension saves entries as pi holds them in memory.

When you change the pi version, run `make check` and then the verification in [section 5](#5-verify-the-integration) before relying on it. An extension that loads but never saves shows up only as a conversation that does not restore, so verify a restore, not just a successful start.

## 3. Prepare tools and cloud resources

### Local tools

| Tool | Used for |
| --- | --- |
| Docker | Building the image and running containers with `--platform linux/amd64` |
| `agr` | Creating a SessionSpace; the demo script also uses it to read the cloud Session |
| Python 3 | Running `session_demo.py` |
| Node.js 24 | `make check` and `make setup` only |

### Cloud resources and conversation identity

A conversation is identified by `SpaceId`, `UserId` and `SessionId`. In this example `SpaceId` and `UserId` come from the environment, and the Session ID is pi's session ID, which you choose with `PI_SESSION_ID`. A session ID may contain letters, digits, `-`, `_` and `.`, and must start and end with a letter or digit.

`SESSION_AGENT_ID` is optional. When it is set, the extension tags each Session it creates with it, and listing is limited to Sessions with that tag. Use it to keep several agents apart in one SessionSpace.

### Credentials

Use a dedicated test account or temporary credentials. The same `TENCENTCLOUD_*` values are used inside the container by the extension and outside by `agr`. They need permission for the Session actions: `CreateSession`, `DescribeSession`, `DescribeSessions`, `AppendEvent`, `DescribeEvents` and, for cleanup, `DeleteSession`. The model API key is separate and is not covered by Session credentials.

### Configure environment variables

```bash
cp .env.example .env
# Edit .env and fill in dedicated test credentials.
```

| Variable | Meaning |
| --- | --- |
| `AGR_REGION` | Region of the SessionSpace |
| `SESSION_API_ENDPOINT` | Session API endpoint, `ags.tencentcloudapi.com` by default |
| `SESSION_SPACE_ID` | SessionSpace ID; see the next section |
| `SESSION_USER_ID` | User ID inside the space |
| `SESSION_AGENT_ID` | Optional agent tag |
| `TENCENTCLOUD_SECRET_ID`, `TENCENTCLOUD_SECRET_KEY`, `TENCENTCLOUD_SESSION_TOKEN` | Credentials; the token is needed only for temporary credentials |
| `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` | OpenAI-compatible model service |

`.env` is ignored by Git and by `.dockerignore`. Do not commit it or bake it into an image.

### Create or reuse a SessionSpace

Create one as in the quick start, or list the spaces you already have:

```bash
agr session space list --region "$AGR_REGION" --cloud-endpoint "$SESSION_API_ENDPOINT" --output json
```

## 4. Run the example

### Build

```bash
make build
```

This builds `pi-session:local` from [dockerfiles/Dockerfile](./dockerfiles/Dockerfile): the pinned pi release from npm, then the extension from [extension/](./extension) with its locked dependencies. Set `PI_SESSION_IMAGE` to build or run another image name.

### What the container does

[dockerfiles/entrypoint.sh](./dockerfiles/entrypoint.sh) requires `AGR_REGION` and `PI_SESSION_ID`, runs `prepare.mjs`, then starts pi:

```text
pi --mode rpc --offline \
   --session-dir /var/pi/sessions --session-id "$PI_SESSION_ID" \
   --extension /opt/pi/extension/index.js \
   --provider custom --model "$LLM_MODEL" \
   --no-skills --no-prompt-templates --no-themes --no-context-files
```

`--session-id` opens the restored session file, or creates a session with that ID when none exists. pi prints `Warning: No project session found with id ...; creating a new session` to stderr in that case, which is expected on the first run.

`--mode rpc` makes pi read commands from stdin and write events to stdout as JSON lines. The demo script drives it that way. The flags after `--model` switch off discovery of local skills, prompt templates, themes and `AGENTS.md`, so the container behaves the same wherever it runs. Remove them to use those features.

The model configuration is written to `~/.pi/agent/models.json` as a provider named `custom` with the API type `openai-completions`. The key is not written to the file; the file holds `$LLM_API_KEY`, which pi reads from the environment on each request. Set `PI_SKIP_MODEL_CONFIG=true` to keep your own `models.json`, and then `LLM_*` are not checked, but `--model` still needs a model name in `LLM_MODEL`.

### Variables that only the container reads

| Variable | Default | Meaning |
| --- | --- | --- |
| `PI_SESSION_ID` | Required | Session to open or create |
| `PI_SESSION_DIR` | `/var/pi/sessions` | Directory pi reads sessions from |
| `PI_RESTORE_ALL` | Unset | `true` also restores every session of this user (and agent) before pi starts; see [section 6](#6-use-pis-own-session-commands) |
| `PI_SKIP_MODEL_CONFIG` | Unset | `true` skips writing `models.json` |

## 5. Verify the integration

### What to verify

1. **The cloud holds the messages**: the Session has the pi header and the entries of a finished turn.
2. **The running instance was really replaced**: each phase starts its own container with `--rm`, with no volume.
3. **The new container loaded the original history**: asked a question that does not contain the marker, the model returns it.
4. **New turns keep being written to the cloud**: the Session has more Events after the second turn.

### Verify with the script

```bash
make seed
make resume
```

`make seed` generates a session ID and a random marker, starts a container, and asks the model to remember the marker. When the turn has settled it closes pi's stdin so pi shuts down in order and the extension makes a last sync, then reads the Session through `agr` and checks the pi header, the contiguous sequence numbers, the marker in the stored user message and an assistant message. It saves the session ID and marker in `.local/session.json`.

```text
Session: <id>
Cloud header and 5 events verified. State: .local/session.json
The container was removed. Run resume to continue the conversation in a fresh one.
```

`make resume` starts a new container for the same session ID, asks `What marker did I ask you to remember?`, and checks that the answer is the marker and that the Session now has more Events.

```text
Session: <the same id>
Persisted history loaded and a new turn completed: session-proof-...
The Session now holds 8 events (was 5).
This verifies sequential recovery, not concurrent writers or automatic failover.
```

A seed turn stores five Events: the model change, the thinking level, the system prompt, the user message and the assistant message. A turn that calls a tool also stores the tool call and its result.

If a save fails, the extension writes the error to stderr and pi sends it to the client as an extension notification; the demo script stops with `pi extension reported: ...`.

To run another independent check, use a new state path, for example `python3 session_demo.py seed --state .local/another.json`, and the same path for resume.

### Interpreting the results

When something fails, tell two cases apart: history restored but the model answered wrongly is a model recall problem; history not restored is a persistence problem. In the second case, list the Events with `agr session event list` and check whether the first run saved anything.

## 6. Use pi's own session commands

The restored file is an ordinary pi session file, so commands that read session files work on it. By default only `PI_SESSION_ID` is restored. To make the user's other sessions available too, start the container with `PI_RESTORE_ALL=true`: `prepare.mjs` then restores every session of that user (narrowed by `SESSION_AGENT_ID` when set) into the session directory. Each restored session is a full read from the cloud, so use it for a handful of sessions rather than for hundreds.

Checked against pi 1.4.0 in this image, driving pi over RPC:

| Command | Result |
| --- | --- |
| `bash` with `ls /var/pi/sessions` | Lists the restored session files |
| `switch_session` with the restored file's path | Switches to the restored session and its history; `get_state` reports its ID and message count |
| `get_fork_messages`, then `fork` | Creates a new session from an earlier user message. The extension saves it as a new cloud Session with its own ID |
| `clone` | Copies the active branch into a new session. The extension saves it as a new cloud Session holding the copied history and later turns |
| `new_session` | Starts an empty session. The extension saves it as a separate cloud Session once it holds a conversation |

A forked session's header holds `parentSession`, the path of the source file inside the container that created the fork. The path means nothing in another container; the cloud Session keeps it only as a record.

## 7. Minimal integration: keep history in memory

Use this when you only need a conversation to continue in a new container and have no use for pi's session commands. It removes the session file, the start-up step and the extension. The program embeds pi as a library, loads the Session's entries into an in-memory session manager, runs a prompt, and sends the entries pi added back to the Session. [minimal/run-once.mjs](./minimal/run-once.mjs) is the complete 50-line program:

```js
const stored = await readSession(client, sessionId)          // 1. load from the cloud
const sessionManager = SessionManager.inMemory(
  cwd, { id: sessionId }, stored && [stored.header, ...stored.entries])

const { session } = await createAgentSession({ sessionManager, modelRuntime, model, noTools: 'builtin' })
await session.prompt(prompt)                                 // 2. run the turn
session.dispose()

const sync = await SessionSync.open(client, sessionId)       // 3. save what pi added
await sync.flush(sessionManager.getHeader(), sessionManager.getEntries())
```

It reuses the same conversion and sync code as the extension, so the Session it writes has the same layout and can be opened by the full integration. The image includes it:

```bash
set -a; . ./.env; set +a
SID=$(python3 -c 'import uuid; print(uuid.uuid4())')
run() { docker run --rm --platform linux/amd64 --env-file .env -e PI_SESSION_ID=$SID \
  --entrypoint sh pi-session:local -c 'node /opt/pi/extension/prepare.mjs 2>/dev/null && node /opt/pi/minimal/run-once.mjs "$1"' sh "$1"; }
run "Remember the code word MINIMAL-42. Reply with only OK."
run "What was the code word? Reply with only it."
```

The second container prints `MINIMAL-42`. What you give up compared with the full integration:

- **No pi binary.** The program is your own Node entry point; pi is a library inside it. You implement the loop that feeds it prompts.
- **No session commands.** The program calls `session.prompt` directly. Commands that replace the active session, such as `switch_session`, `fork` and `new_session`, belong to pi's session runtime and open session files, so they do not apply to an in-memory session. Start a new conversation by running the program with a new session ID.
- **Save at the end of a run.** Entries are sent when your program calls `flush`, not at each turn, so a crash before that loses the run. Call `flush` more often if you need to.
- **One writer per session ID**, as everywhere in this example.

## 8. Clean up

Preview what will be cleaned up, then delete:

```bash
make cleanup
# After checking the preview, delete:
make cleanup DELETE=1
```

Without `DELETE=1`, the script only lists the Sessions it would delete. With `SESSION_AGENT_ID` set, only that agent's Sessions are included; without it, every Session of that `UserId` in the space is. When the space is shared, check the preview before deleting.

Remove the local state files:

```bash
rm -rf .local
```

If the SessionSpace was created for this example and nothing in it is needed any more, you can delete it; do not delete a reused or shared space:

```bash
agr session space delete \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --space-id "$SESSION_SPACE_ID" \
  --output json
```

## 9. Limits

- **One writer per session.** The extension does not coordinate between containers. Event IDs come from the sequence number, and the Session service accepts a repeated Event ID only when the content is identical. When two containers write the same session, the first append of a given sequence number succeeds and the other is rejected with `EventId 已存在`. The cloud history stays contiguous, but the rejected container keeps failing on that session and has to be restarted. Route each session to one container.
- **Failure partway through a write.** The extension appends one Event per entry and advances its count only after each succeeds. A failure is written to stderr and sent to the client as an error notification; the next sync point continues from the first entry that did not land, and an Event that did land is not sent twice. The client sees the notification only while pi is running. If the container exits before a retry succeeds, the unsent entries are lost; the demo script avoids this by closing stdin and waiting for pi to exit.
- **Entries since the last sync point.** pi can append several entries between sync points, for example while a long tool call runs. A crash loses what pi added since the last point that succeeded.
- **Event size.** The Session service breaks a whole Session when one Event grows too large: in testing an Event of 200 KB worked and an Event of 300 KB did not, after which reads, further writes and even `DeleteSession` on that Session failed with `Out of sort memory`. A broken Session could not be recovered or deleted through the API. The extension therefore keeps every Event under 200,000 bytes. When an entry would exceed that, the extension cuts the largest text in it down, ending it with `[truncated: original N characters]`, replaces an oversized image with a text note and an oversized tool call's arguments with a note, marks the Event with `piTruncated` and logs a line to stderr. The conversation continues, but the restored entry is the shortened one. A single entry with nothing to cut down, such as a very large custom entry, is rejected with an error and not saved, and the session stops syncing at that entry.
- **Image data and region.** Images are stored in `InlineData` and count towards the Event size limit. `DescribeEvents` returns `InlineData` in `ap-shanghai` but did not in `ap-chongqing` when tested, and there the Session accepts the image but returns an empty Part. Restoring a conversation with an image then stops with `this region does not return InlineData`; conversations without images are unaffected. Use a region where `InlineData` is returned, or do not send images.
- **Tool arguments and results.** They are stored in full, subject to the size limit. Do not run tools that print secrets in a session you save.
- **Only conversation state is restored.** Files the agent wrote, running processes and open connections are not.
- **Existing history is not migrated.** A session that exists only on a local disk is uploaded in full at its first sync point after pi continues it. Nothing uploads sessions pi does not open.
- **Number of sessions.** `PI_RESTORE_ALL=true` reads every session before pi starts.
- **Extension permissions.** The extension runs inside the pi process with its permissions and sees every prompt, tool call and file. Load only extensions you trust.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| `entrypoint: ... is required` | Set `AGR_REGION` and `PI_SESSION_ID`; the demo script sets `PI_SESSION_ID` itself |
| `set LLM_... ; see .env.example` | A model variable is empty. Fill in `LLM_BASE_URL`, `LLM_MODEL` and `LLM_API_KEY`, or set `PI_SKIP_MODEL_CONFIG=true` |
| `SecretId is not found`, `AuthFailure` | The `TENCENTCLOUD_*` values in `.env` are wrong or expired. `prepare.mjs` calls the Session API before pi starts, so this stops the container early |
| `model call failed: 401 ...` | `LLM_API_KEY`, `LLM_BASE_URL` or the model account permission |
| `pi extension reported: saving session ... failed` | The message carries the cloud error. Fix the cause; the extension retries at the next sync point |
| The new container starts an empty conversation | `AGR_REGION`, `SESSION_SPACE_ID`, `SESSION_USER_ID` and `SESSION_AGENT_ID` must match the run that wrote it, and `PI_SESSION_ID` must be the same ID |
| `Session ... exists but was not written by this extension` | The ID belongs to a Session that has no pi header. Use another `PI_SESSION_ID` |
| `belongs to a different SESSION_AGENT_ID` | The Session was created under another `SESSION_AGENT_ID`. Use the original value, or another `PI_SESSION_ID` |
| `Session ... is not contiguous` | An Event is missing. Stop writing and investigate; do not delete Events to hide it |
| `holds N entries in the cloud but only M locally` | The local file is behind the cloud. Delete the local file and restore it again, or find which container wrote the extra entries |
| `Out of sort memory` from the Session API | The Session holds an Event of roughly 300 KB or more, written by something other than this extension. The Session could not be read or deleted through the API in testing |
| `does not return InlineData` | The region drops `InlineData` on read; see Limits. Use a region that returns it |
| `unsupported pi session format` | The Session was written by a different version of this extension |

## Appendix: local unit tests

```bash
make setup      # npm ci in extension/
make check      # shell syntax, extension tests, demo script tests
```

The extension tests cover the entry-to-Event conversion with a round trip for every entry kind, the size limit, the sync and restore logic against an in-memory Session service, the Session API client, and the model configuration. They do not call the cloud.
