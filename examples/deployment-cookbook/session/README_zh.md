# 将 DSH Brain 与 Hands 接入 Agent Runtime 云端 Session 服务

本教程演示如何将运行在 Brain Deployment 中的 DeepSeek Harness（DSH）Agent Loop 及其调用的 Hands Deployment 接入腾讯云 Agent Runtime Session。一次用户会话只对应一个 Session：其中既保存 DSH 的多轮对话，也记录 Brain、Hands Deployment、Hands affinity 和工具执行 Events。同一 Session 会回到原 workspace，新 Session 则获得隔离的 workspace。

随教程提供的 [`SessionPersistence` 插件](./brain/plugin/index.js)负责创建和恢复 Session、写入 Brain 与 Hands Events、恢复 DSH 对话上下文，并将 DSH 工具调用路由到该 Session 对应的 Hands workspace。除了直接使用示例镜像，使用自有 DSH 镜像时也可以集成该插件。

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
export DSH_SESSION_IMAGE='ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:v0.1.1-rc.2-ags.4-session.8'
export HANDS_TOOL_NAME='dsh-hands-session-your-name'
export HANDS_DEPLOYMENT_NAME='dsh-hands-session-your-name'
export HANDS_SESSION_IMAGE='ccr.ccs.tencentyun.com/ags.dev/hands-session:v0.1.0'

export TENCENTCLOUD_SECRET_ID='replace-me'
export TENCENTCLOUD_SECRET_KEY='replace-me'
# 使用临时凭证时设置：
# export TENCENTCLOUD_SESSION_TOKEN='replace-me'

agr status --cloud-endpoint "$SESSION_API_ENDPOINT"
```

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `AGR_REGION` | 是 | Session、Tool 和 Deployment 所在地域，三类资源必须保持一致。 |
| `AGR_DOMAIN` | 是 | Brain Deployment 数据面域名。 |
| `SESSION_API_ENDPOINT` | 是 | Session、Tool 和 Deployment 使用的云 API 域名。 |
| `AGR_ROLE_ARN` | 是 | 创建自定义 Sandbox Tool 使用的 CAM 角色 ARN。 |
| `SESSION_SPACE_NAME` | 创建 SessionSpace 时必填 | 新建 SessionSpace 的名称；复用已有 SessionSpace 时不使用。 |
| `SESSION_USER_ID` | 是 | 示例会话所属的用户标识。创建、查询和删除 Session 时必须保持一致。 |
| `DSH_TOOL_NAME` | 是 | 承载 DSH 镜像的 Sandbox Tool 名称，建议使用唯一名称。 |
| `DSH_DEPLOYMENT_NAME` | 是 | Brain Deployment 名称，建议使用唯一名称。 |
| `DSH_SESSION_IMAGE` | 是 | 已集成 `SessionPersistence` 插件的 DSH 镜像地址。默认使用本教程发布的公开镜像。 |
| `HANDS_TOOL_NAME` | 是 | 承载 workspace 服务镜像的 Sandbox Tool 名称，建议使用唯一名称。 |
| `HANDS_DEPLOYMENT_NAME` | 是 | Hands Deployment 名称，建议使用唯一名称。 |
| `HANDS_SESSION_IMAGE` | 是 | 本教程使用的公开 Hands workspace 服务镜像。 |
| `TENCENTCLOUD_SECRET_ID` | 是 | 容器内插件调用 Session 云 API 使用的腾讯云 SecretId。它独立于本地 `agr` 已配置的凭证。 |
| `TENCENTCLOUD_SECRET_KEY` | 是 | 与 SecretId 配套的 SecretKey。 |
| `TENCENTCLOUD_SESSION_TOKEN` | 使用临时凭证时必填 | 临时凭证对应的 Session Token；使用长期密钥时无需设置。 |

本教程为便于展示完整接入链路，通过 Tool 环境变量向插件提供云 API 凭证。请使用专用子账号或临时凭证，并仅授予本教程所需的 Session 最小权限；不要使用主账号密钥，也不要把密钥写入镜像或版本库。

## 2. 创建或复用 SessionSpace

SessionSpace 是 Session 的隔离边界。已有可用的 SessionSpace 时直接设置：

```bash
export SESSION_SPACE_ID='space-replace-me'
```

否则创建一个专用 SessionSpace：

```bash
agr api call CreateSessionSpace \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --request '{
    "Name":"'$SESSION_SPACE_NAME'",
    "Description":"DSH Brain conversations"
  }' \
  --output json

