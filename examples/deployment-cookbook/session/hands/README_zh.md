# 将 Hands Deployment 会话接入 Agent Runtime 云端 Session 服务

本教程展示应用如何将 Hands Deployment 的会话路由信息保存到 Agent Runtime Session。示例先创建 Session A 并写入文件，再仅通过 Session A ID 路由回原 workspace；随后创建 Session B，验证不同 Session 使用相互隔离的 workspace。示例客户端在调用 Hands 前从 Session Metadata 读取 Deployment ID 和 affinity，并在调用后保存最新 affinity 和执行 Events。workspace 数据仍保存在 Hands 实例中。

## 前置条件

- 已安装 `agr` v0.6.6 或更高版本，并配置腾讯云凭证。
- 已准备创建自定义 Sandbox Tool 所需的 CAM 角色 ARN。
- 账号可以管理 SessionSpace、Session、Events、Sandbox Tool 和 Deployment。
- 已安装 Python 3.10 或更高版本。

## 1. 配置环境

以下示例使用上海地域；部署到其他地域时修改 `AGR_REGION`：

```bash
export AGR_REGION=ap-shanghai
export AGR_DOMAIN=tencentags.com
export SESSION_API_ENDPOINT=ags.tencentcloudapi.com

export AGR_ROLE_ARN='qcs::cam::uin/100000000001:roleName/replace-me'
export SESSION_SPACE_NAME='hands-session-your-name'
export SESSION_USER_ID='hands-demo-user'
export HANDS_TOOL_NAME='hands-session-your-name'
export HANDS_DEPLOYMENT_NAME='hands-session-your-name'
export HANDS_SESSION_IMAGE='ccr.ccs.tencentyun.com/ags.dev/hands-session:v0.1.0'

agr status --cloud-endpoint "$SESSION_API_ENDPOINT"
```

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `AGR_REGION` | 是 | Session、Tool 和 Deployment 所在地域，三类资源必须保持一致。 |
| `AGR_DOMAIN` | 是 | Hands Deployment 数据面域名。 |
| `SESSION_API_ENDPOINT` | 是 | Session、Tool 和 Deployment 使用的云 API 域名。 |
| `AGR_ROLE_ARN` | 是 | 创建自定义 Sandbox Tool 使用的 CAM 角色 ARN。 |
| `SESSION_SPACE_NAME` | 创建 SessionSpace 时必填 | 新建 SessionSpace 的名称；复用已有 SessionSpace 时不使用。 |
| `SESSION_USER_ID` | 是 | 两个示例 Session 所属的用户标识，创建、恢复和查询时必须一致。 |
| `HANDS_TOOL_NAME` | 是 | 承载 workspace 服务镜像的 Sandbox Tool 名称，建议使用唯一名称。 |
| `HANDS_DEPLOYMENT_NAME` | 是 | Hands Deployment 名称，建议使用唯一名称。 |
| `HANDS_SESSION_IMAGE` | 是 | 本教程使用的 workspace 服务镜像。默认镜像已发布到 `ags.dev`。 |

执行后续步骤时还会设置以下资源 ID：

| 参数 | 来源 | 用途 |
| --- | --- | --- |
| `SESSION_SPACE_ID` | 创建或选择 SessionSpace | 指定 Session 的隔离空间。 |
| `HANDS_TOOL_ID` | 创建 Tool 的输出 | 创建 Hands Deployment。 |
| `HANDS_DEPLOYMENT_ID` | 创建 Deployment 的输出 | 首次调用 Hands，并写入 Session Metadata。 |
| `HANDS_SESSION_A_ID` | `hands_demo.py start` 的输出 | 恢复 Session A 的 workspace。 |
| `HANDS_SESSION_B_ID` | `hands_demo.py isolate` 的输出 | 查询和清理隔离验证产生的 Session B。 |

## 2. 创建或复用 SessionSpace

已有 SessionSpace 时直接设置：

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
    "Description":"Hands workspace sessions"
  }' \
  --output json

