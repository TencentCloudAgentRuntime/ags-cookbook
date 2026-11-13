# 连接托管 Harness：prompt、acp、proxy 与 endpoint

本教程独立创建一个 Harness，并用四种方式与它对话。托管 Harness 通过 [ACP（Agent Client Protocol）](https://agentclientprotocol.com) 的 Streamable HTTP 传输对外服务。

开始前，请完成公共[前置条件](../README_zh.md#前置条件)和[配置](../README_zh.md#配置)。

| 场景 | 命令 | 说明 |
| --- | --- | --- |
| 终端里快速验证、脚本调用 | `agr harness prompt` | 一次一轮，流式输出，支持 JSON 和 NDJSON |
| 编辑器、acpx 等以子进程启动 Agent 的客户端 | `agr harness acp` | 把远端 Harness 变成本地 stdio Agent |
| 浏览器、IDE 插件、ACP SDK 本地调试 | `agr harness proxy` | 本地 HTTP 地址，自动加 Token 和亲和 |
| 自己的服务直连 | `agr harness endpoint` | 输出真实 ACP 地址和请求头，连接由你自己建立 |

示例输出中的真实信息均已脱敏。

## 1. 设置环境变量并创建 Harness

```bash
set -a
source ../.env
set +a
bash ../scripts/preflight.sh connect &&

export MODEL_PROVIDER_NAME="harness-connect-$HARNESS_NAME_SUFFIX" &&
export HARNESS_NAME="harness-connect-$HARNESS_NAME_SUFFIX" &&

MODEL_PROVIDER_ID=$(python3 ../scripts/resources.py create connect model-provider \
  --name "$MODEL_PROVIDER_NAME" \
  --tokenhub-api-key-id "$TOKENHUB_API_KEY_ID" \
  --model hy3) && export MODEL_PROVIDER_ID
```

使用已保存的 Model Provider ID 创建 Harness，并检查 ACP 入口：

```bash
HARNESS_ID=$(python3 ../scripts/resources.py create connect harness \
  --name "$HARNESS_NAME" \
  --engine pi \
  --engine-version 1.3.0 \
  --model "$MODEL_PROVIDER_ID:hy3" \
  --role-arn "$AGR_ROLE_ARN" \
  --subnet-id "$HARNESS_SUBNET_ID" \
  --security-group-id "$HARNESS_SECURITY_GROUP_ID" \
  --wait) && export HARNESS_ID
```

```bash
agr harness endpoint "$HARNESS_ID" --region "$AGR_REGION" --check
```

`Check` 一行应为 `reachable in <n>ms`。

## 2. `prompt`：多轮对话

每次执行 `prompt` 都会新建一个 ACP 连接。要在同一个会话里继续对话，需要把上一轮返回的两个值传回去：

- `SessionId`：ACP 会话 ID。
- `AffinityId`：平台签发的亲和值，把请求路由到保存该会话的实例。它不能用 `SessionId` 代替。

第一轮用 `-o json` 取得这两个值：

```bash
agr harness prompt "$HARNESS_ID" --region "$AGR_REGION" -o json \
  'Remember the code word "cedar". Reply only with "OK".'
```

```json
{
  "Status": "succeeded",
  "Data": {
    "HarnessId": "hns-********",
    "SessionId": "<masked-session-id>",
    "AffinityId": "<masked-affinity-id>",
    "Reply": "OK",
    "ToolCalls": [],
    "StopReason": "end_turn",
    "DurationMs": 2380
  }
}
```

也可以用 `--jq` 直接取值。把两个值写入环境变量，再问第二轮：

```bash
export HARNESS_SESSION_ID='replace-with-session-id'
export HARNESS_AFFINITY_ID='replace-with-affinity-id'

agr harness prompt "$HARNESS_ID" --region "$AGR_REGION" \
  --session-id "$HARNESS_SESSION_ID" \
  --affinity-id "$HARNESS_AFFINITY_ID" \
  'What was the code word?'
```

回复应包含 `cedar`。不带 `--affinity-id` 时，请求可能落到另一个实例；如果没有配置 Session Space，新实例上找不到旧会话。会话跨实例保留见 [scaling-session](../scaling-session/README_zh.md)。

其他常用用法：

```bash
# 从 stdin 读取问题
echo 'List the files in the current directory.' | agr harness prompt "$HARNESS_ID" --region "$AGR_REGION" -

# 逐行输出事件，适合 Agent 边读边处理
agr harness prompt "$HARNESS_ID" --region "$AGR_REGION" -o ndjson 'Say hello.'
```

NDJSON 的第一行是 `started`（包含 `SessionId`）；每个 ACP `session/update` 对应一行 `update`，`Data` 是原始 ACP 内容；最后一行是 `completed`，内容与 `-o json` 的 `Data` 相同：

```text
{"SchemaVersion":"agr.events.v1","Type":"started","Data":{"HarnessId":"hns-********","SessionId":"<masked>"}}
{"SchemaVersion":"agr.events.v1","Type":"update","Data":{"sessionUpdate":"agent_message_chunk","content":{"type":"text","text":"Hello"}}}
{"SchemaVersion":"agr.events.v1","Type":"completed","Data":{"HarnessId":"hns-********","SessionId":"<masked>","Reply":"Hello!","StopReason":"end_turn",...}}
```

`prompt` 不能代替人审批工具调用，收到的权限请求一律回复 `cancelled`。按 `Ctrl+C` 会发送 `session/cancel`，未完成的一轮不会自动重发。

## 3. `acp`：接入编辑器和 acpx

`agr harness acp` 把 stdin/stdout 上的 ACP JSON-RPC 桥接到远端 Harness，整个进程内自动刷新 Token 并保持亲和。stdout 只输出 ACP 消息，诊断信息写到 stderr。

启动桥接时显式加 `-o text`，选择原始 ACP 输出，并覆盖已配置的 JSON 或 NDJSON 默认输出。stdout 仍然发送 ACP JSON-RPC 消息。

桥接会原样转发客户端的 `cwd`，不会映射路径或同步本地文件。创建或恢复会话时，该路径必须是沙箱内已经存在且可访问的绝对目录。下面这个可选的 Unix 连通性示例要求 Node.js 22.13 或更新版本，通过 `npx` 运行 [acpx](https://github.com/openclaw/acpx) 0.22.0。运行前请先安装它们；`prompt`、`proxy` 和 `endpoint` 不依赖它们。示例显式选择本机和托管镜像中都存在的 `/tmp`：

```bash
npx --yes acpx@0.22.0 --cwd /tmp --agent "agr harness acp $HARNESS_ID --region $AGR_REGION -o text" exec 'Summarize what you can do in one sentence.'
```

Zed 等编辑器通常把本地项目路径作为 `cwd`。下面的配置要求同一个绝对路径也存在于目标实例中，它不会准备远端项目目录。如果实例中没有这个路径，请使用 `agr harness prompt`（远端 `cwd` 默认为 `/workspace`），或使用能将工作目录映射到已有远端路径的客户端。

满足上述目录前提后，在 Zed 的 `settings.json` 中添加一个自定义 ACP Agent：

```json
{
  "agent_servers": {
    "managed-harness": {
      "type": "custom",
      "command": "agr",
      "args": ["harness", "acp", "hns-replace-me", "--region", "ap-chongqing", "-o", "text"],
      "env": {}
    }
  }
}
```

其他编辑器的配置方式类似：命令为 `agr`，参数为 `harness acp <harness-id> --region <region> -o text`。编辑器会在需要时启动这个子进程。要回到之前会话所在的实例，在 `args` 末尾加上 `--affinity-id <affinity-id>`。

## 4. `proxy`：本地调试地址

`proxy` 在本机提供一个不需要凭证的 ACP 地址，代理负责添加并刷新 Token，并保持亲和。它会占用当前终端：

```bash
agr harness proxy "$HARNESS_ID" --region "$AGR_REGION" --port 18080
```

预期输出：

```text
ACP endpoint: http://127.0.0.1:18080/acp
Forwarding to https://8080-dpl-********.ap-chongqing.agents.tencentags.com/acp (Deployment dpl-********). Local testing only.
Press Ctrl+C to stop.
Affinity ID: <masked-affinity-id>
```

`Affinity ID` 在第一个请求返回后才会出现。此时把 ACP SDK 或浏览器客户端指向 `http://127.0.0.1:18080/acp` 即可，例如官方 TypeScript SDK 的 HTTP 传输。

让 Agent 在后台启动代理时，使用随机端口和 NDJSON，读取第一行即可拿到地址：

```bash
agr harness proxy "$HARNESS_ID" --region "$AGR_REGION" --port 0 -o ndjson
```

```text
{"SchemaVersion":"agr.events.v1","Type":"ready","Data":{"AcpURL":"http://127.0.0.1:54321/acp","RemoteAcpURL":"https://8080-dpl-********.ap-chongqing.agents.tencentags.com/acp","HarnessId":"hns-********","DeploymentId":"dpl-********","AffinityHeader":"X-Tencent-Agr-Affinity-Id"}}
```

代理仅用于本地调试，默认只监听 `127.0.0.1`。验证后按 `Ctrl+C` 停止。

## 5. `endpoint`：在自己的服务中直连

生产服务应自己调用 `AcquireDeploymentToken` 获取短期 Token，然后直接访问 ACP 地址。`endpoint` 告诉你地址和必须携带的请求头；加 `--show-token` 会同时签发一个 Token，便于手工测试。

```bash
agr harness endpoint "$HARNESS_ID" --region "$AGR_REGION" --show-token -o json \
  --jq '.Data | {AcpURL, AffinityHeader, DeploymentId, ExpiresAt, Headers}'
```

```json
{"AcpURL":"https://8080-dpl-********.ap-chongqing.agents.tencentags.com/acp","AffinityHeader":"X-Tencent-Agr-Affinity-Id","DeploymentId":"dpl-********","ExpiresAt":"<masked-expiration>","Headers":{"X-Access-Token":"<masked-deployment-token>"}}
```

CLI 不会为外部程序刷新 Token。长期运行的服务应在 `ExpiresAt` 之前自己调用 `AcquireDeploymentToken` 重新获取。读取创建时保存的 Deployment ID：

```bash
HARNESS_DEPLOYMENT_ID=$(python3 ../scripts/resources.py get connect DeploymentId) && export HARNESS_DEPLOYMENT_ID

agr api call AcquireDeploymentToken \
  --region "$AGR_REGION" \
  --request '{"DeploymentId":"'$HARNESS_DEPLOYMENT_ID'"}' \
  --output json
```

返回的 Token 位于 `Data.Response.Response.Token`。

### 用 `curl` 走一遍 ACP Streamable HTTP

下面用 `curl` 手工完成一次对话，帮助理解协议。生产中建议使用官方 ACP SDK，它已经处理了这些细节。

协议要点：

1. 所有请求都带 `X-Access-Token`。
2. `initialize` 直接返回 JSON 结果，并在响应头中返回 `Acp-Connection-Id`。之后的请求都要带上这个头。
3. 将响应里的亲和头（默认 `X-Tencent-Agr-Affinity-Id`）在之后的每个请求里原样带回，确保同一个连接的请求落到同一个实例。
4. 之后的 POST 返回 `202 Accepted`，结果和更新通过 GET 打开的 SSE 流到达：一个连接级流，以及每个会话一个带 `Acp-Session-Id` 的会话级流。
5. 结束时用 DELETE 关闭连接。

下面会用到三个终端。把变量写入 `acp.env` 文件，每个新终端先执行 `source acp.env` 即可。从上一步的输出复制地址和 Token：

```bash
cat > acp.env <<'EOF'
export ACP_URL='https://8080-dpl-replace-me.ap-chongqing.agents.tencentags.com/acp'
export ACP_TOKEN='replace-with-token'
EOF
source acp.env
```

Token 在 `ExpiresAt` 后失效，失效后重新执行上一步的 `endpoint --show-token` 并更新 `acp.env`。

**第一步：initialize。** `--include` 显示响应头：

```bash
curl --include --silent --show-error -X POST "$ACP_URL" \
  --header "X-Access-Token: $ACP_TOKEN" \
  --header 'Content-Type: application/json' \
  --header 'Accept: application/json, text/event-stream' \
  --data '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":1,"clientCapabilities":{}}}'
```

```http
HTTP/2 200
content-type: application/json
acp-connection-id: <masked-connection-id>
x-tencent-agr-affinity-id: <masked-affinity-id>

{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":1,"agentCapabilities":{"loadSession":true,...},"agentInfo":{...}}}
```

把这两个响应头追加到 `acp.env`：

```bash
cat >> acp.env <<'EOF'
export ACP_CONNECTION_ID='replace-with-connection-id'
export ACP_AFFINITY_ID='replace-with-affinity-id'
EOF
source acp.env
```

**第二步：打开连接级 SSE 流。** 打开第二个终端，进入同一目录并保持运行，`session/new` 的结果会出现在这里：

```bash
source acp.env

curl --no-buffer --silent --show-error "$ACP_URL" \
  --header "X-Access-Token: $ACP_TOKEN" \
  --header "Acp-Connection-Id: $ACP_CONNECTION_ID" \
  --header "X-Tencent-Agr-Affinity-Id: $ACP_AFFINITY_ID" \
  --header 'Accept: text/event-stream'
```

**第三步：创建会话。** 回到第一个终端：

```bash
curl --include --silent --show-error -X POST "$ACP_URL" \
  --header "X-Access-Token: $ACP_TOKEN" \
  --header "Acp-Connection-Id: $ACP_CONNECTION_ID" \
  --header "X-Tencent-Agr-Affinity-Id: $ACP_AFFINITY_ID" \
  --header 'Content-Type: application/json' \
  --header 'Accept: application/json, text/event-stream' \
  --data '{"jsonrpc":"2.0","id":2,"method":"session/new","params":{"cwd":"/workspace","mcpServers":[]}}'
```

POST 返回 `HTTP/2 202`。SSE 终端中会出现结果：

```text
data: {"jsonrpc":"2.0","id":2,"result":{"sessionId":"<masked-session-id>",...}}
```

把会话 ID 追加到 `acp.env`：

```bash
echo "export ACP_SESSION_ID='replace-with-session-id'" >> acp.env
source acp.env
```

**第四步：打开会话级 SSE 流。** 打开第三个终端，进入同一目录运行，回复的文本片段（`session/update`）和 `session/prompt` 的最终结果会出现在这里：

```bash
source acp.env

curl --no-buffer --silent --show-error "$ACP_URL" \
  --header "X-Access-Token: $ACP_TOKEN" \
  --header "Acp-Connection-Id: $ACP_CONNECTION_ID" \
  --header "Acp-Session-Id: $ACP_SESSION_ID" \
  --header "X-Tencent-Agr-Affinity-Id: $ACP_AFFINITY_ID" \
  --header 'Accept: text/event-stream'
```

**第五步：发送问题。**

```bash
curl --include --silent --show-error -X POST "$ACP_URL" \
  --header "X-Access-Token: $ACP_TOKEN" \
  --header "Acp-Connection-Id: $ACP_CONNECTION_ID" \
  --header "Acp-Session-Id: $ACP_SESSION_ID" \
  --header "X-Tencent-Agr-Affinity-Id: $ACP_AFFINITY_ID" \
  --header 'Content-Type: application/json' \
  --header 'Accept: application/json, text/event-stream' \
  --data '{"jsonrpc":"2.0","id":3,"method":"session/prompt","params":{"sessionId":"'"$ACP_SESSION_ID"'","prompt":[{"type":"text","text":"Say hello in five words."}]}}'
```

会话级 SSE 终端中会依次出现回复片段和最终结果：

```text
data: {"jsonrpc":"2.0","method":"session/update","params":{"sessionId":"<masked>","update":{"sessionUpdate":"agent_message_chunk","content":{"type":"text","text":"Hello"}}}}
...
data: {"jsonrpc":"2.0","id":3,"result":{"stopReason":"end_turn"}}
```

**第六步：关闭连接。** 先在两个 SSE 终端按 `Ctrl+C`，然后：

```bash
curl --include --silent --show-error -X DELETE "$ACP_URL" \
  --header "X-Access-Token: $ACP_TOKEN" \
  --header "Acp-Connection-Id: $ACP_CONNECTION_ID" \
  --header "X-Tencent-Agr-Affinity-Id: $ACP_AFFINITY_ID"
```

常见平台错误以 JSON 返回，例如底层 Tool 不可用时：

```json
{"code":"sandbox_tool_unavailable","message":"sandbox tool is unavailable; tool status: NOT_FOUND","request_id":"<masked-request-id>"}
```

使用 `agr` 命令时，这类错误会被归类为 `ACP_UNAVAILABLE`，平台错误码保存在 `Failure.Details.PlatformCode`。

## 6. 清理资源

删除本场景保存的资源。脚本从 `.state/` 读取 ID、地域和 endpoint，等待删除完成并回查结果；清理中断后可以重复执行。

```bash
python3 ../scripts/resources.py cleanup connect --yes
rm -f acp.env
```

## 常见问题

| 现象 | 原因与处理 |
| --- | --- |
| `ACP_UNAVAILABLE`，`PlatformCode` 为实例未就绪 | 实例仍在启动。稍等后重试 `endpoint --check` |
| `ACP_UNAVAILABLE`，`PlatformCode` 为 `sandbox_tool_unavailable` | 底层 Tool 已被删除或不可用，Harness 不会自动重建。删除该 Harness 后重新创建 |
| `ACP_AUTH_FAILED` | Token 无效或已过期。重新获取 Token；使用 `agr` 命令时检查 `--domain` 和 `AcquireDeploymentToken` 权限 |
| `SESSION_RESTORE_FAILED` | 旧会话不在当前实例上。带上创建会话时的 `--affinity-id` 和 `--cwd`，或配置 Session Space |
| `PROMPT_TIMEOUT` | 在 `--timeout` 内没有回复，已发送 `session/cancel`。加大 `--timeout`，或带 `--session-id` 和 `--affinity-id` 继续 |
| `PROXY_BIND_FAILED` | 本地端口被占用。换一个 `--port`，或用 `--port 0` 自动选择 |
