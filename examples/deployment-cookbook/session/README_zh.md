# 将 DSH Brain 与 Hands 接入 Agent Runtime 云端 Session 服务

本教程通过一个可运行示例，演示如何将运行 DSH agent loop 的 DSH Deployment（Brain 角色）及其调用的 Workspace Deployment（Hands 角色）接入腾讯云 Agent Runtime Session。示例使用 Session 保存对话 Events 以及关联的 Deployment 和 affinity 信息，并据此回到原 Hands workspace。

本文中的 Brain 和 Hands 表示 DSH 组件承担的角色，底层都使用 Agent Runtime Deployment：Brain 运行 agent loop，Hands 承载 workspace 文件操作。

本教程是展示 Agent Runtime Session 与 Deployment 关联方式的独立集成示例，不替代 [`deepseek-harness/brain-hands`](../deepseek-harness/brain-hands/README_zh.md) 中面向完整应用的部署架构。

本文固定使用以下术语：

- **DSH conversation**：用户在 DSH 中发起的一段对话。
- **Agent Runtime Session**：云端保存该对话 Events 和 Deployment 关联信息的 Session。本示例让它与 DSH conversation 使用相同 ID。
- **Deployment affinity ID**：Deployment 数据面路由标识。Hands affinity 保存在 Agent Runtime Session Metadata 中，用于后续请求回到原 workspace。

随教程提供的 [`SessionPersistence` 插件](./brain/plugin/index.js)用于展示 DSH 与 Agent Runtime Session 的接入方式。你可以直接使用示例镜像完成验证；如果使用自己的 DSH 镜像，也可以参考该插件集成 Session 创建、Events 写入以及 Deployment 路由信息保存。

> 该插件是面向正常写入流程的集成示例，并非可直接用于生产环境的完整 DSH PersistenceBackend。它使用稳定的 Event ID 支持幂等重试，但不提供 DSH `appendBatch()` 要求的事务级批次原子性；写入被中断时可能留下空 Session 或部分 Events。

## 前置条件

- 已安装 `agr` v0.6.6 或更高版本，并配置腾讯云凭证。
- 已准备创建自定义 Sandbox Tool 所需的 CAM 角色 ARN。
- 当前账号能够管理 SessionSpace、Session、Sandbox Tool 和 Deployment，并能追加和查询 Events。
- 已准备 TokenHub API Key。本示例镜像已预置 TokenHub provider 和 `deepseek-v4-flash` 模型配置。
- 使用 Python 3.10 或更高版本，并安装 `jq`。

## 1. 配置环境

以下以上海地域为例：

```bash
export AGR_REGION=ap-shanghai
export AGR_DOMAIN=tencentags.com
export SESSION_API_ENDPOINT=ags.tencentcloudapi.com
```

这三个参数分别指定部署地域、Deployment 数据面域名和 Agent Runtime 云 API 域名。切换地域时修改 `AGR_REGION`。

继续设置资源名、镜像和凭证：