export SESSION_SPACE_ID='space-copy-from-response'
export SESSION_SPACE_CREATED_BY_TUTORIAL=1
```

## 3. 使用示例镜像或自有 DSH 镜像

直接验证本教程时，使用 `DSH_SESSION_IMAGE` 和 `HANDS_SESSION_IMAGE` 指定的公开示例镜像即可。DSH 镜像已集成本教程的 [`SessionPersistence` 插件](./brain/plugin/index.js)，会保存 DSH 多轮会话，并将模型发起的文件操作路由到 Hands Deployment。

如果使用自己的 DSH 镜像，可以将本教程提供的 `SessionPersistence` 插件集成到镜像中。该插件负责创建和恢复 Session、写入 Events，并使 DSH 从云端 Session 恢复多轮会话上下文；集成后按照后续步骤配置并部署即可。

## 4. 创建 Hands 与 Brain Deployment

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

创建 Hands Deployment。`EXCLUSIVE` affinity 让每个 Session 对应独立 workspace：

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
    --arg hands "$HANDS_DEPLOYMENT_ID" \
    --arg sid "$TENCENTCLOUD_SECRET_ID" \
    --arg skey "$TENCENTCLOUD_SECRET_KEY" \
    --arg token "${TENCENTCLOUD_SESSION_TOKEN:-}" \
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
        {Name:"HANDS_DEPLOYMENT_ID",Value:$hands},
        {Name:"TENCENTCLOUD_SECRET_ID",Value:$sid},
        {Name:"TENCENTCLOUD_SECRET_KEY",Value:$skey},
        {Name:"TENCENTCLOUD_SESSION_TOKEN",Value:$token}
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

创建使用独占 affinity 的 Brain Deployment，使 DSH Web UI 和对话请求持续访问同一个有状态实例。Brain affinity ID 仅用于 Deployment 路由，不写入 Session Metadata：

```bash
agr deployment create \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --deployment-name "$DSH_DEPLOYMENT_NAME" \
  --tool-id "$DSH_TOOL_ID" \
  --scaling-configuration '{"MinInstanceCount":0,"MaxInstanceCount":1,"MaxInstanceRequestConcurrency":100}' \
  --lifecycle-configuration '{"IdleTimeoutSeconds":600,"IdleAction":"PAUSE"}' \
  --affinity-configuration '{"Mode":"EXCLUSIVE","HeaderName":"X-Tencent-Agr-Affinity-Id"}'

export DSH_DEPLOYMENT_ID='dpl-copy-from-response'
```

将新创建的 Brain Deployment ID 写入 Tool 配置。插件会使用该值自动关联之后创建的每个 Session：

```bash
export DSH_CUSTOM_CONFIGURATION="$(
  jq --arg deployment "$DSH_DEPLOYMENT_ID" \
    '.Env += [{Name:"BRAIN_DEPLOYMENT_ID",Value:$deployment}]' \
    <<<"$DSH_CUSTOM_CONFIGURATION"
)"

agr tool update "$DSH_TOOL_ID" \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --custom-configuration "$DSH_CUSTOM_CONFIGURATION" \
  --wait

unset DSH_CUSTOM_CONFIGURATION
```

## 5. 配置 DSH Agent

启动本地代理：

```bash
agr deployment proxy "$DSH_DEPLOYMENT_ID" 18080:3080 \
  --region "$AGR_REGION" \
  --domain "$AGR_DOMAIN" \
  --cloud-endpoint "$SESSION_API_ENDPOINT"
