# Persist DeepSeek Harness 0.2.1-rc.2 conversations with Agent Runtime Session

[中文](./README_zh.md) | [Choose another DSH version](../README.md)

DeepSeek Harness (DSH) stores conversations in JSONL files on local disk. When DSH runs in a container with no volume mounted, deleting the container also deletes the conversation history. This example uses a persistence plugin to write DSH conversations to Agent Runtime Session in the cloud: after you delete the container and start a fresh one, you can still load the original conversation and keep talking.

This guide applies to **DSH 0.2.1-rc.2**. The plugin is tied to exact versions of DSH's internal modules, so check [section 2](#2-versions-and-dependencies) before you start.

## Quick start

With this example's pre-built image, which is the official DSH 0.2.1-rc.2 plus the persistence plugin, you can save a conversation and restore it in a few commands. From this directory:

```bash
cp .env.example .env            # fill in credentials and the model API key; see section 3
set -a; . ./.env; set +a
agr session space create \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --name dsh-session-demo \
  --output json \
  --jq '.Data.SessionSpace.SpaceId'
# Put the printed SpaceId into SESSION_SPACE_ID in .env, then reload:
set -a; . ./.env; set +a

make start                      # start the pre-built image; prints the sign-in URL once ready
make seed                       # save one turn carrying a marker
make stop && make start         # delete the container and start a fresh one
make resume                     # the fresh container loads history; success when the model returns the marker
```