```bash
export AGR_ROLE_ARN='qcs::cam::uin/100000000001:roleName/replace-me'
export SESSION_SPACE_NAME='dsh-brain-session-your-name'
export SESSION_USER_ID='dsh-demo-user'
export DSH_TOOL_NAME='dsh-brain-session-your-name'
export DSH_DEPLOYMENT_NAME='dsh-brain-session-your-name'
export DSH_SESSION_IMAGE='ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:v0.1.1-rc.2-ags.4-session.9'
export HANDS_TOOL_NAME='dsh-hands-session-your-name'
export HANDS_DEPLOYMENT_NAME='dsh-hands-session-your-name'
export HANDS_SESSION_IMAGE='ccr.ccs.tencentyun.com/ags.dev/hands-session:v0.1.0'

export TENCENTCLOUD_SECRET_ID='replace-me'
export TENCENTCLOUD_SECRET_KEY='replace-me'
export TOKENHUB_API_KEY='replace-me'
# 使用临时凭证时设置：
# export TENCENTCLOUD_SESSION_TOKEN='replace-me'

agr status --cloud-endpoint "$SESSION_API_ENDPOINT"
```

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `AGR_REGION` | 是 | Session、Tool 和 Deployment 所在地域，三类资源必须保持一致。 |
| `AGR_DOMAIN` | 是 | Deployment 数据面域名。 |
| `SESSION_API_ENDPOINT` | 是 | Session、Tool 和 Deployment 使用的云 API 域名。 |
| `AGR_ROLE_ARN` | 是 | 创建自定义 Sandbox Tool 使用的 CAM 角色 ARN。 |
| `SESSION_SPACE_NAME` | 创建 SessionSpace 时必填 | 新建 SessionSpace 的名称；复用已有 SessionSpace 时不使用。 |
| `SESSION_USER_ID` | 是 | 示例会话所属的用户标识。创建、查询和删除 Session 时必须保持一致。 |
| `DSH_TOOL_NAME` | 是 | 承载 DSH 镜像的 Sandbox Tool 名称，建议使用唯一名称。 |
| `DSH_DEPLOYMENT_NAME` | 是 | 运行 DSH agent loop 的 Deployment 名称，建议使用唯一名称。 |
| `DSH_SESSION_IMAGE` | 是 | 已集成 Session 示例插件的 DSH 镜像地址。默认使用本教程发布的公开镜像。 |
| `HANDS_TOOL_NAME` | 是 | 承载 workspace 服务镜像的 Sandbox Tool 名称，建议使用唯一名称。 |
| `HANDS_DEPLOYMENT_NAME` | 是 | 承载 Hands workspace 的 Deployment 名称，建议使用唯一名称。 |
| `HANDS_SESSION_IMAGE` | 是 | 本教程使用的公开 Hands workspace 服务镜像。 |
| `TENCENTCLOUD_SECRET_ID` | 是 | 容器内插件调用 Session 云 API 使用的腾讯云 SecretId。它独立于本地 `agr` 已配置的凭证。 |
| `TENCENTCLOUD_SECRET_KEY` | 是 | 与 SecretId 配套的 SecretKey。 |
| `TENCENTCLOUD_SESSION_TOKEN` | 使用临时凭证时必填 | 临时凭证对应的 Session Token；使用长期密钥时无需设置。 |
| `TOKENHUB_API_KEY` | 是 | DSH 调用示例模型使用的 TokenHub API Key。 |

本教程为便于展示完整接入链路，通过 Tool 环境变量向插件提供云 API 凭证。请使用专用子账号或临时凭证，并仅授予本教程所需的 Session 最小权限；不要使用主账号密钥，也不要把密钥写入镜像或版本库。

## 2. 创建或复用 SessionSpace

SessionSpace 是 Session 的隔离边界。已有可用的 SessionSpace 时直接设置：

```bash
export SESSION_SPACE_ID='space-replace-me'
```

否则创建一个专用 SessionSpace：

```bash
SESSION_SPACE_ID="$(
  agr api call CreateSessionSpace \
    --region "$AGR_REGION" \
    --cloud-endpoint "$SESSION_API_ENDPOINT" \
    --request '{
      "Name":"'$SESSION_SPACE_NAME'",
      "Description":"DSH Brain conversations"
    }' \
    --output json \
    --jq '.Data.Response.Response.SessionSpace.SpaceId'
)"
export SESSION_SPACE_ID
export SESSION_SPACE_CREATED_BY_TUTORIAL=1
echo "$SESSION_SPACE_ID"
```

## 3. 使用示例镜像或自有 DSH 镜像

直接验证本教程时，使用 `DSH_SESSION_IMAGE` 和 `HANDS_SESSION_IMAGE` 指定的公开示例镜像即可。DSH 镜像已集成本教程的 [`SessionPersistence` 示例插件](./brain/plugin/index.js)，用于把 DSH Events 和 Deployment 路由信息写入 Agent Runtime Session。

如果使用自己的 DSH 镜像，可以参考该插件对接 DSH 会话生命周期，在镜像中实现 Session 创建、Events 写入和路由信息保存。用于生产环境前，需要根据业务的一致性要求补充异常恢复机制，并满足 DSH PersistenceBackend 的完整接口契约。

## 4. 创建 Workspace 与 DSH Deployment

先创建承载 workspace 服务的 Hands Tool：

