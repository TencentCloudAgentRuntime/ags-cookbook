# 在 AGR 上部署原生 MCP Server 客户端链路

本教程部署官方 Everything MCP Server，并使用官方 Python MCP SDK 验证。AGS 鉴权和 `BEST_EFFORT` affinity 通过 HTTP hooks 接入；客户端不会重新实现 Streamable HTTP，也不会禁用 SDK 原生的 GET stream。

本教程分别证明以下结果：

- 一个生产客户端完成 `initialize → tools/list → echo`；
- 原生 MCP 流量使活跃容量经历 `0 → N → 0`，其中 `N` 是实测值，而不是根据客户端数量推算的值；
- 空闲 `STOP` 后，可以把保留的 AGS affinity 发送给一个新的 MCP 会话，AGS 也可能返回替换后的 affinity。

官方 Everything server 把 MCP 会话状态保存在单个进程内。因此，`MCP-Session-Id` 与 AGS affinity 是两类不同状态。实例替换后绝不能复用旧 MCP 会话。

## 前置条件

- 已安装 **v0.6.6 或更高版本**的 `agr`，并运行 `agr status`。
- 已安装 [`uv`](https://docs.astral.sh/uv/)。
- 已准备允许 AGR 拉取固定 CCR 镜像的 CAM 角色 ARN。
- 当前账号可以创建和删除 Sandbox Tool、Deployment、Instance，并能获取 Deployment token。
- 仅当需要尝试可选 proxy 诊断时，才需要保证本地端口 `18080` 可用。

预构建镜像为：

```text
ccr.ccs.tencentyun.com/ags.dev/mcp-everything:2026.8.31-ags.1
```

已发布的 OCI index digest：

```text
sha256:3e708366c19c13516b508ac8c58580b060df7cfba4197005070cc433b98c07d3
```

可复现源码、许可证、固定依赖图和发布流程见 [dockerfiles](./dockerfiles/README_zh.md)。

请从当前 `simple` 目录执行全部命令。从命令输出中复制真实资源 ID 和短期 Deployment token；示例值均为占位符。

## 1. 配置本地变量

使用唯一的资源名称后缀，并替换角色 ARN：

```bash
export AGR_REGION=ap-shanghai
export AGR_DOMAIN=tencentags.com
export AGR_ROLE_ARN='qcs::cam::uin/100000000001:roleName/replace-me'
export MCP_TOOL_NAME='mcp-everything-simple-your-name'
export MCP_DEPLOYMENT_NAME='mcp-everything-simple-your-name'
export MCP_STATE_DIR="$(mktemp -d)"
export MCP_AFFINITY_STATE="$MCP_STATE_DIR/smoke-affinity.json"

agr status
uv sync --project client --locked

(
  cd client
  uv run --locked python -m unittest discover -s tests -v
)
```

`MCP_STATE_DIR` 只保存 AGS affinity 状态。客户端用 `0600` 权限创建文件，绝不会写入 Deployment token 或 `MCP-Session-Id`。

客户端项目已将腾讯 PyPI mirror 配置为默认 `uv` index，`uv.lock` 固定了解析后的制品和 hash。

## 2. 创建 Sandbox Tool

运行时无需访问公网。端口 `3001` 提供 MCP 服务；仅容器内部使用的端口 `3000` 提供运维 readiness endpoint。

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

即使镜像已包含同一个 entry point，Custom Tool API 仍要求显式提供 `Command`。`ReadyTimeoutMs=30000` 是 API 上限。

成功输出包含真实 Tool ID。复制并设置：

```bash
export MCP_TOOL_ID='sdt-replace-me'
```

## 3. 创建 Deployment

官方 SDK 会保持一个 GET event stream，同时发送 POST 和 DELETE 请求。每实例请求并发租约 `2` 是已验证的单个原生客户端兼容下限。它不表示永久保留两个租约，也不代表客户端与实例之间存在固定映射。

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

预期 HTTP 状态为 `401`。获取 token：

```bash
agr api call AcquireDeploymentToken \
  --region "$AGR_REGION" \
  --request '{"DeploymentId":"'$MCP_DEPLOYMENT_ID'"}' \
  --output json
```

将 `Data.Response.Response.Token` 只复制到当前 shell：

```bash
export MCP_DEPLOYMENT_TOKEN='replace-with-token'
```

不要把该 token 写入 affinity 状态文件、命令行参数或日志。

## 5. 运行权威原生 smoke

客户端直接使用 `mcp.client.streamable_http.streamable_http_client` 和 `mcp.ClientSession`。`httpx2.AsyncClient` request hook 注入最新 AGS affinity，response hook 在网关返回新值时保存替换值。

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

固定镜像报告 server name `mcp-servers/everything`、版本 `2.0.0` 和 13 个 tool。它必须报告协议 `2025-11-25`，提供 `echo` 和 `trigger-long-running-operation`，并返回 `Echo: ags-cookbook`。

日志只显示 affinity 的 SHA-256 前缀。

## 6. 观察 `0 → N → 0`

先关闭所有 MCP client，并等待到没有 `RUNNING` 实例。即使空闲超时为 60 秒，异步回收也可能需要数分钟：

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

把 `RUNNING` 行数记为 `N`。支持的断言是 `1 <= N <= 3`，不要根据客户端数量推算 `N`。

客户端退出后，不再访问 Deployment。等待至少 60 秒，然后重复列出实例，直到异步状态收敛；这可能需要数分钟。活跃实例数最终必须回到零；历史 `STOPPED` 行可能仍然可见。

可以将 `hold` 改为 `--workers 3`，观察请求装箱或 scale-out。该步骤仅用于诊断：在 `BEST_EFFORT` 下，客户端可能共享实例或迁移；多 worker 执行可能返回 400 或 429，而不是形成一个客户端对应一个实例的关系。

## 7. 用新 MCP 会话验证 `BEST_EFFORT`

smoke 使用的实例变为 `STOPPED` 后，把已保存的 AGS affinity 用于一个全新的官方 MCP transport 和 session：

```bash
uv run --project client --locked python client/mcp_client.py resume \
  --url "$MCP_DEPLOYMENT_URL" \
  --transport direct \
  --state-file "$MCP_AFFINITY_STATE"
```

该命令必须再次完成 `initialize`、`tools/list` 和 `echo`。Affinity 指纹可以保持不变，也可以变化。变化后的值是合法的 `BEST_EFFORT` 行为，并会覆盖状态文件中的旧值。

客户端绝不会重放之前的进程内 `MCP-Session-Id`，也不会自动重试任意失败的 tool call，因为原调用可能已经执行。

## 8. 可选本地 proxy 诊断

`agr deployment proxy` 可用于查看 Deployment，但对这个有状态 server 与原生 SDK 组合而言，它不是验收路径。Proxy 会注入 token 并管理 affinity，因此客户端省略这两项：

```bash
agr deployment proxy "$MCP_DEPLOYMENT_ID" 18080:3001 --region "$AGR_REGION"
```

在另一个终端运行：

```bash
uv run --project client --locked python client/mcp_client.py smoke \
  --url http://127.0.0.1:18080/mcp \
  --transport proxy
```

冷启动可能超过 proxy 的响应头超时并返回 502。请查看实例 readiness，并以生产数据面直连结果作为权威结论。不要因为该可选路径失败而降低生产验收标准。

## 失败模式

| 现象 | 含义与恢复方式 |
| --- | --- |
| HTTP 401 | Deployment token 缺失或过期。重新获取并更新 `MCP_DEPLOYMENT_TOKEN`。 |
| 迁移后 HTTP 400 | 请求到达了不持有旧 MCP session 的进程。关闭 transport，并初始化新的官方 MCP session。 |
| HTTP 429 | 所有请求或连接租约都被占用。关闭遗留 client 或减少并发 worker。 |
| Proxy 502 | 冷启动响应头超过本地 proxy 超时。检查实例 readiness，并改用生产数据面直连。 |
| Affinity 指纹变化 | `BEST_EFFORT` 允许该行为，请使用新返回值。 |
| 实例持续 `RUNNING` | 确保全部 SDK 和 HTTP context 已关闭。如果超过收敛时间仍活跃，请显式删除实例。 |
| 部分多 worker 调用失败 | 这是已知有状态会话兼容边界，不是确定性的伸缩契约。单客户端 smoke 才是权威验收。 |

## 9. 清理

先删除 Deployment：

```bash
agr deployment delete "$MCP_DEPLOYMENT_ID" --region "$AGR_REGION" --wait
agr instance list --tool-id "$MCP_TOOL_ID" --region "$AGR_REGION"
```

删除所有非 `STOPPED` 实例：

```bash
export MCP_INSTANCE_ID='replace-with-non-stopped-instance-id'
agr instance delete "$MCP_INSTANCE_ID" --region "$AGR_REGION" --yes --wait
```

删除 Tool、本地状态，并清除 shell token：

```bash
agr tool delete "$MCP_TOOL_ID" --region "$AGR_REGION" --yes --wait
test -n "$MCP_STATE_DIR" && rm -r -- "$MCP_STATE_DIR"
unset MCP_DEPLOYMENT_TOKEN
```

Tool 删除后可能仍能看到历史 `STOPPED` 实例行。它们不是活跃容量，也不属于清理失败。

## 验收清单

- `uv sync --project client --locked` 成功。
- 客户端测试通过。
- 本地构建镜像的 `/healthz` 返回 200，且通过原生 `smoke`。
- 固定版本 CCR 镜像同时包含 `linux/amd64` 和 `linux/arm64` manifest。
- 新建的上海 Deployment 对未鉴权请求返回 401。
- 一个生产直连原生 smoke 完成。
- 活跃容量经历 `0 → N → 0`，且 `N >= 1`。
- 原实例停止后，`resume` 成功。
- 清理后不存在 Deployment、Tool、非停止实例、token 文件或 affinity 状态文件。

平台层面的独立说明见 [httpbin scaling](../../httpbin/scaling/README_zh.md)、[lifecycle](../../httpbin/lifecycle/README_zh.md) 和 [affinity](../../httpbin/affinity/README_zh.md) 教程。