`make start` waits for up to about 2 minutes. Once DSH is ready it prints `DSH is ready. Sign in at: http://127.0.0.1:18080/?token=...`; if the container exits early or times out, it prints the last 20 lines of the container log. [Section 5](#5-verify-the-integration) explains each step and its expected output; clean up with [section 7](#7-clean-up) when you are done. To integrate the plugin into your own DSH, see [section 4](#4-integrate-the-plugin-into-your-dsh).

## 1. How the integration works

### Integration point

DSH decides where conversations are stored through its **SessionPersistence extension point**; the built-in implementation is the `session-persistence-jsonl` plugin, which writes local files. This example provides the plugin `@tencentcloud/ags-dsh-session-persistence`, which implements the same extension point, and uses a Cordis patch at DSH startup to disable the JSONL plugin and enable this one. Cordis is DSH's plugin framework; a patch is a YAML file that changes which plugins load, and their configuration, without changing DSH code. The rest of DSH, including model calls, tool execution, and the Web UI, needs no change.

```text
DSH writes conversation records  →  the plugin writes them to the cloud  →  Session and Events in the SessionSpace
                                                                                   │
A new DSH process  ←  the plugin reads the history back  ←──────────────────────────┘
```

### Conversation lifecycle

| Stage | What happens |
| --- | --- |
| New conversation | The plugin only registers the conversation in the current process. On the first record written, or when DSH flushes, it calls `CreateSession` with the DSH conversation ID as the Session ID and stores the DSH conversation metadata (the header) in it. A conversation that is created but never written does not appear in the cloud. |
| Later writes | Records from DSH go to the plugin's buffer; records within 200 ms form one batch, appended to the Session in sequence order with one `AppendEvent` per record. When DSH's checkpoint policy triggers a flush, buffered records are written immediately. |
| A new process lists conversations | When DSH lists conversations after starting, the plugin queries this user's Sessions in the SessionSpace and returns only DSH conversations written by this version of the plugin; with `SESSION_AGENT_ID` set, only that Agent's. The conversation list in the Web UI sidebar comes from here. |
| Opening an existing conversation | The plugin reads back the header and every Event, checks that the sequence is contiguous and the records are well formed, and hands them to DSH to rebuild the conversation. Within one process, a conversation has at most one writer at a time. |

The plugin creates the cloud Session when it first writes; you do not create it by hand.

### Data layout

Besides the standard Session fields, the plugin uses these custom fields to store what DSH needs to restore a conversation:

| Data | Location | Purpose |
| --- | --- | --- |
| DSH conversation header | `State.CustomState.dshHeader` | Lets the plugin recognize DSH conversations and rebuild their metadata |
| Records inherited by a fork | `State.CustomState.dshInheritedEventCount` | Written only for forked conversations: how many records came from the parent |
| Original DSH event | `Extensions.dshEvent` on the Event | Lets the plugin rebuild the conversation log exactly |
| Event ID | `dsh-<conversation ID>-<sequence number>` | On a retried write, the Session service uses it to recognize a duplicate request |
| Message text and reasoning | `Content.Parts`, with reasoning marked as Thought | For other systems to read directly; not used when DSH restores |
| Tool calls and results | `Content.Parts[].FunctionCall` / `FunctionResponse` | Same as above |
| Some configuration changes | `Actions.StateDelta` | Same as above |
| Type, sequence number, turn markers | `Event.Metadata`, including Partial, TurnComplete, Interrupted | Same as above |

"Fork" here means DSH's session fork (`session/fork`): a new conversation derived from an existing one at a chosen point, whose log starts with that inherited prefix. `dshInheritedEventCount` records how many records the prefix holds; ordinary conversations do not write it.

DSH restores a conversation from two places only:

- **`State.CustomState.dshHeader`** (on the Session): marks the Session as a DSH conversation. Without it, the Session does not appear in the conversation list and cannot be opened.
- **`Extensions.dshEvent`** (on each Event): holds the complete event content, which restore replays record by record. An Event without it is skipped.

Both field names and their formats are defined by this plugin; the Session service only stores them as they are and does not interpret, validate, or convert them.

### Before you integrate

These points affect how existing conversations behave once the plugin is enabled; [section 8](#8-limits) has the details:

- **Existing history is not migrated.** Local JSONL history, and conversations written to the cloud by the DSH 0.1.1-rc.2 plugin, are not visible in this version.
- **Do not let several DSH instances write the same conversation at once.** Several instances can share a space and each handle different conversations, but the plugin does not coordinate concurrent writes to one conversation; on a conflict, the replica that writes later fails; see [Multi-replica deployment](#multi-replica-deployment).
- **Only the conversation is restored, not the working environment.** Files, running processes, and long-lived model connections are not restored; if an instance exits mid-turn, that turn has to be sent again.

## 2. Versions and dependencies

The plugin uses DSH's internal modules directly, and these modules changed incompatibly between some DSH versions. **Pin the versions in the table below; do not use "latest".** For example, `npm install -g @deepseek-ai/dsh` without a version installs whatever is newest on npm; when that differs from the version this plugin targets, DSH fails at startup.

### Required versions

| Dependency | Requirement | Notes |
| --- | --- | --- |
| DSH `@deepseek-ai/dsh` | Exactly `0.2.1-rc.2` | Always name the version: `npm install -g @deepseek-ai/dsh@0.2.1-rc.2`. Other versions are not verified |
| DSH internal modules: `@deepseek-ai/cordis`, `dsh-session`, `dsh-session-persistence`, `schemastery` | Exactly `4.0.5`, `0.2.1-rc.2`, `0.2.1-rc.2`, `3.18.5` | Installed with DSH; do not install or upgrade them separately. The plugin shares these modules with DSH, so their versions must match `peerDependencies` in [plugin/package.json](./plugin/package.json) exactly |
| Node.js | 24.x | The example image is based on `node:24.8.0-bookworm-slim`, i.e. Node.js 24.8.0 |
| npm | 11.x | Node.js 24.8.0 ships npm 11.6.0. npm 11 installs DSH's dependencies under the DSH package's own `node_modules`; see "Module location" below |
| pnpm | Exactly `11.19.0` | Installs the plugin's dependencies, matching [plugin/pnpm-lock.yaml](./plugin/pnpm-lock.yaml); builds use `--frozen-lockfile` |
| `tencentcloud-sdk-nodejs-ags` | Exactly `4.1.302` | The SDK the plugin uses to call the Session API, pinned by the lock file |
| Docker | Able to run `linux/amd64` images | The example image's build platform |
| Python | 3.10 or later | Verification script |
| AGR CLI `agr` | v0.7.0 or later | Manages SessionSpaces and Sessions from your machine |

### Module location

The plugin must find the internal modules DSH actually installed and link to that same copy. When DSH is installed with npm 11, they are in:

```text
/usr/local/lib/node_modules/@deepseek-ai/dsh/node_modules/@deepseek-ai/
```

A DSH installed another way may keep them directly under `/usr/local/lib/node_modules/@deepseek-ai/`. The script in [Check your image](#check-your-image) prints the actual location.

### What a version mismatch looks like

| Situation | Error |
| --- | --- |
| DSH is 0.2.x, but the plugin built for 0.1.1-rc.2 is used | `does not provide an export named 'PersistenceCoordinator'` |
| DSH is 0.1.x, but this plugin is used | `does not provide an export named 'SessionAlreadyExistsError'` |

When you see these errors, use the plugin directory that matches your DSH version; see [Choose a DSH version](../README.md). Do not silence the error by changing the versions in the plugin's `peerDependencies`: different DSH versions have different persistence interfaces, and changing the version numbers alone does not make the plugin work.

## 3. Prepare tools and cloud resources

### Local tools

- Docker, Python 3.10 or later, and `jq`.
- `agr` (AGR CLI) v0.7.0 or later. This guide uses `agr session` on your machine to create, query, and clean up SessionSpaces and Sessions; the command is available from v0.7.0. On first use, initialize it as described in the [AGR CLI credential setup on GitHub](https://github.com/TencentCloudAgentRuntime/ags-cli#initialize-cli-credentials), then run `agr status` and `agr doctor`.
- To change the plugin and run its unit tests locally, you also need Node.js 24 and pnpm 11.19.0; see the [appendix](#appendix-local-unit-tests).

### Cloud resources and conversation identity

The plugin uses these identifiers to decide where each conversation is stored:

| Identifier | Provided by | Role |
| --- | --- | --- |
| Region `AGR_REGION` | Your configuration | Region of the SessionSpace; the plugin and `agr` must use the same one |
| SessionSpace `SESSION_SPACE_ID` | Created or chosen by you in advance | The logical space that manages conversation data |
| User `SESSION_USER_ID` | Your configuration | An application-defined user ID, unrelated to Tencent Cloud accounts. The plugin reads it once at startup and uses it for every conversation of that instance. To separate conversations by business user, see [Separating conversations by business user](#separating-conversations-by-business-user) |
| Session ID | The DSH conversation ID | The plugin creates the matching cloud Session when it writes; no manual creation needed |
| Agent ID `SESSION_AGENT_ID` | Defined by you, optional | An application-defined Agent ID. When several Agents share a space it separates each Agent's conversations; unset, nothing is separated. See [Multiple Agents in one space](#multiple-agents-in-one-space) |

To restore a conversation, the new process must reach it in the **same region, SessionSpace, and user**, with read permission; with `SESSION_AGENT_ID` set, the value must also match. If any of these differs, the new process cannot see the original conversation.

### Credentials

This guide uses two kinds of credentials, for different purposes:

| Credential | Used by | Purpose | Required permissions |
| --- | --- | --- | --- |
| `TENCENTCLOUD_SECRET_ID` and `TENCENTCLOUD_SECRET_KEY` in `.env` | The persistence plugin in the container | Reading and writing Sessions while DSH runs | Create, list and read Sessions; append and read Events |
| The credential configured when initializing `agr` | `agr` on your machine | Creating the space, verification, cleanup | Manage SessionSpaces; read and delete Sessions |

The plugin does not read `agr`'s configuration. Make sure both credentials belong to the same account; otherwise Sessions written by the plugin cannot be found through `agr`. Use a sub-account or temporary credentials, not the root account's keys.

### Configure environment variables

From this directory:

```bash
cp .env.example .env
# Edit .env and fill in dedicated test credentials.
set -a
. ./.env
set +a
agr status --cloud-endpoint "$SESSION_API_ENDPOINT"
```

`.env` serves both your machine and the container:

- Variables loaded with `. ./.env` between `set -a` and `set +a` are exported automatically for `agr` and the verification script on your machine. Run these three lines again after changing `.env`.
- `make start` passes the same file to the container with `docker run --env-file .env`. Restart the container after changing `.env`.

Docker does not parse quotes or expressions in `--env-file`, so `.env` must use plain `KEY=value` lines with no quotes around values. Do not commit `.env`.

For what each variable means, see [Cloud resources and conversation identity](#cloud-resources-and-conversation-identity); the table below covers the values to fill in.

| Variable | Required | Used by | Notes |
| --- | --- | --- | --- |
| `AGR_REGION` | Yes | Plugin, `agr` | Example default `ap-shanghai`; must match the SessionSpace's region |
| `SESSION_SPACE_ID` | Yes | Plugin, `agr` | Which SessionSpace stores the conversations; see [Create or reuse a SessionSpace](#create-or-reuse-a-sessionspace) |
| `SESSION_USER_ID` | Yes | Plugin, `agr` | Example default `dsh-demo-user`; keep it the same for restore and cleanup |
| `SESSION_AGENT_ID` | No | Plugin, verification script | Optional; separates conversations by Agent. When unset, nothing is separated |
| `TENCENTCLOUD_SECRET_ID`, `TENCENTCLOUD_SECRET_KEY` | Yes | Plugin | Cloud API credentials the plugin uses to read and write Sessions; see [Credentials](#credentials) |
| `TENCENTCLOUD_SESSION_TOKEN` | With temporary credentials | Plugin | Token of the temporary credentials; update it and restart the container when it expires |
| `SESSION_API_ENDPOINT` | No | Plugin, `agr` | Cloud API domain, `ags.tencentcloudapi.com` by default; change it only to reach another environment |
| `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` | Yes | Example image | The model service DSH calls; TokenHub's `deepseek-v4-flash` by default. See [Changing the model service](#changing-the-model-service). Only this example's image uses them; your own DSH can keep its existing model configuration |

### Create or reuse a SessionSpace

A SessionSpace is a logical space that stores and manages conversation data. It does not map one-to-one to Agents or running instances: several instances of one Agent, and several different Agents, can share a space. Whether to split spaces depends on business, environment, and permission needs, not on how many Agents or instances you run; for example, create separate spaces for test and production if they are managed separately.

A SessionSpace is not an execution workspace and does not share local files between instances. For separating conversations of several Agents in one space, see [Multiple Agents in one space](#multiple-agents-in-one-space).

This example needs one space, created or reused. You do not recreate it when adding, restarting, or replacing instances. If you already have a usable space, put it in `SESSION_SPACE_ID` in `.env`; otherwise create one for this example:

```bash
agr session space create \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --name dsh-session-demo \
  --description "DSH Session integration" \
  --output json \
  --jq '.Data.SessionSpace.SpaceId'
```

The output is the new space's SpaceId. Open `.env`, replace the placeholder in `SESSION_SPACE_ID=space-replace-me` with it, save, and reload:

```bash
set -a
. ./.env
set +a
```

You can also reuse a space the DSH 0.1.1-rc.2 plugin has written to, but its old conversations are not visible in this version; see [section 8](#8-limits).

## 4. Integrate the plugin into your DSH

### Minimal changes

Integrating Session takes these four changes:

| Step | Change | When | How to confirm |
| --- | --- | --- | --- |
| 1. Install the plugin | Copy this directory's `plugin` directory (`index.js`, `package.json`, `pnpm-lock.yaml`) into the image, run `pnpm install --prod --frozen-lockfile` with pnpm 11.19.0, and place it under `@tencentcloud/ags-dsh-session-persistence` in the Node.js global modules directory | Image build | See "Post-build check" below |
| 2. Share modules with DSH | Delete the `@deepseek-ai` directory under the plugin's `node_modules`, and symlink `cordis`, `dsh-session`, `dsh-session-persistence`, and `schemastery` to the module directory DSH actually installed (see [Module location](#module-location)), so the plugin and DSH use the same copy | Image build | See "Post-build check" below |
| 3. Register the plugin in the Web profile | The Web profile is the directory DSH loads plugins from when it runs as a Web app. Before DSH starts, link the plugin to `$DSH_HOME/profiles/web/node_modules/@tencentcloud/ags-dsh-session-persistence`; DSH loads it from there by name | Container start | The path exists and points at the step 1 install directory |
| 4. Enable the plugin | Copy the [Cordis patch](./dockerfiles/agent-runtime-session.cordis.yml) into the image, add `--patch <patch path>` to the command that starts DSH, and give the container the environment variables the plugin needs | Container start | See "Post-start check" below |

In step 4, the plugin needs `AGR_REGION`, `SESSION_SPACE_ID`, `SESSION_USER_ID`, `TENCENTCLOUD_SECRET_ID`, `TENCENTCLOUD_SECRET_KEY`, and optionally `TENCENTCLOUD_SESSION_TOKEN`, `SESSION_API_ENDPOINT`, and `SESSION_AGENT_ID`; see [section 3](#3-prepare-tools-and-cloud-resources).

### Cordis patch

```yaml
- id: session-persistence-jsonl
  disabled: true

- insert:
    - id: session-persistence-agent-runtime
      name: '@tencentcloud/ags-dsh-session-persistence'
      config:
        region: !!js process.env.AGR_REGION
        endpoint: !!js process.env.SESSION_API_ENDPOINT
        spaceId: !!js process.env.SESSION_SPACE_ID
        userId: !!js process.env.SESSION_USER_ID
        agentId: !!js process.env.SESSION_AGENT_ID
        secretId: !!js process.env.TENCENTCLOUD_SECRET_ID
        secretKey: !!js process.env.TENCENTCLOUD_SECRET_KEY
        sessionToken: !!js process.env.TENCENTCLOUD_SESSION_TOKEN

# The next two entries are the example's model configuration, not required for the integration; see "Required items and example choices"
- id: llm-pi-ai
  config:
    providers:
      custom:
        displayName: Configured Model Service
        apiKeyEnv: LLM_API_KEY
        api: openai-completions
        baseURL: !!js process.env.LLM_BASE_URL
        models:
          - id: !!js process.env.LLM_MODEL

- id: agent-default-model
  config:
    provider: custom
    model: !!js process.env.LLM_MODEL
```

- The first entry disables DSH's built-in JSONL persistence plugin by `id`.
- `insert` adds this plugin. `name` is the plugin's package name; DSH looks it up by this name in the Web profile's `node_modules`, so it must match the step 3 registration path.
- `!!js process.env.*` in `config` reads values from environment variables when DSH starts, so credentials are never written into the image or the patch. `agentId` is optional; see [Multiple Agents in one space](#multiple-agents-in-one-space).
- The last two entries configure the model service; see [Changing the model service](#changing-the-model-service).

The keys under the plugin's `config` (`region`, `spaceId`, `userId`, and so on) are defined by the plugin and cannot change; the environment variable names on the right can.

### Required items and example choices

Besides the Session integration, this example's image makes some choices of its own. When integrating into your DSH, separate them as follows:

| Item | Required for the integration | When integrating into your DSH |
| --- | --- | --- |
| The persistence plugin, the first two patch entries, the plugin's environment variables | Yes | Add them with the four steps above |
| Versions of DSH and its internal modules | Yes | Must follow [section 2](#2-versions-and-dependencies); see "Check your image" below |
| The plugin's install directory | No | Can change, but must match the step 3 registration path |
| Start options: listen address, port 3080, `--public-url`, `--no-open` | No | Keep your DSH's own start options and only add `--patch`. The official DSH rejects `--host 0.0.0.0`; see [Start options](#start-options) |
| Model configuration: the `llm-pi-ai` and `agent-default-model` patch entries and the `LLM_*` variables | No | To keep your own model configuration, delete those two patch entries; entrypoint.sh skips the `LLM_*` check when the patch has no `llm-pi-ai` |
| Platform `linux/amd64` | No | The example image's build platform; the plugin itself is platform-independent |

### Start options

This example's [entrypoint.sh](./dockerfiles/entrypoint.sh) starts DSH with:

```sh
dsh --profile web \
  --patch /opt/dsh/agent-runtime-session.cordis.yml \
  --host "<container IP>" \
  --port 3080 \
  --no-open \
  --public-url "$DSH_PUBLIC_URL"
```

| Option | Notes |
| --- | --- |
| `--profile web` | Run as a Web app. In DSH 0.2, `dsh web` is equivalent to `dsh --profile web` |
| `--host` | The official DSH accepts only one concrete IP address and rejects wildcard addresses such as `0.0.0.0`. In a container, bind the container's own IP so the host can reach it through the published port; entrypoint.sh gets it with `hostname -i`, or from the `DSH_HOST` environment variable |
| `--public-url` | Optional. The root DSH uses when it prints the sign-in URL to the log; it grants no access. `make start` sets it to `http://127.0.0.1:18080/` so the printed URL opens directly on your machine |
| `--no-open` | Do not try to open a browser |

When you access DSH locally, the Host of browser and script requests is `127.0.0.1:18080`, a local address DSH trusts by default, so no `--trusted-host` is needed. To reach DSH through another domain, declare it with `--trusted-host`, using a full domain or `domain:port` only; wildcards such as `*.example.com` are not supported.

### Check your image

Check your image with the command below, replacing `your-registry/your-dsh:version`:

```bash
make check-dsh-image DSH_IMAGE=your-registry/your-dsh:version
```

It runs [check-dsh-image.sh](./dockerfiles/check-dsh-image.sh) in the image, checks every version in [section 2](#2-versions-and-dependencies), and prints where DSH's internal modules actually are. A passing check prints:

```text
OK    npm 11.6.0
OK    Node.js v24.8.0
OK    @deepseek-ai/dsh 0.2.1-rc.2
OK    dsh command on PATH
INFO  DSH_MODULES=/usr/local/lib/node_modules/@deepseek-ai/dsh/node_modules/@deepseek-ai
OK    @deepseek-ai/cordis 4.0.5
OK    @deepseek-ai/dsh-session 0.2.1-rc.2
OK    @deepseek-ai/dsh-session-persistence 0.2.1-rc.2
OK    @deepseek-ai/schemastery 3.18.5
```

- **No `FAIL`**: use option 1. If `DSH_MODULES` differs from the output above, pass it at build time; see option 1.
- **`WARN`**: Node.js is not 24. You can still build, but run the post-build check.
- **DSH or internal module versions differ**: change the DSH in your image to `0.2.1-rc.2`, or use the plugin directory for that DSH version. Do not only change the versions in the plugin's `peerDependencies`.
- **npm or the `dsh` command not found**: add them to your image, or use option 2 and adjust the install and start steps yourself.

### Option 1: build with this example's Dockerfile

If your image passes the check, use this example's [Dockerfile](./dockerfiles/Dockerfile) to add the plugin on top of it. First export the name of the image to build; the build, start, and check commands all use it:

```bash
export DSH_SESSION_IMAGE=your-registry/your-dsh:version-session-persistence
make build DSH_IMAGE=your-registry/your-dsh:version
```

Without `DSH_IMAGE`, the Dockerfile first installs the official DSH 0.2.1-rc.2 with npm on `node:24.8.0-bookworm-slim`, then adds the plugin; this example's pre-built image is built that way. If the check printed a `DSH_MODULES` different from the default, build with `docker build --build-arg DSH_MODULES=<actual directory>`.

Name the result after its base image's repository and version with `-session-persistence` appended to the tag, so the original image and the one with the plugin are easy to tell apart. This example's pre-built image follows that naming: `deepseek-harness:v0.2.1-rc.2-session-persistence.2`, where the trailing `.2` is the plugin's release number.

Besides the four steps, this example's Dockerfile uses this example's [entrypoint.sh](./dockerfiles/entrypoint.sh) as the start command. If your image has its own start options, merge them into entrypoint.sh and keep its plugin registration and `--patch`.

### Option 2: integrate in your own Dockerfile

If your image does not pass the check, or you want to integrate the plugin in your own build, add the following to your Dockerfile and start script. Your build context must include this directory's `plugin` directory and the Cordis patch; exclude `plugin/node_modules` in `.dockerignore` so dependencies installed on your machine are not copied into the image.

Add steps 1 and 2 to the Dockerfile:

```dockerfile
FROM your-registry/your-dsh:version

# Where DSH's internal modules are in your image; use the DSH_MODULES printed by make check-dsh-image
ARG DSH_MODULES=/usr/local/lib/node_modules/@deepseek-ai/dsh/node_modules/@deepseek-ai
# Where the persistence plugin is installed
ARG PLUGIN_DIR=/usr/local/lib/node_modules/@tencentcloud/ags-dsh-session-persistence

# Step 1: install the plugin and its dependencies; the pnpm version must match pnpm-lock.yaml
COPY plugin /tmp/ags-dsh-session-persistence
RUN npm install --global pnpm@11.19.0 \
    && cd /tmp/ags-dsh-session-persistence \
    && pnpm install --prod --frozen-lockfile \
    && mkdir -p "$(dirname "$PLUGIN_DIR")" \
    && rm -rf "$PLUGIN_DIR" \
    && mv /tmp/ags-dsh-session-persistence "$PLUGIN_DIR" \
    && rm -rf /root/.npm /root/.local/share/pnpm/store

# Step 2: link the DSH modules the plugin depends on to DSH's install location, sharing one copy with DSH
RUN rm -rf "$PLUGIN_DIR/node_modules/@deepseek-ai" \
    && mkdir -p "$PLUGIN_DIR/node_modules/@deepseek-ai" \
    && for package in cordis dsh-session dsh-session-persistence schemastery; do \
         ln -s "$DSH_MODULES/$package" "$PLUGIN_DIR/node_modules/@deepseek-ai/$package"; \
       done

# The Cordis patch used by step 4
COPY agent-runtime-session.cordis.yml /opt/dsh/agent-runtime-session.cordis.yml
```

Add steps 3 and 4 to the start script:

```sh
# Step 3: register the plugin in the Web profile; the path must match PLUGIN_DIR in the Dockerfile
profile_modules="${DSH_HOME:-/root/.dsh}/profiles/web/node_modules/@tencentcloud"
mkdir -p "$profile_modules"
ln -sfn /usr/local/lib/node_modules/@tencentcloud/ags-dsh-session-persistence \
  "$profile_modules/ags-dsh-session-persistence"

# Step 4: add --patch to your existing DSH start command and keep the other options
exec dsh --profile web \
  --patch /opt/dsh/agent-runtime-session.cordis.yml \
  ...
```

### Post-build check

Run the plugin's own tests in the built image to confirm steps 1 and 2, that is, that the plugin can find and load the DSH modules:

```bash
docker run --rm --platform linux/amd64 --entrypoint node "$DSH_SESSION_IMAGE" \
  --test /usr/local/lib/node_modules/@tencentcloud/ags-dsh-session-persistence/index.test.js
```

With option 1 you can also run `make check-image`, which uses the exported `DSH_SESSION_IMAGE`. It passes when the output shows `fail 0`. An error like `does not provide an export named ...` means the DSH version in the image does not match the plugin; see [What a version mismatch looks like](#what-a-version-mismatch-looks-like).

### Post-start check

After the container starts, confirm steps 3 and 4.

A service that starts normally does not prove the plugin is active: a DSH that never loaded the patch and still uses JSONL starts normally too. Check the cloud data instead. After one turn of conversation in DSH, confirm that the newest Session carries a DSH header:

```bash
SESSION_ID="$(
  agr session list \
    --region "$AGR_REGION" \
    --cloud-endpoint "$SESSION_API_ENDPOINT" \
    --space-id "$SESSION_SPACE_ID" \
    --user-ids "$SESSION_USER_ID" \
    --limit 100 \
    --output json \
    --jq '(.Data.Sessions // []) | max_by(.CreateTime) | .SessionId // empty'
)"
agr session get \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --space-id "$SESSION_SPACE_ID" \
  --user-id "$SESSION_USER_ID" \
  --session-id "$SESSION_ID" \
  --output json \
  --jq '.Data.Session.State.CustomState | fromjson | .dshHeader.version'
```

`4` means the conversation was written to the cloud by this version of the plugin. [Section 5](#5-verify-the-integration) covers checking Events and verifying restore; the integration is only confirmed once restore succeeds.

If the container exits during startup with a cloud API error such as `SecretId is not found` in its log, the plugin loaded but its credentials are wrong: DSH lists cloud conversations through the plugin when it starts.

## 5. Verify the integration

### What to verify

The pre-built image and your own image are verified the same way. Confirm these four things:

1. **The cloud holds the messages and a complete turn**: the Session's Events include a finished turn.
2. **The running instance was really replaced**: after delete and recreate, the container ID differs and no volume was reused.
3. **The new process loaded the original history**: the new instance lists the original conversation and reads its messages.
4. **New turns keep being written to the cloud**: continuing the conversation, the model recalls the earlier marker and the new turn is written to the cloud too.

You can verify by hand in the Web UI or automatically with the script; both check the same things.

### Choose the image to verify

The commands in this section use `DSH_SESSION_IMAGE` to pick the image; start, recreate, and check must use the same one:

- **Pre-built image**: nothing to set; the default is `ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:v0.2.1-rc.2-session-persistence.2`.
- **Your own image**: export its name first in the terminal where you run these commands, for example `export DSH_SESSION_IMAGE=your-registry/your-dsh:version-session-persistence`. Both `make start` and `make check-image` use it.

Start DSH:

```bash
make start
docker inspect --format '{{.Config.Image}}' dsh-session-demo
```

The last line prints the image the container actually uses; confirm it is the one you expect. `make start` starts the container `dsh-session-demo` with the variables from `.env`, listens only on the loopback address `127.0.0.1:18080`, mounts no volume, and waits for DSH to print its sign-in URL:

```text
DSH is ready. Sign in at: http://127.0.0.1:18080/?token=...
```

The DSH 0.2 Web UI and API require sign-in. The token in the sign-in URL is regenerated every time the container starts; run `make url` to print it again at any time.

If you use your own image with start options different from this example's, start the container your own way and replace the address `http://127.0.0.1:18080` and the container name below with yours. For the script, set `DSH_BASE_URL` to DSH's address and `DSH_LAUNCH_URL` to the sign-in URL printed in the log.

### Verify in the Web UI

**Save a conversation.** Open the sign-in URL printed by `make start` in a browser; DSH signs you in and redirects to the home page. Check that the model shown below the input box matches `LLM_MODEL` in `.env`, then create a conversation and send:

```text
Remember this marker: blue-falcon-42. Reply only "Noted" and do not use tools.
```

After the reply, look up the newest Session in a terminal and check its Events:

```bash
SESSION_ID="$(
  agr session list \
    --region "$AGR_REGION" \
    --cloud-endpoint "$SESSION_API_ENDPOINT" \
    --space-id "$SESSION_SPACE_ID" \
    --user-ids "$SESSION_USER_ID" \
    --limit 100 \
    --output json \
    --jq '(.Data.Sessions // []) | max_by(.CreateTime) | .SessionId // empty'
)"
echo "$SESSION_ID"

agr session event list \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --space-id "$SESSION_SPACE_ID" \
  --user-id "$SESSION_USER_ID" \
  --session-id "$SESSION_ID" \
  --limit 200 \
  --output json \
  --jq '[(.Data.Events // [])[] | .Extensions | fromjson? | .dshEvent | select(. != null)] | {events: length, turns: [.[] | select(.type == "turn/end") | .data.reason.kind]}'
```

Expect output like `{"events":19,"turns":["completed"]}`: `completed` in `turns` means the turn was written to the cloud in full.

**Recreate the container.** Delete the current container and start a new one:

```bash
docker inspect --format '{{.Id}}' dsh-session-demo
make stop
make start
docker inspect --format '{{.Id}}' dsh-session-demo
```

The two container IDs should differ. The new container has no volume and no local conversation data.

**Restore the conversation.** The new container has a new token, so the old page's sign-in no longer works. Open the URL printed by the new container's `make start` in the browser again. The earlier conversation appears in the sidebar; open it to see the previous message and reply. In that conversation, send:

```text
What marker did I ask you to remember? Reply with only that marker and do not use tools.
```

The model should reply `blue-falcon-42`. The new question does not contain the marker, so the model can only answer correctly by reading the history restored from the cloud. Run the `agr session event list` command above again; `turns` should become `["completed","completed"]`.

### Verify with the script

The script automates the steps above. **Save a conversation:**

```bash
make seed
```

The script reads the sign-in URL from the container log and signs in to DSH, creates a DSH conversation, generates a random marker (like `session-proof-…`) and asks the model to remember it, then waits until the cloud Events contain a complete turn and confirms the cloud header exists. The Session ID and marker are saved in `.local/session.json`. Expected output:

```text
Session: <id>
Cloud header and completed turn verified. State: .local/session.json
Stop and remove the DSH container, start a fresh one without volumes, then run resume.
```

**Recreate the container and restore:**

```bash
docker inspect --format '{{.Id}}' dsh-session-demo
make stop
make start
docker inspect --format '{{.Id}}' dsh-session-demo
make resume
```

The two container IDs should differ. The script then checks that the new DSH process reads the original marker from the conversation history (`session/page`), that the model recalls the marker when asked a question that does not contain it, and that the new turn is written to the cloud in full. Expected output:

```text
Session: <the same id>
Persisted history loaded and a new turn completed: session-proof-...
This verifies sequential recovery, not concurrent writers or automatic failover.
```

To run another independent check, use a new state path, for example `python3 session_demo.py seed --state .local/another.json`, and the same path for resume; when running the script directly, set `DSH_LAUNCH_URL="$(make url)"` first. Do not write to that conversation from anywhere else during the test.

### Interpreting the results

The script cannot prove the running instance was replaced, so deleting and recreating the container, and the changed container ID, are part of the evidence.

When something fails, tell two cases apart: history loaded but the model answered wrongly is a model recall problem; history not loaded is a persistence problem.

## 6. Optional: other ways to run

### Changing the model service

This example's image configures the model service from these variables in `.env`, **with no rebuild needed**:

| Variable | Meaning | Default |
| --- | --- | --- |
| `LLM_BASE_URL` | OpenAI-compatible API address | `https://tokenhub.tencentmaas.com/v1` |
| `LLM_MODEL` | Model ID | `deepseek-v4-flash` |
| `LLM_API_KEY` | API key for the model service | None; required |

DSH 0.2 no longer reads `settings.yaml`. The model configuration comes from the `llm-pi-ai` and `agent-default-model` entries in the Cordis patch (see [Cordis patch](#cordis-patch)), which read their values from these environment variables when DSH starts:

```text
LLM_* variables in .env
        ↓
llm-pi-ai.providers.custom and agent-default-model in the Cordis patch
        ↓
read by DSH at startup
```

The API key is never written to a file: `apiKeyEnv: LLM_API_KEY` means DSH reads the key from that environment variable at runtime. When the patch keeps the sample model configuration, any empty variable makes the container exit during startup and the log shows `entrypoint: set LLM_...`; after you delete the `llm-pi-ai` and `agent-default-model` patch entries, these variables are not checked.

After changing `.env`, run `make stop` and `make start` to restart the container.

DSH records the model (provider and model ID) of each conversation and stores it with the conversation, and a restored conversation keeps that record. So after changing the model service, new conversations use the new model, while earlier ones still point at the old model; if the old model is no longer configured, continuing them fails. Switch to the currently configured model below the input box in the Web UI.

The `api` field in the patch sets the API type; DSH 0.2.1-rc.2 supports `openai-completions`, `openai-responses`, and `anthropic-messages`. To use another API type or configure several models, edit the [Cordis patch](./dockerfiles/agent-runtime-session.cordis.yml) and rebuild the image:

```bash
make build
make start DSH_SESSION_IMAGE=dsh-session:local
```

Without an image name, `make build` writes the local image `dsh-session:local` and does not overwrite the pre-built image.

### Multiple Agents in one space

An Agent here is an independent DSH application, such as a support assistant and a coding assistant, each with its own purpose and configuration. One Agent can run several containers or replicas at once; they still belong to that one Agent.

**By default, Agents sharing a space see each other's conversations.** The plugin looks up conversations by SessionSpace and `SESSION_USER_ID` only. If the support assistant and the coding assistant use the same space and the same UserId, the sidebar of either assistant's Web UI lists both sides' conversations, and either can open and continue the other's.

There are two ways to let each Agent see only its own conversations:

- **Use a different SessionSpace for each Agent.** Create one space per Agent and put it in `SESSION_SPACE_ID` in that Agent's `.env`. Simplest; no extra configuration.
- **Share one space and separate with `SESSION_AGENT_ID`.** Suits keeping all conversation data in one space; see below.

#### Using SESSION_AGENT_ID

`SESSION_AGENT_ID` is an Agent ID you define, unrelated to Tencent Cloud accounts or resource IDs; it only has to be unique within the space and stable. You can reuse an Agent ID from your own system, or assign one per Agent as below in each Agent's `.env`:

| Agent | Setting in `.env` |
| --- | --- |
| Support assistant (however many containers) | `SESSION_AGENT_ID=agt-10001` |
| Coding assistant | `SESSION_AGENT_ID=agt-10002` |

Every container or replica of one Agent must use the same ID; otherwise a replaced container cannot find the earlier conversations. After changing `.env`, run `make stop` and `make start` to restart the container.

With it set:

- each Agent's sidebar lists only the conversations it created;
- even with the ID of another Agent's conversation, opening it directly through the DSH API fails;
- conversations created before `SESSION_AGENT_ID` was set are no longer shown. They remain in the cloud and are not deleted; clear the variable and restart the container to see them again.

**How it works.** When the plugin creates a conversation, it writes the Agent ID into the Session's Metadata. Metadata is a set of custom key-value pairs on a Session that queries can filter on; the plugin lists conversations by filtering on this pair. This example uses the key `example.com/dsh-agent-id`. To use another key, for example one matching your system's naming, change `AGENT_METADATA_KEY` in both [plugin/index.js](./plugin/index.js) and [session_demo.py](./session_demo.py), then rebuild the image as at the end of [Changing the model service](#changing-the-model-service). After switching keys, conversations recorded under the old key are no longer shown.

Besides the Agent ID, Metadata can record other business identifiers such as tenant, business line, or channel for grouping and querying conversations. This example's plugin writes only the Agent ID; to record other identifiers, change `createStoredSession` in [plugin/index.js](./plugin/index.js) to add the Metadata when creating the Session, and rebuild the image.

#### Verification

1. Set `SESSION_AGENT_ID=agt-10001` in `.env`, run `make stop` and `make start`, and save one conversation as in [section 5](#5-verify-the-integration).
2. Change it to `agt-10002`, restart the container, and save another conversation. The sidebar now shows only this conversation, not the one from step 1.
3. Change it back to `agt-10001` and restart the container. The conversation from step 1 appears in the sidebar again and opens.

With the script, each `seed` needs a new state file, so give each Agent its own path, for example `python3 session_demo.py seed --state .local/agt-10001.json`, and use the same path for `resume`.

### Separating conversations by business user

**The Session service itself isolates conversations by user.** Each conversation belongs to the UserId given when it was created; listing, reading, appending Events, and deleting all take a UserId and only reach that UserId's conversations, and access with another UserId returns "session not found". The caller supplies the UserId and the Session service does not check that the caller is that user: a program holding cloud API credentials can use any UserId, so the application must pass the right user ID.

**This example's plugin uses one fixed UserId.** The plugin reads one user ID from `SESSION_USER_ID` at startup, and every conversation this DSH instance creates or queries uses it. The plugin cannot tell different users of one instance apart: the create, open, and list calls DSH 0.2.1-rc.2 makes to the persistence plugin carry conversation information only, not "which user is acting". So **one DSH instance maps to one user ID**, and everyone using the same instance sees the same conversations.

To let each business user see only their own conversations, give each business user a separate DSH instance: start one DSH container per user, with that user's ID from your system in `SESSION_USER_ID`.

| Business user | Setting in that user's instance `.env` |
| --- | --- |
| User A, ID `u-1001` in your system | `SESSION_USER_ID=u-1001` |
| User B, ID `u-1002` in your system | `SESSION_USER_ID=u-1002` |

When user A comes back later, start a new instance with the same `SESSION_USER_ID=u-1001` and their earlier conversations load; user B's instance cannot see user A's conversations. This needs no plugin change.

### Multi-replica deployment

This section covers running several DSH replicas (for example, several sandbox instances) to serve users: how conversations are used and handed over, and what problems to expect. A "replica" here is a DSH process from the same image with the same `AGR_REGION`, `SESSION_SPACE_ID`, `SESSION_USER_ID`, and `SESSION_AGENT_ID`. To run this example's image on AGS, first complete the adaptation in [Deploying to AGS](#deploying-to-ags).

#### Supported usage

| Scenario | Supported | Notes |
| --- | --- | --- |
| Different conversations handled by different replicas in parallel | Yes | Each replica handles its own conversations without affecting the others |
| One conversation handled by A first, then by B after A stops | Yes | When B receives the first message for the conversation, it reads the history back from the cloud and continues. Verified on 0.2.1-rc.2 (A stopped normally; B was a newly started container) |
| One conversation handled by several replicas at the same time | **No** | See "Why one conversation must have one replica" |
| Each turn handled by any replica, with requests landing anywhere | **No** | See "Approaches that are not supported" |

"A stops" means A's process has exited or restarted, so it no longer holds the conversation in memory. Merely stopping requests to A does not count: A keeps its old state, and a later write conflicts with the new replica; see below.

#### Why one conversation must have one replica

- Each replica reads the conversation into its own memory and numbers new records onward in memory.
- When written to the cloud, a record's EventId is `dsh-<conversation ID>-<sequence number>`. For the same EventId, the Session service treats an identical event as a duplicate request and succeeds; an event with different content is rejected with `ResourceInUse.EventIdDuplicate`, whose message is `EventId 已存在` ("EventId already exists").
- The cloud does not tell replicas that someone else wrote new content, and a replica does not re-read the history before each write. Two replicas that each number onward write to the same sequence number: the first write succeeds and the later one is rejected.
- The cloud history is not corrupted by this and stays contiguous. But the rejected replica's in-memory records no longer match the cloud, so messages for that conversation keep failing on that replica until it reloads from the cloud.

The plugin guarantees a single writer per conversation only inside one DSH process; it has no cross-process lease or lock.

#### Situations that trigger the conflict

1. **The old replica is still running.** A is not receiving requests for a conversation for now, but its process is alive and holds the old history in memory. After B takes the conversation over and keeps chatting, if a request lands on A again, A continues numbering from the old history, the write is rejected, that turn fails, and later turns keep failing. This is the typical case.
2. **Two replicas handle one conversation at almost the same time.** The replica that takes over later reads the turn the first one has not finished, records that turn as interrupted, writes repair records, and continues with its own turn. The first replica's reply for that turn cannot be written to the cloud, yet it still shows that turn as completed on its side; the error appears the next time a message is sent through it. Whether this happens depends on which replica writes first, so it does not happen every time.

#### What you see

- The UI shows `本轮运行失败 EventId 已存在` ("turn failed, EventId already exists") with error code `UNKNOWN`. The failing replica may also show only a generic internal-error message.
- Some failure paths leave no container log. These conflicts usually show up only as a UI error, and a failed foreground write is not logged; background write failures and final drain failures are logged as warnings that start with `session-persistence:` and name the conversation. Search for those warnings first, then check the entry point's routing logs.
- The same conversation works on the other replica, and the cloud history is contiguous.

#### How to confirm and recover

- **Confirm**: in your gateway or access logs, check whether the failing conversation's ID was sent to more than one replica.
- **Recover**: first make sure only one replica handles the conversation; the other replicas must stop executing and writing it, or taking over again conflicts anew. Then restart the failing replica: on its next request for the conversation it reloads the complete history from the cloud and continues. Measured: after a restart, that replica read the full history back and continued the conversation, and the cloud records stayed contiguous. Stopping requests to it is not enough; its in-memory records do not disappear.
- There is no way to "refresh" just that conversation on this replica; only restarting the replica, which reloads from the cloud, clears the old state. DSH's interface can unload one conversation (`AgentHandle.dispose()`), but the Web entry does not offer that operation; it is usable only when you manage conversation creation and teardown yourself, which this example does not do.

#### Steps when switching replicas

1. Let the old replica exit or restart. Merely stopping requests to it is not enough: it may still be running a turn or hold unflushed buffered events, and will then conflict with the new replica. Its in-memory state is cleared only when the process exits or restarts.
2. Make sure the new replica has not loaded this conversation yet. A replica that has already loaded it keeps using its in-memory records and does not refresh from the cloud; restart that replica first in that case.
3. Let requests land on the new replica. On its first message for the conversation, it reads the latest history from the cloud and continues.
4. Content the old replica had not written to the cloud yet, and the turn that was running at the time of the switch, are not continued automatically. That turn is recorded as interrupted, and the user needs to send it again.

#### Routing at your entry point

Sandbox instances are independent, so how requests are distributed is up to your own entry point. Recommended:

- Choose the replica by conversation ID, so one conversation always lands on the same replica while different conversations spread across replicas.
- The conversation ID is not in the request path. DSH's `session/prompt` and similar calls carry it in the request body as `sessionId` (`session/page` uses `address.sessionId`), so your entry point has to parse the body to route by conversation. If it cannot, pin by a client identity such as the user instead, so one user's conversations land on one replica.
- When a replica fails or is reclaimed, have the entry point reassign the conversation to another replica; the new replica picks it up from the cloud automatically.

#### State that replicas do not share

Conversation event records live in the cloud; every other kind of state is local to a replica and does not follow a conversation to another replica:

| State | Location | Effect |
| --- | --- | --- |
| Sign-in | Each replica generates its own sign-in token and the key that signs cookies, stored in `$DSH_HOME/.credentials.yaml` | A browser cookie does not validate on another replica; sign in again with that replica's URL. The token also changes on every start |
| Live event stream | The browser connects over one WebSocket to one replica, and events come only from that replica | When a request is sent to another replica, the UI does not show that turn's output live |
| Attachments | `$DSH_HOME/attachments/v1` | Attachments uploaded earlier are not found on another replica |
| Workspace files | The container's working directory (`/workspace` in this example) | The workspace contents are not there on another replica |
| Projection cache | `$DSH_HOME/storages` | Only a cache; rebuilt automatically on another replica |

So "stateless multi-replica" currently holds only for conversation records: history survives replacing a replica, but replicas are not interchangeable. If you need sign-in state or the event stream to be consistent across replicas, you have to handle it yourself, for example by provisioning the same signing key on all replicas and routing consistently at your entry point; this example does not implement it.

#### Approaches that are not supported

- **Requests landing on any replica.** A replica holds the writer and the in-memory state while it handles a conversation. Handing the next turn to another replica requires the old replica to unload the conversation first; the current Web entry offers no such operation, so only a process restart clears the old state.
- **Several replicas handling one conversation together.** This needs a cross-replica lease or lock plus forwarding of requests and events between replicas. This example does not implement it.

### Deploying to AGS

This example's image **cannot run directly in an AGS sandbox or Deployment** yet. The reason is not the persistence plugin but the network restrictions of the official DSH 0.2.1-rc.2 Web server. This section describes the adaptation needed, for reference if you implement it yourself.

These conclusions come from comparing the DSH 0.2.1-rc.2 source with the AGS patch used for DSH 0.1.1-rc.2. They have not been tested on AGS.

#### What DSH 0.1.1-rc.2 does

The DSH 0.1.1-rc.2 AGS image patches DSH at build time ([0001-support-ags-deployment-web.patch](../../../deployment-cookbook/deepseek-harness/all-in-one/dockerfiles/0001-support-ags-deployment-web.patch)) to lift these restrictions:

| Patch | Purpose |
| --- | --- |
| Allow `--host 0.0.0.0` | Lets the sandbox gateway reach DSH from outside the Pod |
| `--trusted-host` accepts `*.suffix` wildcards | Sandbox access domains change per instance; one wildcard covers them |
| The browser Origin may be another trusted HTTPS domain | Requests are not rejected when the gateway rewrites Host to an internal domain and keeps the browser's public Origin |
| Adds `--allow-remote-management` | Lets trusted domains call management APIs otherwise limited to the local machine |

#### How DSH 0.2.1-rc.2 behaves

| Aspect | Official DSH 0.2.1-rc.2 | What deploying to AGS needs |
| --- | --- | --- |
| Listen address | Accepts one concrete IP only and rejects `0.0.0.0` | Bind the Pod's own IP, as this example's entrypoint.sh already does; confirm the gateway reaches DSH through the Pod IP |
| Trusted domains | Accepts a full `domain` or `domain:port` only, no wildcards | Get this instance's full access domain at startup and pass it to `--trusted-host`; confirm whether the instance ID or access domain is available inside the sandbox |
| Host and Origin | The browser request's Origin must match its Host | Nothing to do if the gateway keeps the original Host; if it rewrites Host, port the patch's Origin relaxation to 0.2.1-rc.2, or add a reverse proxy in the container that normalizes Host |
| Management APIs | Every API requires sign-in, with no local/remote distinction; `--allow-remote-management` is no longer needed | Nothing to do |
| Sign-in | The first visit needs the `?token=` from the startup log, regenerated on every start | Get the sign-in URL from the instance log, and use `--public-url` so the printed URL points at the gateway address; for script verification, set that URL as `DSH_LAUNCH_URL` |

#### Implementation options

| Option | Changes | Notes |
| --- | --- | --- |
| Port the AGS patch | Port the wildcard `--trusted-host` and Origin relaxation from the patch to `dsh-web-app` and `dsh-client-connection` in DSH 0.2.1-rc.2, and build the image from the patched DSH | Same approach as 0.1.1-rc.2, but you maintain a DSH patch and port it again on every DSH upgrade |
| Do not modify DSH | Bind the Pod IP, compute the full access domain at startup for `--trusted-host`, and add a reverse proxy in the container if the gateway rewrites Host | No DSH patch to maintain. The reverse proxy bypasses DSH's own Host/Origin checks, so the gateway must enforce access control |

Both options touch only DSH's start options and image; the persistence plugin and the Cordis patch stay unchanged.

## 7. Clean up

Stop the local container, preview what will be cleaned up, then delete:

```bash
make stop
python3 session_demo.py cleanup
# After checking the preview, delete:
python3 session_demo.py cleanup --delete
```

Without `--delete`, the script only lists the conversations it would delete. With `SESSION_AGENT_ID` set, only that Agent's conversations are included; without it, every conversation of that UserId in the space is. When the space is shared, check the preview before deleting.

After every conversation prints `deleted`, remove the local state files:

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

## 8. Limits

This example's persistence plugin handles the normal write path only. These cases are not handled:

- **Existing history is not migrated.** With the plugin enabled, DSH reads and writes cloud conversations only, and existing local conversations are no longer visible. Conversations written by the DSH 0.1.1-rc.2 plugin (header `version` 0) do not appear in the list, and opening one reports an unsupported format. Use a different SessionSpace or `SESSION_AGENT_ID` for each version.
- **Failure partway through a write.** The plugin appends Events one by one and advances the sequence only after the whole batch succeeds. On a failure, Events already written stay in the cloud, the unwritten records stay in the buffer, and the next flush retries the whole batch; Events that already landed are resent with the same Event ID, which the Session service treats as a duplicate request. The plugin backs off and retries automatically on cloud API rate limits. If the container exits before a retry succeeds, the buffered records are lost.
- **Several writers.** The plugin guarantees one writer per conversation within a single DSH process only, with no coordination across instances. When several DSH instances handle the same conversation, the first write succeeds and the later one is rejected by the cloud (`EventId 已存在`). The cloud history stays contiguous, but the rejected replica keeps failing on that conversation afterwards and has to be restarted. See [Multi-replica deployment](#multi-replica-deployment).
- **An in-flight turn is not resumed.** If the DSH process exits mid-turn, no other process continues that turn. When a new process opens the conversation, DSH appends closing records for the interrupted turn; the written history is kept, and the user has to send the request again.
- **Only conversation state is restored.** Files, running processes, and long-lived model connections are not.
- **Very large Events.** The plugin writes each Event whole without splitting. When a tool returns a lot of content, one Event can exceed the Session API's size limit and fail to write.
- **Number of conversations.** Each time DSH lists conversations, the plugin queries all of the user's Sessions and reads the Event count once per conversation. With many conversations, the list loads more slowly and rate limits are more likely.
- **Integrity checks.** Loading sorts by the original events and checks that the sequence is contiguous and the records are well formed. This catches most incomplete writes but not every case.

Before using this plugin in production, or letting several DSH instances write the same conversation, add handling for the cases above.

## Troubleshooting

- **Startup fails with `does not provide an export named ...`**: the DSH version does not match the plugin; see [What a version mismatch looks like](#what-a-version-mismatch-looks-like).
- **Startup fails with `--host 0.0.0.0 is an unspecified (wildcard) address`**: the official DSH 0.2 rejects wildcard addresses; bind a concrete IP, see [Start options](#start-options).
- **The page or API returns `dsh web authentication required`**: you are not signed in or the token expired. Run `make url` and open the URL printed for the current container.
- **Credential or space errors**: check the account, region, SpaceId, permissions, and temporary credential expiry used by `agr` and by the container, separately.
- **The container exits right after starting**: run `docker logs dsh-session-demo`. A cloud API error such as `SecretId is not found` means the `TENCENTCLOUD_*` credentials in `.env` are wrong: DSH lists conversations through the persistence plugin at startup and fails when the plugin's credentials are invalid. A line starting with `entrypoint: set ...` names the variables to fill in.
- **Connection refused**: wait for `make start` to print the sign-in URL and check the container log. If you changed `PORT`, change `DSH_BASE_URL` for the script to match.
- **Model call errors**: check `LLM_BASE_URL`, `LLM_MODEL`, and `LLM_API_KEY` in `.env`, and the account's model permissions. Session credentials do not include model permissions.
- **Old conversations fail after changing the model**: DSH records each conversation's model, and old conversations still point at the old one. Switch to the currently configured model below the input box in the Web UI; see [Changing the model service](#changing-the-model-service).
- **The new container does not see the original conversation**: make sure the new container's `AGR_REGION`, `SESSION_SPACE_ID`, `SESSION_USER_ID`, and `SESSION_AGENT_ID` match those used when writing, and confirm with `docker inspect --format '{{.Config.Image}}' dsh-session-demo` that it uses an image with the plugin. Conversations written by DSH 0.1.1-rc.2 are not visible in this version.
- **The UI shows `本轮运行失败 EventId 已存在` (turn failed, EventId already exists)**: the same conversation was handled by several replicas, or a request landed on a replica that still holds old history. The conversation keeps failing on that replica until it is restarted. For how to investigate and how to switch replicas, see [Multi-replica deployment](#multi-replica-deployment).
- **Non-contiguous history** (`non-contiguous DSH event log`): stop writing first, then investigate the incompletely written events. Do not delete events to hide the error.
- **Several users**: every conversation in this example uses the same `SESSION_USER_ID`. To separate conversations by business user, see [Separating conversations by business user](#separating-conversations-by-business-user).

## Appendix: local unit tests

These checks touch no cloud resources and are for self-testing after changing the plugin or the script. They need Node.js 24 and pnpm 11.19.0.

```bash
make setup
make check
# Run the plugin tests in an image, the one named by DSH_SESSION_IMAGE (the pre-built image by default):
make check-image
```

The plugin tests use DSH 0.2.1-rc.2's persistence interface and validation directly, and cover event projection, conversation creation and restore, single-writer ownership, failure retry, and history loading. They do not replace the real seed → new container → resume flow.