```bash
agr tool create \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --tool-name "$HANDS_TOOL_NAME" \
  --tool-type custom \
  --persistent \
  --role-arn "$AGR_ROLE_ARN" \
  --network-configuration '{"NetworkMode":"PUBLIC"}' \
  --custom-configuration '{
    "Image":"'$HANDS_SESSION_IMAGE'",
    "ImageRegistryType":"personal",
    "Command":["python3","/opt/hands/workspace_server.py"],
    "Args":[],
    "Env":[],
    "Ports":[{"Name":"http","Port":8080,"Protocol":"TCP"}],
    "Resources":{"CPU":"1","Memory":"1Gi"},
    "Probe":{"HttpGet":{"Path":"/health","Port":8080,"Scheme":"HTTP"},"ReadyTimeoutMs":30000,"ProbeTimeoutMs":3000,"ProbePeriodMs":3000,"SuccessThreshold":1,"FailureThreshold":10}
  }' \
  --wait

export HANDS_TOOL_ID='sdt-copy-from-response'
```

创建承担 Hands 角色的 Workspace Deployment。示例为每个 Session 保存不同的 `EXCLUSIVE` affinity，使其后续请求回到各自的 workspace；这不是用户或租户安全隔离机制：

```bash
agr deployment create \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --deployment-name "$HANDS_DEPLOYMENT_NAME" \
  --tool-id "$HANDS_TOOL_ID" \
  --scaling-configuration '{"MinInstanceCount":0,"MaxInstanceCount":2,"MaxInstanceRequestConcurrency":1}' \
  --lifecycle-configuration '{"IdleTimeoutSeconds":600,"IdleAction":"PAUSE"}' \
  --affinity-configuration '{"Mode":"EXCLUSIVE","HeaderName":"X-Tencent-Agr-Affinity-Id"}'

export HANDS_DEPLOYMENT_ID='dpl-copy-from-response'
```

创建用于运行 DSH 的 Sandbox Tool：

```bash
export DSH_CUSTOM_CONFIGURATION="$(
  jq -n \
    --arg image "$DSH_SESSION_IMAGE" \
    --arg region "$AGR_REGION" \
    --arg domain "$AGR_DOMAIN" \
    --arg endpoint "$SESSION_API_ENDPOINT" \
    --arg space "$SESSION_SPACE_ID" \
    --arg user "$SESSION_USER_ID" \
    --arg deploymentName "$DSH_DEPLOYMENT_NAME" \
    --arg hands "$HANDS_DEPLOYMENT_ID" \
    --arg sid "$TENCENTCLOUD_SECRET_ID" \
    --arg skey "$TENCENTCLOUD_SECRET_KEY" \
    --arg token "${TENCENTCLOUD_SESSION_TOKEN:-}" \
    --arg tokenhub "$TOKENHUB_API_KEY" \
    '{
      Image:$image,
      ImageRegistryType:"personal",
      Command:["/opt/dsh/entrypoint.sh"],
      Args:[],
      Env:[
        {Name:"AGR_REGION",Value:$region},
        {Name:"AGR_DOMAIN",Value:$domain},
        {Name:"SESSION_API_ENDPOINT",Value:$endpoint},
        {Name:"SESSION_SPACE_ID",Value:$space},
        {Name:"SESSION_USER_ID",Value:$user},
        {Name:"DSH_DEPLOYMENT_NAME",Value:$deploymentName},
        {Name:"HANDS_DEPLOYMENT_ID",Value:$hands},
        {Name:"TENCENTCLOUD_SECRET_ID",Value:$sid},
        {Name:"TENCENTCLOUD_SECRET_KEY",Value:$skey},
        {Name:"TENCENTCLOUD_SESSION_TOKEN",Value:$token},
        {Name:"TOKENHUB_API_KEY",Value:$tokenhub}
      ],
      Ports:[{Name:"web",Port:3080,Protocol:"TCP"}],
      Resources:{CPU:"2",Memory:"4Gi"},
      Probe:{HttpGet:{Path:"/",Port:3080,Scheme:"HTTP"},ReadyTimeoutMs:30000,ProbeTimeoutMs:3000,ProbePeriodMs:3000,SuccessThreshold:1,FailureThreshold:10}
    }'
)"

agr tool create \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --tool-name "$DSH_TOOL_NAME" \
  --tool-type custom \
  --persistent \
  --role-arn "$AGR_ROLE_ARN" \
  --network-configuration '{"NetworkMode":"PUBLIC"}' \
  --custom-configuration "$DSH_CUSTOM_CONFIGURATION" \
  --wait

export DSH_TOOL_ID='sdt-copy-from-response'
```

创建承担 Brain 角色的无状态 DSH Deployment。它不使用 affinity；插件会根据已配置的 Deployment 名称查询其 ID，并写入 Session Metadata：

