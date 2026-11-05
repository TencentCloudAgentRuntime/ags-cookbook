# 使用 Agent Runtime Session 持久化 pi 会话

[English](./README.md)

[pi](https://github.com/earendil-works/pi) 是一个终端编码 Agent，它把每个会话保存在本地磁盘的 JSONL 文件中，因此删除容器也会删除会话。本示例提供一个 pi 扩展，把会话的每个条目复制到云端的 Agent Runtime Session；同时提供一个启动前步骤，在 pi 启动前把会话写回磁盘。删除容器并启动新容器后，pi 会打开原来的会话，你可以继续对话。

容器里运行的是官方 `pi` 可执行文件。pi 自带的会话命令（`/resume`、`/fork`、`/tree`、`/compact`）仍然可用，因为 pi 读写的仍是它自己的会话文件。

## 快速开始

pi 1.4.0 没有预构建镜像，需要在本目录自行构建。你需要 Docker、Python 3，以及按 [AGR CLI 凭证初始化](https://github.com/TencentCloudAgentRuntime/ags-cli#initialize-cli-credentials)配置好的 `agr` v0.7.0 或更高版本。

```bash
cp .env.example .env            # 填入凭证和模型 API Key，见第 3 节
set -a; . ./.env; set +a
agr session space create \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --name pi-session-demo \
  --output json \
  --jq '.Data.SessionSpace.SpaceId'
# 把输出的 SpaceId 填入 .env 的 SESSION_SPACE_ID，然后重新加载：
set -a; . ./.env; set +a

make build                      # 构建 pi-session:local
make seed                       # 启动容器，保存带标记的一轮对话，然后删除容器
make resume                     # 启动全新容器；模型返回该标记即成功
```

`make seed` 和 `make resume` 各自用 `docker run --rm` 启动容器，命令返回时容器已删除，容器磁盘上的内容不会保留。完成后按[第 8 节](#8-清理)清理。

## 1. 集成原理

### 集成点

**要解决的问题。** pi 把会话保存在本地磁盘的 JSONL 文件里，也没有存储插件可以替换。删除容器，文件就跟着没了。

**思路。** 让 pi 继续用它自己的文件，把云端 Session 当作能保留下来的那份副本。由两个小部分完成，一个在 pi 启动前，一个在 pi 运行时：

| 组成部分 | 何时运行 | 做什么 |
| --- | --- | --- |
| `prepare.mjs` | 在容器入口脚本中、pi 启动前运行一次 | 从云端读取 Session，写到磁盘上，成为 pi 的会话文件 |
| `ags-pi-session` 扩展 | 在 pi 进程内、pi 运行时 | 把 pi 新增的每个对话条目复制到 Session |

pi 本身是官方可执行文件，用同一个会话 ID 启动。它会找到 `prepare.mjs` 写好的文件，像一直就在那里一样继续对话。

```text
 第一个容器                                          新容器（删除旧容器之后）
 ──────────                                         ────────────────────────
 pi 把条目写入自己的文件                              prepare.mjs 从云端读取 Session
        │                                           并写出会话文件
        ▼                                                   │
 扩展把新条目复制 ──────────► 云端 Session ───────────────►│
                              （保留下来）                   ▼
                                                    pi 打开该文件并继续对话
```

**“同步点”是什么。** 扩展需要知道 pi 什么时候新增了条目。pi 没有“每新增一个条目就触发”的事件，所以扩展换了一种做法：在特定时刻，数一数 pi 持有的条目数和云端已有的条目数，把云端缺的部分按顺序逐条 `AppendEvent`。这些时刻就是同步点：每条消息结束（`message_end`）、每个回合结束（`turn_end`）、每次运行结束（`agent_end`）、pi 进入空闲前（`agent_before_settle`）、压缩或会话树变化后（`session_compact`、`session_tree`）、会话名称变化时（`session_info_changed`），以及 pi 关闭时（`session_shutdown`）。没有新内容的同步点什么也不做，所以调用频繁也没有副作用。

pi 的模型调用、工具、技能和 RPC 协议都不变。

### 会话生命周期

| 阶段 | 发生的事 |
| --- | --- |
| 新会话 | pi 在内存中创建会话。会话包含用户或助手消息之前，不会写入云端，规则与 pi 写文件的时机一致。 |
| 首次写入 | 扩展调用 `CreateSession`，以 pi 的会话 ID 作为 Session ID，把 pi 的会话头保存到 `State.CustomState`，然后追加到目前为止的所有条目。 |
| 后续写入 | 每个同步点只追加超出已保存数量的条目。某次追加失败时，计数停在最后成功的条目，下一个同步点从那里继续。 |
| 用已有会话启动容器 | `prepare.mjs` 读取会话头和全部 Event，检查序号连续，然后在会话目录写出 `<时间戳>_<id>.jsonl`。文件已存在时不覆盖。 |
| 关闭 | 关闭 pi 的 stdin 会触发 `session_shutdown`，在 pi 退出前发送最后的条目。 |

### 数据布局

一个条目的内容只存一份。Part 能表达的内容放进 `Content.Parts`，其他系统可以直接读取；其余部分放进 `Extensions`，是去掉上述内容后的同一个条目。恢复时把两部分合并，所以还原出的会话文件与 pi 写入的条目完全一致。

| 数据 | 位置 |
| --- | --- |
| pi 会话头 | Session 的 `State.CustomState.piHeader` |
| 消息文本、推理内容、工具调用名称与参数、工具结果、压缩与分支摘要 | Event 的 `Content.Parts` |
| 条目 id 与父节点、类型、时间戳、签名、用量、模型、工具调用 id、`details` 及其他字段 | Event 的 `Extensions.pi.entry`，已去掉上述内容 |
| 不含对话内容的条目：模型与思考级别变更、系统提示、标签、自定义条目 | 整个放在 `Extensions.pi.entry`，Event 没有 `Content` |
| 图片数据 | Event 的 `InlineData`（`MimeType`、`Data`），base64 数据不再放在 `Extensions.pi.entry` 里 |
| Event ID | `pi-<会话 ID>-<序号>`；重试写入时 Session 服务据此识别重复请求 |
| Author、角色、错误 | `Author` 为 `user`、`assistant`、`tool` 或 `pi`；失败的工具调用和模型调用会设置 `ErrorCode` 与 `ErrorMessage` |

`State.CustomState.piHeader` 和 `Extensions.pi` 的字段名与格式由本扩展定义，Session 服务只原样存储，不解释。

### 集成前须知

- 扩展依赖 pi 的会话文件格式（版本 3）和扩展事件，所以 pi 固定在精确版本，见[第 2 节](#2-版本与依赖)。
- 同一时刻一个会话只能有一个写入方，见[第 9 节](#9-限制与边界)。
- 每个条目都会发送到云端，包括工具输出和系统提示。请使用允许存放这些数据的 SessionSpace 和凭证。

## 2. 版本与依赖

| 组件 | 版本 | 原因 |
| --- | --- | --- |
| pi | `@earendil-works/pi-coding-agent@1.4.0` | 扩展基于该版本编写和验证。旧包 `@mariozechner/pi-coding-agent` 已废弃，不使用。 |
| Node.js | 镜像内 24.8.0；本地 24 | 镜像基础版本；`make check` 在 Node 24 下运行 |
| `tencentcloud-sdk-nodejs-ags` | 4.1.332 | 扩展使用的 Session API 客户端，由 `package-lock.json` 锁定 |

pi 1.4.0 的会话文件格式为版本 3。pi 加载旧格式时会自动迁移，扩展保存的是 pi 内存中持有的条目。

更换 pi 版本时，先运行 `make check`，再按[第 5 节](#5-验证集成)验证，之后才能依赖它。扩展加载成功但从不保存，只会表现为会话无法恢复，所以要验证恢复，而不只是启动成功。

## 3. 准备工具与云资源

### 本地工具

| 工具 | 用途 |
| --- | --- |
| Docker | 构建镜像，并以 `--platform linux/amd64` 运行容器 |
| `agr` | 创建 SessionSpace；演示脚本也用它读取云端 Session |
| Python 3 | 运行 `session_demo.py` |
| Node.js 24 | 仅用于 `make check` 和 `make setup` |

### 云资源与会话标识

会话由 `SpaceId`、`UserId` 和 `SessionId` 标识。本示例中 `SpaceId` 和 `UserId` 来自环境变量，Session ID 就是 pi 的会话 ID，通过 `PI_SESSION_ID` 指定。会话 ID 可包含字母、数字、`-`、`_` 和 `.`，且必须以字母或数字开头和结尾。

`SESSION_AGENT_ID` 可选。设置后，扩展为创建的每个 Session 打上该标签，列表也只包含带该标签的 Session。同一 SessionSpace 中有多个 Agent 时用它区分。

### 凭证

使用专用测试账号或临时凭证。同一组 `TENCENTCLOUD_*` 值在容器内由扩展使用，在容器外由 `agr` 使用。它们需要 Session 相关操作的权限：`CreateSession`、`DescribeSession`、`DescribeSessions`、`AppendEvent`、`DescribeEvents`，清理时还需要 `DeleteSession`。模型 API Key 是另一份，不包含在 Session 凭证中。

### 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入专用测试凭证。
```

| 变量 | 含义 |
| --- | --- |
| `AGR_REGION` | SessionSpace 所在地域 |
| `SESSION_API_ENDPOINT` | Session API 地址，默认 `ags.tencentcloudapi.com` |
| `SESSION_SPACE_ID` | SessionSpace ID，见下一节 |
| `SESSION_USER_ID` | 空间内的用户 ID |
| `SESSION_AGENT_ID` | 可选的 Agent 标签 |
| `TENCENTCLOUD_SECRET_ID`、`TENCENTCLOUD_SECRET_KEY`、`TENCENTCLOUD_SESSION_TOKEN` | 凭证；仅临时凭证需要 token |
| `LLM_BASE_URL`、`LLM_MODEL`、`LLM_API_KEY` | OpenAI 兼容的模型服务 |

`.env` 已被 Git 和 `.dockerignore` 忽略。不要提交它，也不要打进镜像。

### 创建或复用 SessionSpace

按快速开始创建，或列出已有空间：

```bash
agr session space list --region "$AGR_REGION" --cloud-endpoint "$SESSION_API_ENDPOINT" --output json
```

## 4. 运行示例

### 构建

```bash
make build
```

按 [dockerfiles/Dockerfile](./dockerfiles/Dockerfile) 构建 `pi-session:local`：先从 npm 安装固定版本的 pi，再安装 [extension/](./extension) 及其锁定的依赖。设置 `PI_SESSION_IMAGE` 可以构建或运行其他镜像名。

### 容器做了什么

[dockerfiles/entrypoint.sh](./dockerfiles/entrypoint.sh) 要求设置 `AGR_REGION` 和 `PI_SESSION_ID`，运行 `prepare.mjs`，然后启动 pi：

```text
pi --mode rpc --offline \
   --session-dir /var/pi/sessions --session-id "$PI_SESSION_ID" \
   --extension /opt/pi/extension/index.js \
   --provider custom --model "$LLM_MODEL" \
   --no-skills --no-prompt-templates --no-themes --no-context-files
```

`--session-id` 会打开已恢复的会话文件；没有该会话时，用这个 ID 新建。此时 pi 会向 stderr 输出 `Warning: No project session found with id ...; creating a new session`，首次运行时这是正常现象。

`--mode rpc` 让 pi 从 stdin 读取命令，把事件按 JSON 行写到 stdout，演示脚本就是这样驱动它的。`--model` 之后的参数关闭了本地技能、提示模板、主题和 `AGENTS.md` 的自动发现，使容器在任何环境下行为一致。需要这些功能时去掉它们。

模型配置写入 `~/.pi/agent/models.json`，提供方名为 `custom`，API 类型为 `openai-completions`。密钥不会写进文件，文件里是 `$LLM_API_KEY`，pi 在每次请求时从环境变量读取。设置 `PI_SKIP_MODEL_CONFIG=true` 可以保留自己的 `models.json`，此时不再检查 `LLM_*`，但 `--model` 仍需要 `LLM_MODEL` 提供模型名。

### 只有容器读取的变量

| 变量 | 默认值 | 含义 |
| --- | --- | --- |
| `PI_SESSION_ID` | 必填 | 要打开或新建的会话 |
| `PI_SESSION_DIR` | `/var/pi/sessions` | pi 读取会话的目录 |
| `PI_RESTORE_ALL` | 未设置 | 设为 `true` 时，pi 启动前还会恢复该用户（设置了 `SESSION_AGENT_ID` 时限定该 Agent）的所有会话，见[第 6 节](#6-使用-pi-自带的会话命令) |
| `PI_SKIP_MODEL_CONFIG` | 未设置 | 设为 `true` 时不写 `models.json` |

## 5. 验证集成

### 验证什么

1. **云端保存了消息**：Session 中有 pi 会话头和一轮完整对话的条目。
2. **运行实例确实被替换**：每个阶段都用 `--rm` 启动自己的容器，不挂载卷。
3. **新容器加载了原始历史**：问一个不含标记的问题，模型能答出标记。
4. **新一轮继续写入云端**：第二轮之后 Session 中的 Event 变多。

### 用脚本验证

```bash
make seed
make resume
```

`make seed` 生成会话 ID 和随机标记，启动容器，让模型记住标记。该轮结束后关闭 pi 的 stdin，让 pi 有序退出、扩展做最后一次同步，然后通过 `agr` 读取 Session，检查 pi 会话头、序号连续、用户消息中的标记和助手消息。会话 ID 和标记保存在 `.local/session.json`。

```text
Session: <id>
Cloud header and 5 events verified. State: .local/session.json
The container was removed. Run resume to continue the conversation in a fresh one.
```

`make resume` 用同一个会话 ID 启动新容器，问 `What marker did I ask you to remember?`，检查回答是该标记，并且 Session 中的 Event 变多。

```text
Session: <相同的 id>
Persisted history loaded and a new turn completed: session-proof-...
The Session now holds 8 events (was 5).
This verifies sequential recovery, not concurrent writers or automatic failover.
```

seed 的一轮会保存五个 Event：模型变更、思考级别、系统提示、用户消息和助手消息。调用了工具的一轮还会保存工具调用及其结果。

保存失败时，扩展把错误写入 stderr，pi 会把它作为扩展通知发给客户端；演示脚本会以 `pi extension reported: ...` 停止。

要再做一次独立检查，换一个状态路径，例如 `python3 session_demo.py seed --state .local/another.json`，resume 使用同一路径。

### 如何解读结果

出问题时要区分两种情况：历史已恢复但模型答错，是模型回忆的问题；历史没有恢复，是持久化的问题。后一种情况下，用 `agr session event list` 列出 Event，确认第一次运行是否保存了内容。

## 6. 使用 pi 自带的会话命令

恢复出的文件就是普通的 pi 会话文件，因此读取会话文件的命令都能用。默认只恢复 `PI_SESSION_ID`。要让该用户的其他会话也可用，用 `PI_RESTORE_ALL=true` 启动容器：`prepare.mjs` 会把该用户（设置了 `SESSION_AGENT_ID` 时限定该 Agent）的每个会话都恢复到会话目录。每个恢复的会话都要从云端完整读取一次，适合几个会话，不适合几百个。

以下是在本镜像中针对 pi 1.4.0、通过 RPC 驱动 pi 的检查结果：

| 命令 | 结果 |
| --- | --- |
| `bash` 执行 `ls /var/pi/sessions` | 列出已恢复的会话文件 |
| `switch_session`，参数为已恢复文件的路径 | 切换到已恢复的会话及其历史；`get_state` 返回其 ID 和消息数 |
| `get_fork_messages`，然后 `fork` | 从较早的用户消息创建新会话。扩展把它保存为带独立 ID 的新云端 Session |
| `clone` | 把当前分支复制到新会话。扩展把它保存为新的云端 Session，包含复制的历史和之后的对话 |
| `new_session` | 开始一个空会话。包含对话后，扩展把它保存为独立的云端 Session |

fork 出的会话，其会话头里的 `parentSession` 是创建该 fork 的容器内源文件路径。这个路径在其他容器里没有意义，云端 Session 只把它作为记录保存。

## 7. 最小接入：把历史放在内存里

只需要让会话在新容器里继续、不需要 pi 的会话命令时，用这种方式。它去掉了会话文件、启动前步骤和扩展。程序把 pi 当作库嵌入，把 Session 的条目加载到内存会话管理器，运行一次提示，再把 pi 新增的条目发回 Session。[minimal/run-once.mjs](./minimal/run-once.mjs) 是完整的 50 行程序：

```js
const stored = await readSession(client, sessionId)          // 1. 从云端加载
const sessionManager = SessionManager.inMemory(
  cwd, { id: sessionId }, stored && [stored.header, ...stored.entries])

const { session } = await createAgentSession({ sessionManager, modelRuntime, model, noTools: 'builtin' })
await session.prompt(prompt)                                 // 2. 运行这一轮
session.dispose()

const sync = await SessionSync.open(client, sessionId)       // 3. 保存 pi 新增的条目
await sync.flush(sessionManager.getHeader(), sessionManager.getEntries())
```

它复用了与扩展相同的转换和同步代码，所以写出的 Session 布局相同，完整集成也能打开它。镜像里已包含该程序：

```bash
set -a; . ./.env; set +a
SID=$(python3 -c 'import uuid; print(uuid.uuid4())')
run() { docker run --rm --platform linux/amd64 --env-file .env -e PI_SESSION_ID=$SID \
  --entrypoint sh pi-session:local -c 'node /opt/pi/extension/prepare.mjs 2>/dev/null && node /opt/pi/minimal/run-once.mjs "$1"' sh "$1"; }
run "Remember the code word MINIMAL-42. Reply with only OK."
run "What was the code word? Reply with only it."
```

第二个容器会输出 `MINIMAL-42`。与完整集成相比，你放弃的是：

- **没有 pi 可执行文件。** 程序是你自己的 Node 入口，pi 是其中的库。喂提示的循环由你实现。
- **没有会话命令。** 程序直接调用 `session.prompt`。`switch_session`、`fork`、`new_session` 这类替换当前会话的命令属于 pi 的会话运行时，并且会打开会话文件，不适用于内存会话。要开始新对话，用新的会话 ID 运行程序。
- **在一次运行结束时保存。** 条目在程序调用 `flush` 时发送，而不是每一轮，所以在此之前崩溃会丢失这次运行。需要时可以更频繁地调用 `flush`。
- **每个会话 ID 只能有一个写入方**，与本示例其他部分一致。

## 8. 清理

先预览要清理的内容，再删除：

```bash
make cleanup
# 确认预览后，删除：
make cleanup DELETE=1
```

不带 `DELETE=1` 时，脚本只列出将要删除的 Session。设置了 `SESSION_AGENT_ID` 时，只包含该 Agent 的 Session；未设置时，包含该空间中此 `UserId` 的所有 Session。空间是共用的时候，删除前务必检查预览。

删除本地状态文件：

```bash
rm -rf .local
```

如果 SessionSpace 是专为本示例创建且里面的内容都不再需要，可以删除它；复用的或共享的空间不要删：

```bash
agr session space delete \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --space-id "$SESSION_SPACE_ID" \
  --output json
```

## 9. 限制与边界

- **一个会话只能有一个写入方。** 扩展不在容器之间协调。Event ID 由序号生成，Session 服务只在内容完全相同时接受重复的 Event ID。两个容器写同一个会话时，某个序号的第一次追加成功，另一个被拒绝并报 `EventId 已存在`。云端历史保持连续，但被拒绝的容器之后在该会话上会一直失败，需要重启。请把每个会话路由到同一个容器。
- **写入中途失败。** 扩展为每个条目追加一个 Event，成功后才推进计数。失败会写入 stderr，并作为错误通知发给客户端；下一个同步点从第一个没有写入的条目继续，已经写入的 Event 不会重复发送。客户端只能在 pi 运行期间看到通知。如果容器在重试成功前退出，未发送的条目会丢失；演示脚本通过关闭 stdin 并等待 pi 退出来避免这一点。
- **上一个同步点之后的条目。** 两个同步点之间 pi 可能追加多个条目，例如长时间的工具调用期间。崩溃会丢失自上次成功同步以来 pi 新增的内容。
- **Event 大小。** 单个 Event 过大时，Session 服务会让整个 Session 损坏：测试中 200 KB 的 Event 正常，300 KB 的 Event 不行，之后该 Session 的读取、继续写入乃至 `DeleteSession` 都会报 `Out of sort memory`。损坏的 Session 无法通过 API 恢复或删除。因此扩展把每个 Event 控制在 200,000 字节以内。条目会超出时，扩展把其中最大的文本截短，并以 `[truncated: original N characters]` 结尾；过大的图片替换为文本说明，过大的工具调用参数也替换为说明；Event 上标记 `piTruncated`，并向 stderr 输出一行日志。对话继续，但恢复出的是截短后的条目。没有可截短内容的单个条目，例如特别大的自定义条目，会报错且不保存，该会话在这个条目处停止同步。
- **图片数据与地域。** 图片存放在 `InlineData`，计入 Event 大小限制。`DescribeEvents` 在 `ap-shanghai` 会返回 `InlineData`，测试时 `ap-chongqing` 不返回：Session 接受图片，读回来的 Part 是空的。此时恢复带图片的会话会以 `this region does not return InlineData` 停止；不含图片的会话不受影响。请使用会返回 `InlineData` 的地域，或不发送图片。
- **工具参数与结果。** 在大小限制内完整保存。不要在要保存的会话里运行会打印机密的工具。
- **只恢复会话状态。** Agent 写的文件、运行中的进程和已打开的连接不会恢复。
- **不迁移已有历史。** 只存在于本地磁盘的会话，在 pi 继续它之后的第一个同步点会被完整上传。pi 不打开的会话不会被上传。
- **会话数量。** `PI_RESTORE_ALL=true` 会在 pi 启动前读取每个会话。
- **扩展权限。** 扩展在 pi 进程内以 pi 的权限运行，能看到每个提示、工具调用和文件。只加载你信任的扩展。

## 故障排查

| 现象 | 检查 |
| --- | --- |
| `entrypoint: ... is required` | 设置 `AGR_REGION` 和 `PI_SESSION_ID`；演示脚本会自己设置 `PI_SESSION_ID` |
| `set LLM_... ; see .env.example` | 某个模型变量为空。填写 `LLM_BASE_URL`、`LLM_MODEL` 和 `LLM_API_KEY`，或设置 `PI_SKIP_MODEL_CONFIG=true` |
| `SecretId is not found`、`AuthFailure` | `.env` 中的 `TENCENTCLOUD_*` 有误或已过期。`prepare.mjs` 在 pi 启动前就调用 Session API，所以容器会提前退出 |
| `model call failed: 401 ...` | 检查 `LLM_API_KEY`、`LLM_BASE_URL` 或模型账号权限 |
| `pi extension reported: saving session ... failed` | 消息里带有云端错误。解决原因后，扩展会在下一个同步点重试 |
| 新容器开始的是空会话 | `AGR_REGION`、`SESSION_SPACE_ID`、`SESSION_USER_ID`、`SESSION_AGENT_ID` 必须与写入时一致，`PI_SESSION_ID` 必须是同一个 ID |
| `Session ... exists but was not written by this extension` | 该 ID 属于没有 pi 会话头的 Session。换一个 `PI_SESSION_ID` |
| `belongs to a different SESSION_AGENT_ID` | 该 Session 由另一个 `SESSION_AGENT_ID` 创建。使用原来的值，或换一个 `PI_SESSION_ID` |
| `Session ... is not contiguous` | 缺少 Event。停止写入并排查，不要删除 Event 来掩盖 |
| `holds N entries in the cloud but only M locally` | 本地文件落后于云端。删除本地文件后重新恢复，或查明是哪个容器写入了多出的条目 |
| Session API 报 `Out of sort memory` | 该 Session 含有约 300 KB 或更大的 Event，由本扩展之外的程序写入。测试中这样的 Session 无法通过 API 读取或删除 |
| `does not return InlineData` | 该地域读取时丢弃 `InlineData`，见限制。换用会返回它的地域 |
| `unsupported pi session format` | 该 Session 由其他版本的本扩展写入 |

## 附录：本地单元测试

```bash
make setup      # 在 extension/ 中 npm ci
make check      # shell 语法、扩展测试、演示脚本测试
```

扩展测试覆盖：每种条目与 Event 的往返转换、大小限制、基于内存 Session 服务的同步与恢复逻辑、Session API 客户端和模型配置。测试不调用云端。
