# 使用 Agent Runtime Session 持久化 DeepSeek Harness 0.2.1-rc.2 会话

[English](./README.md) | [选择其他 DSH 版本](../README_zh.md)

DeepSeek Harness（下文简称 DSH）默认将会话保存在本地磁盘的 JSONL 文件中。若 DSH 运行在未挂载数据卷的容器中，删除容器后会话历史也随之丢失。本示例通过持久化插件将 DSH 的会话写入云端 Agent Runtime Session：删除容器再启动全新的容器后，仍可加载原会话并继续对话。

本文适用于 **DSH 0.2.1-rc.2**。插件与 DSH 的内部模块版本严格绑定，使用前请先阅读[第 2 节](#2-版本与依赖约定)确认版本。

## 快速体验

使用本示例的预集成镜像（官方 DSH 0.2.1-rc.2 加持久化插件），可以快速完成一次会话的保存与恢复。在本目录执行：

```bash
cp .env.example .env            # 填入凭证和模型 API Key，见第 3 节
set -a; . ./.env; set +a
agr session space create \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --name dsh-session-demo \
  --output json \
  --jq '.Data.SessionSpace.SpaceId'
# 将输出的 SpaceId 填入 .env 的 SESSION_SPACE_ID，然后重新加载：
set -a; . ./.env; set +a

make start                      # 启动预集成镜像，就绪后输出登录地址
make seed                       # 保存一轮带标识的对话
make stop && make start         # 删除容器，再启动新容器
make resume                     # 新容器加载历史，模型答出标识即成功
```

`make start` 最多等待约 2 分钟。DSH 就绪后输出 `DSH is ready. Sign in at: http://127.0.0.1:18080/?token=...`；容器提前退出或超时时，输出容器日志的最后 20 行。各步骤的含义和预期输出见[第 5 节](#5-验证接入)，用完后按[第 7 节](#7-清理)清理。如需将插件集成到自有 DSH，见[第 4 节](#4-将插件集成到现有-dsh)。

## 1. 接入原理

### 接入点

DSH 通过 **SessionPersistence 扩展点**决定会话保存在哪里，内置实现是写本地文件的 `session-persistence-jsonl` 插件。本示例提供实现同一扩展点的插件 `@tencentcloud/ags-dsh-session-persistence`，并在 DSH 启动时通过 Cordis 补丁禁用 JSONL 插件、启用本插件。Cordis 是 DSH 的插件框架，补丁是一个 YAML 配置文件，用于在不修改 DSH 代码的情况下调整加载哪些插件及其配置。DSH 的其他部分，包括模型调用、工具执行和 Web UI，都不需要修改。

```text
DSH 产生会话记录  →  持久化插件写入云端  →  SessionSpace 中的 Session 和 Events
                                                    │
新 DSH 进程  ←  持久化插件读取历史  ←────────────────┘
```

### 会话的生命周期

| 阶段 | 发生了什么 |
| --- | --- |
| 新建会话 | 插件只在当前进程中登记该会话。第一次写入记录或 DSH 执行 flush 时，插件才沿用 DSH 会话 ID 作为 Session ID 调用 `CreateSession`，并将 DSH 的会话元数据（header）写入其中。只新建、从未写入的会话不会出现在云端。 |
| 后续写入 | DSH 产生的记录先进入插件的缓冲区，200 毫秒内的记录合并为一批，按序号逐条通过 `AppendEvent` 追加到该 Session。DSH 的检查点策略触发 flush 时，立即写出缓冲区中的记录。 |
| 新进程列出会话 | DSH 启动后列出会话时，插件查询该用户在 SessionSpace 中的 Session，只返回由本版本插件写入的 DSH 会话；设置了 `SESSION_AGENT_ID` 时，只返回该 Agent 的会话。Web UI 侧边栏中的会话列表即来源于此。 |
| 打开原会话 | 插件读回 header 和全部 Event，检查序号连续性和记录格式后，交给 DSH 重建会话。同一进程内，一个会话同时只允许一个写入方。 |

云端 Session 由插件在写入时创建，不需要手动创建。

### 数据约定

插件在 Session 的标准字段之外，用以下自定义字段保存 DSH 恢复会话所需的数据：

| 数据 | 位置 | 用途 |
| --- | --- | --- |
| DSH 会话 header | `State.CustomState.dshHeader` | 插件据此识别 DSH 会话并重建元数据 |
| fork 继承的记录数 | `State.CustomState.dshInheritedEventCount` | 仅 fork 出的会话写入，记录从父会话继承的记录数 |
| 原始 DSH 事件 | Event 的 `Extensions.dshEvent` | 插件据此原样重建会话日志 |
| Event ID | `dsh-<会话 ID>-<序号>` | 重试写入时，Session 服务按此识别重复请求 |
| 消息正文和推理内容 | `Content.Parts`，推理内容标记为 Thought | 便于其他系统直接读取，DSH 恢复时不使用 |
| 工具调用与结果 | `Content.Parts[].FunctionCall` / `FunctionResponse` | 同上 |
| 部分配置变更 | `Actions.StateDelta` | 同上 |
| 类型、序号、回合标记 | `Event.Metadata`，含 Partial、TurnComplete、Interrupted | 同上 |

注：表中的 fork 指 DSH 的会话 fork（`session/fork`），即从一个会话的指定位置派生出新会话，新会话的日志以父会话的这段记录开头。`dshInheritedEventCount` 记录这段继承了多少条，普通会话不写入。

DSH 恢复会话时，只看两个地方：

- **`State.CustomState.dshHeader`**（存在 Session 上）：标记这个 Session 属于 DSH。没有它的 Session 不会出现在会话列表里，也打不开。
- **`Extensions.dshEvent`**（存在每条 Event 上）：保存完整的事件内容，恢复时按它逐条重建。没有它的 Event 会被跳过。

这两个字段的名字和格式由插件定义，Session 服务只负责原样保存，不理解它们的含义，也不做校验或转换。

### 接入前须知

以下几点会影响接入后现有会话的行为，详细说明见[第 8 节](#8-限制与边界)：

- **已有的历史不会迁移。** 本地 JSONL 历史和 DSH 0.1.1-rc.2 插件写入云端的会话，在本版本中都不可见。
- **同一个会话不要同时由多个 DSH 实例写入。** 多个实例可以共用一个空间、各自处理不同的会话，但插件不协调多个实例同时写入同一个会话；发生冲突时，后写入的副本会报错，见[多副本部署](#多副本部署)。
- **只恢复会话，不恢复工作环境。** 文件、运行中的进程和模型长连接都不会恢复；一轮对话进行中时实例退出，这一轮需要重新发起。

## 2. 版本与依赖约定

插件直接使用 DSH 的内部模块，这些模块在部分 DSH 版本之间有不兼容变更。**请按下表固定版本，不要使用"最新版本"。** 例如 `npm install -g @deepseek-ai/dsh` 不带版本号时会安装 npm 上当前的最新版本；当最新版本与插件适配的版本不同时，DSH 启动即报错。

### 版本要求

| 依赖 | 要求 | 说明 |
| --- | --- | --- |
| DSH `@deepseek-ai/dsh` | 精确为 `0.2.1-rc.2` | 安装时须写明版本：`npm install -g @deepseek-ai/dsh@0.2.1-rc.2`。其他版本未经验证 |
| DSH 内部模块：`@deepseek-ai/cordis`、`dsh-session`、`dsh-session-persistence`、`schemastery` | 精确为 `4.0.5`、`0.2.1-rc.2`、`0.2.1-rc.2`、`3.18.5` | 随 DSH 一起安装，不要单独安装或升级。插件与 DSH 共用这几个模块，版本须与 [plugin/package.json](./plugin/package.json) 的 `peerDependencies` 完全一致 |
| Node.js | 24.x | 示例镜像基于 `node:24.8.0-bookworm-slim`，即 Node.js 24.8.0 |
| npm | 11.x | Node.js 24.8.0 自带 npm 11.6.0。npm 11 将 DSH 的依赖安装在 DSH 包自己的 `node_modules` 下，见下方「模块位置」 |
| pnpm | 精确为 `11.19.0` | 用于安装插件依赖，与 [plugin/pnpm-lock.yaml](./plugin/pnpm-lock.yaml) 对应，构建时使用 `--frozen-lockfile` |
| `tencentcloud-sdk-nodejs-ags` | 精确为 `4.1.302` | 插件调用 Session API 使用的 SDK，由 lock 文件锁定 |
| Docker | 支持运行 `linux/amd64` 镜像 | 示例镜像的构建平台 |
| Python | 3.10 或更高版本 | 验证脚本 |
| AGR CLI `agr` | v0.7.0 或更高版本 | 宿主机上管理 SessionSpace 和 Session |

### 模块位置

插件需要找到 DSH 实际安装的内部模块，并链接到同一份模块。用 npm 11 安装 DSH 时，这些模块位于：

```text
/usr/local/lib/node_modules/@deepseek-ai/dsh/node_modules/@deepseek-ai/
```

用其他方式安装的 DSH，模块可能直接位于 `/usr/local/lib/node_modules/@deepseek-ai/` 下。[检查自有镜像](#检查自有镜像)的脚本会输出实际位置。

### 版本不一致时的表现

| 情况 | 报错 |
| --- | --- |
| DSH 是 0.2.x，却使用了适配 0.1.1-rc.2 的插件 | `does not provide an export named 'PersistenceCoordinator'` |
| DSH 是 0.1.x，却使用了本插件 | `does not provide an export named 'SessionAlreadyExistsError'` |

出现以上报错时，请使用与 DSH 版本对应的插件目录，见[选择 DSH 版本](../README_zh.md)。不要通过修改插件 `peerDependencies` 的版本号来消除报错：不同版本的 DSH 持久化接口不同，仅修改版本号无法运行。

## 3. 准备工具与云端资源

### 本地工具

- Docker、Python 3.10 或更高版本，以及 `jq`。
- `agr`（AGR CLI）v0.7.0 或更高版本。本文在宿主机上使用 `agr session` 命令创建、查询和清理 SessionSpace 与 Session，该命令从 v0.7.0 起提供。首次使用时，请按 [AGR CLI 官方 GitHub 凭证配置说明](https://github.com/TencentCloudAgentRuntime/ags-cli/blob/main/README-zh.md#初始化-cli-凭证)完成初始化，再运行 `agr status` 和 `agr doctor`。
- 修改插件并在本地运行单元测试时，还需要 Node.js 24 和 pnpm 11.19.0，见[附录](#附录本地单元测试)。

### 云端资源和会话身份

插件按以下标识确定每个会话保存在哪里：

| 标识 | 由谁提供 | 作用 |
| --- | --- | --- |
| 地域 `AGR_REGION` | 自行配置 | SessionSpace 所在地域，插件和 `agr` 必须使用同一地域 |
| SessionSpace `SESSION_SPACE_ID` | 用户预先创建或选择 | 会话数据的逻辑管理空间 |
| 用户 `SESSION_USER_ID` | 自行配置 | 应用自定义的业务用户标识，与腾讯云账号无关。插件启动时读取一次，此后该实例的所有会话都使用这个值。如需按业务用户区分会话，见[按业务用户区分会话](#按业务用户区分会话) |
| Session ID | 沿用 DSH 会话 ID | 由插件在写入时创建对应的云端 Session，无需手动创建 |
| Agent ID `SESSION_AGENT_ID` | 自行定义，可选 | 业务自定义的 Agent 标识。多个 Agent 共用一个空间时，用于区分各 Agent 的会话；不设置时不区分，见[多个 Agent 共用空间](#多个-agent-共用空间) |

新进程恢复会话时，必须访问**同一地域、同一 SessionSpace、同一用户**下的原会话，并具备读取权限；设置了 `SESSION_AGENT_ID` 时，还需使用相同的值。任一项不同，新进程都看不到原会话。

### 凭证

本文涉及两类凭证，用途各不相同：

| 凭证 | 使用者 | 用途 | 所需权限 |
| --- | --- | --- | --- |
| `.env` 中的 `TENCENTCLOUD_SECRET_ID`、`TENCENTCLOUD_SECRET_KEY` | 容器内的持久化插件 | DSH 运行时读写 Session | 创建、列举、读取 Session，追加和读取 Event |
| `agr` 初始化时配置的凭证 | 宿主机上的 `agr` 命令 | 创建空间、验证和清理 | 管理 SessionSpace，读取和删除 Session |

插件不会读取 `agr` 的配置。请确认两类凭证属于同一账号，否则插件写入的 Session 无法通过 `agr` 查询到。请使用子账号或临时凭证，不要使用主账号密钥。

### 配置环境变量

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

- `set -a` 与 `set +a` 之间通过 `. ./.env` 加载的变量会自动导出，供宿主机上的 `agr` 命令和验证脚本使用。修改 `.env` 后需重新执行这三行。
- `make start` 通过 `docker run --env-file .env` 将同一文件传给容器。修改 `.env` 后需重启容器才能生效。

Docker 读取 `--env-file` 时不解析引号和表达式，因此 `.env` 只能使用简单的 `KEY=value` 格式，值两侧不要加引号，也不要将 `.env` 提交到版本库。

各变量的含义见[云端资源和会话身份](#云端资源和会话身份)，下表说明如何填写。

| 变量 | 是否必填 | 使用者 | 说明 |
| --- | --- | --- | --- |
| `AGR_REGION` | 是 | 插件、`agr` | 示例默认 `ap-shanghai`，须与 SessionSpace 所在地域一致 |
| `SESSION_SPACE_ID` | 是 | 插件、`agr` | 会话保存在哪个 SessionSpace，获取方法见[创建或复用 SessionSpace](#创建或复用-sessionspace) |
| `SESSION_USER_ID` | 是 | 插件、`agr` | 示例默认 `dsh-demo-user`，恢复和清理时须保持一致 |
| `SESSION_AGENT_ID` | 否 | 插件、验证脚本 | 可选，用于区分不同 Agent 的会话；不设置时不区分 |
| `TENCENTCLOUD_SECRET_ID`、`TENCENTCLOUD_SECRET_KEY` | 是 | 插件 | 插件读写 Session 使用的云 API 凭证，见[凭证](#凭证) |
| `TENCENTCLOUD_SESSION_TOKEN` | 使用临时凭证时必填 | 插件 | 临时凭证对应的 Token，过期后需更新并重启容器 |
| `SESSION_API_ENDPOINT` | 否 | 插件、`agr` | 云 API 域名，默认为 `ags.tencentcloudapi.com`，仅在访问其他环境时需要修改 |
| `LLM_BASE_URL`、`LLM_MODEL`、`LLM_API_KEY` | 是 | 示例镜像 | DSH 调用的模型服务，默认使用 TokenHub 的 `deepseek-v4-flash`，见[更换模型服务](#更换模型服务)。仅本示例的镜像使用，集成到自有 DSH 时可沿用原有的模型配置 |

### 创建或复用 SessionSpace

SessionSpace 是存放和管理会话数据的逻辑空间，不与 Agent 或运行实例一一对应。同一个 Agent 的多个运行实例、多个不同 Agent 都可以共用一个空间。是否拆分空间，取决于业务、环境和权限管理需求，而不是 Agent 或实例数量；例如需要独立管理的测试和生产环境可分别创建空间。

SessionSpace 不是执行工作区（workspace），不会在实例之间共享本地文件。多个 Agent 共用空间时如何区分会话，见[多个 Agent 共用空间](#多个-agent-共用空间)。

本示例只需创建或复用一个空间。新增、重启或替换运行实例时无需重新创建。已有可用空间时，填写 `.env` 中的 `SESSION_SPACE_ID`；没有时，执行以下命令为本次示例创建空间：

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

已经用 DSH 0.1.1-rc.2 的插件写入过会话的空间也可以复用，但旧会话在本版本中不可见，见[第 8 节](#8-限制与边界)。

## 4. 将插件集成到现有 DSH

### 最小改动清单

接入 Session 需要以下四项改动：

| 步骤 | 改动 | 何时完成 | 如何确认生效 |
| --- | --- | --- | --- |
| 1. 安装插件 | 将本目录的 `plugin` 目录（`index.js`、`package.json`、`pnpm-lock.yaml`）复制到镜像中，用 pnpm 11.19.0 执行 `pnpm install --prod --frozen-lockfile`，放到 Node.js 全局模块目录下的 `@tencentcloud/ags-dsh-session-persistence` | 构建镜像时 | 见下方「构建后检查」 |
| 2. 与 DSH 共用模块 | 删除插件 `node_modules` 下的 `@deepseek-ai` 目录，将 `cordis`、`dsh-session`、`dsh-session-persistence`、`schemastery` 符号链接到 DSH 实际安装的模块目录（见[模块位置](#模块位置)），使插件和 DSH 使用同一份模块 | 构建镜像时 | 见下方「构建后检查」 |
| 3. 在 Web profile 中注册插件 | Web profile 是 DSH 以 Web 方式运行时加载插件的目录。启动 DSH 前，将插件链接到 `$DSH_HOME/profiles/web/node_modules/@tencentcloud/ags-dsh-session-persistence`，DSH 从这里按名称加载插件 | 容器启动时 | 该路径存在，且指向步骤 1 的安装目录 |
| 4. 启用插件 | 将 [Cordis 补丁](./dockerfiles/agent-runtime-session.cordis.yml)复制到镜像中，在启动 DSH 的命令中加上 `--patch <补丁路径>`，并为容器提供插件所需的环境变量 | 容器启动时 | 见下方「启动后检查」 |

步骤 4 中，插件所需的环境变量为 `AGR_REGION`、`SESSION_SPACE_ID`、`SESSION_USER_ID`、`TENCENTCLOUD_SECRET_ID`、`TENCENTCLOUD_SECRET_KEY`，以及可选的 `TENCENTCLOUD_SESSION_TOKEN`、`SESSION_API_ENDPOINT` 和 `SESSION_AGENT_ID`，含义见[第 3 节](#3-准备工具与云端资源)。

### Cordis 补丁

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

# 以下两项是示例的模型配置，不是接入必需项，见「必需项与示例选择」
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

- 第一项按 `id` 禁用 DSH 内置的 JSONL 持久化插件。
- `insert` 加入本插件：`name` 是插件的包名，DSH 按此名称在 Web profile 的 `node_modules` 中查找插件，因此须与步骤 3 的注册路径一致。
- `config` 中的 `!!js process.env.*` 表示在 DSH 启动时从环境变量读取配置，凭证不会写入镜像或补丁文件。`agentId` 为可选项，见[多个 Agent 共用空间](#多个-agent-共用空间)。
- 后两项配置模型服务，说明见[更换模型服务](#更换模型服务)。

插件 `config` 下的配置项名称（`region`、`spaceId`、`userId` 等）由插件定义，不能修改；右侧的环境变量名称可以按需调整。

### 必需项与示例选择

本示例的镜像除接入 Session 外，还包含一些示例自身的选择。集成到自有 DSH 时，请按下表区分：

| 内容 | 是否接入必需 | 集成到自有 DSH 时 |
| --- | --- | --- |
| 持久化插件、补丁中的前两项、插件所需的环境变量 | 是 | 按上面的四个步骤加入 |
| DSH 及其内部模块的版本 | 是 | 须符合[第 2 节](#2-版本与依赖约定)，见下方「检查自有镜像」 |
| 插件的安装目录 | 否 | 可调整，但须与步骤 3 的注册路径一致 |
| 启动参数：监听地址、端口 3080、`--public-url`、`--no-open` | 否 | 保留自有 DSH 原有的启动参数，只加上 `--patch`。官方 DSH 不接受 `--host 0.0.0.0`，见[启动参数](#启动参数) |
| 模型配置：补丁中的 `llm-pi-ai`、`agent-default-model` 两项和 `LLM_*` 变量 | 否 | 使用自有的模型配置时，删除补丁中的这两项；entrypoint.sh 检测到补丁里没有 `llm-pi-ai` 时会跳过 `LLM_*` 校验 |
| 平台 `linux/amd64` | 否 | 示例镜像的构建平台，插件本身不限平台 |

### 启动参数

本示例的 [entrypoint.sh](./dockerfiles/entrypoint.sh) 使用以下参数启动 DSH：

```sh
dsh --profile web \
  --patch /opt/dsh/agent-runtime-session.cordis.yml \
  --host "<容器 IP>" \
  --port 3080 \
  --no-open \
  --public-url "$DSH_PUBLIC_URL"
```

| 参数 | 说明 |
| --- | --- |
| `--profile web` | 以 Web 方式运行。DSH 0.2 中 `dsh web` 与 `dsh --profile web` 等价 |
| `--host` | 官方 DSH 只接受一个具体的 IP 地址，拒绝 `0.0.0.0` 等通配地址。在容器中需要绑定容器自身的 IP，宿主机才能通过端口映射访问；entrypoint.sh 通过 `hostname -i` 获取，也可以用环境变量 `DSH_HOST` 指定 |
| `--public-url` | 可选。DSH 在日志中打印登录地址时使用的根地址，不影响访问控制。`make start` 将其设为 `http://127.0.0.1:18080/`，使打印的地址可以直接在宿主机上打开 |
| `--no-open` | 不尝试打开浏览器 |

本地访问时，浏览器或脚本请求中的 Host 为 `127.0.0.1:18080`，属于 DSH 默认信任的本机地址，不需要配置 `--trusted-host`。通过其他域名访问 DSH 时，需要用 `--trusted-host` 声明该域名，且只能写完整的域名或 `域名:端口`，不支持 `*.example.com` 这类通配写法。

### 检查自有镜像

运行以下命令检查自有镜像，将 `your-registry/your-dsh:version` 替换为自有镜像：

```bash
make check-dsh-image DSH_IMAGE=your-registry/your-dsh:version
```

该命令在镜像中运行 [check-dsh-image.sh](./dockerfiles/check-dsh-image.sh)，逐项核对[第 2 节](#2-版本与依赖约定)中的版本，并输出 DSH 内部模块的实际位置。通过时的输出：

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

- **没有 `FAIL`**：可以使用方式一。`DSH_MODULES` 与上面的输出不同时，构建时一并传入，见方式一。
- **`WARN`**：Node.js 不是 24，仍可继续构建，但请在构建后执行检查。
- **DSH 或内部模块的版本不符**：请将自有镜像中的 DSH 换成 `0.2.1-rc.2`，或使用与该 DSH 版本对应的插件目录。不要只修改插件 `peerDependencies` 的版本号。
- **未找到 npm 或 `dsh` 命令**：请在自有镜像中补充，或使用方式二自行调整安装和启动步骤。

### 方式一：使用本示例的 Dockerfile 构建

自有镜像通过上述检查时，可以直接用本示例的 [Dockerfile](./dockerfiles/Dockerfile) 在自有镜像上叠加插件。先导出构建产物的镜像名，之后的构建、启动和检查命令都会使用它：

```bash
export DSH_SESSION_IMAGE=your-registry/your-dsh:version-session-persistence
make build DSH_IMAGE=your-registry/your-dsh:version
```

不指定 `DSH_IMAGE` 时，Dockerfile 先在 `node:24.8.0-bookworm-slim` 上用 npm 安装官方 DSH 0.2.1-rc.2，再叠加插件，本示例的预集成镜像即由此构建。检查输出的 `DSH_MODULES` 与默认值不同时，用 `docker build --build-arg DSH_MODULES=<实际目录>` 构建。

构建产物建议沿用基础镜像的仓库和版本，并在标签后加上 `-session-persistence`，以便区分原镜像与加装了插件的镜像。本示例的预集成镜像也采用这一命名，即 `deepseek-harness:v0.2.1-rc.2-session-persistence.2`，末尾的 `.2` 为插件的发布序号。

本示例的 Dockerfile 除了完成四个步骤，还会使用本示例的 [entrypoint.sh](./dockerfiles/entrypoint.sh) 作为启动命令。如自有镜像有自己的启动参数，请将其合并到 entrypoint.sh 中，保留其中的插件注册和 `--patch`。

### 方式二：在自有 Dockerfile 中集成

自有镜像未通过检查，或希望在自己的构建流程中集成插件时，在自有 Dockerfile 和启动脚本中加入以下内容。构建上下文中需包含本目录的 `plugin` 目录和 Cordis 补丁；建议在 `.dockerignore` 中排除 `plugin/node_modules`，避免将本机安装的依赖复制进镜像。

Dockerfile 中加入步骤 1、2：

```dockerfile
FROM your-registry/your-dsh:version

# 自有镜像中 DSH 内部模块的实际目录，以 make check-dsh-image 输出的 DSH_MODULES 为准
ARG DSH_MODULES=/usr/local/lib/node_modules/@deepseek-ai/dsh/node_modules/@deepseek-ai
# 持久化插件的安装目录
ARG PLUGIN_DIR=/usr/local/lib/node_modules/@tencentcloud/ags-dsh-session-persistence

# 步骤 1：安装插件及其依赖，pnpm 版本须与 pnpm-lock.yaml 对应
COPY plugin /tmp/ags-dsh-session-persistence
RUN npm install --global pnpm@11.19.0 \
    && cd /tmp/ags-dsh-session-persistence \
    && pnpm install --prod --frozen-lockfile \
    && mkdir -p "$(dirname "$PLUGIN_DIR")" \
    && rm -rf "$PLUGIN_DIR" \
    && mv /tmp/ags-dsh-session-persistence "$PLUGIN_DIR" \
    && rm -rf /root/.npm /root/.local/share/pnpm/store

# 步骤 2：将插件依赖的 DSH 模块链接到 DSH 的安装位置，与 DSH 共用同一份模块
RUN rm -rf "$PLUGIN_DIR/node_modules/@deepseek-ai" \
    && mkdir -p "$PLUGIN_DIR/node_modules/@deepseek-ai" \
    && for package in cordis dsh-session dsh-session-persistence schemastery; do \
         ln -s "$DSH_MODULES/$package" "$PLUGIN_DIR/node_modules/@deepseek-ai/$package"; \
       done

# 步骤 4 使用的 Cordis 补丁
COPY agent-runtime-session.cordis.yml /opt/dsh/agent-runtime-session.cordis.yml
```

启动脚本中加入步骤 3、4：

```sh
# 步骤 3：在 Web profile 中注册插件，路径需与 Dockerfile 中的 PLUGIN_DIR 一致
profile_modules="${DSH_HOME:-/root/.dsh}/profiles/web/node_modules/@tencentcloud"
mkdir -p "$profile_modules"
ln -sfn /usr/local/lib/node_modules/@tencentcloud/ags-dsh-session-persistence \
  "$profile_modules/ags-dsh-session-persistence"

# 步骤 4：在原有的 DSH 启动命令中加上 --patch，其余参数保持不变
exec dsh --profile web \
  --patch /opt/dsh/agent-runtime-session.cordis.yml \
  ...
```

### 构建后检查

在构建产物中运行插件自带的测试，确认步骤 1、2 生效，即插件能找到并加载 DSH 模块：

```bash
docker run --rm --platform linux/amd64 --entrypoint node "$DSH_SESSION_IMAGE" \
  --test /usr/local/lib/node_modules/@tencentcloud/ags-dsh-session-persistence/index.test.js
```

使用方式一时，也可以执行 `make check-image`，它使用已导出的 `DSH_SESSION_IMAGE`。输出中 `fail` 为 0 即通过。如果报错 `does not provide an export named ...`，说明镜像中 DSH 的版本与插件不一致，见[版本不一致时的表现](#版本不一致时的表现)。

### 启动后检查

启动容器后，确认步骤 3、4 生效：

服务能正常启动并不能说明插件已生效：未加载补丁、仍使用 JSONL 的 DSH 同样可以正常启动。请以云端数据为准，在 DSH 中完成一轮对话后，确认最新的 Session 带有 DSH header：

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

输出 `4` 说明会话已由本版本的插件写入云端。Event 的检查和恢复验证见[第 5 节](#5-验证接入)，恢复成功才能确认接入完成。

如果容器在启动阶段退出，且日志中出现 `SecretId is not found` 等云 API 错误，说明插件已加载但凭证有误：DSH 启动时会通过插件查询云端会话列表。

## 5. 验证接入

### 验证内容

预集成镜像和自建镜像的验证方式相同，需确认以下四项：

1. **云端保存了消息和完整回合**：Session 的 Event 中包含已完成的回合。
2. **运行实例确实被替换**：删除并重建后，容器 ID 不同，且没有复用数据卷。
3. **新进程加载了原历史**：新实例能列出原会话，并读到其中的消息。
4. **新一轮对话继续写入云端**：在原会话中继续对话，模型能答出之前的标识，新回合也写入了云端。

验证可以在 Web UI 中手动完成，也可以通过脚本自动完成，两种方式检查的内容相同。

### 选择要验证的镜像

本节命令通过 `DSH_SESSION_IMAGE` 指定镜像，启动、重建和检查需使用同一镜像：

- **使用预集成镜像**：无需设置，默认为 `ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:v0.2.1-rc.2-session-persistence.2`。
- **使用自建镜像**：在执行本节命令的终端中先导出镜像名，例如 `export DSH_SESSION_IMAGE=your-registry/your-dsh:version-session-persistence`。`make start` 和 `make check-image` 都会使用它。

启动 DSH：

```bash
make start
docker inspect --format '{{.Config.Image}}' dsh-session-demo
```

最后一行输出容器实际使用的镜像，请确认与预期一致。`make start` 启动容器 `dsh-session-demo`，通过 `.env` 传入环境变量，只监听本机回环地址 `127.0.0.1:18080`，不挂载数据卷，并等待 DSH 输出登录地址：

```text
DSH is ready. Sign in at: http://127.0.0.1:18080/?token=...
```

DSH 0.2 的 Web UI 和接口都需要登录。登录地址中的 token 在每次启动容器时重新生成，之后可以随时用 `make url` 再次查看。

使用自建镜像且启动参数与本示例不同时，请按自己的方式启动容器，并将下文的地址 `http://127.0.0.1:18080` 和容器名替换为实际值；脚本验证时，通过 `DSH_BASE_URL` 指定 DSH 的地址，通过 `DSH_LAUNCH_URL` 指定日志中打印的登录地址。

### 通过 Web UI 验证

**保存会话。** 在浏览器中打开 `make start` 输出的登录地址，DSH 会完成登录并跳转到首页。确认输入框下方显示的模型与 `.env` 中的 `LLM_MODEL` 一致，然后新建会话，发送：

```text
请记住这个标识：blue-falcon-42。只回复"已记住"，不要使用工具。
```

收到回复后，在终端中查询最新的 Session，并检查其中的 Event：

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

预期输出类似 `{"events":19,"turns":["completed"]}`：`turns` 中的 `completed` 表示这一轮对话已完整写入云端。

**重建容器。** 删除当前容器，再启动新容器：

```bash
docker inspect --format '{{.Id}}' dsh-session-demo
make stop
make start
docker inspect --format '{{.Id}}' dsh-session-demo
```

前后两次的容器 ID 应不相同。新容器没有挂载数据卷，本地没有任何会话数据。

**恢复会话。** 新容器的 token 已经变化，原页面的登录状态失效。请用新容器的 `make start` 输出的地址重新打开浏览器页面。侧边栏中会出现刚才的会话；打开后可以看到上一轮的消息和回复。在该会话中继续发送：

```text
我之前让你记住的标识是什么？只回复该标识，不要使用工具。
```

模型应回复 `blue-falcon-42`。新问题中不包含该标识，模型只有读到从云端恢复的历史才能答对。再次执行上面的 `agr session event list` 命令，`turns` 应变为 `["completed","completed"]`。

### 通过脚本验证

脚本自动完成上述操作。**保存会话：**

```bash
make seed
```

脚本从容器日志读取登录地址并登录 DSH，新建 DSH 会话，生成随机字符串作为标识（形如 `session-proof-…`）并发给模型要求记住，然后等待云端 Event 中出现完整回合，并确认云端 header 存在。Session ID 和标识保存在 `.local/session.json`。预期输出：

```text
Session: <id>
Cloud header and completed turn verified. State: .local/session.json
Stop and remove the DSH container, start a fresh one without volumes, then run resume.
```

**重建容器并恢复：**

```bash
docker inspect --format '{{.Id}}' dsh-session-demo
make stop
make start
docker inspect --format '{{.Id}}' dsh-session-demo
make resume
```

前后两次的容器 ID 应不相同。脚本随后检查：新 DSH 进程能从会话历史（`session/page`）中读到原标识；向模型发送不含标识的新问题，模型能答出该标识；新一轮对话完整写入云端。预期输出：

```text
Session: <相同的 id>
Persisted history loaded and a new turn completed: session-proof-...
This verifies sequential recovery, not concurrent writers or automatic failover.
```

如需再次独立验证，请使用新的 state 路径，例如 `python3 session_demo.py seed --state .local/another.json`，resume 阶段使用相同路径；直接运行脚本时，需先设置 `DSH_LAUNCH_URL="$(make url)"`。测试期间不要从其他入口写入该会话。

### 结果解读

脚本无法证明运行实例确已替换，因此删除、重建容器以及容器 ID 的变化也是验证依据。

排查失败时，需区分两类情况：历史加载成功但模型回答错误，属于模型召回问题；历史未能加载，才属于持久化问题。

## 6. 可选：其他运行方式

### 更换模型服务

本示例的镜像通过 `.env` 中的以下变量配置模型服务，**无需重新构建镜像**：

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `LLM_BASE_URL` | OpenAI 兼容接口地址 | `https://tokenhub.tencentmaas.com/v1` |
| `LLM_MODEL` | 模型 ID | `deepseek-v4-flash` |
| `LLM_API_KEY` | 模型服务的 API Key | 无，必须填写 |

DSH 0.2 不再读取 `settings.yaml`，模型配置通过 Cordis 补丁中的 `llm-pi-ai` 和 `agent-default-model` 两项提供（见[Cordis 补丁](#cordis-补丁)），DSH 启动时从上述环境变量读取取值：

```text
.env 中的 LLM_* 变量
        ↓
Cordis 补丁中的 llm-pi-ai.providers.custom 与 agent-default-model
        ↓
DSH 启动时读取
```

API Key 不会写入文件：`apiKeyEnv: LLM_API_KEY` 表示 DSH 在运行时从该环境变量读取密钥。使用补丁中的示例模型配置时，任一变量为空都会让容器在启动阶段报错退出，日志提示 `entrypoint: set LLM_...`；删除补丁中的 `llm-pi-ai` 和 `agent-default-model` 后不再校验这些变量。

修改 `.env` 后，执行 `make stop` 和 `make start` 重启容器即可生效。

DSH 会为每个会话单独记录所使用的模型（provider 和模型 ID），并随会话一起保存，恢复会话时沿用该记录。因此，更换模型服务后，新建的会话使用新模型；之前创建的会话仍指向原模型，如果原模型已不在新配置中，继续对话时会报错。此时在 Web UI 输入框下方切换为当前配置的模型即可。

补丁中的 `api` 字段指定接口类型，DSH 0.2.1-rc.2 支持 `openai-completions`、`openai-responses` 和 `anthropic-messages`。如需改用其他接口类型或配置多个模型，请修改 [Cordis 补丁](./dockerfiles/agent-runtime-session.cordis.yml)，并重新构建镜像：

```bash
make build
make start DSH_SESSION_IMAGE=dsh-session:local
```

不指定镜像名时，`make build` 输出本地镜像 `dsh-session:local`，不会覆盖预集成镜像。

### 多个 Agent 共用空间

这里的 Agent 指一个独立的 DSH 应用，例如一个客服助手和一个代码助手，它们有各自的用途和配置。同一个 Agent 可以同时运行多个容器或副本，它们仍属于同一个 Agent。

**默认情况下，共用空间的 Agent 会看到彼此的会话。** 插件只按 SessionSpace 和 `SESSION_USER_ID` 查找会话。如果客服助手和代码助手使用同一个空间和同一个 UserId，打开任意一个助手的 Web UI，侧边栏都会同时列出两边的会话，也能打开并继续另一个助手的会话。

有两种方式让各 Agent 只看到自己的会话：

- **为每个 Agent 使用不同的 SessionSpace。** 为每个 Agent 创建一个空间，分别填入各自 `.env` 的 `SESSION_SPACE_ID`。最简单，不需要额外配置。
- **共用一个空间，用 `SESSION_AGENT_ID` 区分。** 适合希望把会话数据集中在一个空间里管理的场景，设置方法见下文。

#### 使用 SESSION_AGENT_ID

`SESSION_AGENT_ID` 是由业务自行定义的 Agent ID，与腾讯云账号或资源 ID 无关，只需在同一空间内唯一且保持不变。可以直接使用业务系统中已有的 Agent ID，也可以按以下示例自行分配，填入各 Agent 的 `.env`：

| Agent | `.env` 中的设置 |
| --- | --- |
| 客服助手（无论运行几个容器） | `SESSION_AGENT_ID=agt-10001` |
| 代码助手 | `SESSION_AGENT_ID=agt-10002` |

同一个 Agent 的所有容器或副本必须使用相同的 ID，否则替换容器后找不到原来的会话。修改 `.env` 后，执行 `make stop` 和 `make start` 重启容器生效。

设置后的效果：

- 每个 Agent 的侧边栏只列出自己创建的会话；
- 即使知道其他 Agent 的会话 ID，通过 DSH 接口直接访问也无法打开；
- 设置 `SESSION_AGENT_ID` 之前创建的会话不再显示。这些会话仍保存在云端，并没有被删除；清空该变量并重启容器后可以重新看到。

**实现方式。** 插件新建会话时，会把 Agent ID 写入 Session 的 Metadata。Metadata 是 Session 上的一组自定义键值对，查询会话时可以作为过滤条件；插件列出会话时，就是按这个键值对筛选出当前 Agent 的会话。本示例使用的 key 是 `example.com/dsh-agent-id`。如需改用其他 key，例如与业务系统已有的命名保持一致，请同时修改 [plugin/index.js](./plugin/index.js) 和 [session_demo.py](./session_demo.py) 中的 `AGENT_METADATA_KEY`，再按[更换模型服务](#更换模型服务)末尾的方法重新构建镜像。改用新 key 后，按原 key 记录的会话不再显示。

除 Agent ID 外，Metadata 也可以记录租户、业务线、渠道等其他业务标识，用于归类和查询会话。本示例的插件只写入 Agent ID；如需记录其他标识，请修改 [plugin/index.js](./plugin/index.js) 中的 `createStoredSession`，在创建 Session 时补充相应的 Metadata，并重新构建镜像。

#### 验证

1. 在 `.env` 中设置 `SESSION_AGENT_ID=agt-10001`，执行 `make stop` 和 `make start` 重启容器，按[第 5 节](#5-验证接入)保存一轮会话。
2. 将其改为 `agt-10002` 并重启容器，再保存一轮会话。此时侧边栏中只有这一步的会话，看不到第 1 步的会话。
3. 改回 `agt-10001` 并重启容器。第 1 步的会话重新出现在侧边栏中，并且可以打开。

使用脚本验证时，每次 `seed` 都需要一个新的 state 文件，请为每个 Agent 指定不同的路径，例如 `python3 session_demo.py seed --state .local/agt-10001.json`，`resume` 时使用相同的路径。

### 按业务用户区分会话

**Session 服务本身支持按用户隔离会话。** 每个会话属于创建时指定的 UserId；列出、读取、追加 Event 和删除会话时都需要传入 UserId，只能访问该 UserId 下的会话，使用其他 UserId 访问时，服务返回会话不存在。UserId 由调用方传入，Session 服务不会校验调用方是否就是该用户，持有云 API 凭证的程序可以使用任意 UserId，因此应由应用确保传入正确的用户 ID。

**本示例的插件只使用一个固定的 UserId。** 插件在启动时从 `SESSION_USER_ID` 读取一个用户 ID，这个 DSH 实例创建和查询的所有会话都使用这个值。插件无法区分实例中的不同使用者：DSH 0.2.1-rc.2 交给持久化插件的创建、打开和列出请求都只包含会话信息，不包含"当前是哪个用户在操作"。因此，**一个 DSH 实例只对应一个用户 ID**，使用同一个实例的所有人会看到同一批会话。

如需让每个业务用户只看到自己的会话，请为每个业务用户使用独立的 DSH 实例：为每个用户启动一个 DSH 容器，启动时将该用户在业务系统中的用户 ID 填入 `SESSION_USER_ID`。

| 业务用户 | 该用户实例的 `.env` 中的设置 |
| --- | --- |
| 用户 A，业务系统中的用户 ID 为 `u-1001` | `SESSION_USER_ID=u-1001` |
| 用户 B，业务系统中的用户 ID 为 `u-1002` | `SESSION_USER_ID=u-1002` |

用户 A 之后再次使用时，为其启动新实例并使用相同的 `SESSION_USER_ID=u-1001`，即可加载之前的会话；用户 B 的实例看不到用户 A 的会话。这种方式不需要修改插件。

### 多副本部署

本节说明用多个 DSH 副本（例如多个沙箱实例）共同提供服务时，会话如何使用和切换，以及会遇到的问题。这里的"副本"指使用同一份镜像、相同 `AGR_REGION`、`SESSION_SPACE_ID`、`SESSION_USER_ID` 和 `SESSION_AGENT_ID` 的多个 DSH 进程。在 AGS 上运行本示例的镜像，需要先完成[部署到 AGS](#部署到-ags)中的适配。

#### 支持的使用方式

| 场景 | 是否支持 | 说明 |
| --- | --- | --- |
| 不同会话由不同副本并行处理 | 支持 | 各副本处理各自的会话，互不影响 |
| 同一个会话先由 A 处理，A 停止后由 B 接着处理 | 支持 | B 收到该会话的第一条消息时，从云端读回历史后继续。已在 0.2.1-rc.2 上验证（A 正常停止，B 为新启动的容器） |
| 同一个会话同时由多个副本处理 | **不支持** | 见「为什么同一个会话只能由一个副本处理」 |
| 每一轮对话由任意副本处理，请求可以落到任何副本 | **不支持** | 见「不支持的方式」 |

"A 停止"指 A 的进程已退出或已重启，内存里不再保留该会话。仅停止向 A 发送请求不算停止：A 仍持有旧状态，之后的写入会和新副本冲突，见下文。

#### 为什么同一个会话只能由一个副本处理

- 每个副本把会话读进自己的内存，新产生的记录在内存里接着往后编号。
- 写入云端时，记录的 EventId 是 `dsh-<会话 ID>-<序号>`。对同一个 EventId，Session 服务在内容完全相同时视为重复请求并返回成功；内容不同则拒绝，返回 `ResourceInUse.EventIdDuplicate`，提示 `EventId 已存在`。
- 云端不会通知副本"别人写了新内容"，副本也不会在每次写入前重新读取历史。两个副本各自往后编号，就会写到同一个序号上：先写入的成功，后写入的被拒绝。
- 云端历史不会因此被写坏，仍然是连续的。但被拒绝的副本，内存里的记录已经和云端不一致，该会话再发消息，会在这个副本上持续失败，直到它重新从云端加载。

插件只在单个 DSH 进程内保证一个会话只有一个写入方，没有跨进程的租约或锁。

#### 会触发冲突的情况

1. **旧副本还在运行。** A 暂时没有收到某个会话的请求，但进程仍在运行，内存里保留着旧的历史。B 接手该会话并继续对话之后，如果请求又落回 A，A 会按旧历史继续编号，写入被拒绝，这一轮失败，之后持续失败。这是最典型的情况。
2. **两个副本几乎同时处理同一个会话。** 后接手的副本会读到先到副本尚未完成的一轮，把这一轮记为中断，写入修复记录后继续自己的一轮。先到副本这一轮的回复无法写入云端，但它自己这边仍显示该轮已完成，下一次通过它发消息时才会报错。是否触发取决于两个副本写入的先后，并非每次都会发生。

#### 现象

- 界面显示 `本轮运行失败 EventId 已存在`，错误码 `UNKNOWN`。出错的副本上也可能只显示通用的内部错误提示。
- 部分失败路径不会留下容器日志：这类冲突通常只表现为界面报错，前台写入失败不写日志；后台写入失败和关闭时的排空失败会记录警告，以 `session-persistence:` 开头并带会话 ID。建议先搜这类警告，再结合入口路由日志判断。
- 同一个会话在另一个副本上正常，云端历史连续。

#### 如何确认和恢复

- **确认**：在入口或网关日志中，查看出错会话的 ID 是否被分发到了不止一个副本。
- **恢复**：先确认该会话只由一个副本处理，其他副本不再执行和写入这个会话，否则重新接手会再次冲突。然后重启出错的副本，它在下一次收到该会话的请求时，从云端重新加载完整历史并继续。已实测：重启后该副本读回完整历史、继续对话，云端记录保持连续。仅停止向它发送请求不够，它内存里的旧记录不会消失。
- 无法只在这个副本上"刷新"该会话，只能重启副本，让它重新从云端加载。DSH 的接口本身支持卸载单个会话（`AgentHandle.dispose()`），但 Web 入口没有提供这个操作；只有在集成时自行管理会话的创建和销毁才能用上，本示例没有这样做。

#### 切换副本的步骤

1. 让原副本退出或重启。只停止向它发送请求不够：它可能仍在执行某一轮，或缓冲区里还有未写入的事件，之后会和新副本冲突。进程退出或重启后，内存里的旧状态才消失。
2. 确认接手副本还没有加载过这个会话。已经加载过的副本会继续用它内存里的旧记录，不会自动从云端刷新；这种情况下需要先重启该副本。
3. 让请求落到新副本。它第一次收到该会话的消息时，会从云端读取最新历史并继续。
4. 原副本还没来得及写入云端的内容，以及切换时正在执行的那一轮，不会自动接续。这一轮会被记为中断，用户需要重新发送。

#### 入口路由

沙箱实例各自独立，请求如何分发取决于自己的入口。建议：

- 按会话 ID 选择副本，使同一个会话固定落在同一个副本上，不同会话分散到多个副本。
- 会话 ID 不在请求路径里。DSH 的 `session/prompt` 等接口把它放在请求体的 `sessionId` 中（`session/page` 放在 `address.sessionId`），入口需要解析请求体才能按会话路由。做不到时，可以退而按客户端标识（例如用户）固定，使同一个用户的会话落在同一个副本。
- 副本故障或被回收后，由入口把该会话重新分配给另一个副本，新副本自动从云端接手。

#### 副本之间不共享的状态

会话的事件记录保存在云端，其余状态都在副本本地，不会跟着会话换到另一个副本：

| 状态 | 位置 | 影响 |
| --- | --- | --- |
| 登录状态 | 每个副本自己生成登录 token 和签发 cookie 的签名密钥，保存在 `$DSH_HOME/.credentials.yaml` | 浏览器 cookie 在其他副本上验证不通过，需要用该副本的登录地址重新登录。token 每次启动也会变化 |
| 实时事件流 | 浏览器通过一条 WebSocket 连接到某个副本，事件只来自该副本 | 请求被分发到其他副本时，界面不会实时显示这一轮的输出 |
| 附件 | `$DSH_HOME/attachments/v1` | 换副本后读不到之前上传的附件 |
| 工作区文件 | 容器内的工作目录（本示例为 `/workspace`） | 换副本后工作区内容不在 |
| 投影缓存 | `$DSH_HOME/storages` | 只是缓存，换副本后自动重建 |

所以"无状态多副本"目前只对会话记录成立：会话历史可以随副本的替换保留，但副本之间不能互换使用。需要登录状态或事件流在所有副本之间一致时，需要自行处理，例如为所有副本预置同一份签名密钥、在入口统一路由，本示例没有实现。

#### 不支持的方式

- **请求落到任意副本处理。** 副本在处理会话期间持有写入方和内存状态。让另一个副本处理下一轮，需要原副本先卸载该会话；目前的 Web 入口没有提供这个操作，只能通过重启进程清掉旧状态。
- **多个副本共同处理同一个会话。** 需要跨副本的租约或锁，以及副本之间转发请求和事件，本示例没有实现。

### 部署到 AGS

本示例的镜像目前**不能直接运行在 AGS 沙箱或 Deployment 中**。原因不在持久化插件，而在官方 DSH 0.2.1-rc.2 的 Web 服务对网络访问的限制。本节说明需要哪些适配，供自行实现时参考。

以下结论来自 DSH 0.2.1-rc.2 的源码和 DSH 0.1.1-rc.2 版本 AGS 适配补丁的对比，尚未在 AGS 上实测。

#### DSH 0.1.1-rc.2 的做法

DSH 0.1.1-rc.2 的 AGS 镜像在构建时为 DSH 打了一个补丁（[0001-support-ags-deployment-web.patch](../../../deployment-cookbook/deepseek-harness/all-in-one/dockerfiles/0001-support-ags-deployment-web.patch)），放开了以下限制：

| 补丁内容 | 作用 |
| --- | --- |
| 允许 `--host 0.0.0.0` | 沙箱网关从 Pod 外部访问 DSH |
| `--trusted-host` 支持 `*.后缀` 通配 | 沙箱的访问域名随实例变化，用通配一次覆盖 |
| 浏览器 Origin 可以是另一个受信任的 HTTPS 域名 | 网关将 Host 改写为内部域名、保留浏览器的公网 Origin 时，请求不被拒绝 |
| 新增 `--allow-remote-management` | 允许受信任的域名调用原本只允许本机访问的管理接口 |

#### DSH 0.2.1-rc.2 的对应行为

| 方面 | 官方 DSH 0.2.1-rc.2 | 部署到 AGS 时需要的处理 |
| --- | --- | --- |
| 监听地址 | 只接受一个具体的 IP，拒绝 `0.0.0.0` | 绑定 Pod 自身的 IP，本示例的 entrypoint.sh 已这样处理；需确认网关通过 Pod IP 访问 DSH |
| 受信任的域名 | 只接受完整的 `域名` 或 `域名:端口`，不支持通配 | 在启动时得到本实例的完整访问域名并传给 `--trusted-host`；需确认沙箱内能否获取实例 ID 或访问域名 |
| Host 与 Origin | 浏览器请求的 Origin 必须与 Host 一致 | 网关保留原始 Host 时无需处理；改写 Host 时，需要把补丁中的 Origin 放宽逻辑移植到 0.2.1-rc.2，或在容器内增加一层统一 Host 的反向代理 |
| 管理接口 | 所有接口都要求登录，不再区分本机和远程，`--allow-remote-management` 已不需要 | 无需处理 |
| 登录 | 首次访问须带启动日志中的 `?token=`，每次启动重新生成 | 需要从实例日志中取得登录地址，并用 `--public-url` 让日志中打印的地址指向网关访问地址；脚本验证时把该地址设为 `DSH_LAUNCH_URL` |

#### 可选的实现方式

| 方式 | 改动 | 说明 |
| --- | --- | --- |
| 移植 AGS 补丁 | 将补丁中的通配 `--trusted-host` 和 Origin 放宽移植到 DSH 0.2.1-rc.2 的 `dsh-web-app` 与 `dsh-client-connection`，用补丁后的 DSH 构建镜像 | 与 0.1.1-rc.2 的做法一致，但需维护 DSH 补丁，每次升级 DSH 都要重新移植 |
| 不修改 DSH | 绑定 Pod IP，启动时计算完整访问域名传给 `--trusted-host`，网关改写 Host 时在容器内增加反向代理 | 不需要维护 DSH 补丁。反向代理会绕过 DSH 自身的 Host/Origin 校验，需由网关负责访问控制 |

两种方式都只涉及 DSH 的启动参数和镜像，持久化插件和 Cordis 补丁无需修改。

## 7. 清理

停止本地容器，先预览清理范围，再删除：

```bash
make stop
python3 session_demo.py cleanup
# 核对预览结果后删除：
python3 session_demo.py cleanup --delete
```

不带 `--delete` 时，脚本只列出将要删除的会话。设置了 `SESSION_AGENT_ID` 时，只包含该 Agent 的会话；未设置时，包含该 UserId 在空间中的全部会话。共用空间时，请先核对预览结果再删除。

确认每个会话均输出 `deleted` 后，再删除本地 state 文件：

```bash
rm -rf .local
```

如果 SessionSpace 是为本示例新建的，且其中内容均不再需要，可将其删除；复用的已有空间或共用空间不要删除：

```bash
agr session space delete \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --space-id "$SESSION_SPACE_ID" \
  --output json
```

## 8. 限制与边界

本示例的持久化插件只处理正常的写入流程，以下情况未做处理：

- **已有的历史不会迁移。** 启用插件后，DSH 只读写云端会话，原有的本地会话不再可见。DSH 0.1.1-rc.2 的插件写入的会话（header 的 `version` 为 0）不会出现在会话列表中，直接打开时提示格式不受支持。两个版本请使用不同的 SessionSpace 或 `SESSION_AGENT_ID`。
- **写入中途失败。** 插件逐条追加 Event，一批全部成功后才推进序号。中途失败时，已写入的 Event 留在云端，未写入的记录保留在缓冲区，下一次 flush 时整批重试；重试中已写入的 Event 使用相同的 Event ID，Session 服务视为重复请求。插件遇到云 API 限流时会自动退避重试。容器在重试成功前退出时，缓冲区中的记录会丢失。
- **多个写入者。** 插件只在单个 DSH 进程内保证一个会话只有一个写入方，没有跨实例的协调机制。多个 DSH 实例处理同一个会话时，先写入的成功，后写入的被云端拒绝（`EventId 已存在`），云端历史保持连续，但被拒绝的副本之后在该会话上持续失败，需要重启该副本。详见[多副本部署](#多副本部署)。
- **进行中的回合不会自动接续。** DSH 进程在一轮对话进行中退出时，这一轮不会由其他进程自动继续。新进程打开会话时，DSH 会为中断的回合追加结束记录，已写入的历史仍保留，需要用户重新发起请求。
- **只恢复会话状态。** 文件、运行中的进程和模型长连接都不会恢复。
- **超大 Event。** 插件将每个 Event 完整写入，不做拆分。工具返回大量内容时，单个 Event 可能超出 Session API 的大小限制而写入失败。
- **会话数量。** DSH 每次列出会话时，插件会查询该用户的全部 Session，并为每个会话读取一次 Event 数量。会话很多时，列表加载会变慢，也更容易触发限流。
- **完整性检查。** 加载时会按原始事件排序并检查序号连续性和记录格式，可发现大部分不完整的写入，但无法覆盖全部情况。

如需将本插件用于生产环境，或让多个 DSH 实例写入同一会话，需要先针对以上情况补充相应的处理。

## 常见问题

- **启动报错 `does not provide an export named ...`**：DSH 的版本与插件不一致，见[版本不一致时的表现](#版本不一致时的表现)。
- **启动报错 `--host 0.0.0.0 is an unspecified (wildcard) address`**：官方 DSH 0.2 不接受通配地址，请绑定具体的 IP，见[启动参数](#启动参数)。
- **页面或接口返回 `dsh web authentication required`**：未登录或 token 已失效。执行 `make url`，用当前容器输出的地址重新打开页面。
- **凭证或空间报错**：分别核对 `agr` 和容器所用的账号、地域、SpaceId、权限以及临时凭证有效期。
- **容器启动后立即退出**：执行 `docker logs dsh-session-demo`。若出现 `SecretId is not found` 等云 API 错误，请核对 `.env` 中的 `TENCENTCLOUD_*` 凭证：DSH 启动时会通过持久化插件查询会话列表，插件凭证无效时启动即失败。若出现 `entrypoint: set ...`，请按提示补全变量。
- **连接被拒绝**：等待 `make start` 输出登录地址，并查看容器日志。如修改了 `PORT`，需同步修改脚本使用的 `DSH_BASE_URL`。
- **模型调用报错**：核对 `.env` 中的 `LLM_BASE_URL`、`LLM_MODEL`、`LLM_API_KEY`，以及账号的模型权限。Session 凭证不包含模型权限。
- **更换模型后旧会话报错**：DSH 为每个会话记录了所使用的模型，旧会话仍指向原模型。请在 Web UI 输入框下方切换为当前配置的模型，见[更换模型服务](#更换模型服务)。
- **新容器看不到原会话**：确认新容器的 `AGR_REGION`、`SESSION_SPACE_ID`、`SESSION_USER_ID`、`SESSION_AGENT_ID` 与写入时一致，并用 `docker inspect --format '{{.Config.Image}}' dsh-session-demo` 确认使用的是已集成插件的镜像。DSH 0.1.1-rc.2 写入的会话在本版本中不可见。
- **界面提示 `本轮运行失败 EventId 已存在`**：同一个会话被多个副本处理，或请求落回了仍保留旧历史的副本。该副本上的这个会话会持续失败，重启该副本后恢复。排查方法和切换步骤见[多副本部署](#多副本部署)。
- **历史序号不连续**（`non-contiguous DSH event log`）：先停止写入，再排查未完整写入的事件，不要通过删除事件来掩盖报错。
- **多用户场景**：本示例的所有会话都使用同一个 `SESSION_USER_ID`。如需按业务用户区分会话，见[按业务用户区分会话](#按业务用户区分会话)。

## 附录：本地单元测试

以下检查不访问云端资源，用于修改插件或脚本后的自测。需要 Node.js 24 和 pnpm 11.19.0。

```bash
make setup
make check
# 在镜像中运行插件测试，检查 DSH_SESSION_IMAGE 指定的镜像，默认为预集成镜像：
make check-image
```

插件测试直接使用 DSH 0.2.1-rc.2 的持久化接口和校验逻辑，覆盖事件投影、会话创建与恢复、单写者、失败重试和历史加载，但不能替代真实的 seed → 新容器 → resume 流程。