```bash
agr deployment create \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --deployment-name "$DSH_DEPLOYMENT_NAME" \
  --tool-id "$DSH_TOOL_ID" \
  --scaling-configuration '{"MinInstanceCount":1,"MaxInstanceCount":4,"MaxInstanceRequestConcurrency":100}' \
  --lifecycle-configuration '{"IdleTimeoutSeconds":600,"IdleAction":"STOP"}'

export DSH_DEPLOYMENT_ID='dpl-copy-from-response'
```

DSH conversation 状态由 Agent Runtime Session 保存，DSH Deployment 不依赖 Brain affinity。

## 5. 配置 DSH Agent

启动本地代理：

```bash
agr deployment proxy "$DSH_DEPLOYMENT_ID" 18080:3080 \
  --region "$AGR_REGION" \
  --domain "$AGR_DOMAIN" \
  --cloud-endpoint "$SESSION_API_ENDPOINT"
```

打开 <http://127.0.0.1:18080>，新建会话，并确认当前模型为 `tokenhub/deepseek-v4-flash`。TokenHub API Key 已通过 Tool 环境变量提供，因此所有 Brain 副本使用相同模型配置。此后无论通过 Web UI 还是示例脚本发起 DSH conversation，插件都会创建同 ID 的 Agent Runtime Session、写入 Events，并自动记录 Brain Deployment ID。

## 6. 验证 Session 关联并恢复 Hands workspace

可以通过 Web UI 手动操作，也可以运行示例脚本自动验证。验证重点是从 Session 取得 Deployment 和 affinity 信息，并使用这些信息回到原 Hands workspace。

### 通过 Web UI 触发，通过命令行验证

Web UI 用于创建 DSH conversation 并触发 Hands 工具调用；随后的命令行操作模拟客户应用根据 Agent Runtime Session 恢复 Deployment 路由信息。

#### 在 Web UI 中触发任务

在新会话中发送：

```text
What is 37 + 58? Use hands_write_file to store the numerical answer in session-value.txt, then answer with only the number.
```

预期得到 `95`，且轨迹中包含 `hands_write_file` 调用。该调用会在 Hands workspace 中创建 `session-value.txt`，并将 DSH、Workspace Deployment ID、Hands affinity 和相关 Events 写入对应的 Agent Runtime Session。

#### 在终端中验证 Session 关联

发送消息后立即在终端中通过 DSH Deployment ID 和示例用户查询最新 Session：

```bash
DSH_SESSION_ID="$(
  agr api call DescribeSessions \
    --region "$AGR_REGION" \
    --cloud-endpoint "$SESSION_API_ENDPOINT" \
    --request '{
      "SpaceId":"'$SESSION_SPACE_ID'",
      "UserIds":["'$SESSION_USER_ID'"],
      "Filters":[{
        "Name":"metadata:example.com/brain-deployment-id",
        "Values":["'$DSH_DEPLOYMENT_ID'"]
      }],
      "Offset":0,
      "Limit":100
    }' \
    --output json \
    --jq '.Data.Response.Response.Sessions | max_by(.CreateTime) | .SessionId'
)"
export DSH_SESSION_ID
echo "$DSH_SESSION_ID"
```

读取该 Session，并从 Metadata 中取得 Workspace Deployment ID 和 Hands affinity：

```bash
DSH_SESSION_JSON="$(
  agr api call DescribeSession \
    --region "$AGR_REGION" \
    --cloud-endpoint "$SESSION_API_ENDPOINT" \
    --request '{
      "SpaceId":"'$SESSION_SPACE_ID'",
      "UserId":"'$SESSION_USER_ID'",
      "SessionId":"'$DSH_SESSION_ID'"
    }' \
    --output json
)"

RESTORED_HANDS_DEPLOYMENT_ID="$(
  jq -r '.Data.Response.Response.Session.Metadata[]
    | select(.Name == "example.com/hands-deployment-id")
    | .Value' <<<"$DSH_SESSION_JSON"
)"
RESTORED_HANDS_AFFINITY_ID="$(
  jq -r '.Data.Response.Response.Session.Metadata[]
    | select(.Name == "example.com/hands-affinity-id")
    | .Value' <<<"$DSH_SESSION_JSON"
)"
export RESTORED_HANDS_DEPLOYMENT_ID RESTORED_HANDS_AFFINITY_ID
```

确认两个 Deployment 均可查询：

