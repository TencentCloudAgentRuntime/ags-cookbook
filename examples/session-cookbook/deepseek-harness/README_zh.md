# 使用 Agent Runtime Session 持久化 DeepSeek Harness 会话

[English](./README.md)

DeepSeek Harness（下文简称 DSH）默认将会话保存在本地磁盘的 JSONL 文件中。若 DSH 运行在未挂载数据卷的容器中（本示例即是如此），删除容器后会话历史也随之丢失。

本示例将 DSH 的会话持久化对接到云端的 Agent Runtime Session：与 DSH 完成一轮对话后删除容器，再启动全新的容器，即可从云端加载原会话并继续对话。

本示例只涉及会话持久化。如需同时保留工作区文件，并将后续请求路由回原工作区，请参考 [Session 与工作区关联示例](../../deployment-cookbook/brain-hands-session/README_zh.md)。

**操作步骤**

1. 配置环境，准备 SessionSpace。
2. 启动已集成持久化插件的 DSH 镜像。
3. 在 DSH 中完成一轮对话，让模型记住一个标识，并确认对话已写入云端。
4. 删除容器，再启动新容器。
5. 在新容器中打开同一会话，询问模型之前记住的标识。新问题中不包含该标识，模型只有读到从云端恢复的历史才能答对。

第 3～5 步可以在 Web UI 中手动完成（[第 4 节](#4-通过-web-ui-验证)），也可以通过脚本自动完成（[第 5 节](#5-通过脚本验证)）。Web UI 方式更直观；脚本方式会额外检查云端 Events 中的完整回合，适合需要重复验证的场景。

整个流程在本地 Docker 中运行，使用真实的云端 Session API。由于流程中间需要删除并重建容器，本示例的 `make run` 不会执行演示，只打印步骤提示，请按各节说明逐条执行命令。

本文使用以下术语：

- **DSH 会话**：用户在 DSH 中发起的一段对话。
- **Agent Runtime Session**：云端保存该对话的 Session。本示例让它与 DSH 会话使用相同 ID。
- **SessionSpace**：Session 的隔离边界，每个 Session 都属于一个 SessionSpace。
- **header**：DSH 对会话元数据的称呼，包括会话 ID、格式版本、创建时间等，保存在 Session 中。

## 前置条件

- Docker（需支持运行 `linux/amd64` 镜像）、Python 3.10 或更高版本，以及 `jq`。
- 已安装 **v0.7.0 或更高版本**的 `agr`（AGR CLI）。本示例在宿主机上使用 `agr session` 命令创建、查询和清理 SessionSpace 与 Session，该命令从 v0.7.0 起提供。首次使用时，请按 [AGR CLI 官方 GitHub 凭证配置说明](https://github.com/TencentCloudAgentRuntime/ags-cli/blob/main/README-zh.md#初始化-cli-凭证)完成初始化，再运行 `agr status` 和 `agr doctor`。
- 模型服务的 API Key。示例默认通过 TokenHub 调用 `deepseek-v4-flash`，使用其他模型服务的方法见[更换模型服务](#更换模型服务)。
- 具备以下权限的云 API 凭证：创建和管理测试 SessionSpace，创建、列举和读取 Session，追加和读取 Events。清理阶段还需要删除权限。

## 1. 配置环境

在本目录执行：

```bash
cp .env.example .env
# 编辑 .env，填入专用测试凭证。
set -a
. ./.env
set +a
agr status --cloud-endpoint "$SESSION_API_ENDPOINT"
```

`.env` 同时供宿主机和容器使用：

- `set -a` 与 `set +a` 之间通过 `. ./.env` 加载的变量会自动导出为环境变量，供宿主机上的 `agr` 命令和示例脚本使用。修改 `.env` 后需重新执行这三行。
- `make start` 通过 `docker run --env-file .env` 将同一文件传给容器，供容器内的持久化插件使用。修改 `.env` 后需重启容器才能生效。

Docker 读取 `--env-file` 时不会像 Shell 那样解析引号和表达式，因此 `.env` 只能使用简单的 `KEY=value` 格式，值两侧不要加引号。请使用子账号或临时凭证，不要使用主账号密钥，也不要将 `.env` 提交到版本库。

| 变量 | 是否必填 | 说明 |
| --- | --- | --- |
| `AGR_REGION` | 是 | SessionSpace 所在地域，示例默认为上海。 |
| `SESSION_API_ENDPOINT` | 是 | 云 API 域名，本示例使用 `ags.tencentcloudapi.com`。 |
| `SESSION_SPACE_ID` | 是 | 写入的 SessionSpace ID，在[第 2 节](#2-创建或复用-sessionspace)中获取。 |
| `SESSION_USER_ID` | 是 | 示例会话所属的用户标识。seed、resume 和清理阶段必须保持一致。 |
| `TENCENTCLOUD_SECRET_ID`、`TENCENTCLOUD_SECRET_KEY` | 是 | 容器内持久化插件调用 Session 云 API 使用的凭证。 |
| `TENCENTCLOUD_SESSION_TOKEN` | 使用临时凭证时必填 | 临时凭证对应的 Session Token；使用长期密钥时留空。凭证过期后需更新并重启容器。 |
| `TOKENHUB_API_KEY` | 是 | 模型服务的 API Key，与 Session 凭证相互独立。变量名由模型配置决定，见[更换模型服务](#更换模型服务)。 |
| `AGR_DOMAIN` | 在云上运行时必填 | 仅在[第 8 节](#8-可选在云上运行同一镜像)中生效，用于生成 DSH 信任的沙箱和 Deployment 访问域名。本地运行保持默认值 `tencentags.com` 即可。 |

本示例涉及两套相互独立的凭证：

- **`agr` 的凭证**：初始化 `agr` 时配置在本机，用于在宿主机上执行创建空间、查询事件和清理资源等命令。
- **持久化插件的凭证**：即 `.env` 中的 `TENCENTCLOUD_SECRET_ID`、`TENCENTCLOUD_SECRET_KEY`，在 DSH 运行时由容器内的插件用于读写 Session。

插件不会读取 `agr` 的配置。请确认两套凭证属于同一账号，并使用相同地域，否则插件写入的 Session 可能无法通过 `agr` 查询到。

## 2. 创建或复用 SessionSpace

已有可用的测试 SessionSpace 时，将其 ID 填入 `.env` 的 `SESSION_SPACE_ID`，然后跳到[第 3 节](#3-启动-dsh)。

否则，创建专用的 SessionSpace：

```bash
agr session space create \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --name dsh-session-demo \
  --description "DSH Session integration" \
  --output json \
  --jq '.Data.SessionSpace.SpaceId'
```

命令输出的即为新空间的 SpaceId。打开 `.env`，将 `SESSION_SPACE_ID=space-replace-me` 中的占位值替换为该 SpaceId，保存后重新加载：

```bash
set -a
. ./.env
set +a
```

## 3. 启动 DSH

本示例提供已集成持久化插件的公开镜像 `ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:v0.1.1-rc.2-ags.4-session-persistence.2`，可直接使用。依次执行以下命令：

```bash
make start
curl --fail http://127.0.0.1:18080/
```

- `make start`：拉取公开镜像并启动容器 `dsh-session-demo`，通过 `.env` 传入环境变量。首次启动需要拉取镜像，耗时较长。容器只监听本机回环地址 `127.0.0.1:18080`，不挂载数据卷。
- `curl`：检查 DSH 服务是否已就绪。

服务启动需要一些时间；若长时间未就绪，请查看 `docker logs dsh-session-demo`。随后在浏览器中打开 <http://127.0.0.1:18080>，确认输入框下方显示的模型为 `deepseek-v4-flash`。

公开镜像以 DSH 镜像 `deepseek-harness:v0.1.1-rc.2-ags.4` 为基础，安装了本示例的持久化插件，并调整了 DSH 的启动配置：禁用内置的 JSONL 持久化插件 `session-persistence-jsonl`，改为启用云端持久化插件。本地已有的 JSONL 会话历史不会自动迁移到云端。

如需修改插件、更换模型服务或使用自有 DSH 镜像，需要自行构建镜像，见[第 7 节](#7-自定义模型与镜像)。

## 4. 通过 Web UI 验证

### 保存会话

打开 <http://127.0.0.1:18080>，新建会话，发送：

```text
请记住这个标识：blue-falcon-42。只回复"已记住"，不要使用工具。
```

收到回复后，在终端中查询该用户在 SessionSpace 中的 Session，确认对话已写入云端：

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

输出中应出现一条新的 Session，CreateTime 与刚才发送消息的时间一致。

### 重建容器

删除当前容器，再启动新容器：

```bash
docker inspect --format '{{.Id}}' dsh-session-demo
make stop
make start
curl --fail http://127.0.0.1:18080/
docker inspect --format '{{.Id}}' dsh-session-demo
```

前后两次的容器 ID 应不相同，且未复用任何 DSH 数据卷，此时新容器本地没有任何会话数据。

### 恢复会话

刷新浏览器页面。侧边栏「工作区」的「未分组」下会出现刚才的会话，标题为第一条消息的内容，这条记录由持久化插件从云端读取。打开该会话，可以看到上一轮的消息和回复。

在该会话中继续发送：

```text
我之前让你记住的标识是什么？只回复该标识，不要使用工具。
```

模型应回复 `blue-falcon-42`。新问题中不包含该标识，模型只有读到从云端恢复的历史才能答对。

## 5. 通过脚本验证

脚本会自动完成第 4 节的操作，并额外检查云端 Events 中是否出现完整回合，而不仅是页面上出现输出。

### 保存会话

```bash
make seed
```

脚本新建 DSH 会话，生成随机字符串作为标识（形如 `session-proof-…`）并发给模型要求记住，然后等待**云端 Events 中出现完整回合**。确认云端 header 后，脚本将 Session ID 和标识写入 `.local/session.json`。整个过程不依赖工具调用。

预期输出：

```text
Session: <id>
Cloud header and completed turn verified. State: .local/session.json
Stop and remove the DSH container, start a fresh one without volumes, then run resume.
```

如需查看云端存储的内容：

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

该命令只返回第一页结果（最多 200 条），脚本则会读取全部分页。

### 重建容器并恢复

确认 `make seed` 成功后再继续，且测试期间不要从其他入口写入该会话。

```bash
docker inspect --format '{{.Id}}' dsh-session-demo
make stop
make start
curl --fail http://127.0.0.1:18080/
docker inspect --format '{{.Id}}' dsh-session-demo
# 等待新容器就绪：
make resume
```

前后两次的容器 ID 应不相同。脚本随后执行以下检查：

1. 新 DSH 进程的 `session.history` 能返回 seed 阶段的标识。
2. 向模型发送不包含标识的新问题，模型能回忆出该标识。
3. 新一轮对话完整写入云端，且回答与标识一致。

预期输出：

```text
Session: <相同的 id>
Persisted history loaded and a new turn completed: session-proof-...
This verifies sequential recovery, not concurrent writers or automatic failover.
```

如需再次独立验证，请使用新的 state 路径，例如 `python3 session_demo.py seed --state .local/another.json`，resume 阶段使用相同路径。

## 6. 理解验证结果

### 验证了什么

本示例验证的是**顺序恢复**：旧容器删除后，新容器能从云端加载完整历史并继续对话。在 Web UI 中，新容器的侧边栏能列出原会话、打开后能看到历史消息，说明 DSH 通过持久化插件从云端读取了会话；模型答出标识，则说明恢复的历史已进入模型上下文。脚本本身无法证明进程确已替换，因此删除、重建容器以及容器 ID 的变化也是验证依据。

排查失败时需区分两类情况：历史加载成功但模型回答错误，属于模型召回问题；历史未能加载，才属于持久化问题。

### 实现方式

```text
DSH  →  持久化插件  →  SessionSpace  →  Session（会话元数据）+ Events（消息、工具调用、回合标记）
```

持久化插件注册为 DSH 的持久化后端，替代内置的 JSONL 实现。DSH 创建会话时，插件在云端创建对应的 `Session`，并将 header 写入其中；此后 DSH 每向会话日志追加一条记录，插件就将其转换为云端 `Event` 并追加到该 `Session`；DSH 再次打开该会话时，插件读回 header 和这些 Event，重建日志。

插件通过 DSH 启动参数 `--patch` 加载 [Cordis 补丁](./dockerfiles/agent-runtime-session.cordis.yml)完成替换。本插件是 [Session 与工作区关联示例](../../deployment-cookbook/brain-hands-session/README_zh.md)的纯持久化版本，不注册工具，也不调用 Deployment API。

### 数据存储位置

| 数据 | 位置 |
| --- | --- |
| DSH 会话身份和 header | 相同的 `SessionId`，`State.CustomState.dshHeader` |
| 消息正文和推理内容 | `Content.Parts`，推理内容标记为 Thought |
| 工具调用与结果 | `Content.Parts[].FunctionCall` / `FunctionResponse` |
| 部分配置变更 | `Actions.StateDelta` |
| 类型、序号、回合标记 | JSON `Event.Metadata`，含 Partial、TurnComplete、Interrupted |
| 原始 DSH 事件（原样保留） | JSON `Extensions.dshEvent` |

加载时会按原始事件排序并检查序号连续性，可发现大部分不完整批次，但无法覆盖全部情况。`supportsRawArtifacts=false` 表示不提供逐会话的原始日志文本导出，并不表示不支持历史加载。

Session 只恢复会话状态，文件、运行中的进程和模型长连接都不会恢复。

### 本适配器的限制

本示例的持久化插件只处理正常的写入流程，以下情况未做处理：

- **写入中途失败。** `appendBatch()` 先创建 Session，再逐条追加 Event，中途失败可能留下空 Session 或不完整的历史。稳定的 Event ID 使重试具备幂等性，但不会回滚已写入的内容。
- **多个写入者。** 插件没有跨实例的协调机制。多个 DSH 实例同时写入同一会话时，可能写入序号冲突的 Event，导致历史不一致。
- **进行中的回合不会自动接续。** DSH 进程在一轮对话进行中退出时，例如模型正在生成回复或工具正在执行，这一轮不会由其他进程自动继续。已写入的历史仍保留在 Session 中，新进程加载会话后，需要用户重新发起请求。
- **超大 Event。** 插件将每个 Event 完整写入，不做拆分。工具返回大量内容时，单个 Event 可能超出 Session API 的大小限制而写入失败。

如需将本插件用于生产环境，或让多个 DSH 实例写入同一会话，需要先针对以上情况补充相应的处理。

## 7. 自定义模型与镜像

公开镜像使用本示例默认的插件和模型配置。修改插件、更换模型服务或使用自有 DSH 镜像时，需要自行构建镜像。

### 自行构建镜像

在本目录执行：

```bash
make build
make start DSH_SESSION_IMAGE=dsh-session:local
```

`make build` 按 [Dockerfile](./dockerfiles/Dockerfile) 在本机构建镜像 `dsh-session:local`，构建过程与公开镜像相同；`make start` 需通过 `DSH_SESSION_IMAGE` 指定该本地镜像，否则会使用公开镜像。本地镜像名仅存在于本机，可通过 `make build DSH_SESSION_IMAGE=<镜像名>` 自定义。

如容器已在运行，请先执行 `make stop`。

### 更换模型服务

模型配置位于 [`dockerfiles/settings.yaml`](./dockerfiles/settings.yaml)，构建时写入镜像。默认配置通过 OpenAI 兼容接口（`api: openai-completions`）访问 TokenHub。如需使用其他模型服务，请修改该文件：

- `llm-pi-ai.providers` 下的 provider 名称、`baseURL` 和 `models`；
- `apiKeyEnv`，即读取 API Key 的环境变量名；
- `agent-default-model` 中的 `provider` 和 `model`。

修改后按[自行构建镜像](#自行构建镜像)重新构建并启动，并在 `.env` 中按新的 `apiKeyEnv` 填写 API Key。如需按第 8 节在云上运行，还需同步修改 [`deployment_config.py`](./deployment_config.py) 中 `REQUIRED` 列表里的 `TOKENHUB_API_KEY`，否则生成配置时会因缺少该变量而失败。

### 使用自有 DSH 镜像

`make build` 不会从源码构建 DSH，而是以一个已有的 DSH 镜像为基础，叠加持久化插件后生成新镜像：

| 变量 | 含义 | 默认值 |
| --- | --- | --- |
| `DSH_IMAGE` | 基础镜像，即已安装 DSH 的镜像 | 公开镜像 `deepseek-harness:v0.1.1-rc.2-ags.4` |
| `DSH_SESSION_IMAGE` | 构建产物，即基础镜像加上持久化插件 | `make build` 默认输出本地镜像 `dsh-session:local`；`make start` 默认使用公开镜像。推送到镜像仓库时需改为仓库地址，见[第 8 节](#8-可选在云上运行同一镜像) |

如果已有自己的 DSH 镜像，可按以下两种方式之一接入。

#### 方式一：以自有镜像为基础构建

镜像目录结构与默认镜像一致时，直接替换基础镜像即可：

```bash
make build DSH_IMAGE=your-registry/your-dsh:version DSH_SESSION_IMAGE=dsh-session:custom
make start DSH_SESSION_IMAGE=dsh-session:custom
```

自有镜像需满足以下条件：

| 条件 | 默认镜像中的取值 | 原因 |
| --- | --- | --- |
| DSH 以全局模块安装 | `/usr/local/lib/node_modules/@deepseek-ai` | 构建时会将插件依赖的 DSH 模块链接到此目录，使插件与 DSH 共用同一份模块 |
| DSH 模块版本与插件一致 | `cordis` 4.0.1；`dsh-session`、`dsh-session-persistence` 0.1.1-rc.2；`schemastery` 3.18.1 | 版本以 [package.json](./plugin/package.json) 的 `peerDependencies` 为准 |
| Node.js 24 | v24.8.0 | 构建时通过 npm 安装 pnpm 并安装插件依赖 |
| Web profile 位于 `$DSH_HOME/profiles/web` | `DSH_HOME` 默认为 `/root/.dsh` | 启动时会将插件链接到该 profile 的 `node_modules`，供 DSH 加载 |
| 平台为 `linux/amd64` | — | Makefile 按该平台构建和运行 |

可以用以下命令检查自有镜像中的 Node.js 和 DSH 模块版本：

```bash
docker run --rm --platform linux/amd64 --entrypoint sh your-registry/your-dsh:version -c \
  'cd /usr/local/lib/node_modules/@deepseek-ai && node -v && for p in cordis dsh-session dsh-session-persistence schemastery; do echo "$p $(node -p "require(\"./$p/package.json\").version")"; done'
```

版本不一致时，修改 [package.json](./plugin/package.json) 中 `peerDependencies` 的版本，在 `plugin` 目录执行 `pnpm install` 更新 `pnpm-lock.yaml`，再执行 `make check` 和 `make check-image` 验证插件与该版本是否兼容。

另外需要注意两点：

- **模型配置会被覆盖。** 构建会将 [settings.yaml](./dockerfiles/settings.yaml) 复制到 `/root/.dsh/settings.yaml`。若自有镜像已包含模型配置，请删除 [Dockerfile](./dockerfiles/Dockerfile) 中对应的 `COPY` 行，或将两份配置合并。
- **启动命令会被替换。** 构建产物使用本示例的 [entrypoint.sh](./dockerfiles/entrypoint.sh) 作为入口。若自有镜像的启动命令包含额外参数，例如其他可信主机或端口，请将这些参数合并到 entrypoint.sh 中。

#### 方式二：在自有 Dockerfile 中集成插件

镜像目录结构不同，或希望在自己的构建流程中集成插件时，参照本示例的 [Dockerfile](./dockerfiles/Dockerfile) 和 [entrypoint.sh](./dockerfiles/entrypoint.sh) 完成以下四步：

1. **安装插件。** 将 `plugin` 目录复制到镜像中，执行 `pnpm install --prod --frozen-lockfile`，并将其放到 Node.js 全局模块目录下的 `@tencentcloud/ags-dsh-session-persistence`。
2. **与 DSH 共用模块。** 删除插件 `node_modules` 下的 `@deepseek-ai` 目录，改为将 `cordis`、`dsh-session`、`dsh-session-persistence`、`schemastery` 符号链接到 DSH 的实际安装位置。
3. **在 Web profile 中注册插件。** 启动 DSH 前，将插件链接到 `$DSH_HOME/profiles/web/node_modules/@tencentcloud/ags-dsh-session-persistence`。DSH 按 Cordis 补丁中的 `name` 从这里加载插件。
4. **启用插件。** 将 [Cordis 补丁](./dockerfiles/agent-runtime-session.cordis.yml)复制到镜像中，并在启动 `dsh web` 时传入 `--patch <补丁路径>`。补丁会禁用内置的 `session-persistence-jsonl`，启用云端持久化插件，并从环境变量读取配置。

第 1、2 步在构建时完成，第 3、4 步在容器启动时完成。构建上下文中需包含本示例的 `plugin` 目录、Cordis 补丁和启动脚本；建议在 `.dockerignore` 中排除 `plugin/node_modules`，避免将本机安装的依赖复制进镜像。

Dockerfile 示例：

```dockerfile
FROM your-registry/your-dsh:version

# 自有镜像中 DSH 模块的实际安装目录
ARG DSH_MODULES=/usr/local/lib/node_modules/@deepseek-ai
# 持久化插件的安装目录
ARG PLUGIN_DIR=/usr/local/lib/node_modules/@tencentcloud/ags-dsh-session-persistence

# 第 1 步：安装插件及其依赖
COPY plugin /tmp/ags-dsh-session-persistence
RUN npm install --global pnpm@11.19.0 \
    && cd /tmp/ags-dsh-session-persistence \
    && pnpm install --prod --frozen-lockfile \
    && mkdir -p "$(dirname "$PLUGIN_DIR")" \
    && mv /tmp/ags-dsh-session-persistence "$PLUGIN_DIR" \
    && rm -rf /root/.npm /root/.local/share/pnpm/store

# 第 2 步：将插件依赖的 DSH 模块链接到 DSH 的安装位置，与 DSH 共用同一份模块
RUN rm -rf "$PLUGIN_DIR/node_modules/@deepseek-ai" \
    && mkdir -p "$PLUGIN_DIR/node_modules/@deepseek-ai" \
    && for package in cordis dsh-session dsh-session-persistence schemastery; do \
         ln -s "$DSH_MODULES/$package" "$PLUGIN_DIR/node_modules/@deepseek-ai/$package"; \
       done

# 第 3、4 步由启动脚本完成
COPY agent-runtime-session.cordis.yml /opt/dsh/agent-runtime-session.cordis.yml
COPY entrypoint.sh /opt/dsh/entrypoint.sh
RUN chmod 0755 /opt/dsh/entrypoint.sh
ENTRYPOINT ["/opt/dsh/entrypoint.sh"]
```

启动脚本 `entrypoint.sh` 示例：

```sh
#!/bin/sh
set -eu

# 第 3 步：在 Web profile 中注册插件，路径需与 Dockerfile 中的 PLUGIN_DIR 一致
profile_modules="${DSH_HOME:-/root/.dsh}/profiles/web/node_modules/@tencentcloud"
mkdir -p "$profile_modules"
ln -sfn /usr/local/lib/node_modules/@tencentcloud/ags-dsh-session-persistence \
  "$profile_modules/ags-dsh-session-persistence"

# 第 4 步：启动 DSH，并通过 --patch 加载 Cordis 补丁。
# 以下为本示例的启动参数，请替换为自有镜像原有的启动命令和参数，并保留 --patch。
exec node --expose-internals \
  /usr/local/lib/node_modules/@deepseek-ai/dsh/lib/bin.js \
  web \
  --patch /opt/dsh/agent-runtime-session.cordis.yml \
  --host 0.0.0.0 \
  --port 3080
```

可信主机等其余启动参数，请参考本示例完整的 [entrypoint.sh](./dockerfiles/entrypoint.sh)。

构建完成后，可以在镜像中运行插件自带的测试，确认插件能正确加载 DSH 模块：

```bash
docker run --rm --platform linux/amd64 --entrypoint node your-dsh-session:version \
  --test /usr/local/lib/node_modules/@tencentcloud/ags-dsh-session-persistence/index.test.js
```

容器启动时，还需提供[第 1 节](#1-配置环境)表格中的环境变量。无论采用哪种方式，都请固定并验证所用的 DSH 版本，不要假定任意版本均可兼容。

## 8. 可选：在云上运行同一镜像

完成本地验证后，可以将同一镜像放到云上运行。本节提供两种方式：直接在 AGS 沙箱中运行，或托管到 Deployment。两种方式使用相同的镜像和沙箱工具。

### 准备镜像和沙箱工具

默认使用本示例的公开镜像。如使用[第 7 节](#7-自定义模型与镜像)自行构建的镜像，需先自行标记并推送到账号可拉取的仓库，再将 `DSH_SESSION_IMAGE` 指向该镜像；Makefile 不会执行推送。此外，需按[自定义 Sandbox CAM 角色](https://cloud.tencent.com/document/product/1814/129691)准备 `AGR_ROLE_ARN`，并为操作者授予 `cam:PassRole`，以及创建沙箱工具、沙箱实例或 Deployment 和获取访问 Token 的权限。

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

生成的配置文件包含凭证：请在 `umask 077` 下生成，不要外传，并在沙箱工具创建完成后删除。`agr tool create` 的完整输出也会包含工具配置中的凭证，因此上述命令只提取 ToolId。生成器按 public/personal 仓库类型输出配置，使用其他类型的仓库时需相应调整。

云上运行时，不要让本地容器同时写入同一会话。以下两种方式均使用新的 state 路径，与本地验证的会话互不影响。

### 方式一：在 AGS 沙箱中运行

创建沙箱实例，并将其 3080 端口转发到本地：

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

`--timeout` 指定沙箱的存活时间，请按验证所需的时长设置。代理在前台运行，请保持该终端打开。

在另一个终端中加载相同的环境变量，保存会话：

```bash
export DSH_BASE_URL=http://127.0.0.1:18082
python3 session_demo.py seed --state .local/sandbox.json
```

在代理所在的终端中按 `Ctrl+C` 停止代理，然后删除该沙箱，再创建新沙箱并重新启动代理：

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

前后两次输出的实例 ID 应不相同。代理启动后，在第二个终端中恢复会话：

```bash
python3 session_demo.py resume --state .local/sandbox.json
```

预期输出与[第 5 节](#5-通过脚本验证)相同。

本方式只能通过脚本验证，无法在浏览器中使用 Web UI。原因是 `agr instance proxy` 转发请求时不会改写浏览器请求中的来源地址（Origin），DSH 出于安全考虑会拒绝这类请求。脚本请求不携带来源地址，不受影响。需要使用 Web UI 时，请采用方式二。

镜像的 [entrypoint.sh](./dockerfiles/entrypoint.sh) 已将沙箱域名 `*.<地域>.<AGR_DOMAIN>` 加入 DSH 的可信主机，使通过沙箱访问的请求能够被接受。使用自有镜像时，需要在启动参数中加入同样的配置。

### 方式二：托管到 Deployment

基于同一沙箱工具创建 Deployment，并将其 3080 端口转发到本地：

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

代理启动后，可以在浏览器中打开 <http://127.0.0.1:18081> 访问 Web UI。也可以在另一个终端中加载相同的环境变量，设置 `DSH_BASE_URL=http://127.0.0.1:18081`，并使用新的 `--state` 路径执行 seed。

## 9. 清理

停止本地容器，并删除 `SESSION_USER_ID` 在该 SessionSpace 中的全部 Session。这样可以同时清理通过 Web UI 和脚本创建的会话：

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

若该 SessionSpace 为共用空间，且其他人也使用相同的 `SESSION_USER_ID`，上述命令会删除他们的 Session。此时请先单独执行 `agr session list` 核对列表，只删除本示例创建的 Session。

确认每一行输出均为 `succeeded` 后，再删除本地 state 文件：

```bash
rm -rf .local
```

如果 SessionSpace 是在[第 2 节](#2-创建或复用-sessionspace)中为本示例新建的，且其中内容均不再需要，可将其删除；复用的已有空间或共用空间不要删除：

```bash
agr session space delete \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --space-id "$SESSION_SPACE_ID" \
  --output json
```

如果完成了第 8 节，还需删除云上资源。若使用了方式二，先删除 Deployment：

```bash
agr deployment delete "$DSH_DEPLOYMENT_ID" \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --wait
```

然后删除该沙箱工具下所有未停止的实例（包括方式一创建的沙箱），最后删除沙箱工具。已删除的实例会以 `STOPPED` 状态保留在列表中，无需再次删除：

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

## 常见问题

- **凭证或空间报错**：分别核对 `agr` 和容器所用的账号、地域、SpaceId、权限以及临时凭证有效期。
- **容器启动后立即退出**：DSH 启动时会通过持久化插件查询会话列表，插件凭证无效时启动即失败。执行 `docker logs dsh-session-demo`，若出现 `SecretId is not found` 等云 API 错误，请核对 `.env` 中的 `TENCENTCLOUD_*` 凭证。
- **连接被拒绝**：等待服务启动完成，并查看容器日志。如修改了 `PORT`，需同步修改脚本使用的 `DSH_BASE_URL`。
- **模型调用报错**：核对模型服务的 API Key、`settings.yaml` 中的模型配置以及账号的模型权限。Session 凭证不包含模型权限。
- **历史序号不连续**（`non-contiguous DSH event log`）：先停止写入，再排查未完整写入的事件，不要通过删除事件来掩盖报错。
- **重启后找不到标识**：核对 SpaceId、UserId、Session ID，以及 DSH 与插件的版本是否兼容，并保留 state 文件和日志。
- **多用户场景**：固定的 `SESSION_USER_ID` 仅用于演示。生产环境需接入可信身份并进行归属校验，不能按请求修改共享插件的 UserId。

## 附录：本地单元测试

以下检查不访问云端资源，用于修改插件或脚本后的自测。需要 Node.js 24 和 pnpm 11.19.0。

```bash
make setup
make check
# 在镜像中运行插件测试，默认检查公开镜像：
make check-image
# 检查自行构建的镜像：
make check-image DSH_SESSION_IMAGE=dsh-session:local
```

这些测试覆盖事件投影、历史加载和验证逻辑，但不能替代真实的 seed → 新容器 → resume 流程。
