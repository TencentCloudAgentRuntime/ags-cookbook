# 使用 Agent Runtime Session 持久化 DeepSeek Harness 会话

[English](./README.md)

DeepSeek Harness（下文简称 DSH）默认将会话保存在本地磁盘的 JSONL 文件中。若 DSH 运行在未挂载数据卷的容器中，删除容器后会话历史也随之丢失。本示例通过持久化插件将 DSH 的会话写入云端 Agent Runtime Session：删除容器再启动全新的容器后，仍可加载原会话并继续对话。

本示例只涉及会话持久化。如需同时保留工作区文件，并将后续请求路由回原工作区，请参考 [Session 与工作区关联示例](../../deployment-cookbook/brain-hands-session/README_zh.md)。

## 快速体验

使用本示例的预集成镜像（已安装持久化插件），可以快速完成一次会话的保存与恢复。在本目录执行：

```bash
cp .env.example .env            # 填入凭证和模型 API Key，见第 2 节
set -a; . ./.env; set +a
agr session space create \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --name dsh-session-demo \
  --output json \
  --jq '.Data.SessionSpace.SpaceId'
# 将输出的 SpaceId 填入 .env 的 SESSION_SPACE_ID，然后重新加载：
set -a; . ./.env; set +a

make start                      # 启动预集成镜像
curl -sf -o /dev/null --retry 60 --retry-delay 2 --retry-all-errors --max-time 5 http://127.0.0.1:18080/ || docker logs --tail 20 dsh-session-demo
make seed                       # 保存一轮带标识的对话
make stop && make start         # 删除容器，再启动新容器
curl -sf -o /dev/null --retry 60 --retry-delay 2 --retry-all-errors --max-time 5 http://127.0.0.1:18080/ || docker logs --tail 20 dsh-session-demo
make resume                     # 新容器加载历史，模型答出标识即成功
```

