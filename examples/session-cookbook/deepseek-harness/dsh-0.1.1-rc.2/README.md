# Persist DeepSeek Harness 0.1.1-rc.2 conversations with Agent Runtime Session

[中文](./README_zh.md) | [Choose another DSH version](../README.md)

DeepSeek Harness (DSH) stores conversations in JSONL files on local disk. When DSH runs in a container with no volume mounted, deleting the container also deletes the conversation history. This example uses a persistence plugin to write DSH conversations to Agent Runtime Session in the cloud: after you delete the container and start a fresh one, you can still load the original conversation and keep talking.

It covers conversation persistence only. To also keep workspace files and route later requests back to the same workspace, see [Session and workspace association](../../../deployment-cookbook/brain-hands-session/README.md).

## Versions and dependencies

This guide applies to **DSH 0.1.1-rc.2**. The plugin uses DSH's internal modules directly, and these modules changed incompatibly between some DSH versions, so DSH and its dependencies must match the table below. For a new integration, or a DSH installed from the official npm package, prefer the [DSH 0.2.1-rc.2 example](../dsh-0.2.1-rc.2/README.md).

| Dependency | Requirement | Notes |
| --- | --- | --- |
| DSH `@deepseek-ai/dsh` | Exactly `0.1.1-rc.2` | The pre-built image is built from the DSH source tag `dsh-v0.1.1-rc.2` with its own lockfile, plus an AGS adaptation patch; see the [all-in-one image build guide](../../../deployment-cookbook/deepseek-harness/all-in-one/dockerfiles/README.md) |
| DSH internal modules: `@deepseek-ai/cordis`, `dsh-session`, `dsh-session-persistence`, `schemastery` | Exactly `4.0.1`, `0.1.1-rc.2`, `0.1.1-rc.2`, `3.18.1` | The plugin shares these modules with DSH, so their versions must match `peerDependencies` in [plugin/package.json](./plugin/package.json) exactly |
| Cordis plugins: `@deepseek-ai/cordis-plugin-hmr`, `cordis-plugin-loader`, `cordis-plugin-include`, `cordis-plugin-timer` | Exactly `1.0.16`, `1.0.2`, `1.0.6`, `1.1.3` | DSH's own dependencies. With newer versions, DSH 0.1.1-rc.2 does not start; see below |
| Node.js | 24.x | The pre-built image is based on `node:24.8.0-bookworm-slim` |
| pnpm | Exactly `11.19.0` | Installs the plugin's dependencies, matching [plugin/pnpm-lock.yaml](./plugin/pnpm-lock.yaml) |
| `tencentcloud-sdk-nodejs-ags` | Exactly `4.1.302` | The SDK the plugin uses to call the Session API, pinned by the lock file |
| Docker, Python, `agr` | Able to run `linux/amd64`; 3.10 or later; v0.7.0 or later | See [Local tools](#local-tools) |

The pre-built image already meets the table. When you install DSH 0.1.1-rc.2 yourself from the official npm package, note the following:

1. **Always name the version.** `npm install -g @deepseek-ai/dsh` without a version installs whatever is newest on npm (currently 0.2.1-rc.2), and loading the plugin fails with `does not provide an export named 'PersistenceCoordinator'`. For DSH 0.2.1-rc.2, use the plugin in [dsh-0.2.1-rc.2](../dsh-0.2.1-rc.2/README.md).
2. **Pin DSH's indirect dependencies.** DSH 0.1.1-rc.2 declares version ranges for its Cordis dependencies (for example `^4.0.1`), and npm installs the newest version in range, such as cordis 4.0.5 and cordis-plugin-hmr 1.0.20. These are incompatible with DSH 0.1.1-rc.2: even without the plugin, DSH fails at startup with `user patch-layer watching requires the Cordis HMR service`. npm `overrides` does not finish resolving this set of dependencies in reasonable time; install DSH with pnpm in a separate directory and pin the versions instead, as shown below.
3. **The official DSH 0.1.1-rc.2 Web server listens on `127.0.0.1` only.** It rejects `--host 0.0.0.0` and other addresses, so in a container it cannot be reached through a published port. The pre-built image's AGS adaptation patch lifts this restriction; to run in a container or on AGS, use the pre-built image or build one yourself as in the [all-in-one image build guide](../../../deployment-cookbook/deepseek-harness/all-in-one/dockerfiles/README.md).
4. **DSH's internal modules are in a different place than in the pre-built image.** In the pre-built image they are in `/usr/local/lib/node_modules/@deepseek-ai`. With an npm 11 global install they are in `/usr/local/lib/node_modules/@deepseek-ai/dsh/node_modules/@deepseek-ai`; with the pnpm install below, in `/opt/dsh/node_modules/@deepseek-ai`. Integrate the plugin with [option 2](#option-2-integrate-in-your-own-dockerfile) and set `DSH_MODULES` to the actual directory; also change `m=` in the script under [Check your image](#check-your-image) to that directory.

To install with pnpm and pin the versions, put these two files in `/opt/dsh` and run `pnpm install --prod` with pnpm 11.19.0. `allowBuilds` lets the native modules DSH depends on run their install scripts. After the install, the DSH entry point is `/opt/dsh/node_modules/@deepseek-ai/dsh/lib/bin.js`.

`package.json`:

```json
{
  "name": "dsh-0.1.1-rc.2",
  "private": true,
  "dependencies": {
    "@deepseek-ai/dsh": "0.1.1-rc.2"
  }
}
```

`pnpm-workspace.yaml`:

```yaml
overrides:
  '@deepseek-ai/cordis': 4.0.1
  '@deepseek-ai/cordis-plugin-hmr': 1.0.16
  '@deepseek-ai/cordis-plugin-loader': 1.0.2
  '@deepseek-ai/cordis-plugin-include': 1.0.6
  '@deepseek-ai/cordis-plugin-timer': 1.1.3
  '@deepseek-ai/schemastery': 3.18.1
nodeLinker: hoisted
allowBuilds:
  '@deepseek-ai/dsh-subprocess-local': true
  '@google/genai': true
  koffi: true
  node-pty: true
  protobufjs: true
```

## Quick start

With this example's pre-built image, which already includes the persistence plugin, you can save a conversation and restore it in a few commands. From this directory:

```bash
cp .env.example .env            # fill in credentials and the model API key; see section 2
set -a; . ./.env; set +a
agr session space create \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --name dsh-session-demo \
  --output json \
  --jq '.Data.SessionSpace.SpaceId'
# put the printed SpaceId in SESSION_SPACE_ID in .env, then reload it:
set -a; . ./.env; set +a

make start                      # start the pre-built image
curl -sf -o /dev/null --retry 60 --retry-delay 2 --retry-all-errors --max-time 5 http://127.0.0.1:18080/ || docker logs --tail 20 dsh-session-demo
make seed                       # save a turn that contains a marker
make stop && make start         # delete the container and start a fresh one
curl -sf -o /dev/null --retry 60 --retry-delay 2 --retry-all-errors --max-time 5 http://127.0.0.1:18080/ || docker logs --tail 20 dsh-session-demo
make resume                     # the new container loads the history; the model names the marker
```

The readiness check retries for about 2 minutes and prints the last 20 lines of the container log if it times out. [Section 4](#4-verify-the-integration) explains each step and its expected output; clean up with [section 6](#6-clean-up) when you are done. To integrate the plugin into your own DSH, see [section 3](#3-integrate-the-plugin-into-your-dsh).

## 1. How the integration works

### Integration point

DSH decides where conversations are stored through its **SessionPersistence extension point**; the built-in implementation is the `session-persistence-jsonl` plugin, which writes local files. This example provides a plugin for the same extension point, `@tencentcloud/ags-dsh-session-persistence`, and at DSH startup a Cordis patch disables the JSONL plugin and enables this one. Cordis is DSH's plugin framework; a patch is a YAML file that changes which plugins load without modifying DSH's code. The rest of DSH — model calls, tool execution and the Web UI — needs no changes.

```text
DSH writes conversation records  →  the plugin writes them to the cloud  →  Session and Events in the SessionSpace
                                                                                    │
A new DSH process  ←  the plugin reads the history back  ←──────────────────────────┘
```

### Conversation lifecycle

| Stage | What happens |
| --- | --- |
| Saving starts | After the first message in a new conversation, the plugin creates the matching cloud Session with `CreateSession`, using the DSH conversation ID as the Session ID, and stores the DSH conversation metadata (the header) in it. A conversation that is created but never sent a message is not written to the cloud. |
| Later writes | Each time DSH appends to the conversation log, the plugin turns the entry into an Event and appends it to that Session with `AppendEvent`. |
| A new process lists conversations | When DSH lists conversations after starting, the plugin queries this user's Sessions in the SessionSpace and returns only those with a DSH header; with `SESSION_AGENT_ID` set, only that Agent's. The conversation list in the Web UI sidebar comes from here. |
| Opening an existing conversation | The plugin reads back the header and every Event, sorts them by sequence number, checks that the sequence is contiguous, and hands them to DSH to rebuild the conversation. |

The plugin creates the cloud Session when it first writes; you do not create it by hand.

### Data conventions

Besides the standard Session fields, the plugin uses these custom fields to store what DSH needs to restore a conversation:

| Data | Location | Purpose |
| --- | --- | --- |
| DSH conversation header | `State.CustomState.dshHeader` | Identifies a DSH conversation and rebuilds its metadata |
| The original DSH event | the Event's `Extensions.dshEvent` | Rebuilds the conversation log verbatim |
| Event ID | `dsh-<conversation ID>-<sequence number>` | On a retried write, the Session service uses it to recognize a duplicate request |
| Message text and reasoning | `Content.Parts`, reasoning flagged with `Thought` | Readable by other systems; not used by DSH when restoring |
| Tool calls and results | `Content.Parts[].FunctionCall` / `FunctionResponse` | Same as above |
| Some configuration changes | `Actions.StateDelta` | Same as above |
| Event type, sequence, turn markers | `Event.Metadata`, including `Partial`, `TurnComplete`, `Interrupted` | Same as above |

DSH restores a conversation from two places only:

- **`State.CustomState.dshHeader`** (on the Session): marks the Session as a DSH conversation. Without it, the Session does not appear in the conversation list and cannot be opened.
- **`Extensions.dshEvent`** (on each Event): holds the complete event content, which restore replays record by record. An Event without it is skipped.

Both field names and their formats are defined by this plugin; the Session service only stores them as they are and does not interpret, validate, or convert them.

### Before you integrate

These points affect how existing conversations behave once the plugin is enabled; [section 7](#7-limits) has the details:

- **Existing local JSONL history is not migrated to the cloud.** With the plugin enabled, DSH sees only cloud conversations.
- **Do not let several DSH instances write the same conversation at once.** Several instances can share a space and each handle different conversations, but the plugin does not coordinate concurrent writes to one conversation.
- **Conversations are restored, working environments are not.** Files, running processes and live model connections are not restored; if an instance exits mid-turn, that turn has to be sent again.

## 2. Prepare tools and cloud resources

### Local tools

- Docker able to run `linux/amd64` images, Python 3.10 or later, and `jq`.
- Install `agr` (the AGR CLI) **v0.7.0 or later**. This guide uses the `agr session` commands, available since v0.7.0, on the host to create, inspect and clean up SessionSpaces and Sessions. For first-time setup, follow the [official AGR CLI credential guide](https://github.com/TencentCloudAgentRuntime/ags-cli#initialize-cli-credentials), then run `agr status` and `agr doctor`.

### Cloud resources and conversation identity

The plugin uses these identifiers to decide where each conversation is stored:

| Identifier | Provided by | Role |
| --- | --- | --- |
| Region `AGR_REGION` | Your configuration | Region of the SessionSpace; the plugin and `agr` must use the same one |
| SessionSpace `SESSION_SPACE_ID` | You, created or chosen in advance | Logical space for storing and managing Sessions |
| User `SESSION_USER_ID` | Your configuration | An application-defined user ID, unrelated to Tencent Cloud accounts. The plugin reads it once at startup and uses it for every conversation of that instance. To separate conversations by business user, see [Separating conversations by business user](#separating-conversations-by-business-user) |
| Session ID | The DSH conversation ID | The plugin creates the matching cloud Session when it writes; no manual creation needed |
| Agent ID `SESSION_AGENT_ID` | Defined by you, optional | A business-defined Agent identifier. Tells Agents apart when several share one space; not set means no distinction. See [Multiple Agents in one space](#multiple-agents-in-one-space) |

To restore a conversation, the new process must access it in **the same region, SessionSpace and user**, with read permission, and with the same `SESSION_AGENT_ID` if one is set. If any of these differ, the new process cannot see the conversation.

### Credentials

This guide uses three kinds of credentials, each for a different purpose:

| Credential | Used by | Purpose | Permissions |
| --- | --- | --- | --- |
| `TENCENTCLOUD_SECRET_ID` and `TENCENTCLOUD_SECRET_KEY` in `.env` | The persistence plugin in the container | Reading and writing Sessions while DSH runs | Create, list and read Sessions; append and read Events |
| The credentials configured when initialising `agr` | `agr` commands on the host | Creating the space, verification and cleanup | Manage SessionSpaces; read and delete Sessions |
| The CAM role `AGR_ROLE_ARN` | AGS sandboxes | Only for running DSH in the cloud in [section 5](#5-optional-other-ways-to-run) | See section 5 |

The plugin does not read `agr`'s configuration. Make sure the first two belong to the same account; otherwise Sessions written by the plugin cannot be found with `agr`. Use a sub-account or temporary credentials rather than your main account key.

### Configure environment variables

From this directory:

```bash
cp .env.example .env
# Edit .env with dedicated test credentials.
set -a
. ./.env
set +a
agr status --cloud-endpoint "$SESSION_API_ENDPOINT"
```

`.env` is shared by the host and the container:

- Variables loaded with `. ./.env` between `set -a` and `set +a` are exported automatically for the `agr` commands and verification scripts on the host. Rerun these three lines after editing `.env`.
- `make start` passes the same file to the container with `docker run --env-file .env`. Restart the container after editing `.env`.

Docker reads `--env-file` without parsing quotes or expressions, so keep `.env` to plain `KEY=value` lines with no quotes around values, and keep it out of version control.

For what each variable means, see [Cloud resources and conversation identity](#cloud-resources-and-conversation-identity); the table below covers the values to fill in.

| Variable | Required | Used by | Description |
| --- | --- | --- | --- |
| `AGR_REGION` | Yes | Plugin, `agr` | Example default `ap-shanghai`; must match the SessionSpace's region |
| `SESSION_SPACE_ID` | Yes | Plugin, `agr` | The SessionSpace that stores conversations; see [Create or reuse a SessionSpace](#create-or-reuse-a-sessionspace) |
| `SESSION_USER_ID` | Yes | Plugin, `agr` | Example default `dsh-demo-user`; keep it the same for restore and cleanup |
| `SESSION_AGENT_ID` | No | Plugin, verification script | Optional; separates conversations by Agent. When unset, nothing is separated |
| `TENCENTCLOUD_SECRET_ID`, `TENCENTCLOUD_SECRET_KEY` | Yes | Plugin | Cloud API credentials the plugin uses to read and write Sessions; see [Credentials](#credentials) |
| `TENCENTCLOUD_SESSION_TOKEN` | With temporary credentials | Plugin | Token for temporary credentials; refresh it and restart the container when it expires |
| `SESSION_API_ENDPOINT` | No | Plugin, `agr` | Cloud API endpoint; defaults to `ags.tencentcloudapi.com`. Change it only to reach another environment |
| `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` | Yes | Example image | The model service DSH calls; TokenHub's `deepseek-v4-flash` by default, see [Changing the model service](#changing-the-model-service). Used only by this example's image; when integrating into your own DSH you can keep its existing model configuration |
| `AGR_DOMAIN` | When running in the cloud | Example image | Used only for [Running in the cloud](#running-in-the-cloud); leave the default `tencentags.com` for local runs |

### Create or reuse a SessionSpace

A SessionSpace is a logical space for storing and managing Sessions, not a one-to-one binding to an Agent or runtime instance. Multiple instances of one Agent, and multiple different Agents, can share a space. Split spaces according to business, environment and access-management requirements, not Agent or instance counts; for example, manage test and production environments in separate spaces.

A SessionSpace is not an execution workspace and does not share local files between instances. To keep Agents apart within a shared space, see [Multiple Agents in one space](#multiple-agents-in-one-space).

Create or reuse one space for this example. Adding, restarting or replacing runtime instances does not require another space. Put an existing space's ID in `SESSION_SPACE_ID` in `.env`, or run the following command to create a space for this example:

```bash
agr session space create \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --name dsh-session-demo \
  --description "DSH Session integration" \
  --output json \
  --jq '.Data.SessionSpace.SpaceId'
```

The command prints the new SpaceId. Open `.env`, replace the placeholder in `SESSION_SPACE_ID=space-replace-me` with it, save, and reload:

```bash
set -a
. ./.env
set +a
```

## 3. Integrate the plugin into your DSH

### Minimal changes

Integrating Session takes these four changes:

| Step | Change | When | How to confirm |
| --- | --- | --- | --- |
| 1. Install the plugin | Copy this repository's `plugin` directory (`index.js`, `package.json`, `pnpm-lock.yaml`) into the image, run `pnpm install --prod --frozen-lockfile`, and place it under `@tencentcloud/ags-dsh-session-persistence` in the Node.js global modules directory | Image build | See "Post-build check" below |
| 2. Share modules with DSH | Delete the `@deepseek-ai` directory under the plugin's `node_modules` and symlink `cordis`, `dsh-session`, `dsh-session-persistence` and `schemastery` to where DSH is actually installed, so the plugin and DSH use the same modules | Image build | See "Post-build check" below |
| 3. Register the plugin in the Web profile | The Web profile is the directory DSH loads plugins from when it runs in Web mode. Before DSH starts, link the plugin to `$DSH_HOME/profiles/web/node_modules/@tencentcloud/ags-dsh-session-persistence`; DSH loads it from there by name | Container start | The path exists and points to the step 1 install directory |
| 4. Enable the plugin | Copy the [Cordis patch](./dockerfiles/agent-runtime-session.cordis.yml) into the image, add `--patch <patch path>` to the `dsh web` start command, and give the container the environment variables the plugin needs | Container start | See "Post-start check" below |

For step 4, the plugin needs `AGR_REGION`, `SESSION_SPACE_ID`, `SESSION_USER_ID`, `TENCENTCLOUD_SECRET_ID` and `TENCENTCLOUD_SECRET_KEY`, plus the optional `TENCENTCLOUD_SESSION_TOKEN`, `SESSION_API_ENDPOINT` and `SESSION_AGENT_ID`; see [section 2](#2-prepare-tools-and-cloud-resources).

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
```

- The first entry disables DSH's built-in JSONL persistence plugin by `id`.
- `insert` adds this plugin. `name` is the plugin's package name; DSH looks for it by this name in the Web profile's `node_modules`, so it must match the registration path in step 3.
- `!!js process.env.*` in `config` reads each value from an environment variable when DSH starts, so credentials are never written into the image or the patch. `agentId` is optional; see [Multiple Agents in one space](#multiple-agents-in-one-space).

The keys under `config` (`region`, `spaceId`, `userId` and so on) are defined by the plugin and cannot be renamed; the environment variable names on the right can be changed as needed.

### Required versus example choices

Beyond the Session integration, this example's image makes some choices of its own. When integrating into your own DSH, tell them apart with this table:

| Item | Required for the integration | In your own DSH |
| --- | --- | --- |
| The persistence plugin, the Cordis patch, and the plugin's environment variables | Yes | Add them with the four steps above |
| DSH module versions matching the plugin | Yes | See "Check your image" below |
| The plugin's install directory | No | Can change, but must match the registration path in step 3 |
| Start arguments: listen address, port 3080, trusted hosts, `--allow-remote-management` | No | Keep your DSH's own start arguments and just add `--patch` |
| Model configuration: settings.yaml generated from `LLM_*` variables ([configure-model.mjs](./dockerfiles/configure-model.mjs)), TokenHub, `deepseek-v4-flash` | No | Keep your DSH's own model configuration |
| The `linux/amd64` platform | No | The example image's build platform; the plugin itself is platform-independent |

### Check your image

The plugin depends on some internal DSH modules, whose versions must match `peerDependencies` in the plugin's [package.json](./plugin/package.json). Check your image with the following, replacing `your-registry/your-dsh:version`:

```bash
docker run --rm --platform linux/amd64 --entrypoint sh your-registry/your-dsh:version -c '
m=/usr/local/lib/node_modules/@deepseek-ai
ok() { echo "OK    $1"; }; bad() { echo "FAIL  $1"; fail=1; }
[ -f "$m/dsh/lib/bin.js" ] && ok "DSH entry $m/dsh/lib/bin.js" || bad "DSH entry not found: $m/dsh/lib/bin.js"
command -v npm >/dev/null && ok "npm" || bad "npm not found"
case "$(node -v 2>/dev/null)" in v24.*) ok "Node.js $(node -v)";; *) echo "WARN  Node.js $(node -v 2>/dev/null || echo none); the plugin is verified on Node.js 24 only";; esac
for p in cordis:4.0.1 dsh-session:0.1.1-rc.2 dsh-session-persistence:0.1.1-rc.2 schemastery:3.18.1; do
  n=${p%%:*}; want=${p#*:}
  have=$(node -p "require(\"$m/$n/package.json\").version" 2>/dev/null) || have=none
  [ "$have" = "$want" ] && ok "$n $have" || bad "$n $want required, found $have"
done
exit ${fail:-0}'
```

- **No `FAIL`** — your image has the same layout as this example's base image; use option 1.
- **`WARN`** — Node.js is not version 24. You can still build, but run the post-build check afterwards.
- **DSH entry or modules not found** — DSH is not in that directory. Use option 2 and set its `DSH_MODULES` to where DSH is actually installed.
- **npm not found** — install npm in your image, or use option 2 and adjust the install steps.
- **Module versions differ** — change them in `peerDependencies` of [package.json](./plugin/package.json), run `pnpm install` in the `plugin` directory to update `pnpm-lock.yaml`, then confirm compatibility with the post-build check below.

### Option 1: build with this example's Dockerfile

If your image passes the check, use this example's [Dockerfile](./dockerfiles/Dockerfile) to add the plugin on top of it. Export the output image name first; the build, start and check commands that follow all use it:

```bash
export DSH_SESSION_IMAGE=your-registry/your-dsh:version-session-persistence
make build DSH_IMAGE=your-registry/your-dsh:version
```

Name the output after its base image — same repository and version, with `-session-persistence` appended to the tag — so the original image and the one with the plugin are easy to tell apart. This example's pre-built image follows the same convention: `deepseek-harness:v0.1.1-rc.2-ags.4-session-persistence.4`, where the trailing `.4` is the plugin's release number.

Besides the four steps, this example's Dockerfile uses this example's [entrypoint.sh](./dockerfiles/entrypoint.sh) as the start command. Following "Required versus example choices", if your image has its own start arguments or model configuration:

- **Start arguments** — merge your image's start arguments into entrypoint.sh, keeping its plugin registration and `--patch`.
- **Model configuration** — at startup entrypoint.sh sets `llm-pi-ai.providers.custom` and `agent-default-model` in `$DSH_HOME/settings.yaml` from the `LLM_*` variables and leaves the rest unchanged. To keep your own model configuration, remove the line that runs `configure-model.mjs` from entrypoint.sh.

### Option 2: integrate in your own Dockerfile

If your image does not pass the check, or you want to integrate the plugin in your own build, add the following to your Dockerfile and start script. Your build context must include this example's `plugin` directory and the Cordis patch; exclude `plugin/node_modules` in `.dockerignore` so dependencies installed on your machine are not copied into the image.

Add steps 1 and 2 to your Dockerfile:

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
    && rm -rf "$PLUGIN_DIR" \
    && mv /tmp/ags-dsh-session-persistence "$PLUGIN_DIR" \
    && rm -rf /root/.npm /root/.local/share/pnpm/store

# Step 2: link the plugin's DSH dependencies to DSH's install location so both share one copy
RUN rm -rf "$PLUGIN_DIR/node_modules/@deepseek-ai" \
    && mkdir -p "$PLUGIN_DIR/node_modules/@deepseek-ai" \
    && for package in cordis dsh-session dsh-session-persistence schemastery; do \
         ln -s "$DSH_MODULES/$package" "$PLUGIN_DIR/node_modules/@deepseek-ai/$package"; \
       done

# The Cordis patch used in step 4
COPY agent-runtime-session.cordis.yml /opt/dsh/agent-runtime-session.cordis.yml
```

Add steps 3 and 4 to your start script:

```sh
# Step 3: register the plugin in the Web profile; the path must match PLUGIN_DIR in the Dockerfile
profile_modules="${DSH_HOME:-/root/.dsh}/profiles/web/node_modules/@tencentcloud"
mkdir -p "$profile_modules"
ln -sfn /usr/local/lib/node_modules/@tencentcloud/ags-dsh-session-persistence \
  "$profile_modules/ags-dsh-session-persistence"

# Step 4: add --patch to your existing dsh web start command and keep the other arguments
exec node --expose-internals \
  /usr/local/lib/node_modules/@deepseek-ai/dsh/lib/bin.js \
  web \
  --patch /opt/dsh/agent-runtime-session.cordis.yml \
  ...
```

### Post-build check

Run the plugin's own tests in the output image to confirm steps 1 and 2 — that the plugin can find and load the DSH modules:

```bash
docker run --rm --platform linux/amd64 --entrypoint node "$DSH_SESSION_IMAGE" \
  --test /usr/local/lib/node_modules/@tencentcloud/ags-dsh-session-persistence/index.test.js
```

With option 1 you can also run `make check-image`, which uses the exported `DSH_SESSION_IMAGE`. The check passes when the output shows `fail 0`.

### Post-start check

After starting the container, confirm steps 3 and 4.

A service that starts normally is not proof that the plugin is in effect: DSH without the patch, still using JSONL, starts just as well. Rely on the cloud data instead. After one turn of conversation in DSH, confirm that the latest Session has a DSH header:

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
  --jq '.Data.Session.State.CustomState | fromjson | has("dshHeader")'
```

`true` means the plugin wrote the conversation to the cloud. Checking Events and verifying restore are covered in [section 4](#4-verify-the-integration); the integration is complete only once restore succeeds.

If the container exits at startup with a cloud API error such as `SecretId is not found` in its log, the plugin is loaded but its credentials are wrong: DSH lists conversations through the plugin at startup.

## 4. Verify the integration

### What to verify

The pre-built image and your own image are verified the same way. Confirm these four things:

1. **The cloud holds the messages and a completed turn** — the Session's Events include a finished turn.
2. **The running instance was really replaced** — after deleting and recreating, the container ID differs and no volume was reused.
3. **The new process loaded the original history** — the new instance lists the original conversation and reads its messages.
4. **The next turn is also written to the cloud** — continuing the original conversation, the model names the earlier marker and the new turn is written to the cloud too.

You can verify by hand in the Web UI or automatically with a script; both check the same things.

### Choose the image to verify

The commands in this section pick the image through `DSH_SESSION_IMAGE`. Use the same image to start, recreate and check:

- **Pre-built image** — nothing to set; the default is `ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:v0.1.1-rc.2-ags.4-session-persistence.4`.
- **Your own image** — export its name first in the terminal where you run this section, for example `export DSH_SESSION_IMAGE=your-registry/your-dsh:version-session-persistence`. Both `make start` and `make check-image` use it.

Start DSH:

```bash
make start
curl -sf -o /dev/null --retry 60 --retry-delay 2 --retry-all-errors --max-time 5 http://127.0.0.1:18080/ || docker logs --tail 20 dsh-session-demo
docker inspect --format '{{.Config.Image}}' dsh-session-demo
```

The last line prints the image the container actually runs; confirm it is the one you expect. `make start` starts the container `dsh-session-demo` with the environment variables from `.env`; it listens only on the loopback address `127.0.0.1:18080` and mounts no volume. If the service stays unavailable, check `docker logs dsh-session-demo`.

If your own image uses different start arguments, start the container your own way and substitute your address for `http://127.0.0.1:18080` and your container name below. For the script, point `DSH_BASE_URL` at your DSH address.

### Verify in the Web UI

**Save a conversation.** Open <http://127.0.0.1:18080> in a browser, confirm the model shown below the input box matches `LLM_MODEL` in `.env`, start a new conversation, and send:

```text
Remember this marker: blue-falcon-42. Reply with only "Noted". Do not use tools.
```

Once the reply arrives, find the latest Session from a terminal and check its Events:

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

Expect output like `{"events":42,"turns":["completed"]}`: `completed` in `turns` means the turn was fully written to the cloud.

**Recreate the container.** Delete the current container and start a fresh one:

```bash
docker inspect --format '{{.Id}}' dsh-session-demo
make stop
make start
curl -sf -o /dev/null --retry 60 --retry-delay 2 --retry-all-errors --max-time 5 http://127.0.0.1:18080/ || docker logs --tail 20 dsh-session-demo
docker inspect --format '{{.Id}}' dsh-session-demo
```

The two container IDs should differ. The new container mounts no volume and has no local conversation data.

**Restore the conversation.** Refresh the browser page. The earlier conversation appears in the sidebar under the ungrouped section of the workspace list, titled with its first message; open it to see the previous message and reply. Continue in that conversation and send:

```text
What marker did I ask you to remember? Reply with only the marker. Do not use tools.
```

The model should reply `blue-falcon-42`. The marker is not in the new prompt, so the model can only answer correctly if the history was restored from the cloud. Run the `agr session event list` command above again; `turns` should now be `["completed","completed"]`.

### Verify with the script

The script automates the steps above. **Save a conversation:**

```bash
make seed
```

The script creates a DSH conversation, generates a random string as a marker (like `session-proof-…`), asks the model to remember it, waits for a completed turn in the cloud Events, and confirms the cloud header exists. The Session ID and marker are saved in `.local/session.json`. Expected output:

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
curl -sf -o /dev/null --retry 60 --retry-delay 2 --retry-all-errors --max-time 5 http://127.0.0.1:18080/ || docker logs --tail 20 dsh-session-demo
docker inspect --format '{{.Id}}' dsh-session-demo
make resume
```

The two container IDs should differ. The script then checks that the new DSH process reads the original marker from `session.history`, that the model names the marker when asked a new question that does not contain it, and that the new turn is fully written to the cloud. Expected output:

```text
Session: <same id>
Persisted history loaded and a new turn completed: session-proof-...
This verifies sequential recovery, not concurrent writers or automatic failover.
```

For another independent run, use a new state path, for example `python3 session_demo.py seed --state .local/another.json`, and the same path for `resume`. Do not write to the conversation from anywhere else during the test.

### Interpreting the results

The script cannot prove on its own that the running instance was replaced, which is why deleting and recreating the container and the changed container ID are part of the evidence.

When something fails, keep two cases apart: history loaded but the model answered wrong is a model recall problem; history that did not load is a persistence problem.

## 5. Optional: other ways to run

### Changing the model service

This example's image configures the model service through these variables in `.env`; **no image rebuild is needed**:

| Variable | Description | Default |
| --- | --- | --- |
| `LLM_BASE_URL` | OpenAI-compatible API address | `https://tokenhub.tencentmaas.com/v1` |
| `LLM_MODEL` | Model ID | `deepseek-v4-flash` |
| `LLM_API_KEY` | API key for the model service | None; required |

When the container starts, [entrypoint.sh](./dockerfiles/entrypoint.sh) runs [configure-model.mjs](./dockerfiles/configure-model.mjs) before DSH and writes these values into `/root/.dsh/settings.yaml`:

```text
.env or cloud Tool environment variables
        ↓
entrypoint.sh runs configure-model.mjs
        ↓
writes /root/.dsh/settings.yaml
        ↓
DSH starts and reads the generated configuration
```

With the defaults above, it generates:

```yaml
llm-pi-ai:
  providers:
    custom:
      displayName: Configured Model Service
      apiKeyEnv: LLM_API_KEY
      api: openai-completions
      baseURL: https://tokenhub.tencentmaas.com/v1
      models:
        - id: deepseek-v4-flash
agent-default-model:
  provider: custom
  model: deepseek-v4-flash
```

The API key is never written to the file: `apiKeyEnv: LLM_API_KEY` tells DSH to read the key from that environment variable at runtime. The script updates only these two entries and leaves the rest of `settings.yaml` unchanged. If any of the variables is empty, the container exits at startup and its log names the missing variables.

After editing `.env`, run `make stop` and `make start` to apply the change.

DSH records the model each conversation uses (provider and model ID), stores it with the conversation, and keeps using it when the conversation is restored. So after you change the model service, new conversations use the new model, while earlier conversations still point at the old one; if the old model is no longer configured, continuing them fails with `UNKNOWN_MODEL`. Switch to the configured model below the input box in the Web UI to continue.

Only OpenAI-compatible APIs are supported. For another API type or several models, edit configure-model.mjs and rebuild the image:

```bash
make build
make start DSH_SESSION_IMAGE=dsh-session:local
```

Without an image name, `make build` writes the local image `dsh-session:local` and does not overwrite the pre-built image.

### Multiple Agents in one space

An Agent here means one standalone DSH application — say, a support assistant and a coding assistant, each with its own purpose and configuration. One Agent can run several containers or replicas at once; they all still belong to the same Agent.

**By default, Agents that share a space see each other's conversations.** The plugin finds conversations by SessionSpace and `SESSION_USER_ID` only. If the support assistant and the coding assistant use the same space and the same UserId, the sidebar in either assistant's Web UI lists the conversations of both, and either one can open and continue the other's conversations.

There are two ways to let each Agent see only its own conversations:

- **Give each Agent its own SessionSpace.** Create one space per Agent and put each space's ID in `SESSION_SPACE_ID` in that Agent's `.env`. The simplest option; nothing else to configure.
- **Share one space and tell Agents apart with `SESSION_AGENT_ID`.** Useful when you want all conversation data managed in one space; set it up as described below.

#### Using SESSION_AGENT_ID

`SESSION_AGENT_ID` is an Agent ID that your business defines. It is unrelated to Tencent Cloud accounts or resource IDs; it only has to be unique within the space and stay the same over time. You can reuse an Agent ID that already exists in your business system, or assign one as in the example below, and put it in each Agent's `.env`:

| Agent | Setting in `.env` |
| --- | --- |
| Support assistant (however many containers it runs) | `SESSION_AGENT_ID=agt-10001` |
| Coding assistant | `SESSION_AGENT_ID=agt-10002` |

All containers or replicas of one Agent must use the same ID; otherwise a replaced container cannot find the earlier conversations. After editing `.env`, run `make stop` and `make start` to apply it.

With it set:

- each Agent's sidebar lists only the conversations it created;
- even with another Agent's conversation ID, accessing it directly through the DSH API fails; DSH reports it as not found;
- conversations created before you set `SESSION_AGENT_ID` are no longer listed. They are still stored in the cloud, not deleted; clear the variable and restart the container to see them again.

**How it works.** When the plugin creates a conversation, it writes the Agent ID into the Session's Metadata. Metadata is a set of custom key-value pairs on a Session that can be used as filters when querying Sessions; when listing conversations, the plugin filters on this key-value pair to find the current Agent's conversations. This example uses the key `example.com/dsh-agent-id`. To use a different key, for example to match naming already used in your business system, change `AGENT_METADATA_KEY` in both [plugin/index.js](./plugin/index.js) and [session_demo.py](./session_demo.py), then rebuild the image as described at the end of [Changing the model service](#changing-the-model-service). After switching keys, conversations recorded under the old key are no longer listed.

Besides the Agent ID, Metadata can hold other business identifiers such as tenant, business line or channel, for grouping and querying conversations. This example's plugin writes only the Agent ID; to record other identifiers, modify `appendBatch` in [plugin/index.js](./plugin/index.js) to add the corresponding Metadata when the Session is created, then rebuild the image.

#### Verify

1. Set `SESSION_AGENT_ID=agt-10001` in `.env`, run `make stop` and `make start` to restart the container, and save a conversation as in [section 4](#4-verify-the-integration).
2. Change it to `agt-10002`, restart the container, and save another conversation. The sidebar now shows only this conversation, not the one from step 1.
3. Change it back to `agt-10001` and restart the container. The conversation from step 1 reappears in the sidebar and opens.

When verifying with the script, each `seed` needs a new state file, so give each Agent its own path, for example `python3 session_demo.py seed --state .local/agt-10001.json`, and use the same path for `resume`.

### Separating conversations by business user

**The Session service itself isolates conversations by user.** Each conversation belongs to the UserId given when it was created; listing, reading, appending Events and deleting all take a UserId and only reach conversations under it, and the service reports conversations as not found when accessed with another UserId. The UserId is supplied by the caller and the Session service does not check that the caller is that user: a program holding the cloud API credentials can pass any UserId, so your application is responsible for passing the right user ID.

**This example's plugin uses one fixed UserId.** At startup the plugin reads one user ID from `SESSION_USER_ID`, and every conversation that DSH instance creates or queries uses it. The plugin cannot tell the people using an instance apart: the reads and writes DSH hands to the plugin carry only a conversation ID, not who is acting, and the DSH Web UI in this example has no user login. So **one DSH instance maps to one user ID**, and everyone using the same instance sees the same conversations.

To let each business user see only their own conversations, give each business user their own DSH instance: start a DSH container or sandbox per user, setting `SESSION_USER_ID` to that user's ID from your business system.

| Business user | Setting in that user's instance `.env` |
| --- | --- |
| User A, whose business-system user ID is `u-1001` | `SESSION_USER_ID=u-1001` |
| User B, whose business-system user ID is `u-1002` | `SESSION_USER_ID=u-1002` |

When user A comes back later, start a new instance with the same `SESSION_USER_ID=u-1001` and their earlier conversations load; user B's instance cannot see user A's conversations. No plugin changes are needed.

This example does not support several business users sharing one DSH instance. The limitation comes from DSH and this example's plugin, not from the Session service: the DSH version this example was verified with (0.1.1-rc.2) has no notion of user identity, so the plugin cannot see who the current user is and cannot pick the matching UserId for each request.

### Running in the cloud

Once local verification passes, you can run the same image in the cloud, either directly in an AGS sandbox or hosted in a Deployment. Both are created from the same sandbox tool, which defines the image, environment variables and resources a sandbox uses.

**Prepare the image and sandbox tool.** The pre-built image is used by default. To use your own image, push it to a registry your account can pull from first, for example `docker push your-registry/your-dsh:version-session-persistence`; the Makefile does not push. You also need `AGR_ROLE_ARN` from the [custom Sandbox role guide](https://cloud.tencent.com/document/product/1814/129691), `cam:PassRole` for the operator, and permission to create sandbox tools, sandbox instances or Deployments, and to obtain access tokens.

```bash
export DSH_SESSION_IMAGE="${DSH_SESSION_IMAGE:-ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:v0.1.1-rc.2-ags.4-session-persistence.4}"
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

While running in the cloud, do not let the local container write to the same conversation, and use a new state path for verification.

#### Run in an AGS sandbox

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

Stop the proxy with `Ctrl+C` in its terminal and delete the sandbox:

```bash
agr instance delete "$DSH_INSTANCE_ID" \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --yes \
  --wait
```

Then rerun the commands above that create the sandbox and start the proxy. The two instance IDs printed should differ. Once the proxy is up, restore the conversation from the second terminal:

```bash
python3 session_demo.py resume --state .local/sandbox.json
```

The expected output matches [Verify with the script](#verify-with-the-script).

This option works with the script only, not with the Web UI in a browser. `agr instance proxy` does not rewrite the browser's Origin header when forwarding requests, and DSH rejects such requests for security reasons. Script requests carry no Origin and are not affected. If you need the Web UI, host DSH in a Deployment.

The image's [entrypoint.sh](./dockerfiles/entrypoint.sh) already adds the sandbox domain `*.<region>.<AGR_DOMAIN>` to DSH's trusted hosts so requests through the sandbox are accepted. If you use your own image, add the same setting to its start arguments.

#### Host in a Deployment

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

Once the proxy is up, verify as in [section 4](#4-verify-the-integration), with two differences:

- **Address** — the Web UI is at <http://127.0.0.1:18081>; for the script, set `DSH_BASE_URL=http://127.0.0.1:18081` first and use a new `--state` path.
- **Recreating DSH** — instead of deleting the container and starting a fresh one, delete the Deployment (command in [section 6](#6-clean-up)), then create it again with the commands above and restart the proxy.

This verifies that conversations survive deleting and recreating DSH's Deployment. Replacing an instance within the same Deployment, such as scaling in and back out, is outside the scope of this section.

## 6. Clean up

Stop the local container, preview the cleanup scope, then delete:

```bash
make stop
python3 session_demo.py cleanup
# delete after reviewing the preview:
python3 session_demo.py cleanup --delete
```

Without `--delete`, the script only lists the conversations it would delete: with `SESSION_AGENT_ID` set, only that Agent's; without it, every conversation of that UserId in the space. Review the preview before deleting in a shared space.

Once every conversation reports `deleted`, remove the local state files:

```bash
rm -rf .local
```

If you created the SessionSpace for this example and no longer need anything in it, you can delete it. Do not delete a reused or shared space:

```bash
agr session space delete \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --space-id "$SESSION_SPACE_ID" \
  --output json
```

If you ran in the cloud, delete the cloud resources too. If you hosted in a Deployment, delete the Deployment first:

```bash
agr deployment delete "$DSH_DEPLOYMENT_ID" \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --wait
```

Then delete every instance of the sandbox tool that is not already stopped, and finally the sandbox tool itself. Deleted instances stay in the list as `STOPPED` and need no further action:

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

## 7. Limits

The persistence plugin in this example handles the normal write path only. It does not handle:

- **Migrating local JSONL history.** With the plugin enabled, DSH reads and writes cloud conversations only; existing local conversations are no longer visible.
- **Failures mid-write.** `appendBatch()` creates the Session and then appends events one by one, so a failure part-way can leave an empty Session or a partial history. Stable Event IDs make a retry idempotent, but nothing already written is rolled back. The plugin backs off and retries when the cloud API rate-limits it.
- **Multiple writers.** The plugin has no cross-instance coordination. Each write uses the Event ID `dsh-<conversation ID>-<sequence number>`; the Session service rejects the same Event ID with different content (`EventId 已存在`), so a sequence number holds at most one record and the cloud history cannot be interleaved. How this version behaves when several DSH instances handle the same conversation has not been verified; for measured results on 0.2.1-rc.2, see [Multi-replica deployment](../dsh-0.2.1-rc.2/README.md#multi-replica-deployment).
- **Resuming an in-progress turn.** If the DSH process exits mid-turn — while the model is generating a reply or a tool is running — no other process carries that turn on. The history written so far stays in the Session; after a new process loads the conversation, the user has to send the request again.
- **Anything beyond conversation state.** Files, running processes and live model connections are not restored.
- **Oversized events.** The plugin writes each event whole, without splitting it. When a tool returns a lot of content, a single event can exceed the Session API's size limit and fail to write.
- **Complete integrity checking.** Loading sorts the original events and rejects a gap in the sequence, which catches most incomplete writes but not every one. The plugin offers no verbatim per-conversation log export (`supportsRawArtifacts=false`); this does not affect history loading.

Before using this plugin in production, or letting several DSH instances write to the same conversation, add handling for each of these cases.

## Troubleshooting

- **Credential or space errors** — check account, region, SpaceId, permissions and temporary-credential expiry for both `agr` and the container.
- **Container exits right after starting** — DSH lists conversations through the persistence plugin at startup, so invalid plugin credentials make startup fail. Run `docker logs dsh-session-demo`: a cloud API error such as `SecretId is not found` means the `TENCENTCLOUD_*` credentials in `.env` need checking; a message starting with `configure-model:` names the `LLM_*` variables to fill in.
- **Connection refused** — wait for startup and check the container log. If you override `PORT`, update `DSH_BASE_URL` for the script too.
- **Model errors** — check `LLM_BASE_URL`, `LLM_MODEL` and `LLM_API_KEY` in `.env`, and your account's model access. The `configure-model:` line in the container log shows the model and address actually in use. Session credentials do not grant model access.
- **`UNKNOWN_MODEL` in an old conversation after changing models** — DSH records the model each conversation uses, and old conversations still point at the old model. Switch to the configured model below the input box in the Web UI; see [Changing the model service](#changing-the-model-service).
- **The new container cannot see the original conversation** — confirm that `AGR_REGION`, `SESSION_SPACE_ID`, `SESSION_USER_ID` and `SESSION_AGENT_ID` match those used when writing, and run `docker inspect --format '{{.Config.Image}}' dsh-session-demo` to confirm the container runs an image with the plugin.
- **Non-contiguous history** (`non-contiguous DSH event log`) — stop writing and inspect the incomplete history. Do not delete events to make the error go away.
- **Serving multiple users** — every conversation in this example uses the same `SESSION_USER_ID`. To separate conversations by business user, see [Separating conversations by business user](#separating-conversations-by-business-user).

## Appendix: local unit tests

These checks touch no cloud resources and are meant for self-testing after you change the plugin or scripts. They need Node.js 24 and pnpm 11.19.0.

```bash
make setup
make check
# run the plugin tests in the image named by DSH_SESSION_IMAGE; the pre-built image by default:
make check-image
```

They cover the event projections, history loading and the verification logic, but do not replace the real seed → fresh container → resume flow.
