# 在 AGR 上部署 Everything MCP Server

本示例在 AGR 上运行官方 Everything MCP Server，并使用官方 Python MCP SDK 连接。示例客户端会自动携带 AGS token 与 `BEST_EFFORT` affinity。

你将完成：

- 通过生产访问地址运行 `initialize → tools/list → echo`；
- 观察活跃容量从 `0 → N → 0`；
- 空闲 `STOP` 后复用保存的 AGS affinity，同时建立新的 MCP 会话。

示例会在多次运行之间保留 AGS affinity，并在实例停止后创建新的 MCP 会话。

## 前置条件

- 已安装 **v0.6.6 或更高版本**的 `agr`。如果尚未配置 CLI，请先按[AGR CLI 官方 GitHub 凭证配置说明](https://github.com/TencentCloudAgentRuntime/ags-cli/blob/main/README-zh.md#初始化-cli-凭证)完成初始化，再运行 `agr status` 和 `agr doctor`。
- 已安装 [`uv`](https://docs.astral.sh/uv/)。
- 按官方[自定义沙箱角色与权限指南](https://cloud.tencent.com/document/product/1814/129691)创建 Agent Runtime CAM 角色，并向 CLI 使用的身份授予该角色的 `cam:PassRole` 权限。下方已发布镜像是公共镜像；只有改用自己私有 CCR 或 TCR 仓库中的镜像时，才需要额外授予仓库拉取权限。
- CLI 使用的身份可以创建和删除 Sandbox Tool 与 Deployment、查询和删除 Instance，并能获取 Deployment token。

使用以下已发布镜像：

```text
ccr.ccs.tencentyun.com/ags.dev/mcp-everything:2026.8.31-ags.1
```

可以直接使用该已发布的示例镜像。如需将镜像构建并推送到自己的仓库，请参考 [dockerfiles](./dockerfiles/README_zh.md)。

请从当前 `simple` 目录执行全部命令。从命令输出中复制真实资源 ID；第 4 步会把 Deployment token 直接载入当前 shell。示例资源 ID 均为占位符。

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
```

`MCP_STATE_DIR` 保存示例客户端使用的 AGS affinity。

## 2. 创建 Sandbox Tool

端口 `3001` 提供 MCP 服务，端口 `3000` 提供就绪检查。下面的命令使用已发布的示例镜像。如果已构建自有镜像，请将完整镜像地址粘贴到 `Image`；CCR 个人版的 `ImageRegistryType` 使用 `personal`，TCR 企业版使用 `enterprise`。

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

成功输出包含真实 Tool ID。复制并设置：

```bash
export MCP_TOOL_ID='sdt-replace-me'
```

## 3. 创建 Deployment

官方 SDK 会保持一个 GET event stream，同时发送 POST 和 DELETE 请求，因此本示例把单实例请求并发设为 `2`。

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

将 Deployment token 直接获取到当前 shell：

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

示例客户端从 `MCP_DEPLOYMENT_TOKEN` 读取 Token，并把 AGS affinity 保存到 `MCP_AFFINITY_STATE`。

## 5. 测试生产访问地址

客户端使用官方 Python MCP SDK，并读取上面配置的 Token 与 affinity。

```bash
uv run --project client --locked python client/mcp_client.py smoke \
  --url "$MCP_DEPLOYMENT_URL" \
  --transport direct \
  --state-file "$MCP_AFFINITY_STATE"
```

命令应完成 `initialize`、`tools/list` 和 `echo`。使用这个已发布镜像时，预期看到服务端名称 `mcp-servers/everything`、版本 `2.0.0`、协议 `2025-11-25` 和 13 个工具。客户端会检查 `echo` 与 `trigger-long-running-operation` 是否可用，并确认 `echo` 结果为 `Echo: ags-cookbook`。

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

## 7. 用新 MCP 会话验证 `BEST_EFFORT`

smoke 使用的实例变为 `STOPPED` 后，把已保存的 AGS affinity 用于一个全新的官方 MCP 传输和会话：

```bash
uv run --project client --locked python client/mcp_client.py resume \
  --url "$MCP_DEPLOYMENT_URL" \
  --transport direct \
  --state-file "$MCP_AFFINITY_STATE"
```

该命令应再次完成 `initialize`、`tools/list` 和 `echo`。Affinity 指纹可能保持不变，也可能变化；如果变化，客户端会保存新值。

## 8. 清理

删除 Deployment，并列出它的实例：

```bash
agr deployment delete "$MCP_DEPLOYMENT_ID" --region "$AGR_REGION" --wait
agr instance list --tool-id "$MCP_TOOL_ID" --region "$AGR_REGION"
```

复制每个当前处于 `RUNNING` 或 `PAUSED` 状态的实例 ID，并逐个执行删除命令：

```bash
export MCP_INSTANCE_ID='replace-with-instance-id'
agr instance delete "$MCP_INSTANCE_ID" --region "$AGR_REGION" --yes --wait
```

删除 Tool、本地状态和 shell token：

```bash
agr tool delete "$MCP_TOOL_ID" --region "$AGR_REGION" --yes --wait
rm -r -- "$MCP_STATE_DIR"
unset MCP_DEPLOYMENT_TOKEN
```

## 检查清单

- `uv sync --project client --locked` 成功。
- 一个生产直连原生 smoke 完成。
- 活跃容量经历 `0 → N → 0`，且 `N >= 1`。
- 原实例停止后，`resume` 成功。
- 清理步骤会删除 Deployment、当前实例、Tool 与 affinity 状态目录，并清除 `MCP_DEPLOYMENT_TOKEN`。

平台层面的独立说明见 [httpbin scaling](../../httpbin/scaling/README_zh.md)、[lifecycle](../../httpbin/lifecycle/README_zh.md) 和 [affinity](../../httpbin/affinity/README_zh.md) 教程。
