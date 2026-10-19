# Persist DeepSeek Harness conversations with Agent Runtime Session

[中文](./README_zh.md)

DeepSeek Harness (DSH) writes conversations to a JSONL file on local disk. When DSH runs in a container with no volume mounted, as it does in this example, the file disappears with the container — delete the container and the conversation goes with it.

This example connects DSH's conversation persistence to Agent Runtime Session in the cloud. You have a conversation with DSH, delete the container, start a brand-new one, and load the same conversation from the cloud to continue where you left off.

It covers conversation persistence only. To also keep workspace files and route later requests back to the same workspace, see [Session and workspace association](../../deployment-cookbook/session-workspace/README.md).

**Steps**

1. Configure the environment and prepare a SessionSpace.
2. Start a DSH image that already includes the persistence plugin.
3. Have a conversation in DSH that asks the model to remember a marker, and confirm it was written to the cloud.
4. Delete the container and start a fresh one.
5. Open the same conversation in the new container and ask the model for the marker. The marker is not in the new prompt, so the model can only answer correctly if the history was restored from the cloud.

Steps 3–5 can be done by hand in the Web UI ([section 4](#4-verify-in-the-web-ui)) or automatically with a script ([section 5](#5-verify-with-the-script)). The Web UI is more visual; the script additionally checks for a completed turn in the cloud events, which suits repeated runs.

Everything runs locally in Docker against the real Session API. Because the flow deletes and recreates the container midway, `make run` does not run the demo — it only prints the steps. Run the commands in each section in turn.

Terms used in this guide:

- **DSH conversation** — a conversation a user starts in DSH.
- **Agent Runtime Session** — the cloud-side Session that stores that conversation. This example gives it the same ID as the DSH conversation.
- **SessionSpace** — the isolation boundary for Sessions; every Session belongs to one SessionSpace.
- **header** — DSH's name for conversation metadata such as the conversation ID, format version and creation time. It is stored in the Session.

## Prerequisites

- Docker able to run `linux/amd64` images, Python 3.10 or later, and `jq`.
- Install `agr` (the AGR CLI) **v0.7.0 or later**. This example uses the `agr session` commands, available since v0.7.0, on the host to create, inspect and clean up SessionSpaces and Sessions. For first-time setup, follow the [official AGR CLI credential guide](https://github.com/TencentCloudAgentRuntime/ags-cli#initialize-cli-credentials), then run `agr status` and `agr doctor`.
- An API key for your model service. By default the example calls `deepseek-v4-flash` through TokenHub; see [Changing the model service](#changing-the-model-service) to use another provider.
- Cloud API credentials allowed to create and manage the test SessionSpace, create, list and read Sessions, and append and read Events. Cleanup also needs delete permission.

## 1. Configure the environment

Run these from this directory:

```bash
cp .env.example .env
# Edit .env with dedicated test credentials.
set -a
. ./.env
set +a
agr status --cloud-endpoint "$SESSION_API_ENDPOINT"
```

`.env` is shared by the host and the container:

- Variables loaded with `. ./.env` between `set -a` and `set +a` are exported automatically, so the `agr` commands and example scripts on the host can read them. Rerun these three lines after editing `.env`.
- `make start` passes the same file to the container with `docker run --env-file .env`, for the persistence plugin inside it. Restart the container after editing `.env`.

Docker reads `--env-file` without shell parsing of quotes or expressions, so keep `.env` to plain `KEY=value` lines with no quotes around values. Use a sub-account or temporary credentials rather than your main account key, and keep `.env` out of version control.

| Variable | Required | Description |
| --- | --- | --- |
| `AGR_REGION` | Yes | Region of the SessionSpace; the example default is Shanghai. |
| `SESSION_API_ENDPOINT` | Yes | Cloud API endpoint; `ags.tencentcloudapi.com` here. |
| `SESSION_SPACE_ID` | Yes | SessionSpace to write into; obtained in [section 2](#2-create-or-reuse-a-sessionspace). |
| `SESSION_USER_ID` | Yes | Owner of the demo conversation. Keep it identical across seed, resume and cleanup. |
| `TENCENTCLOUD_SECRET_ID`, `TENCENTCLOUD_SECRET_KEY` | Yes | Credentials the persistence plugin uses inside the container to call the Session API. |
| `TENCENTCLOUD_SESSION_TOKEN` | With temporary credentials | Session token for temporary credentials; leave empty for long-term keys. Refresh and restart the container when it expires. |
| `TOKENHUB_API_KEY` | Yes | Model service API key, separate from the Session credentials. The variable name comes from the model configuration; see [Changing the model service](#changing-the-model-service). |
| `AGR_DOMAIN` | When running in the cloud | Only takes effect in [section 8](#8-optional-run-the-same-image-in-the-cloud); used to build the sandbox and Deployment access domains DSH trusts. Leave the default `tencentags.com` for local runs. |

This example uses two independent sets of credentials:

- **`agr` credentials** — configured on your machine when you initialised `agr`, and used for the host-side commands that create the space, inspect events and clean up.
- **Plugin credentials** — `TENCENTCLOUD_SECRET_ID` and `TENCENTCLOUD_SECRET_KEY` in `.env`, used by the plugin inside the container to read and write Sessions while DSH runs.

The plugin does not read `agr`'s configuration. Make sure both belong to the same account and use the same region; otherwise Sessions written by the plugin may not show up when you query them with `agr`.

## 2. Create or reuse a SessionSpace

If you already have a test SessionSpace, put its ID in `SESSION_SPACE_ID` in `.env` and skip to [section 3](#3-start-dsh).

Otherwise, create a dedicated one:

```bash
agr session space create \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --name dsh-session-demo \
  --description "DSH Session integration" \
  --output json \
  --jq '.Data.SessionSpace.SpaceId'
```

The command prints the new SpaceId. Open `.env`, replace the placeholder in `SESSION_SPACE_ID=space-replace-me` with that SpaceId, save, and reload it:

```bash
set -a
. ./.env
set +a
```

## 3. Start DSH

This example provides a published image with the persistence plugin already installed, `ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:v0.1.1-rc.2-ags.4-session-persistence.2`, ready to use. Run these commands in order:

```bash
make start
curl --fail http://127.0.0.1:18080/
```

- `make start` — pulls the published image and starts the container `dsh-session-demo`, passing environment variables from `.env`. The first start pulls the image and takes a while. The container listens only on the loopback address `127.0.0.1:18080` and mounts no volume.
- `curl` — checks that the DSH service is ready.

The service takes a moment to come up; if it does not, look at `docker logs dsh-session-demo`. Then open <http://127.0.0.1:18080> in a browser and confirm the model shown below the input box is `deepseek-v4-flash`.

The published image is built on the DSH image `deepseek-harness:v0.1.1-rc.2-ags.4`. It installs this example's persistence plugin and adjusts how DSH starts: it disables the built-in JSONL persistence plugin, `session-persistence-jsonl`, and enables the cloud one instead. Existing local JSONL history is not migrated to the cloud.

To change the plugin, the model service, or use your own DSH image, build the image yourself; see [section 7](#7-customise-the-model-and-image).

## 4. Verify in the Web UI

### Save a conversation

Open <http://127.0.0.1:18080>, start a new conversation, and send:

```text
Remember this marker: blue-falcon-42. Reply with only "Noted". Do not use tools.
```

Once the reply arrives, list this user's Sessions in the SessionSpace from a terminal to confirm the conversation reached the cloud:

```bash
agr session list \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --space-id "$SESSION_SPACE_ID" \
  --user-ids "$SESSION_USER_ID" \
  --limit 20 \
  --output json \
  --jq '(.Data.Sessions // [])[] | {SessionId, CreateTime}'
```

A new Session should appear, with a CreateTime matching when you sent the message.

### Recreate the container

Delete the current container and start a fresh one:

```bash
docker inspect --format '{{.Id}}' dsh-session-demo
make stop
make start
curl --fail http://127.0.0.1:18080/
docker inspect --format '{{.Id}}' dsh-session-demo
```

The two container IDs should differ, and no DSH data volume is carried over, so the new container has no local conversation data at all.

### Restore the conversation

Refresh the browser page. The earlier conversation appears in the sidebar under the ungrouped section of the workspace list, titled with its first message — the persistence plugin read it from the cloud. Open it and you will see the previous message and reply.

Continue in that conversation and send:

```text
What marker did I ask you to remember? Reply with only the marker. Do not use tools.
```

The model should reply `blue-falcon-42`. The marker is not in the new prompt, so the model can only answer correctly if the history was restored from the cloud.

## 5. Verify with the script

The script automates section 4, and additionally checks for a completed turn in the cloud events rather than just text appearing on the page.

### Save a conversation

```bash
make seed
```

The script creates a fresh DSH conversation, generates a random string as a marker (like `session-proof-…`), asks the model to remember it, and then waits for a *completed turn in the cloud events*. It checks the cloud header and records the Session ID and the marker in `.local/session.json`. No tools are involved.

Expected output:

```text
Session: <id>
Cloud header and completed turn verified. State: .local/session.json
Stop and remove the DSH container, start a fresh one without volumes, then run resume.
```

To look at what was stored in the cloud:

```bash
SESSION_ID="$(jq -r .sessionId .local/session.json)"
agr session event list \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --space-id "$SESSION_SPACE_ID" \
  --user-id "$SESSION_USER_ID" \
  --session-id "$SESSION_ID" \
  --limit 200 \
  --output json
```

This command returns only the first page (up to 200 events); the script reads every page.

### Recreate the container and restore

Only continue once `make seed` has succeeded, and do not write to this conversation from anywhere else while you test.

```bash
docker inspect --format '{{.Id}}' dsh-session-demo
make stop
make start
curl --fail http://127.0.0.1:18080/
docker inspect --format '{{.Id}}' dsh-session-demo
# once the new container answers:
make resume
```

The two container IDs should differ. The script then checks that:

1. The new DSH process returns the seed marker from `session.history`.
2. Asked a new question that does not contain the marker, the model recalls it.
3. The new turn is fully written to the cloud and the reply matches the marker.

Expected output:

```text
Session: <same id>
Persisted history loaded and a new turn completed: session-proof-...
This verifies sequential recovery, not concurrent writers or automatic failover.
```

For another independent run, use a new state path, for example `python3 session_demo.py seed --state .local/another.json`, and the same path for `resume`.

## 6. Understanding the results

### What was verified

This example verifies **sequential recovery**: after the old container is deleted, a new one loads the full history from the cloud and continues the conversation. In the Web UI, the new container listing the earlier conversation in the sidebar and showing its messages means DSH read the conversation from the cloud through the persistence plugin; the model naming the marker means the restored history reached the model's context. No script can prove on its own that the process was really replaced, which is why deleting and recreating the container and the changed container ID are part of the evidence.

When something fails, keep two cases apart: history loaded but the model answered wrong is a recall problem; history that did not load is a persistence problem.

### How it works

```text
DSH  →  persistence plugin  →  SessionSpace  →  Session (conversation metadata) + Events (messages, tool calls, turn markers)
```

The persistence plugin registers itself as DSH's persistence backend and takes over from the built-in JSONL one. When DSH creates a conversation, the plugin creates a matching cloud `Session` and stores the header in it. From then on, whenever DSH appends to the conversation, the plugin turns that entry into a cloud `Event` and appends it to the `Session`. When DSH later reopens the conversation, the plugin reads back the header and the events and rebuilds the log.

The swap is done by loading a [Cordis patch](./dockerfiles/agent-runtime-session.cordis.yml) through DSH's `--patch` startup flag. This plugin is the persistence-only version of the [Session and workspace association](../../deployment-cookbook/session-workspace/README.md) example: it registers no tools and makes no Deployment API calls.

### Where each piece of data lands

| Data | Location |
| --- | --- |
| DSH conversation identity and header | Same `SessionId`; `State.CustomState.dshHeader` |
| Message text and reasoning | `Content.Parts`, reasoning flagged with `Thought` |
| Tool calls and results | `Content.Parts[].FunctionCall` / `FunctionResponse` |
| Some configuration changes | `Actions.StateDelta` |
| Event type, sequence, turn markers | JSON `Event.Metadata`, including `Partial`, `TurnComplete`, `Interrupted` |
| The original DSH event, kept verbatim | JSON `Extensions.dshEvent` |

Loading sorts the original events and rejects a gap in the sequence; that catches most, but not every, incomplete batch. `supportsRawArtifacts=false` means there is no verbatim per-session log file to export — it does not mean history loading is off.

Session restores conversation state only: files, running processes and live model connections are not restored.

### Limits of this adapter

The persistence plugin in this example handles the normal write path only. It does not handle:

- **Failures mid-write.** `appendBatch()` creates the Session and then appends events one by one, so a failure part-way can leave an empty Session or a partial history. Stable Event IDs make a retry idempotent, but nothing already written is rolled back.
- **Multiple writers.** The plugin has no cross-instance coordination. If several DSH instances write to the same conversation at once, they can write events with conflicting sequence numbers and leave the history inconsistent.
- **Resuming an in-progress turn.** If the DSH process exits in the middle of a turn — while the model is generating a reply or a tool is running — no other process carries that turn on. The history written so far stays in the Session; after a new process loads the conversation, the user has to send the request again.
- **Oversized events.** The plugin writes each event whole, without splitting it. When a tool returns a lot of content, a single event can exceed the Session API's size limit and fail to write.

Before using this plugin in production, or letting several DSH instances write to the same conversation, add handling for each of these cases.

## 7. Customise the model and image

The published image uses this example's default plugin and model configuration. To change the plugin, change the model service, or use your own DSH image, build the image yourself.

### Building the image yourself

From this directory:

```bash
make build
make start DSH_SESSION_IMAGE=dsh-session:local
```

`make build` builds the image `dsh-session:local` on your machine from the [Dockerfile](./dockerfiles/Dockerfile), the same way the published image is built. `make start` needs `DSH_SESSION_IMAGE` pointed at that local image; otherwise it uses the published one. The local image name exists only on your machine; change it with `make build DSH_SESSION_IMAGE=<image name>`.

If the container is already running, run `make stop` first.

### Changing the model service

The model configuration lives in [`dockerfiles/settings.yaml`](./dockerfiles/settings.yaml) and is baked into the image at build time. The default reaches TokenHub through an OpenAI-compatible API (`api: openai-completions`). To use another model service, edit:

- the provider name, `baseURL` and `models` under `llm-pi-ai.providers`;
- `apiKeyEnv`, the environment variable the API key is read from;
- `provider` and `model` under `agent-default-model`.

Then rebuild and restart as in [Building the image yourself](#building-the-image-yourself), and put the API key in `.env` under the new `apiKeyEnv` name. If you also run in the cloud as described in section 8, replace `TOKENHUB_API_KEY` in the `REQUIRED` list of [`deployment_config.py`](./deployment_config.py) as well; otherwise config generation fails on the missing variable.

### Using your own DSH image

`make build` does not build DSH from source. It takes an existing DSH image as the base and adds the persistence plugin on top to produce a new image:

| Variable | Meaning | Default |
| --- | --- | --- |
| `DSH_IMAGE` | Base image — an image with DSH installed | Published image `deepseek-harness:v0.1.1-rc.2-ags.4` |
| `DSH_SESSION_IMAGE` | Build output — the base image plus the persistence plugin | `make build` writes the local image `dsh-session:local` by default; `make start` uses the published image by default. Use a registry address when pushing; see [section 8](#8-optional-run-the-same-image-in-the-cloud) |

If you already have your own DSH image, integrate it in one of two ways.

#### Option 1: build on top of your image

If your image has the same layout as the default one, just swap the base image:

```bash
make build DSH_IMAGE=your-registry/your-dsh:version DSH_SESSION_IMAGE=dsh-session:custom
make start DSH_SESSION_IMAGE=dsh-session:custom
```

Your image must meet these requirements:

| Requirement | Value in the default image | Why |
| --- | --- | --- |
| DSH installed as global modules | `/usr/local/lib/node_modules/@deepseek-ai` | The build links the plugin's DSH dependencies to this directory, so the plugin and DSH share one copy of each module |
| DSH module versions match the plugin | `cordis` 4.0.1; `dsh-session`, `dsh-session-persistence` 0.1.1-rc.2; `schemastery` 3.18.1 | Versions follow `peerDependencies` in [package.json](./plugin/package.json) |
| Node.js 24 | v24.8.0 | The build installs pnpm through npm and installs the plugin's dependencies |
| Web profile at `$DSH_HOME/profiles/web` | `DSH_HOME` defaults to `/root/.dsh` | At startup the plugin is linked into that profile's `node_modules` for DSH to load |
| `linux/amd64` platform | — | The Makefile builds and runs for that platform |

To check Node.js and the DSH module versions in your image:

```bash
docker run --rm --platform linux/amd64 --entrypoint sh your-registry/your-dsh:version -c \
  'cd /usr/local/lib/node_modules/@deepseek-ai && node -v && for p in cordis dsh-session dsh-session-persistence schemastery; do echo "$p $(node -p "require(\"./$p/package.json\").version")"; done'
```

If the versions differ, change them in `peerDependencies` of [package.json](./plugin/package.json), run `pnpm install` in the `plugin` directory to update `pnpm-lock.yaml`, then run `make check` and `make check-image` to confirm the plugin works with that version.

Two more things to watch:

- **Model configuration is overwritten.** The build copies [settings.yaml](./dockerfiles/settings.yaml) to `/root/.dsh/settings.yaml`. If your image ships its own model configuration, remove that `COPY` line from the [Dockerfile](./dockerfiles/Dockerfile) or merge the two.
- **The startup command is replaced.** The output image uses this example's [entrypoint.sh](./dockerfiles/entrypoint.sh). If your image starts DSH with extra arguments, such as other trusted hosts or ports, merge them into entrypoint.sh.

#### Option 2: integrate the plugin in your own Dockerfile

If your image has a different layout, or you want to integrate the plugin in your own build, follow this example's [Dockerfile](./dockerfiles/Dockerfile) and [entrypoint.sh](./dockerfiles/entrypoint.sh) through four steps:

1. **Install the plugin.** Copy the `plugin` directory into the image, run `pnpm install --prod --frozen-lockfile`, and place it under `@tencentcloud/ags-dsh-session-persistence` in the Node.js global modules directory.
2. **Share modules with DSH.** Delete the `@deepseek-ai` directory under the plugin's `node_modules`, and symlink `cordis`, `dsh-session`, `dsh-session-persistence` and `schemastery` to where DSH is actually installed.
3. **Register the plugin in the Web profile.** Before starting DSH, link the plugin to `$DSH_HOME/profiles/web/node_modules/@tencentcloud/ags-dsh-session-persistence`. DSH loads it from there by the `name` in the Cordis patch.
4. **Enable the plugin.** Copy the [Cordis patch](./dockerfiles/agent-runtime-session.cordis.yml) into the image and pass `--patch <patch path>` when starting `dsh web`. The patch disables the built-in `session-persistence-jsonl`, enables the cloud persistence plugin, and reads its configuration from environment variables.

Steps 1 and 2 happen at build time; steps 3 and 4 happen when the container starts. Your build context must include this example's `plugin` directory, the Cordis patch and the startup script. Exclude `plugin/node_modules` in `.dockerignore` so dependencies installed on your machine are not copied into the image.

Example Dockerfile:

```dockerfile
FROM your-registry/your-dsh:version

# Where DSH modules are actually installed in your image
ARG DSH_MODULES=/usr/local/lib/node_modules/@deepseek-ai
# Where the persistence plugin is installed
ARG PLUGIN_DIR=/usr/local/lib/node_modules/@tencentcloud/ags-dsh-session-persistence

# Step 1: install the plugin and its dependencies
COPY plugin /tmp/ags-dsh-session-persistence
RUN npm install --global pnpm@11.19.0 \
    && cd /tmp/ags-dsh-session-persistence \
    && pnpm install --prod --frozen-lockfile \
    && mkdir -p "$(dirname "$PLUGIN_DIR")" \
    && mv /tmp/ags-dsh-session-persistence "$PLUGIN_DIR" \
    && rm -rf /root/.npm /root/.local/share/pnpm/store

# Step 2: link the plugin's DSH dependencies to DSH's install location so both share one copy
RUN rm -rf "$PLUGIN_DIR/node_modules/@deepseek-ai" \
    && mkdir -p "$PLUGIN_DIR/node_modules/@deepseek-ai" \
    && for package in cordis dsh-session dsh-session-persistence schemastery; do \
         ln -s "$DSH_MODULES/$package" "$PLUGIN_DIR/node_modules/@deepseek-ai/$package"; \
       done

# Steps 3 and 4 are done by the startup script
COPY agent-runtime-session.cordis.yml /opt/dsh/agent-runtime-session.cordis.yml
COPY entrypoint.sh /opt/dsh/entrypoint.sh
RUN chmod 0755 /opt/dsh/entrypoint.sh
ENTRYPOINT ["/opt/dsh/entrypoint.sh"]
```

Example startup script `entrypoint.sh`:

```sh
#!/bin/sh
set -eu

# Step 3: register the plugin in the Web profile; the path must match PLUGIN_DIR in the Dockerfile
profile_modules="${DSH_HOME:-/root/.dsh}/profiles/web/node_modules/@tencentcloud"
mkdir -p "$profile_modules"
ln -sfn /usr/local/lib/node_modules/@tencentcloud/ags-dsh-session-persistence \
  "$profile_modules/ags-dsh-session-persistence"

# Step 4: start DSH and load the Cordis patch with --patch.
# These are this example's arguments; replace them with your image's own start command and arguments, keeping --patch.
exec node --expose-internals \
  /usr/local/lib/node_modules/@deepseek-ai/dsh/lib/bin.js \
  web \
  --patch /opt/dsh/agent-runtime-session.cordis.yml \
  --host 0.0.0.0 \
  --port 3080
```

For trusted hosts and the other startup arguments, see this example's full [entrypoint.sh](./dockerfiles/entrypoint.sh).

After building, run the plugin's own tests inside the image to confirm it loads the DSH modules correctly:

```bash
docker run --rm --platform linux/amd64 --entrypoint node your-dsh-session:version \
  --test /usr/local/lib/node_modules/@tencentcloud/ags-dsh-session-persistence/index.test.js
```

The container also needs the environment variables in the [section 1](#1-configure-the-environment) table at startup. Whichever option you choose, pin and test your DSH version; do not assume any version is compatible.

## 8. Optional: run the same image in the cloud

Once the local test passes, you can run the same image in the cloud. This section offers two ways: run it directly in an AGS sandbox, or host it in a Deployment. Both use the same image and sandbox tool.

### Prepare the image and sandbox tool

This uses the example's published image by default. To use an image you built in [section 7](#7-customise-the-model-and-image), tag and push it to a registry your account can pull from first, and set `DSH_SESSION_IMAGE` to it; the Makefile does not push. You also need `AGR_ROLE_ARN` from the [custom Sandbox role guide](https://cloud.tencent.com/document/product/1814/129691), `cam:PassRole` for the operator, and permission to create sandbox tools, sandbox instances or Deployments, and to obtain access tokens.

```bash
export DSH_SESSION_IMAGE='ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:v0.1.1-rc.2-ags.4-session-persistence.2'
export AGR_ROLE_ARN='qcs::cam::uin/replace-me:roleName/replace-me'
mkdir -p .local
umask 077
python3 deployment_config.py > .local/tool-config.json
DSH_TOOL_ID="$(
  agr tool create \
    --region "$AGR_REGION" \
    --cloud-endpoint "$SESSION_API_ENDPOINT" \
    --tool-name dsh-session-demo \
    --tool-type custom \
    --persistent \
    --role-arn "$AGR_ROLE_ARN" \
    --network-configuration '{"NetworkMode":"PUBLIC"}' \
    --custom-configuration "$(cat .local/tool-config.json)" \
    --wait \
    --output json \
    --jq '.Data.ToolId'
)"
rm .local/tool-config.json
export DSH_TOOL_ID
echo "$DSH_TOOL_ID"
```

The generated config contains credentials: create it under `umask 077`, do not share it, and delete it once the sandbox tool exists. The full output of `agr tool create` also contains the credentials from the tool configuration, so the command above extracts only the ToolId. The generator assumes a public/personal registry; adjust the registry settings if yours differs.

While running in the cloud, do not let the local container write to the same conversation. Both ways below use a new state path, so they do not touch the conversation from the local test.

### Option 1: run in an AGS sandbox

Create a sandbox instance and forward its port 3080 to your machine:

```bash
DSH_INSTANCE_ID="$(
  agr instance create \
    --region "$AGR_REGION" \
    --cloud-endpoint "$SESSION_API_ENDPOINT" \
    --tool-id "$DSH_TOOL_ID" \
    --timeout 1h \
    --wait \
    --output json \
    --jq '.Data.InstanceId'
)"
echo "$DSH_INSTANCE_ID"

agr instance proxy "$DSH_INSTANCE_ID" 18082:3080 \
  --region "$AGR_REGION" \
  --domain "$AGR_DOMAIN" \
  --cloud-endpoint "$SESSION_API_ENDPOINT"
```

`--timeout` sets how long the sandbox lives; choose a value that covers the test. The proxy runs in the foreground, so keep that terminal open.

In a second terminal with the same environment loaded, save a conversation:

```bash
export DSH_BASE_URL=http://127.0.0.1:18082
python3 session_demo.py seed --state .local/sandbox.json
```

Stop the proxy with `Ctrl+C` in its terminal, delete the sandbox, then create a new one and start the proxy again:

```bash
agr instance delete "$DSH_INSTANCE_ID" \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --yes \
  --wait

DSH_INSTANCE_ID="$(
  agr instance create \
    --region "$AGR_REGION" \
    --cloud-endpoint "$SESSION_API_ENDPOINT" \
    --tool-id "$DSH_TOOL_ID" \
    --timeout 1h \
    --wait \
    --output json \
    --jq '.Data.InstanceId'
)"
echo "$DSH_INSTANCE_ID"

agr instance proxy "$DSH_INSTANCE_ID" 18082:3080 \
  --region "$AGR_REGION" \
  --domain "$AGR_DOMAIN" \
  --cloud-endpoint "$SESSION_API_ENDPOINT"
```

The two instance IDs printed should differ. Once the proxy is up, restore the conversation from the second terminal:

```bash
python3 session_demo.py resume --state .local/sandbox.json
```

The expected output matches [section 5](#5-verify-with-the-script).

This option works with the script only, not with the Web UI in a browser. `agr instance proxy` does not rewrite the browser's Origin header when forwarding requests, and DSH rejects such requests for security reasons. Script requests carry no Origin and are not affected. If you need the Web UI, use option 2.

The image's [entrypoint.sh](./dockerfiles/entrypoint.sh) already adds the sandbox domain `*.<region>.<AGR_DOMAIN>` to DSH's trusted hosts so requests through the sandbox are accepted. If you use your own image, add the same setting to its startup arguments.

### Option 2: host in a Deployment

Create a Deployment from the same sandbox tool and forward its port 3080 to your machine:

```bash
DSH_DEPLOYMENT_ID="$(
  agr deployment create \
    --region "$AGR_REGION" \
    --cloud-endpoint "$SESSION_API_ENDPOINT" \
    --deployment-name dsh-session-demo \
    --tool-id "$DSH_TOOL_ID" \
    --scaling-configuration '{"MinInstanceCount":1,"MaxInstanceCount":1,"MaxInstanceRequestConcurrency":100}' \
    --lifecycle-configuration '{"IdleTimeoutSeconds":600,"IdleAction":"STOP"}' \
    --output json \
    --jq '.Data.Deployment.DeploymentId'
)"
export DSH_DEPLOYMENT_ID
echo "$DSH_DEPLOYMENT_ID"

agr deployment proxy "$DSH_DEPLOYMENT_ID" 18081:3080 \
  --region "$AGR_REGION" \
  --domain "$AGR_DOMAIN" \
  --cloud-endpoint "$SESSION_API_ENDPOINT"
```

Once the proxy is up, you can open <http://127.0.0.1:18081> in a browser to use the Web UI. Alternatively, in a second terminal with the same environment loaded, set `DSH_BASE_URL=http://127.0.0.1:18081` and run `seed` with a new `--state` path.

## 9. Clean up

Stop the local container and delete every Session that `SESSION_USER_ID` owns in the SessionSpace. This covers conversations created both in the Web UI and by the script:

```bash
make stop

agr session list \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --space-id "$SESSION_SPACE_ID" \
  --user-ids "$SESSION_USER_ID" \
  --limit 100 \
  --output json \
  --jq '(.Data.Sessions // [])[].SessionId' | while read -r session_id; do
    delete_status="$(
      agr session delete \
        --region "$AGR_REGION" \
        --cloud-endpoint "$SESSION_API_ENDPOINT" \
        --space-id "$SESSION_SPACE_ID" \
        --user-id "$SESSION_USER_ID" \
        --session-id "$session_id" \
        --output json \
        --jq '.Status'
    )"
    echo "$session_id: $delete_status"
  done
```

If the SessionSpace is shared and other people use the same `SESSION_USER_ID`, this deletes their Sessions too. In that case run `agr session list` on its own first, check the list, and delete only the Sessions this example created.

Once every line reads `succeeded`, remove the local state files:

```bash
rm -rf .local
```

If you created the SessionSpace for this example in [section 2](#2-create-or-reuse-a-sessionspace) and no longer need anything in it, you can delete it. Do not delete a reused or shared space:

```bash
agr session space delete \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --space-id "$SESSION_SPACE_ID" \
  --output json
```

If you completed section 8, delete the cloud resources too. If you used option 2, delete the Deployment first:

```bash
agr deployment delete "$DSH_DEPLOYMENT_ID" \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --wait
```

Then delete every instance of the sandbox tool that is not already stopped, including the sandbox from option 1, and finally the sandbox tool itself. Deleted instances stay in the list as `STOPPED` and need no further action:

```bash
agr instance list \
  --tool-id "$DSH_TOOL_ID" \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --output json \
  --jq '(.Data.Items // [])[] | select(.Status != "STOPPED") | .InstanceId' | while read -r instance_id; do
    agr instance delete "$instance_id" \
      --region "$AGR_REGION" \
      --cloud-endpoint "$SESSION_API_ENDPOINT" \
      --yes \
      --wait
  done

agr tool delete "$DSH_TOOL_ID" \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --yes \
  --wait
```

## Troubleshooting

- **Credential or space errors** — check account, region, SpaceId, permissions and temporary-credential expiry for both `agr` and the container.
- **Container exits right after starting** — DSH lists conversations through the persistence plugin at startup, so invalid plugin credentials make startup fail. Run `docker logs dsh-session-demo`; a cloud API error such as `SecretId is not found` means the `TENCENTCLOUD_*` credentials in `.env` need checking.
- **Connection refused** — wait for startup and check `docker logs dsh-session-demo`. If you override `PORT`, update `DSH_BASE_URL` for the script too.
- **Model errors** — check the model service API key, the model configuration in `settings.yaml`, and your account's model access. Session credentials do not grant model access.
- **Non-contiguous history** (`non-contiguous DSH event log`) — stop writing and inspect the incomplete history. Do not delete events to make the error go away.
- **Marker missing after restart** — confirm the same SpaceId, UserId and Session ID, and compatible DSH and plugin versions. Keep the state file and logs.
- **Serving multiple users** — the fixed `SESSION_USER_ID` is for the demo only. In production, use trusted identity and ownership checks, and never change a shared plugin's UserId per request.

## Appendix: local unit tests

These checks touch no cloud resources and are meant for self-testing after you change the plugin or scripts. They need Node.js 24 and pnpm 11.19.0.

```bash
make setup
make check
# run the plugin tests inside the image; checks the published image by default:
make check-image
# check an image you built yourself:
make check-image DSH_SESSION_IMAGE=dsh-session:local
```

They cover the event projections, history loading and the verification logic, but do not replace the real seed → fresh container → resume flow.
