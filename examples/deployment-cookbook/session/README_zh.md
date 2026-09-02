# Deployment 与 Session 联动

本教程演示 Brain 和 Hands Deployment 如何分别与各自的 Session 联动。Brain Session 记录 Brain Deployment ID；Hands Session 记录 Hands Deployment ID 和当前 affinity ID，使后续请求可以恢复相同的 Hands 路由上下文。

Session Metadata 只保存不透明 ID。Session 与 Deployment 的生命周期相互独立，删除任意一方都不会级联删除另一方。

## 前置条件

- 已安装 `agr` v0.6.6 或更高版本，并先运行 `agr version` 和 `agr status`。
- 已准备允许 AGR 拉取示例 CCR 镜像的 CAM 角色 ARN。
- 账号具有管理 SessionSpace、Session、Sandbox Tool、Deployment 以及获取 Deployment Token 的权限。

在本目录运行 `make run` 只会输出导航信息，不会创建云资源。

## 1. 设置环境变量

替换全部占位符，并让两个 Session 与两个 Deployment 位于同一地域。

```bash
export AGR_REGION=ap-shanghai
export AGR_DOMAIN=tencentags.com
export AGR_ROLE_ARN='qcs::cam::uin/100000000001:roleName/replace-me'
export SESSION_SPACE_NAME='deployment-session-your-name'
export SESSION_USER_ID='user-demo'
export BRAIN_SESSION_ID='brain-session-your-name'
export HANDS_SESSION_ID='hands-session-your-name'
export SESSION_TOOL_NAME='httpbin-session-your-name'
export BRAIN_DEPLOYMENT_NAME='httpbin-brain-your-name'
export HANDS_DEPLOYMENT_NAME='httpbin-hands-your-name'

agr status
```

## 2. 创建 SessionSpace

为本教程创建一个独立的 SessionSpace：

```bash
agr api call CreateSessionSpace \
  --region "$AGR_REGION" \
  --request '{
    "Name":"'$SESSION_SPACE_NAME'",
    "Description":"Session and Deployment integration cookbook"
  }' \
  --output json
```

从响应中复制 SessionSpace ID：

```bash
export SESSION_SPACE_ID='space-replace-me'
```

## 3. 创建共享 Tool

两个 Deployment 共用一个持久化 httpbin Tool。`USE_REAL_HOSTNAME` 使 `/hostname` 返回后端 hostname，从而直观展示 Hands 路由复用。

```bash
agr tool create \
  --region "$AGR_REGION" \
  --tool-name "$SESSION_TOOL_NAME" \
  --tool-type custom \
  --persistent \
  --role-arn "$AGR_ROLE_ARN" \
  --network-configuration '{"NetworkMode":"PUBLIC"}' \
  --custom-configuration '{
    "Image":"ccr.ccs.tencentyun.com/ags.dev/go-httpbin:v2.25.0",
    "ImageRegistryType":"personal",
    "Command":["/bin/go-httpbin"],
    "Args":["-host","0.0.0.0","-port","8080"],
    "Env":[
      {"Name":"EXCLUDE_HEADERS","Value":"X-Access-Token"},
      {"Name":"USE_REAL_HOSTNAME","Value":"true"}
    ],
    "Ports":[{"Name":"http","Port":8080,"Protocol":"TCP"}],
    "Resources":{"CPU":"200m","Memory":"500Mi"},
    "Probe":{"HttpGet":{"Path":"/status/200","Port":8080,"Scheme":"HTTP"},"ReadyTimeoutMs":30000,"ProbeTimeoutMs":1000,"ProbePeriodMs":3000,"SuccessThreshold":1,"FailureThreshold":10}
  }' \
  --wait
```

复制 Tool ID：

```bash
export SESSION_TOOL_ID='sdt-replace-me'
```

## 4. 创建 Brain 和 Hands Deployment

创建 Brain Deployment：

```bash
agr deployment create \
  --region "$AGR_REGION" \
  --deployment-name "$BRAIN_DEPLOYMENT_NAME" \
  --tool-id "$SESSION_TOOL_ID" \
  --scaling-configuration '{"MinInstanceCount":0,"MaxInstanceCount":2,"MaxInstanceRequestConcurrency":10}' \
  --lifecycle-configuration '{"IdleTimeoutSeconds":600,"IdleAction":"STOP"}'
```

创建支持 affinity 的 Hands Deployment：

```bash
agr deployment create \
  --region "$AGR_REGION" \
  --deployment-name "$HANDS_DEPLOYMENT_NAME" \
  --tool-id "$SESSION_TOOL_ID" \
  --scaling-configuration '{"MinInstanceCount":0,"MaxInstanceCount":2,"MaxInstanceRequestConcurrency":10}' \
  --lifecycle-configuration '{"IdleTimeoutSeconds":600,"IdleAction":"STOP"}' \
  --affinity-configuration '{"Mode":"BEST_EFFORT","HeaderName":"X-Session-Affinity"}'
```

