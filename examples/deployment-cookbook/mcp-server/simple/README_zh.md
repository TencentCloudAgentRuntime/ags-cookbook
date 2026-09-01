# 在 AGR 上部署 Everything MCP Server

本示例在 AGR 上运行官方 Everything MCP Server，并使用官方 Python MCP SDK 连接。HTTP hook 负责添加 AGS token 和 `BEST_EFFORT` affinity header，Streamable HTTP 仍由 SDK 处理。

你将完成：

- 通过生产访问地址运行 `initialize → tools/list → echo`；
- 观察活跃容量从 `0 → N → 0`；
- 空闲 `STOP` 后复用保存的 AGS affinity，同时建立新的 MCP 会话。

Everything MCP Server 把 MCP 会话状态保存在自己的进程内。`MCP-Session-Id` 和 AGS affinity 是两类状态：实例停止后可以再次发送 affinity，但 MCP 客户端需要新建会话。

## 前置条件

- 已安装 **v0.6.6 或更高版本**的 `agr`。如果尚未配置 CLI，请先按[AGR CLI 官方 GitHub 凭证配置说明](https://github.com/TencentCloudAgentRuntime/ags-cli/blob/main/README-zh.md#初始化-cli-凭证)完成初始化，再运行 `agr status` 和 `agr doctor`。
- 已安装 [`uv`](https://docs.astral.sh/uv/)。
- 按官方[自定义沙箱角色与权限指南](https://cloud.tencent.com/document/product/1814/129691)创建 Agent Runtime CAM 角色，授予该角色所用 CCR 或 TCR 仓库的访问权限，并向 CLI 使用的身份授予该角色的 `cam:PassRole` 权限。
- CLI 使用的身份可以创建和删除 Sandbox Tool 与 Deployment、查询和删除 Instance，并能获取 Deployment token。
- 仅当需要尝试可选的本地代理诊断时，才需要保证本地端口 `18080` 可用。

使用以下已发布镜像：

```text
ccr.ccs.tencentyun.com/ags.dev/mcp-everything:2026.8.31-ags.1
```

镜像 digest（可选，用于核对镜像内容）：

```text
sha256:3e708366c19c13516b508ac8c58580b060df7cfba4197005070cc433b98c07d3
```

可以直接使用该已发布的示例镜像。如需将镜像构建并推送到自己的仓库，请参考 [dockerfiles](./dockerfiles/README_zh.md)。

请从当前 `simple` 目录执行全部命令。从命令输出中复制真实资源 ID 和短期 Deployment token；示例值均为占位符。

## 1. 配置本地变量

使用唯一的资源名称后缀，并替换角色 ARN。本教程通过 `AGR_REGION` 指定上海地域，且每个云端命令都显式传入 `--region`，无需修改 CLI 的全局 region。

```bash
export AGR_REGION=ap-shanghai
export AGR_DOMAIN=tencentags.com
export AGR_ROLE_ARN='qcs::cam::uin/100000000001:roleName/replace-me'
export MCP_TOOL_NAME='mcp-everything-simple-your-name'
export MCP_DEPLOYMENT_NAME='mcp-everything-simple-your-name'
export MCP_STATE_DIR="${TMPDIR:-/tmp}/ags-cookbook-$MCP_TOOL_NAME"
export MCP_AFFINITY_STATE="$MCP_STATE_DIR/smoke-affinity.json"

mkdir -p "$MCP_STATE_DIR"
chmod 700 "$MCP_STATE_DIR"

agr status
agr doctor
uv sync --project client --locked

(
  cd client
  uv run --locked python -m unittest discover -s tests -v
)
```

`MCP_STATE_DIR` 只保存 AGS affinity 状态。客户端用 `0600` 权限创建文件，不会写入 Deployment token 或 `MCP-Session-Id`。

客户端项目已将腾讯 PyPI mirror 配置为默认 `uv` index，`uv.lock` 固定了解析后的制品和 hash。

## 2. 创建 Sandbox Tool

运行时无需访问公网。端口 `3001` 提供 MCP 服务；仅容器内部使用的端口 `3000` 提供就绪检查地址。下面的命令使用已发布的示例镜像。如果已构建自有镜像，请将完整镜像地址粘贴到 `Image`；CCR 个人版的 `ImageRegistryType` 使用 `personal`，TCR 企业版使用 `enterprise`。

```bash
agr tool create \
  --region "$AGR_REGION" \
  --tool-name "$MCP_TOOL_NAME" \
  --tool-type custom \
  --persistent \
  --role-arn "$AGR_ROLE_ARN" \
  --network-configuration '{"NetworkMode":"SANDBOX"}' \
  --custom-configuration '{
    "Image": "ccr.ccs.tencentyun.com/ags.dev/mcp-everything:2026.8.31-ags.1",
    "ImageRegistryType": "personal",
    "Command": [
      "node",
      "entrypoint.mjs"
    ],
    "Ports": [
      {
        "Name": "mcp",
        "Port": 3001,
        "Protocol": "TCP"
      }
    ],
    "Resources": {
      "CPU": "500m",
      "Memory": "1Gi"
    },
    "Probe": {
      "HttpGet": {
        "Path": "/healthz",
        "Port": 3000,
        "Scheme": "HTTP"
      },
      "ReadyTimeoutMs": 30000,
      "ProbeTimeoutMs": 1000,
      "ProbePeriodMs": 3000,
      "SuccessThreshold": 1,
      "FailureThreshold": 10
    }
  }' \
  --wait
```

本教程显式提供 `Command`，让 Tool 配置直接显示启动命令；镜像中也包含相同的入口。`ReadyTimeoutMs=30000` 是 API 上限。

成功输出包含真实 Tool ID。复制并设置：

```bash
export MCP_TOOL_ID='sdt-replace-me'
```

## 3. 创建 Deployment

官方 SDK 会保持一个 GET event stream，同时发送 POST 和 DELETE 请求。将每实例请求并发设为 `2`；这是单个原生客户端的实测最低值，不表示客户端和实例之间存在固定映射。

```bash
agr deployment create \
  --region "$AGR_REGION" \
  --deployment-name "$MCP_DEPLOYMENT_NAME" \
  --tool-id "$MCP_TOOL_ID" \
  --scaling-configuration '{
    "MinInstanceCount": 0,
    "MaxInstanceCount": 3,
    "MaxInstanceRequestConcurrency": 2
  }' \
  --lifecycle-configuration '{
    "IdleTimeoutSeconds": 60,
    "IdleAction": "STOP"
  }' \
  --affinity-configuration '{
    "Mode": "BEST_EFFORT",
    "HeaderName": "X-Tencent-Agr-Affinity-Id"
  }'
```

复制 Deployment ID，并构造生产 URL：

```bash
export MCP_DEPLOYMENT_ID='dpl-replace-me'
export MCP_DEPLOYMENT_URL="https://3001-$MCP_DEPLOYMENT_ID.$AGR_REGION.agents.$AGR_DOMAIN/mcp"

agr deployment get "$MCP_DEPLOYMENT_ID" --region "$AGR_REGION"
agr instance list --tool-id "$MCP_TOOL_ID" --region "$AGR_REGION"
```

第一次请求前，不应存在 `RUNNING` 实例。

## 4. 获取短期 token

没有 Deployment token 的数据面请求会被拒绝。下面的 GET 只用于鉴权检查，不是 MCP 协议操作：

```bash
curl --include --silent --show-error "$MCP_DEPLOYMENT_URL"
```

预期 HTTP 状态为 `401`。将 token 直接获取到当前 shell：

```bash
MCP_DEPLOYMENT_TOKEN="$(
  agr api call AcquireDeploymentToken \
    --region "$AGR_REGION" \
    --request '{"DeploymentId":"'$MCP_DEPLOYMENT_ID'"}' \
    --output json \
    --jq '.Data.Response.Response.Token'
)"
export MCP_DEPLOYMENT_TOKEN
```

如果命令失败或 `MCP_DEPLOYMENT_TOKEN` 为空，请停止操作。该命令会直接捕获 token，不会将其打印到终端或把 token 值写入 shell history。不要把该 token 写入 affinity 状态文件、命令行参数或日志。

## 5. 测试生产访问地址

客户端直接使用 `mcp.client.streamable_http.streamable_http_client` 和 `mcp.ClientSession`。客户端依赖的 `httpx2` 提供请求/响应 hook 使用的 `AsyncClient`：一个 hook 添加最新的 AGS affinity，另一个在网关返回新值时将其保存。

```bash
uv run --project client --locked python client/mcp_client.py smoke \
  --url "$MCP_DEPLOYMENT_URL" \
  --transport direct \
  --state-file "$MCP_AFFINITY_STATE"
```

成功的 JSON Lines 事件包括：

```json
{"affinity":"<sha256-prefix>","event":"initialize","protocol":"2025-11-25","server":"mcp-servers/everything","server_version":"2.0.0","worker":"worker-1"}
{"event":"tools_list","required_present":true,"tool_count":13,"worker":"worker-1"}
{"event":"tool_call","result":"ok","tool":"echo","worker":"worker-1"}
{"command":"smoke","event":"command_done","failed":0,"succeeded":1}
```

使用这个固定镜像时，预期看到服务端名称 `mcp-servers/everything`、版本 `2.0.0`、协议 `2025-11-25` 和 13 个工具。结果中应包含 `echo`、`trigger-long-running-operation` 和 `Echo: ags-cookbook`。

日志只显示 affinity 的 SHA-256 前缀。

## 6. 观察 `0 → N → 0`

先关闭所有 MCP 客户端，并等待到没有 `RUNNING` 实例。即使空闲超时为 60 秒，异步回收也可能需要数分钟：

```bash
agr instance list --tool-id "$MCP_TOOL_ID" --region "$AGR_REGION"
```

在第一个终端保持一个 90 秒的原生 MCP 调用：

```bash
uv run --project client --locked python client/mcp_client.py hold \
  --url "$MCP_DEPLOYMENT_URL" \
  --transport direct \
  --state-dir "$MCP_STATE_DIR/hold" \
  --workers 1 \
  --duration 90
```

当 `trigger-long-running-operation` 调用仍在进行时，在第二个终端运行：

```bash
agr instance list --tool-id "$MCP_TOOL_ID" --region "$AGR_REGION"
```

统计 `RUNNING` 行数，将其记为 `N`。此时应看到 `1 <= N <= 3`。`N` 以实例列表为准，不要根据客户端数量推算。

客户端退出后，不再访问 Deployment。等待至少 60 秒，然后重复列出实例，直到异步状态收敛；这可能需要数分钟。活跃实例数最终必须回到零；历史 `STOPPED` 行可能仍然可见。

可以将 `hold` 改为 `--workers 3`，观察请求装箱或扩容。在 `BEST_EFFORT` 下，客户端可能共享实例或迁移，因此多工作进程执行可能返回 400 或 429，不会稳定地形成一个客户端对应一个实例的关系。

## 7. 用新 MCP 会话验证 `BEST_EFFORT`

smoke 使用的实例变为 `STOPPED` 后，把已保存的 AGS affinity 用于一个全新的官方 MCP 传输和会话：

```bash
uv run --project client --locked python client/mcp_client.py resume \
  --url "$MCP_DEPLOYMENT_URL" \
  --transport direct \
  --state-file "$MCP_AFFINITY_STATE"
```

该命令应再次完成 `initialize`、`tools/list` 和 `echo`。Affinity 指纹可能保持不变，也可能变化；如果变化，客户端会保存新值。

客户端不会重放之前的进程内 `MCP-Session-Id`，也不会自动重试失败的工具调用，因为原调用可能已经执行。

## 8. 可选：通过本地代理排查问题

`agr deployment proxy` 适合用于排查 Deployment。该本地代理会注入 token 并管理 affinity，因此客户端省略这两项：

```bash
agr deployment proxy "$MCP_DEPLOYMENT_ID" 18080:3001 --region "$AGR_REGION"
```

在另一个终端运行：

```bash
uv run --project client --locked python client/mcp_client.py smoke \
  --url http://127.0.0.1:18080/mcp \
  --transport proxy
```

冷启动可能超过本地代理的响应头超时并返回 502。遇到这种情况时，检查实例就绪状态，并回到生产访问地址直连流程。

## 失败模式

| 现象 | 含义与恢复方式 |
| --- | --- |
| `agr tool create --wait` 失败或超时 | 先查看命令报告的错误，再核对 `AGR_ROLE_ARN`、`cam:PassRole`、镜像仓库拉取权限、`Image`、`ImageRegistryType`，以及就绪检查的端口和路径。按第 9 节查找可能已创建的 Tool，用 `agr tool get "$MCP_TOOL_ID" --region "$AGR_REGION"` 查看详情，再按第 10 节删除后，使用修正后的配置和新的唯一名称重试。 |
| `agr deployment create` 失败 | 用 `agr tool get "$MCP_TOOL_ID" --region "$AGR_REGION"` 确认 Tool 为 `ACTIVE`。按第 9 节查找可能已创建的 Deployment，用 `agr deployment get "$MCP_DEPLOYMENT_ID" --region "$AGR_REGION"` 查看详情，再按第 10 节删除后重试。 |
| HTTP 401 | Deployment token 缺失或过期。重新获取并更新 `MCP_DEPLOYMENT_TOKEN`。 |
| 迁移后 HTTP 400 | 请求到达了不持有旧 MCP 会话的进程。关闭传输，并初始化新的官方 MCP 会话。 |
| HTTP 429 | 所有请求或连接租约都被占用。关闭遗留客户端或减少并发工作进程。 |
| 本地代理返回 502 | 冷启动响应头超过本地代理超时。检查实例就绪状态，并改用生产数据面直连。 |
| Affinity 指纹变化 | `BEST_EFFORT` 允许该行为，请使用新返回值。 |
| 实例持续 `RUNNING` | 确保全部 SDK 和 HTTP context 已关闭。如果超过收敛时间仍活跃，请显式删除实例。 |
| 部分多工作进程调用失败 | 多工作进程运行主要用来观察这个有状态服务；请用单工作进程流程检查基本配置。 |

## 9. 中断后找回资源 ID

如果创建资源的 shell 已经关闭，请重新设置第 1 步使用的唯一名称，并在继续操作或清理前找回 ID：

```bash
export MCP_TOOL_NAME='mcp-everything-simple-your-name'
export MCP_DEPLOYMENT_NAME='mcp-everything-simple-your-name'
export AGR_REGION=ap-shanghai
export AGR_DOMAIN=tencentags.com
export MCP_STATE_DIR="${TMPDIR:-/tmp}/ags-cookbook-$MCP_TOOL_NAME"
export MCP_AFFINITY_STATE="$MCP_STATE_DIR/smoke-affinity.json"

export MCP_TOOL_ID="$(
  agr tool list \
    --region "$AGR_REGION" \
    --filters "[{\"Name\":\"ToolName\",\"Values\":[\"$MCP_TOOL_NAME\"]}]" \
    -o json --jq '(.Data.Items // [])[0].ToolId // empty'
)"

export MCP_DEPLOYMENT_ID="$(
  agr deployment list \
    --region "$AGR_REGION" \
    --filters "[{\"Name\":\"deployment-name\",\"Values\":[\"$MCP_DEPLOYMENT_NAME\"]}]" \
    -o json --jq '(.Data.DeploymentSet // [])[0].DeploymentId // empty'
)"

printf 'Tool: %s\nDeployment: %s\n' "$MCP_TOOL_ID" "$MCP_DEPLOYMENT_ID"

if test -n "$MCP_TOOL_ID"; then
  agr instance list --tool-id "$MCP_TOOL_ID" --region "$AGR_REGION"
fi
```

两个过滤条件都是精确匹配，因此第 1 步要求使用唯一名称。ID 为空表示相应资源尚未创建或已经删除，仍可继续清理另一个资源。仅当两个 ID 都存在时才继续数据面测试。重新构造访问地址，再按第 4 步获取新的短期 token：

```bash
export MCP_DEPLOYMENT_URL="https://3001-$MCP_DEPLOYMENT_ID.$AGR_REGION.agents.$AGR_DOMAIN/mcp"
```

不要保存或尝试找回旧 token。

## 10. 清理

如果 Deployment 存在，先将其删除；如果 Tool 存在，再查询 Instance：

```bash
if test -n "${MCP_DEPLOYMENT_ID:-}"; then
  agr deployment delete "$MCP_DEPLOYMENT_ID" --region "$AGR_REGION" --wait
fi

if test -n "${MCP_TOOL_ID:-}"; then
  agr instance list --tool-id "$MCP_TOOL_ID" --region "$AGR_REGION"
fi
```

如果列表中存在非 `STOPPED` Instance，复制其 ID 并删除。对每个非停止 Instance 重复操作；如果没有则跳过：

```bash
export MCP_INSTANCE_ID='replace-with-non-stopped-instance-id'

if test -n "${MCP_INSTANCE_ID:-}"; then
  agr instance delete "$MCP_INSTANCE_ID" --region "$AGR_REGION" --yes --wait
fi
```

如果 Tool 存在，将其删除；随后删除本地状态并清除 shell token：

```bash
if test -n "${MCP_TOOL_ID:-}"; then
  agr tool delete "$MCP_TOOL_ID" --region "$AGR_REGION" --yes --wait
fi

if test -n "${MCP_STATE_DIR:-}" && test -d "$MCP_STATE_DIR"; then
  rm -r -- "$MCP_STATE_DIR"
fi

unset MCP_DEPLOYMENT_TOKEN
```

Tool 删除后可能仍能看到历史 `STOPPED` 实例行。它们不是活跃容量，也不属于清理失败。

## 检查清单

- `uv sync --project client --locked` 成功。
- 客户端测试通过。
- 新建的上海 Deployment 对未鉴权请求返回 401。
- 一个生产直连原生 smoke 完成。
- 活跃容量经历 `0 → N → 0`，且 `N >= 1`。
- 原实例停止后，`resume` 成功。
- 清理后不存在 Deployment、Tool、非停止实例、token 文件或 affinity 状态文件。

平台层面的独立说明见 [httpbin scaling](../../httpbin/scaling/README_zh.md)、[lifecycle](../../httpbin/lifecycle/README_zh.md) 和 [affinity](../../httpbin/affinity/README_zh.md) 教程。