```

复制代理输出中的 affinity ID，供示例客户端访问同一个 DSH 实例：

```bash
export DSH_AFFINITY_ID='copy-from-proxy-output'
```

打开 <http://127.0.0.1:18080>。如果首次打开时出现填写 API Key 的欢迎弹窗，请关闭该弹窗；它配置的是 DSH 内置的 DeepSeek provider，不是本教程使用的 TokenHub provider。

进入左下角的「设置 → 模型」，找到「Tencent Cloud TokenHub」并点击「编辑」，填入 TokenHub API Key 后保存。确认该 provider 显示“API 密钥已配置”，然后新建会话，并确认当前模型为 `tokenhub/deepseek-v4-flash`。此后无论通过 Web UI 还是示例脚本发起会话，插件都会将 Session 和 Events 持久化，并自动记录 Brain Deployment ID。

## 6. 验证 Brain 与 Hands 共享 Session

可以通过 Web UI 手动验证，也可以运行示例脚本自动验证。两种方式都会把 DSH 对话、Brain 与 Hands Deployment ID、Hands affinity 和工具执行 Events 写入同一个 Session。

### 通过 Web UI 验证

在新会话中依次发送：

```text
What is 37 + 58? Use hands_write_file to store the numerical answer in session-value.txt, then answer with only the number.
Use hands_read_file to read session-value.txt. Multiply the stored number by 3, then answer with only the result.
What arithmetic question was contained in my first message? Exclude any answer-format instructions. Return only this JSON object: {"first_question":"<exact first question>","answer":<number>}
```

预期依次得到 `95`、`285`，以及包含第一轮问题和答案的 JSON。第一轮会调用 `hands_write_file`，第二轮会调用 `hands_read_file`，表明同一 Session 使用其中保存的 affinity 回到了原 workspace。

再新建一个 DSH 会话并发送：

```text
Use hands_read_file to read session-value.txt. If it does not exist, answer only MISSING.
```

预期得到 `MISSING`，表明新的 Session 获得了新的 affinity 和独立 workspace。然后执行第 7 节的查询，找到需要查看的 Session，并设置：

```bash
export DSH_SESSION_ID='copy-from-DescribeSessions-response'
```

### 通过示例脚本验证

在另一个终端中导出前述变量，然后运行：

```bash
python3 session_demo.py
```

示例将完成以下操作：

1. 创建 Session，并自动记录 Brain Deployment ID。
2. 连续发起三轮对话，通过 DSH 工具调用 Hands 写入和读取文件。
3. 在同一个 Session 中保存 Hands Deployment ID、affinity 和执行 Events。
4. 创建新的 Session，确认它无法读取原 workspace。
5. 分别通过 Brain、Hands Deployment ID 查询到同一个 Session。

预期输出形态：

```text
Session: <session-id>
  user: What is 37 + 58? Use hands_write_file to store ...
  assistant: 95
  user: Use hands_read_file to read session-value.txt. Multiply ...
  assistant: 285
  user: What arithmetic question was contained in my first message? ...
  assistant: {"first_question":"What is 37 + 58?","answer":95}
Agent Runtime persisted <count> DSH events
Isolated Session: <session-id>
Brain conversation persistence, Hands workspace continuity, and isolation passed
```

复制脚本输出的 Session ID：

```bash
export DSH_SESSION_ID='copy-from-output'
```

## 7. 查看完整 Session

通过 Brain Deployment ID 查询 Session：

```bash
agr api call DescribeSessions \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --request '{
    "SpaceId":"'$SESSION_SPACE_ID'",
    "Filters":[{
      "Name":"metadata:ae.tencentcloud.com/brain-deployment-id",
      "Values":["'$DSH_DEPLOYMENT_ID'"]
    }],
    "Offset":0,
    "Limit":20
  }' \
  --output json
```

查看 Session 中的完整 Events：

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
```

通过 Hands Deployment ID 查询时会找到同一个 Session：

```bash
agr api call DescribeSessions \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --request '{
    "SpaceId":"'$SESSION_SPACE_ID'",
    "Filters":[{
      "Name":"metadata:ae.tencentcloud.com/hands-deployment-id",
      "Values":["'$HANDS_DEPLOYMENT_ID'"]
    }],
    "Offset":0,
    "Limit":20
  }' \
  --output json
```

Session Metadata 同时保存 Brain Deployment ID、Hands Deployment ID 和 Hands affinity。同一 Session 持续使用相同 affinity；新的 Session 获得新的 affinity。`DescribeEvents` 支持通过 `Offset` 和 `Limit` 分页查询，示例脚本会自动检查两类 Events。

插件按 Event 语义填充标准字段：

| DSH Event | Session 标准字段 |
| --- | --- |
| 用户和助手消息 | `Author`、`Content` |
| 文本和推理流式片段 | `Content`、`Partial` |
| 工具调用与结果 | `FunctionCall`、`FunctionResponse` |
| 配置状态变更 | `Actions.StateDelta` |
| 回合结束、中断与错误 | `TurnComplete`、`Interrupted`、`ErrorCode`、`ErrorMessage` |

DSH Events 的原始数据保存在 `Extensions.dshEvent` 中，用于无损恢复；Hands Events 使用 `FunctionCall` 和 `FunctionResponse` 记录文件操作及结果。两类 Events 均属于同一个 Session。

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
  'ae.tencentcloud.com/brain-deployment-id' "$DSH_DEPLOYMENT_ID"
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
- 三轮对话执行超时：检查 DSH Web UI 中的模型配置和 Deployment 运行状态。