```bash
agr deployment get "$DSH_DEPLOYMENT_ID" \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT"

agr deployment get "$RESTORED_HANDS_DEPLOYMENT_ID" \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT"
```

使用从 Session 读取的 Workspace Deployment ID 和 affinity 直接请求 Workspace Deployment，读取原文件：

```bash
RESTORED_HANDS_TOKEN="$(
  agr api call AcquireDeploymentToken \
    --region "$AGR_REGION" \
    --cloud-endpoint "$SESSION_API_ENDPOINT" \
    --request '{"DeploymentId":"'$RESTORED_HANDS_DEPLOYMENT_ID'"}' \
    --output json \
    --jq '.Data.Response.Response.Token'
)"

curl --fail-with-body \
  -H "X-Access-Token: $RESTORED_HANDS_TOKEN" \
  -H "X-Tencent-Agr-Affinity-Id: $RESTORED_HANDS_AFFINITY_ID" \
  "https://8080-$RESTORED_HANDS_DEPLOYMENT_ID.$AGR_REGION.agents.$AGR_DOMAIN/files/read?path=session-value.txt"
```

预期返回 `exists: true` 和 `content: "95"`。这里的直接请求由命令行发起，不是 Web UI 调用；它模拟客户应用使用 Session 中保存的路由信息，并证明请求能够回到原 Hands workspace。

最后查看本次交互的 Events，并通过 Workspace Deployment ID 反向确认同一个 Session：

```bash
agr api call DescribeEvents \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --request '{
    "SpaceId":"'$SESSION_SPACE_ID'",
    "UserId":"'$SESSION_USER_ID'",
    "SessionId":"'$DSH_SESSION_ID'",
    "Offset":0,
    "Limit":100
  }' \
  --output json

agr api call DescribeSessions \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --request '{
    "SpaceId":"'$SESSION_SPACE_ID'",
    "Filters":[{
      "Name":"metadata:example.com/hands-deployment-id",
      "Values":["'$RESTORED_HANDS_DEPLOYMENT_ID'"]
    }],
    "Offset":0,
    "Limit":20
  }' \
  --output json
```

### 通过示例脚本验证

脚本验证不依赖 Web UI 或本地代理。使用第 1～4 节创建资源时得到的实际值，设置以下变量：

```bash
export AGR_REGION='ap-shanghai'
export AGR_DOMAIN='tencentags.com'
export SESSION_API_ENDPOINT='ags.tencentcloudapi.com'
export SESSION_SPACE_ID='space-copy-from-response'
export SESSION_USER_ID='dsh-demo-user'
export DSH_DEPLOYMENT_ID='dpl-copy-from-dsh-response'
export HANDS_DEPLOYMENT_ID='dpl-copy-from-workspace-response'
```

其中 `AGR_REGION`、`AGR_DOMAIN` 和 `SESSION_API_ENDPOINT` 应与创建资源时的配置保持一致。`agr` 还需要使用本地已配置的腾讯云凭证调用控制面 API。设置完成后，在 `examples/deployment-cookbook/session` 目录运行：

```bash
python3 session_demo.py
```

示例将完成以下操作：

1. 通过 DSH 创建 Session，并调用 Hands 写入文件。
2. 确认 Session Metadata 中记录了 Brain、Hands Deployment ID 和 Hands affinity。
3. 分别通过 DSH、Workspace Deployment ID 反向查询到同一个 Session。
4. 查询两个 Deployment，确认 Metadata 中记录的资源存在。
5. 使用从 Session 读取的 Hands Deployment ID 和 affinity 直接读取文件，确认请求回到原 workspace。
6. 检查 Session 中真实的 `FunctionCall` 和 `FunctionResponse` Events。

预期输出形态：

```text
Session: <session-id>
  user: What is 37 + 58? Use hands_write_file to store ...
  assistant: 95
Agent Runtime persisted <count> DSH events
Hands Deployment: <deployment-id>
Restored session metadata routed the request to the original Hands workspace
```

## 7. 理解验证结果

本示例使用 `example.com/*` 作为可自定义的 Metadata key。Session 保存 Brain Deployment ID、Hands Deployment ID 和 Hands affinity；调用方读取 Hands Deployment ID 和 affinity 后，将它们用于后续 Hands 请求，即可路由回该 affinity 对应的 workspace。Session 负责保存关联信息，实际路由由 Deployment affinity 完成。