分别复制两个 Deployment ID：

```bash
export BRAIN_DEPLOYMENT_ID='dpl-replace-me'
export HANDS_DEPLOYMENT_ID='dpl-replace-me'
```

## 5. 分别创建 Brain 和 Hands Session

创建 Brain Session，并记录 Brain Deployment ID：

```bash
agr api call CreateSession \
  --region "$AGR_REGION" \
  --request '{
    "SpaceId":"'$SESSION_SPACE_ID'",
    "UserId":"'$SESSION_USER_ID'",
    "SessionId":"'$BRAIN_SESSION_ID'",
    "Title":"Brain session demo",
    "Metadata":[
      {"Name":"ae.tencentcloud.com/brain-deployment-id","Value":"'$BRAIN_DEPLOYMENT_ID'"}
    ]
  }' \
  --output json
```

创建 Hands Session，并记录 Hands Deployment ID：

```bash
agr api call CreateSession \
  --region "$AGR_REGION" \
  --request '{
    "SpaceId":"'$SESSION_SPACE_ID'",
    "UserId":"'$SESSION_USER_ID'",
    "SessionId":"'$HANDS_SESSION_ID'",
    "Title":"Hands session demo",
    "Metadata":[
      {"Name":"ae.tencentcloud.com/hands-deployment-id","Value":"'$HANDS_DEPLOYMENT_ID'"}
    ]
  }' \
  --output json
```

创建 Session 时不会检查被引用的 Deployment 是否真实存在。

## 6. 访问 Brain Deployment

获取并复制 Brain Deployment Token：

```bash
agr api call AcquireDeploymentToken \
  --region "$AGR_REGION" \
  --request '{"DeploymentId":"'$BRAIN_DEPLOYMENT_ID'"}' \
  --output json

export BRAIN_DEPLOYMENT_TOKEN='replace-with-token'
```

调用 Brain Deployment：

```bash
curl --silent --show-error \
  --header "X-Access-Token: $BRAIN_DEPLOYMENT_TOKEN" \
  "https://8080-$BRAIN_DEPLOYMENT_ID.$AGR_REGION.agents.$AGR_DOMAIN/hostname"
```

响应会标识 Brain 后端，例如：

```json
{"hostname":"brain-backend-a"}
```

## 7. 访问 Hands 并保存 affinity

获取并复制 Hands Deployment Token：

```bash
agr api call AcquireDeploymentToken \
  --region "$AGR_REGION" \
  --request '{"DeploymentId":"'$HANDS_DEPLOYMENT_ID'"}' \
  --output json

export HANDS_DEPLOYMENT_TOKEN='replace-with-token'
```

第一次请求 Hands 时不携带 affinity header：

```bash
curl --include --silent --show-error \
  --header "X-Access-Token: $HANDS_DEPLOYMENT_TOKEN" \
  "https://8080-$HANDS_DEPLOYMENT_ID.$AGR_REGION.agents.$AGR_DOMAIN/hostname"
```

记录响应中的两个值：

```text
X-Session-Affinity: <first-affinity-id>
{"hostname":"hands-backend-a"}
```

复制 affinity ID：

```bash
export HANDS_AFFINITY_ID='replace-with-response-header'
```

`ModifySession.Metadata` 是全量替换；添加 affinity ID 时必须再次包含 Hands Deployment ID：

```bash
agr api call ModifySession \
  --region "$AGR_REGION" \
  --request '{
    "SpaceId":"'$SESSION_SPACE_ID'",
    "UserId":"'$SESSION_USER_ID'",
    "SessionId":"'$HANDS_SESSION_ID'",
    "Metadata":[
      {"Name":"ae.tencentcloud.com/hands-deployment-id","Value":"'$HANDS_DEPLOYMENT_ID'"},
      {"Name":"ae.tencentcloud.com/hands-affinity-id","Value":"'$HANDS_AFFINITY_ID'"}
    ]
  }' \
  --output json
```

Hands affinity 存在时必须同时存在 Hands Deployment。不传 `Metadata` 表示保持不变，传空数组表示清空全部 Metadata；空字符串是保存的值，不表示删除。

## 8. 恢复两个 Session，并展示 Hands 复用

读取 Brain Session，恢复 `BRAIN_DEPLOYMENT_ID`：

```bash
agr api call DescribeSession \
  --region "$AGR_REGION" \
  --request '{"SpaceId":"'$SESSION_SPACE_ID'","UserId":"'$SESSION_USER_ID'","SessionId":"'$BRAIN_SESSION_ID'"}' \
  --output json
```

读取 Hands Session，恢复 `HANDS_DEPLOYMENT_ID` 和 `HANDS_AFFINITY_ID`：