export SESSION_SPACE_ID='space-copy-from-response'
export SESSION_SPACE_CREATED_BY_TUTORIAL=1
```

## 3. 创建 Hands Tool 和 Deployment

示例镜像提供一个最小化 workspace 服务，可以在实例本地写入和读取文件：

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
    "Resources":{"CPU":"200m","Memory":"500Mi"},
    "Probe":{"HttpGet":{"Path":"/health","Port":8080,"Scheme":"HTTP"},"ReadyTimeoutMs":30000,"ProbeTimeoutMs":1000,"ProbePeriodMs":3000,"SuccessThreshold":1,"FailureThreshold":10}
  }' \
  --wait

export HANDS_TOOL_ID='sdt-copy-from-response'
```

创建最多容纳两个独占 workspace 的 Hands Deployment：

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

`EXCLUSIVE` 为每个 affinity 分配独占实例，从而隔离不同 Session 的 workspace。示例客户端将 Hands Deployment ID 和返回的 affinity 分别保存到 `ae.tencentcloud.com/hands-deployment-id` 和 `ae.tencentcloud.com/hands-affinity-id`。

## 4. Session A：创建 workspace

运行第一段客户端进程：

```bash
python3 hands_demo.py start
```

该进程会：

1. 创建 Session A，并记录 Hands Deployment ID。
2. 首次调用 Hands Deployment，在 workspace 中创建 `session-value.txt`。
3. 将响应中的 affinity 写入 Session A。
4. 将文件写入调用和结果追加到 Session Events。

复制输出中的 Session ID：

```bash
export HANDS_SESSION_A_ID='copy-from-output'
```

## 5. Session A：从新进程恢复 workspace

再次运行脚本时只传入 Session A ID，不传入 Hands Deployment ID 或 affinity：

```bash
env -u HANDS_DEPLOYMENT_ID python3 hands_demo.py resume \
  --session-id "$HANDS_SESSION_A_ID"
```

脚本从 Session Metadata 恢复 Hands Deployment ID 和 affinity，读取第一阶段写入的 `95`，并将本次读取记录到同一个 Session。输出 `Workspace recovery passed` 表示恢复成功。

## 6. Session B：验证独立 workspace

创建新的 Session B，并以不带 affinity 的首次请求访问同一个 Hands Deployment：

```bash
python3 hands_demo.py isolate \
  --reference-session-id "$HANDS_SESSION_A_ID"
```

复制输出中的 Session B ID：

```bash
export HANDS_SESSION_B_ID='copy-from-output'
```

程序会确认 Session B 获得不同的 affinity，并且它的 workspace 中不存在 Session A 创建的文件。输出 `Workspace isolation passed` 表示隔离验证成功。

最终关系如下：

```text
Hands Deployment
├── Session A → affinity A → workspace A（存在 session-value.txt）
└── Session B → affinity B → workspace B（不存在 session-value.txt）
```

## 7. 查看关联 Session 和 Events

通过 Hands Deployment ID 查询两个 Session：

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

两个 Session 记录相同的 Hands Deployment ID，并分别保存自己的 affinity。查看 Session A 的文件调用和结果：

```bash
agr api call DescribeEvents \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --request '{
    "SpaceId":"'$SESSION_SPACE_ID'",
    "UserId":"'$SESSION_USER_ID'",
    "SessionId":"'$HANDS_SESSION_A_ID'",
    "Offset":0,
    "Limit":100
  }' \
  --output json
```

Events 中的 `FunctionCall` 和 `FunctionResponse` 分别记录文件操作及其结果。

## 8. 清理

先删除两个 Session，再删除 Deployment 和 Tool：

```bash
for session_id in "$HANDS_SESSION_A_ID" "$HANDS_SESSION_B_ID"; do
  agr api call DeleteSession \
    --region "$AGR_REGION" \
    --cloud-endpoint "$SESSION_API_ENDPOINT" \
    --request '{"SpaceId":"'$SESSION_SPACE_ID'","UserId":"'$SESSION_USER_ID'","SessionId":"'$session_id'"}' \
    --output json
done

agr deployment delete "$HANDS_DEPLOYMENT_ID" \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --wait

agr instance list \
  --tool-id "$HANDS_TOOL_ID" \
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

- Session A 无法恢复文件：检查 Session Metadata 中是否同时存在 Hands Deployment ID 和 affinity。
- Session B 返回容量不足：确认 `MaxInstanceCount` 至少为 2，并等待 Session A 的首次请求完成。
- 找不到关联 Session：确认查询使用的是 Hands Deployment Metadata，而不是 Brain Deployment Metadata。
- 删除 SessionSpace 失败：先删除其中的 Session。