Hands workspace 文件保存在 Hands Sandbox 中，不存储在 Agent Runtime Session。`PAUSE` 可以保留该 Sandbox 的文件系统；如果 Sandbox 被删除、执行 `STOP` 后无法恢复或底层文件系统丢失，Session 中的 Metadata 只能恢复路由信息，不能重建 workspace 文件。

插件按 Event 语义填充标准字段：

| DSH Event | Session 标准字段 |
| --- | --- |
| 用户和助手消息 | `Author`、`Content` |
| 文本和推理流式片段 | `Content`、`Partial` |
| 工具调用与结果 | `FunctionCall`、`FunctionResponse` |
| 配置状态变更 | `Actions.StateDelta` |
| 回合结束、中断与错误 | `TurnComplete`、`Interrupted`、`ErrorCode`、`ErrorMessage` |

成功写入的 DSH Events 会在 `Extensions.dshEvent` 中保留原始数据；Hands Events 使用 `FunctionCall` 和 `FunctionResponse` 记录文件操作及结果。两类 Events 均属于同一个 Session。

## 8. 清理

```bash
delete_sessions_for_deployment() {
  metadata_name="$1"
  deployment_id="$2"
  agr api call DescribeSessions \
    --region "$AGR_REGION" \
    --cloud-endpoint "$SESSION_API_ENDPOINT" \
    --request '{"SpaceId":"'$SESSION_SPACE_ID'","Filters":[{"Name":"metadata:'"$metadata_name"'","Values":["'"$deployment_id"'"]}],"Offset":0,"Limit":100}' \
    --output json \
    --jq '.Data.Response.Response.Sessions[].SessionId' | while read -r session_id; do
      agr api call DeleteSession \
        --region "$AGR_REGION" \
        --cloud-endpoint "$SESSION_API_ENDPOINT" \
        --request '{"SpaceId":"'$SESSION_SPACE_ID'","UserId":"'$SESSION_USER_ID'","SessionId":"'"$session_id"'"}' \
        --output json
    done
}

delete_sessions_for_deployment \
  'example.com/brain-deployment-id' "$DSH_DEPLOYMENT_ID"
agr deployment delete "$DSH_DEPLOYMENT_ID" \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --wait

agr deployment delete "$HANDS_DEPLOYMENT_ID" \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --wait

for tool_id in "$DSH_TOOL_ID" "$HANDS_TOOL_ID"; do
  agr instance list \
    --tool-id "$tool_id" \
    --region "$AGR_REGION" \
    --cloud-endpoint "$SESSION_API_ENDPOINT" \
    --output json \
    --jq '.Data.Items[].InstanceId' | while read -r instance_id; do
      agr instance delete "$instance_id" \
        --region "$AGR_REGION" \
        --cloud-endpoint "$SESSION_API_ENDPOINT" \
        --yes \
        --wait
    done
done

agr tool delete "$DSH_TOOL_ID" \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --yes \
  --wait

agr tool delete "$HANDS_TOOL_ID" \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --yes \
  --wait
```

只有 SessionSpace 是本教程创建的，才删除它：

```bash
if [ "${SESSION_SPACE_CREATED_BY_TUTORIAL:-0}" = 1 ]; then
  agr api call DeleteSessionSpace \
    --region "$AGR_REGION" \
    --cloud-endpoint "$SESSION_API_ENDPOINT" \
    --request '{"SpaceId":"'$SESSION_SPACE_ID'"}' \
    --output json
fi
```

## 常见问题

- Session 写入时报凭证错误：确认 Tool 中的 `TENCENTCLOUD_*` 环境变量正确；使用临时凭证时必须同时提供 Session Token。
- SessionSpace 不存在：确认 `SESSION_SPACE_ID` 与 `AGR_REGION` 属于同一账号和地域。
- Deployment 或 Session API 无法访问：检查 `AGR_REGION`、`AGR_DOMAIN` 和 `SESSION_API_ENDPOINT`；同时确认 Tool 使用 `PUBLIC` 网络模式。
- 模型调用鉴权失败：确认 TokenHub API Key 有效，并具有所选模型的访问权限。
- 找不到关联 Session：确认 `session_demo.py` 已成功执行，并检查 Session Metadata 中记录的 Brain Deployment ID。
- DSH 对话执行超时：检查 DSH Web UI 中的模型配置和 Deployment 运行状态。