```bash
agr api call DescribeSession \
  --region "$AGR_REGION" \
  --request '{"SpaceId":"'$SESSION_SPACE_ID'","UserId":"'$SESSION_USER_ID'","SessionId":"'$HANDS_SESSION_ID'"}' \
  --output json
```

将恢复出的 affinity 带回 Hands：

```bash
curl --include --silent --show-error \
  --header "X-Access-Token: $HANDS_DEPLOYMENT_TOKEN" \
  --header "X-Session-Affinity: $HANDS_AFFINITY_ID" \
  "https://8080-$HANDS_DEPLOYMENT_ID.$AGR_REGION.agents.$AGR_DOMAIN/hostname"
```

对比两次 Hands 响应：

```text
                       首次请求           恢复后请求
X-Session-Affinity     <affinity-a>       <affinity-a>
hostname               hands-backend-a    hands-backend-a
```

affinity 与 hostname 同时一致，表示恢复出的路由上下文到达了相同的 Hands 后端。`BEST_EFFORT` 在原目标不可用时可以选择新目标；返回值发生变化时，应持久化最新 affinity。

## 9. 通过 Deployment 反查各自的 Session

反查 Brain Session：

```bash
agr api call DescribeSessions \
  --region "$AGR_REGION" \
  --request '{
    "SpaceId":"'$SESSION_SPACE_ID'",
    "Filters":[{"Name":"metadata:ae.tencentcloud.com/brain-deployment-id","Values":["'$BRAIN_DEPLOYMENT_ID'"]}],
    "Offset":0,
    "Limit":20
  }' \
  --output json
```

反查 Hands Session：

```bash
agr api call DescribeSessions \
  --region "$AGR_REGION" \
  --request '{
    "SpaceId":"'$SESSION_SPACE_ID'",
    "Filters":[{"Name":"metadata:ae.tencentcloud.com/hands-deployment-id","Values":["'$HANDS_DEPLOYMENT_ID'"]}],
    "Offset":0,
    "Limit":20
  }' \
  --output json
```

同一 Filter 中多个 Value 是 OR；多个 Filter 之间是 AND；匹配方式为精确匹配。

## 10. 删除当前 Hands affinity

如果需要保留 Hands Deployment 关联并删除 affinity，应替换完整 Metadata 数组：

```bash
agr api call ModifySession \
  --region "$AGR_REGION" \
  --request '{
    "SpaceId":"'$SESSION_SPACE_ID'",
    "UserId":"'$SESSION_USER_ID'",
    "SessionId":"'$HANDS_SESSION_ID'",
    "Metadata":[
      {"Name":"ae.tencentcloud.com/hands-deployment-id","Value":"'$HANDS_DEPLOYMENT_ID'"}
    ]
  }' \
  --output json
```

切换 Hands Deployment 时，必须删除旧 affinity，或在新请求流程中使用新获得的不同 affinity。

## 11. 清理

先删除两个 Session，再删除其 SessionSpace，最后删除两个 Deployment 和共享 Tool：

```bash
agr api call DeleteSession \
  --region "$AGR_REGION" \
  --request '{"SpaceId":"'$SESSION_SPACE_ID'","UserId":"'$SESSION_USER_ID'","SessionId":"'$BRAIN_SESSION_ID'"}' \
  --output json

agr api call DeleteSession \
  --region "$AGR_REGION" \
  --request '{"SpaceId":"'$SESSION_SPACE_ID'","UserId":"'$SESSION_USER_ID'","SessionId":"'$HANDS_SESSION_ID'"}' \
  --output json

agr api call DeleteSessionSpace \
  --region "$AGR_REGION" \
  --request '{"SpaceId":"'$SESSION_SPACE_ID'"}' \
  --output json

agr deployment delete "$BRAIN_DEPLOYMENT_ID" --region "$AGR_REGION" --wait
agr deployment delete "$HANDS_DEPLOYMENT_ID" --region "$AGR_REGION" --wait
agr tool delete "$SESSION_TOOL_ID" --region "$AGR_REGION" --yes --wait
```

不要把 Deployment Token 或 affinity ID 写入应用日志、Trace、截图或版本库。

## 常见问题

- `InvalidParameter.Metadata`：检查空 Name、重复 Name、容量限制，或是否存在只有 Hands affinity、没有 Hands Deployment ID 的组合。
- `ResourceNotFound`：确认 SessionSpace、两个 Session、Tool 和两个 Deployment 属于当前配置的地域与账号。
- `ResourceInUse.SessionSpaceNotEmpty`：删除 SessionSpace 前，必须先删除其中的所有 Session。
- Hands 请求返回了新的 affinity 或 hostname：`BEST_EFFORT` 在原目标不可用时允许迁移，请保存最新 affinity。
- `ModifySession` 删除了无关 Metadata：该接口会替换完整 Metadata 数组，必须先读取、合并，再写回所有需要保留的项。