等待服务就绪的命令最多重试约 2 分钟，超时后会输出容器日志的最后 20 行，便于排查。各步骤的含义和预期输出见[第 4 节](#4-验证接入)，用完后按[第 6 节](#6-清理)清理。如需将插件集成到自有 DSH，见[第 3 节](#3-将插件集成到现有-dsh)。

## 1. 接入原理

### 接入点

DSH 通过 **SessionPersistence 扩展点**决定会话保存在哪里，内置实现是写本地文件的 `session-persistence-jsonl` 插件。本示例提供实现同一扩展点的插件 `@tencentcloud/ags-dsh-session-persistence`，并在 DSH 启动时通过 Cordis 补丁禁用 JSONL 插件、启用本插件。Cordis 是 DSH 的插件框架，补丁是一个 YAML 配置文件，用于在不修改 DSH 代码的情况下调整加载哪些插件。DSH 的其他部分，包括模型调用、工具执行和 Web UI，都不需要修改。

```text
DSH 产生会话记录  →  持久化插件写入云端  →  SessionSpace 中的 Session 和 Events
                                                    │
新 DSH 进程  ←  持久化插件读取历史  ←────────────────┘
```

### 会话的生命周期

| 阶段 | 发生了什么 |
| --- | --- |
| 开始保存 | 在新会话中发送第一条消息后，插件沿用 DSH 会话 ID 作为 Session ID，调用 `CreateSession` 在云端创建对应的 Session，并将 DSH 的会话元数据（header）写入其中。只新建、未发送消息的会话不会写入云端。 |
| 后续写入 | DSH 每向会话日志追加记录，插件就将其转换为 Event，通过 `AppendEvent` 追加到该 Session。 |
| 新进程列出会话 | DSH 启动后列出会话时，插件查询该用户在 SessionSpace 中的 Session，只返回带有 DSH header 的会话；设置了 `SESSION_AGENT_ID` 时，只返回该 Agent 的会话。Web UI 侧边栏中的会话列表即来源于此。 |
| 打开原会话 | 插件读回 header 和全部 Event，按序号排序并检查连续性后，交给 DSH 重建会话。 |

云端 Session 由插件在写入时创建，不需要手动创建。

### 数据约定

插件在 Session 的标准字段之外，用以下自定义字段保存 DSH 恢复会话所需的数据：

| 数据 | 位置 | 用途 |
| --- | --- | --- |
| DSH 会话 header | `State.CustomState.dshHeader` | 插件据此识别 DSH 会话并重建元数据 |
| 原始 DSH 事件 | Event 的 `Extensions.dshEvent` | 插件据此原样重建会话日志 |
| 消息正文和推理内容 | `Content.Parts`，推理内容标记为 Thought | 便于其他系统直接读取，DSH 恢复时不使用 |
| 工具调用与结果 | `Content.Parts[].FunctionCall` / `FunctionResponse` | 同上 |
| 部分配置变更 | `Actions.StateDelta` | 同上 |
| 类型、序号、回合标记 | `Event.Metadata`，含 Partial、TurnComplete、Interrupted | 同上 |

`dshHeader` 和 `dshEvent` 是**本插件定义的约定**，不是 Session 服务的通用格式。DSH 恢复会话只依赖这两部分。由其他应用写入、不带这两部分的 Session 和 Event，不会出现在 DSH 中，也不能作为 DSH 历史恢复。

### 接入前须知

以下几点会影响接入后现有会话的行为，详细说明见[第 7 节](#7-限制与边界)：

- **本地已有的 JSONL 历史不会迁移到云端。** 启用插件后，DSH 只能看到云端的会话。
- **同一个会话不要同时由多个 DSH 实例写入。** 多个实例可以共用一个空间、各自处理不同的会话，但插件不协调多个实例同时写入同一个会话。
- **只恢复会话，不恢复工作环境。** 文件、运行中的进程和模型长连接都不会恢复；一轮对话进行中时实例退出，这一轮需要重新发起。

## 2. 准备工具与云端资源

### 本地工具

- Docker（需支持运行 `linux/amd64` 镜像）、Python 3.10 或更高版本，以及 `jq`。
- 已安装 **v0.7.0 或更高版本**的 `agr`（AGR CLI）。本文在宿主机上使用 `agr session` 命令创建、查询和清理 SessionSpace 与 Session，该命令从 v0.7.0 起提供。首次使用时，请按 [AGR CLI 官方 GitHub 凭证配置说明](https://github.com/TencentCloudAgentRuntime/ags-cli/blob/main/README-zh.md#初始化-cli-凭证)完成初始化，再运行 `agr status` 和 `agr doctor`。

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

本文涉及三类凭证，用途各不相同：

| 凭证 | 使用者 | 用途 | 所需权限 |
| --- | --- | --- | --- |
| `.env` 中的 `TENCENTCLOUD_SECRET_ID`、`TENCENTCLOUD_SECRET_KEY` | 容器内的持久化插件 | DSH 运行时读写 Session | 创建、列举、读取 Session，追加和读取 Event |
| `agr` 初始化时配置的凭证 | 宿主机上的 `agr` 命令 | 创建空间、验证和清理 | 管理 SessionSpace，读取和删除 Session |
| CAM 角色 `AGR_ROLE_ARN` | AGS 沙箱 | 仅在[第 5 节](#5-可选其他运行方式)中将 DSH 部署到云上时使用 | 见第 5 节 |

插件不会读取 `agr` 的配置。请确认前两类凭证属于同一账号，否则插件写入的 Session 无法通过 `agr` 查询到。请使用子账号或临时凭证，不要使用主账号密钥。

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

| 变量 | 是否必填 | 使用者 | 说明 |
| --- | --- | --- | --- |
| `AGR_REGION` | 是 | 插件、`agr` | SessionSpace 所在地域，示例默认为上海 `ap-shanghai`。见[云端资源和会话身份](#云端资源和会话身份) |
| `SESSION_SPACE_ID` | 是 | 插件、`agr` | 会话保存在哪个 SessionSpace，获取方法见[创建或复用 SessionSpace](#创建或复用-sessionspace) |
| `SESSION_USER_ID` | 是 | 插件、`agr` | 业务自定义的用户 ID，本示例可保持默认值 `dsh-demo-user`。恢复和清理时必须保持一致。一个 DSH 实例只对应一个用户 ID，见[按业务用户区分会话](#按业务用户区分会话) |
| `SESSION_AGENT_ID` | 否 | 插件、验证脚本 | 业务自定义的 Agent ID，用于标识会话属于哪个 Agent，与腾讯云账号或资源 ID 无关。多个 Agent 共用一个空间时，各 Agent 只看到自己的会话；同一 Agent 的所有容器使用相同的 ID。见[多个 Agent 共用空间](#多个-agent-共用空间) |
| `TENCENTCLOUD_SECRET_ID`、`TENCENTCLOUD_SECRET_KEY` | 是 | 插件 | 插件读写 Session 使用的云 API 凭证，见[凭证](#凭证) |
| `TENCENTCLOUD_SESSION_TOKEN` | 使用临时凭证时必填 | 插件 | 临时凭证对应的 Token，过期后需更新并重启容器 |
| `SESSION_API_ENDPOINT` | 否 | 插件、`agr` | 云 API 域名，默认为 `ags.tencentcloudapi.com`，仅在访问其他环境时需要修改 |
| `LLM_BASE_URL`、`LLM_MODEL`、`LLM_API_KEY` | 是 | 示例镜像 | DSH 调用的模型服务，默认使用 TokenHub 的 `deepseek-v4-flash`，见[更换模型服务](#更换模型服务)。仅本示例的镜像使用，集成到自有 DSH 时可沿用原有的模型配置 |
| `AGR_DOMAIN` | 在云上运行时必填 | 示例镜像 | 仅在[在云上运行](#在云上运行)时使用，本地运行保持默认值 `tencentags.com` 即可 |

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

## 3. 将插件集成到现有 DSH

### 最小改动清单

接入 Session 需要以下四项改动：

| 步骤 | 改动 | 何时完成 | 如何确认生效 |
| --- | --- | --- | --- |
| 1. 安装插件 | 将本仓库的 `plugin` 目录（`index.js`、`package.json`、`pnpm-lock.yaml`）复制到镜像中，执行 `pnpm install --prod --frozen-lockfile`，放到 Node.js 全局模块目录下的 `@tencentcloud/ags-dsh-session-persistence` | 构建镜像时 | 见下方「构建后检查」 |
| 2. 与 DSH 共用模块 | 删除插件 `node_modules` 下的 `@deepseek-ai` 目录，将 `cordis`、`dsh-session`、`dsh-session-persistence`、`schemastery` 符号链接到 DSH 的实际安装位置，使插件和 DSH 使用同一份模块 | 构建镜像时 | 见下方「构建后检查」 |
| 3. 在 Web profile 中注册插件 | Web profile 是 DSH 以 Web 方式运行时加载插件的目录。启动 DSH 前，将插件链接到 `$DSH_HOME/profiles/web/node_modules/@tencentcloud/ags-dsh-session-persistence`，DSH 从这里按名称加载插件 | 容器启动时 | 该路径存在，且指向步骤 1 的安装目录 |
| 4. 启用插件 | 将 [Cordis 补丁](./dockerfiles/agent-runtime-session.cordis.yml)复制到镜像中，在启动 `dsh web` 的命令中加上 `--patch <补丁路径>`，并为容器提供插件所需的环境变量 | 容器启动时 | 见下方「启动后检查」 |

步骤 4 中，插件所需的环境变量为 `AGR_REGION`、`SESSION_SPACE_ID`、`SESSION_USER_ID`、`TENCENTCLOUD_SECRET_ID`、`TENCENTCLOUD_SECRET_KEY`，以及可选的 `TENCENTCLOUD_SESSION_TOKEN`、`SESSION_API_ENDPOINT` 和 `SESSION_AGENT_ID`，含义见[第 2 节](#2-准备工具与云端资源)。

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
```

- 第一项按 `id` 禁用 DSH 内置的 JSONL 持久化插件。
- `insert` 加入本插件：`name` 是插件的包名，DSH 按此名称在 Web profile 的 `node_modules` 中查找插件，因此须与步骤 3 的注册路径一致。
- `config` 中的 `!!js process.env.*` 表示在 DSH 启动时从环境变量读取配置，凭证不会写入镜像或补丁文件。`agentId` 为可选项，见[多个 Agent 共用空间](#多个-agent-共用空间)。

`config` 下的配置项名称（`region`、`spaceId`、`userId` 等）由插件定义，不能修改；右侧的环境变量名称可以按需调整。

### 必需项与示例选择

本示例的镜像除接入 Session 外，还包含一些示例自身的选择。集成到自有 DSH 时，请按下表区分：

| 内容 | 是否接入必需 | 集成到自有 DSH 时 |
| --- | --- | --- |
| 持久化插件、Cordis 补丁、插件所需的环境变量 | 是 | 按上面的四个步骤加入 |
| DSH 模块版本与插件一致 | 是 | 见下方「检查自有镜像」 |
| 插件的安装目录 | 否 | 可调整，但须与步骤 3 的注册路径一致 |
| 启动参数：监听地址、端口 3080、可信主机、`--allow-remote-management` | 否 | 保留自有 DSH 原有的启动参数，只加上 `--patch` |
| 模型配置：通过 `LLM_*` 变量生成 settings.yaml（[configure-model.mjs](./dockerfiles/configure-model.mjs)）、TokenHub、`deepseek-v4-flash` | 否 | 保留自有 DSH 原有的模型配置 |
| 平台 `linux/amd64` | 否 | 示例镜像的构建平台，插件本身不限平台 |

### 检查自有镜像

插件依赖 DSH 的部分内部模块，版本须与插件的 [package.json](./plugin/package.json) 中 `peerDependencies` 一致。运行以下命令检查自有镜像，将 `your-registry/your-dsh:version` 替换为自有镜像：

```bash
docker run --rm --platform linux/amd64 --entrypoint sh your-registry/your-dsh:version -c '
m=/usr/local/lib/node_modules/@deepseek-ai
ok() { echo "OK    $1"; }; bad() { echo "FAIL  $1"; fail=1; }
[ -f "$m/dsh/lib/bin.js" ] && ok "DSH 入口 $m/dsh/lib/bin.js" || bad "未找到 DSH 入口 $m/dsh/lib/bin.js"
command -v npm >/dev/null && ok "npm" || bad "未找到 npm"
case "$(node -v 2>/dev/null)" in v24.*) ok "Node.js $(node -v)";; *) echo "WARN  Node.js $(node -v 2>/dev/null || echo 未安装)，插件仅在 Node.js 24 下验证过";; esac
for p in cordis:4.0.1 dsh-session:0.1.1-rc.2 dsh-session-persistence:0.1.1-rc.2 schemastery:3.18.1; do
  n=${p%%:*}; want=${p#*:}
  have=$(node -p "require(\"$m/$n/package.json\").version" 2>/dev/null) || have=未安装
  [ "$have" = "$want" ] && ok "$n $have" || bad "$n 需为 $want，当前为 $have"
done
exit ${fail:-0}'
```

- **没有 `FAIL`**：自有镜像与本示例的基础镜像结构一致，可以使用方式一。
- **`WARN`**：Node.js 不是 24，仍可继续构建，但请在构建后执行检查。
- **DSH 入口或模块未找到**：DSH 不在上述目录，请使用方式二，并将其中的 `DSH_MODULES` 设为 DSH 的实际安装目录。
- **未找到 npm**：请在自有镜像中安装 npm，或使用方式二自行调整安装步骤。
- **模块版本不符**：修改 [package.json](./plugin/package.json) 中 `peerDependencies` 的版本，在 `plugin` 目录执行 `pnpm install` 更新 `pnpm-lock.yaml`，再按下方「构建后检查」验证插件与该版本是否兼容。

### 方式一：使用本示例的 Dockerfile 构建

自有镜像通过上述检查时，可以直接用本示例的 [Dockerfile](./dockerfiles/Dockerfile) 在自有镜像上叠加插件。先导出构建产物的镜像名，之后的构建、启动和检查命令都会使用它：

```bash
export DSH_SESSION_IMAGE=your-registry/your-dsh:version-session-persistence
make build DSH_IMAGE=your-registry/your-dsh:version
```

构建产物建议沿用基础镜像的仓库和版本，并在标签后加上 `-session-persistence`，以便区分原镜像与加装了插件的镜像。本示例的预集成镜像也采用这一命名，即 `deepseek-harness:v0.1.1-rc.2-ags.4-session-persistence.4`，末尾的 `.4` 为插件的发布序号。

本示例的 Dockerfile 除了完成四个步骤，还会使用本示例的 [entrypoint.sh](./dockerfiles/entrypoint.sh) 作为启动命令。按「必需项与示例选择」，如自有镜像有自己的启动参数或模型配置：

- **启动参数**：将自有镜像的启动参数合并到 entrypoint.sh 中，保留其中的插件注册和 `--patch`。
- **模型配置**：entrypoint.sh 启动时会根据 `LLM_*` 变量更新 `$DSH_HOME/settings.yaml` 中的 `llm-pi-ai.providers.custom` 和 `agent-default-model`，其他配置保持不变。如需继续使用自有的模型配置，请删除 entrypoint.sh 中调用 `configure-model.mjs` 的一行。

### 方式二：在自有 Dockerfile 中集成

自有镜像未通过检查，或希望在自己的构建流程中集成插件时，在自有 Dockerfile 和启动脚本中加入以下内容。构建上下文中需包含本示例的 `plugin` 目录和 Cordis 补丁；建议在 `.dockerignore` 中排除 `plugin/node_modules`，避免将本机安装的依赖复制进镜像。

Dockerfile 中加入步骤 1、2：

```dockerfile
FROM your-registry/your-dsh:version

# 自有镜像中 DSH 模块的实际安装目录
ARG DSH_MODULES=/usr/local/lib/node_modules/@deepseek-ai
# 持久化插件的安装目录
ARG PLUGIN_DIR=/usr/local/lib/node_modules/@tencentcloud/ags-dsh-session-persistence

# 步骤 1：安装插件及其依赖
COPY plugin /tmp/ags-dsh-session-persistence
RUN npm install --global pnpm@11.19.0 \
    && cd /tmp/ags-dsh-session-persistence \
    && pnpm install --prod --frozen-lockfile \
    && mkdir -p "$(dirname "$PLUGIN_DIR")" \
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

# 步骤 4：在原有的 dsh web 启动命令中加上 --patch，其余参数保持不变
exec node --expose-internals \
  /usr/local/lib/node_modules/@deepseek-ai/dsh/lib/bin.js \
  web \
  --patch /opt/dsh/agent-runtime-session.cordis.yml \
  ...
```

### 构建后检查

在构建产物中运行插件自带的测试，确认步骤 1、2 生效，即插件能找到并加载 DSH 模块：

```bash
docker run --rm --platform linux/amd64 --entrypoint node "$DSH_SESSION_IMAGE" \
  --test /usr/local/lib/node_modules/@tencentcloud/ags-dsh-session-persistence/index.test.js
```

使用方式一时，也可以执行 `make check-image`，它使用已导出的 `DSH_SESSION_IMAGE`。输出中 `fail` 为 0 即通过。

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
  --jq '.Data.Session.State.CustomState | fromjson | has("dshHeader")'
```

输出 `true` 说明会话已由插件写入云端。Event 的检查和恢复验证见[第 4 节](#4-验证接入)，恢复成功才能确认接入完成。

如果容器在启动阶段退出，且日志中出现 `SecretId is not found` 等云 API 错误，说明插件已加载但凭证有误：DSH 启动时会通过插件查询云端会话列表。

## 4. 验证接入

### 验证内容

预集成镜像和自建镜像的验证方式相同，需确认以下四项：

1. **云端保存了消息和完整回合**：Session 的 Event 中包含已完成的回合。
2. **运行实例确实被替换**：删除并重建后，容器 ID 不同，且没有复用数据卷。
3. **新进程加载了原历史**：新实例能列出原会话，并读到其中的消息。
4. **新一轮对话继续写入云端**：在原会话中继续对话，模型能答出之前的标识，新回合也写入了云端。

验证可以在 Web UI 中手动完成，也可以通过脚本自动完成，两种方式检查的内容相同。

### 选择要验证的镜像

本节命令通过 `DSH_SESSION_IMAGE` 指定镜像，启动、重建和检查需使用同一镜像：

- **使用预集成镜像**：无需设置，默认为 `ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:v0.1.1-rc.2-ags.4-session-persistence.4`。
- **使用自建镜像**：在执行本节命令的终端中先导出镜像名，例如 `export DSH_SESSION_IMAGE=your-registry/your-dsh:version-session-persistence`。`make start` 和 `make check-image` 都会使用它。

启动 DSH：

```bash
make start
curl -sf -o /dev/null --retry 60 --retry-delay 2 --retry-all-errors --max-time 5 http://127.0.0.1:18080/ || docker logs --tail 20 dsh-session-demo
docker inspect --format '{{.Config.Image}}' dsh-session-demo
```

最后一行输出容器实际使用的镜像，请确认与预期一致。`make start` 启动容器 `dsh-session-demo`，通过 `.env` 传入环境变量，只监听本机回环地址 `127.0.0.1:18080`，不挂载数据卷。服务长时间未就绪时，请查看 `docker logs dsh-session-demo`。

使用自建镜像且启动参数与本示例不同时，请按自己的方式启动容器，并将下文的地址 `http://127.0.0.1:18080` 和容器名替换为实际值；脚本验证时，通过 `DSH_BASE_URL` 指定 DSH 的地址。

### 通过 Web UI 验证

**保存会话。** 在浏览器中打开 <http://127.0.0.1:18080>，确认输入框下方显示的模型与 `.env` 中的 `LLM_MODEL` 一致，然后新建会话，发送：

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

预期输出类似 `{"events":42,"turns":["completed"]}`：`turns` 中的 `completed` 表示这一轮对话已完整写入云端。

**重建容器。** 删除当前容器，再启动新容器：

```bash
docker inspect --format '{{.Id}}' dsh-session-demo
make stop
make start
curl -sf -o /dev/null --retry 60 --retry-delay 2 --retry-all-errors --max-time 5 http://127.0.0.1:18080/ || docker logs --tail 20 dsh-session-demo
docker inspect --format '{{.Id}}' dsh-session-demo
```

前后两次的容器 ID 应不相同。新容器没有挂载数据卷，本地没有任何会话数据。

**恢复会话。** 刷新浏览器页面。侧边栏「工作区」的「未分组」下会出现刚才的会话，标题为第一条消息的内容；打开后可以看到上一轮的消息和回复。在该会话中继续发送：

```text
我之前让你记住的标识是什么？只回复该标识，不要使用工具。
```

模型应回复 `blue-falcon-42`。新问题中不包含该标识，模型只有读到从云端恢复的历史才能答对。再次执行上面的 `agr session event list` 命令，`turns` 应变为 `["completed","completed"]`。

### 通过脚本验证

脚本自动完成上述操作。**保存会话：**

```bash
make seed
```

脚本新建 DSH 会话，生成随机字符串作为标识（形如 `session-proof-…`）并发给模型要求记住，然后等待云端 Event 中出现完整回合，并确认云端 header 存在。Session ID 和标识保存在 `.local/session.json`。预期输出：

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
curl -sf -o /dev/null --retry 60 --retry-delay 2 --retry-all-errors --max-time 5 http://127.0.0.1:18080/ || docker logs --tail 20 dsh-session-demo
docker inspect --format '{{.Id}}' dsh-session-demo
make resume
```

前后两次的容器 ID 应不相同。脚本随后检查：新 DSH 进程能从 `session.history` 读到原标识；向模型发送不含标识的新问题，模型能答出该标识；新一轮对话完整写入云端。预期输出：

```text
Session: <相同的 id>
Persisted history loaded and a new turn completed: session-proof-...
This verifies sequential recovery, not concurrent writers or automatic failover.
```

如需再次独立验证，请使用新的 state 路径，例如 `python3 session_demo.py seed --state .local/another.json`，resume 阶段使用相同路径。测试期间不要从其他入口写入该会话。

### 结果解读

脚本无法证明运行实例确已替换，因此删除、重建容器以及容器 ID 的变化也是验证依据。

排查失败时，需区分两类情况：历史加载成功但模型回答错误，属于模型召回问题；历史未能加载，才属于持久化问题。

## 5. 可选：其他运行方式

### 更换模型服务

本示例的镜像通过 `.env` 中的以下变量配置模型服务，**无需重新构建镜像**：

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `LLM_BASE_URL` | OpenAI 兼容接口地址 | `https://tokenhub.tencentmaas.com/v1` |
| `LLM_MODEL` | 模型 ID | `deepseek-v4-flash` |
| `LLM_API_KEY` | 模型服务的 API Key | 无，必须填写 |

容器启动时，[entrypoint.sh](./dockerfiles/entrypoint.sh) 会在启动 DSH 前运行 [configure-model.mjs](./dockerfiles/configure-model.mjs)，将上述配置写入 `/root/.dsh/settings.yaml`：

```text
.env 或云上 Tool 环境变量
        ↓
entrypoint.sh 调用 configure-model.mjs
        ↓
写入 /root/.dsh/settings.yaml
        ↓
启动 DSH，读取生成的配置
```

例如上述默认值会生成：

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

API Key 不会写入文件：`apiKeyEnv: LLM_API_KEY` 表示 DSH 在运行时从该环境变量读取密钥。生成脚本只更新上述两处配置，`settings.yaml` 中的其他配置保持不变。任一变量为空时，容器会在启动阶段报错退出，并在日志中提示缺少的变量。

修改 `.env` 后，执行 `make stop` 和 `make start` 重启容器即可生效。

DSH 会为每个会话单独记录所使用的模型（provider 和模型 ID），并随会话一起保存，恢复会话时沿用该记录。因此，更换模型服务后，新建的会话使用新模型；之前创建的会话仍指向原模型，如果原模型已不在新配置中，继续对话时会报错 `UNKNOWN_MODEL`。此时在 Web UI 输入框下方切换为当前配置的模型即可。

当前仅支持 OpenAI 兼容接口。如需使用其他接口类型或配置多个模型，请修改 configure-model.mjs，并重新构建镜像：

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
- 即使知道其他 Agent 的会话 ID，通过 DSH 接口直接访问也无法打开，DSH 会提示会话不存在；
- 设置 `SESSION_AGENT_ID` 之前创建的会话不再显示。这些会话仍保存在云端，并没有被删除；清空该变量并重启容器后可以重新看到。

**实现方式。** 插件新建会话时，会把 Agent ID 写入 Session 的 Metadata。Metadata 是 Session 上的一组自定义键值对，查询会话时可以作为过滤条件；插件列出会话时，就是按这个键值对筛选出当前 Agent 的会话。本示例使用的 key 是 `example.com/dsh-agent-id`。如需改用其他 key，例如与业务系统已有的命名保持一致，请同时修改 [plugin/index.js](./plugin/index.js) 和 [session_demo.py](./session_demo.py) 中的 `AGENT_METADATA_KEY`，再按[更换模型服务](#更换模型服务)末尾的方法重新构建镜像。改用新 key 后，按原 key 记录的会话不再显示。

除 Agent ID 外，Metadata 也可以记录租户、业务线、渠道等其他业务标识，用于归类和查询会话。本示例的插件只写入 Agent ID；如需记录其他标识，请修改 [plugin/index.js](./plugin/index.js) 中的 `appendBatch`，在创建 Session 时补充相应的 Metadata，并重新构建镜像。

#### 验证

1. 在 `.env` 中设置 `SESSION_AGENT_ID=agt-10001`，执行 `make stop` 和 `make start` 重启容器，按[第 4 节](#4-验证接入)保存一轮会话。
2. 将其改为 `agt-10002` 并重启容器，再保存一轮会话。此时侧边栏中只有这一步的会话，看不到第 1 步的会话。
3. 改回 `agt-10001` 并重启容器。第 1 步的会话重新出现在侧边栏中，并且可以打开。

使用脚本验证时，每次 `seed` 都需要一个新的 state 文件，请为每个 Agent 指定不同的路径，例如 `python3 session_demo.py seed --state .local/agt-10001.json`，`resume` 时使用相同的路径。

### 按业务用户区分会话

**Session 服务本身支持按用户隔离会话。** 每个会话属于创建时指定的 UserId；列出、读取、追加 Event 和删除会话时都需要传入 UserId，只能访问该 UserId 下的会话，使用其他 UserId 访问时，服务返回会话不存在。UserId 由调用方传入，Session 服务不会校验调用方是否就是该用户，持有云 API 凭证的程序可以使用任意 UserId，因此应由应用确保传入正确的用户 ID。

**本示例的插件只使用一个固定的 UserId。** 插件在启动时从 `SESSION_USER_ID` 读取一个用户 ID，这个 DSH 实例创建和查询的所有会话都使用这个值。插件无法区分实例中的不同使用者：DSH 交给插件的读写请求只包含会话 ID，不包含"当前是哪个用户在操作"，本示例的 DSH Web UI 也没有用户登录。因此，**一个 DSH 实例只对应一个用户 ID**，使用同一个实例的所有人会看到同一批会话。

如需让每个业务用户只看到自己的会话，请为每个业务用户使用独立的 DSH 实例：为每个用户启动一个 DSH 容器或沙箱，启动时将该用户在业务系统中的用户 ID 填入 `SESSION_USER_ID`。

| 业务用户 | 该用户实例的 `.env` 中的设置 |
| --- | --- |
| 用户 A，业务系统中的用户 ID 为 `u-1001` | `SESSION_USER_ID=u-1001` |
| 用户 B，业务系统中的用户 ID 为 `u-1002` | `SESSION_USER_ID=u-1002` |

用户 A 之后再次使用时，为其启动新实例并使用相同的 `SESSION_USER_ID=u-1001`，即可加载之前的会话；用户 B 的实例看不到用户 A 的会话。这种方式不需要修改插件。

本示例不支持多个业务用户共用一个 DSH 实例。这一限制来自 DSH 和本示例的插件，而不是 Session 服务：本示例验证的 DSH 版本（0.1.1-rc.2）没有用户身份的概念，插件拿不到当前用户的信息，无法为每个请求选择对应的 UserId。

### 在云上运行

本地验证通过后，可以将同一镜像放到云上运行：直接在 AGS 沙箱中运行，或托管到 Deployment。两种方式都基于同一个沙箱工具创建，沙箱工具定义了沙箱使用的镜像、环境变量和资源规格。

**准备镜像和沙箱工具。** 默认使用预集成镜像。使用自建镜像时，需先推送到账号可拉取的仓库，例如 `docker push your-registry/your-dsh:version-session-persistence`；Makefile 不会执行推送。此外，需按[自定义 Sandbox CAM 角色](https://cloud.tencent.com/document/product/1814/129691)准备 `AGR_ROLE_ARN`，并为操作者授予 `cam:PassRole`，以及创建沙箱工具、沙箱实例或 Deployment 和获取访问 Token 的权限。

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

生成的配置文件包含凭证：请在 `umask 077` 下生成，不要外传，并在沙箱工具创建完成后删除。`agr tool create` 的完整输出也会包含工具配置中的凭证，因此上述命令只提取 ToolId。生成器按 public/personal 仓库类型输出配置，使用其他类型的仓库时需相应调整。

云上运行时，不要让本地容器同时写入同一会话，验证时请使用新的 state 路径。

#### 在 AGS 沙箱中运行

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

在代理所在的终端中按 `Ctrl+C` 停止代理，删除该沙箱，再创建新沙箱并重新启动代理：

```bash
agr instance delete "$DSH_INSTANCE_ID" \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --yes \
  --wait
```

然后重新执行上面创建沙箱和启动代理的命令。前后两次输出的实例 ID 应不相同。代理启动后，在第二个终端中恢复会话：

```bash
python3 session_demo.py resume --state .local/sandbox.json
```

预期输出与[通过脚本验证](#通过脚本验证)相同。

本方式只能通过脚本验证，无法在浏览器中使用 Web UI。原因是 `agr instance proxy` 转发请求时不会改写浏览器请求中的来源地址（Origin），DSH 出于安全考虑会拒绝这类请求。脚本请求不携带来源地址，不受影响。需要使用 Web UI 时，请托管到 Deployment。

镜像的 [entrypoint.sh](./dockerfiles/entrypoint.sh) 已将沙箱域名 `*.<地域>.<AGR_DOMAIN>` 加入 DSH 的可信主机，使通过沙箱访问的请求能够被接受。使用自有镜像时，需要在启动参数中加入同样的配置。

#### 托管到 Deployment

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

代理启动后，按[第 4 节](#4-验证接入)的流程验证，有以下两处不同：

- **访问地址**：Web UI 地址为 <http://127.0.0.1:18081>；使用脚本时，先设置 `DSH_BASE_URL=http://127.0.0.1:18081`，并使用新的 `--state` 路径。
- **重建 DSH**：将「删除容器，再启动新容器」改为删除 Deployment（命令见[第 6 节](#6-清理)），再按上面的命令重新创建 Deployment 并启动代理。

这样验证的是 DSH 的 Deployment 被删除并重新创建后，会话能否恢复。同一 Deployment 内的实例替换，例如缩容后重新扩容，不在本节验证范围内。

## 6. 清理

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

如果在云上运行过，还需删除云上资源。若托管到了 Deployment，先删除 Deployment：

```bash
agr deployment delete "$DSH_DEPLOYMENT_ID" \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --wait
```

然后删除该沙箱工具下所有未停止的实例，最后删除沙箱工具。已删除的实例会以 `STOPPED` 状态保留在列表中，无需再次删除：

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

## 7. 限制与边界

本示例的持久化插件只处理正常的写入流程，以下情况未做处理：

- **本地 JSONL 历史不会迁移。** 启用插件后，DSH 只读写云端会话，原有的本地会话不再可见。
- **写入中途失败。** `appendBatch()` 先创建 Session，再逐条追加 Event，中途失败可能留下空 Session 或不完整的历史。稳定的 Event ID 使重试具备幂等性，但不会回滚已写入的内容。插件遇到云 API 限流时会自动退避重试。
- **多个写入者。** 插件没有跨实例的协调机制。多个 DSH 实例同时写入同一会话时，可能写入序号冲突的 Event，导致历史不一致。
- **进行中的回合不会自动接续。** DSH 进程在一轮对话进行中退出时，例如模型正在生成回复或工具正在执行，这一轮不会由其他进程自动继续。已写入的历史仍保留在 Session 中，新进程加载会话后，需要用户重新发起请求。
- **只恢复会话状态。** 文件、运行中的进程和模型长连接都不会恢复。
- **超大 Event。** 插件将每个 Event 完整写入，不做拆分。工具返回大量内容时，单个 Event 可能超出 Session API 的大小限制而写入失败。
- **完整性检查。** 加载时会按原始事件排序并检查序号连续性，可发现大部分不完整的写入，但无法覆盖全部情况。插件不提供逐会话的原始日志文本导出（`supportsRawArtifacts=false`），这不影响历史加载。

如需将本插件用于生产环境，或让多个 DSH 实例写入同一会话，需要先针对以上情况补充相应的处理。

## 常见问题

- **凭证或空间报错**：分别核对 `agr` 和容器所用的账号、地域、SpaceId、权限以及临时凭证有效期。
- **容器启动后立即退出**：DSH 启动时会通过持久化插件查询会话列表，插件凭证无效时启动即失败。执行 `docker logs dsh-session-demo`，若出现 `SecretId is not found` 等云 API 错误，请核对 `.env` 中的 `TENCENTCLOUD_*` 凭证；若出现 `configure-model:` 开头的提示，请按提示补全 `LLM_*` 变量。
- **连接被拒绝**：等待服务启动完成，并查看容器日志。如修改了 `PORT`，需同步修改脚本使用的 `DSH_BASE_URL`。
- **模型调用报错**：核对 `.env` 中的 `LLM_BASE_URL`、`LLM_MODEL`、`LLM_API_KEY`，以及账号的模型权限。容器日志中的 `configure-model:` 一行会显示实际使用的模型和地址。Session 凭证不包含模型权限。
- **更换模型后旧会话报错 `UNKNOWN_MODEL`**：DSH 为每个会话记录了所使用的模型，旧会话仍指向原模型。请在 Web UI 输入框下方切换为当前配置的模型，见[更换模型服务](#更换模型服务)。
- **新容器看不到原会话**：确认新容器的 `AGR_REGION`、`SESSION_SPACE_ID`、`SESSION_USER_ID`、`SESSION_AGENT_ID` 与写入时一致，并用 `docker inspect --format '{{.Config.Image}}' dsh-session-demo` 确认使用的是已集成插件的镜像。
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

这些测试覆盖事件投影、历史加载和验证逻辑，但不能替代真实的 seed → 新容器 → resume 流程。
