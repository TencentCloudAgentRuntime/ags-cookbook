# Deployment 与 Session 联动

本教程通过 Session Metadata 保存 Deployment ID 和当前 affinity ID，将 Session 与有状态 Deployment 关联起来；随后仅根据 Session 恢复这两个值，并继续访问 Deployment。

Session 不拥有、也不校验被引用的 Deployment。Metadata 只保存不透明 ID，删除任意一方都不会级联删除另一方。

## 前置条件

- 已安装 `agr` v0.6.6 或更高版本，并先运行 `agr version` 和 `agr status`。
- 已创建 SessionSpace，并从控制台或 API 响应中复制其 ID。
- 已准备允许 AGR 拉取示例 CCR 镜像的 CAM 角色 ARN。
- 账号具有管理 Sandbox Tool、Deployment、Session 以及获取 Deployment Token 的权限。

在本目录运行 `make run` 只会输出导航信息，不会创建云资源。

## 1. 设置环境变量

替换全部占位符，并让 Session 与 Deployment 位于同一地域。

```bash
export AGR_REGION=ap-shanghai
export AGR_DOMAIN=tencentags.com
export AGR_ROLE_ARN='qcs::cam::uin/100000000001:roleName/replace-me'
export SESSION_SPACE_ID='space-replace-me'
export SESSION_USER_ID='user-demo'
export SESSION_ID='session-demo-your-name'
export SESSION_TOOL_NAME='httpbin-session-your-name'
export SESSION_DEPLOYMENT_NAME='httpbin-session-your-name'

agr status
```

## 2. 创建支持亲和性的 Deployment

创建持久化 httpbin Tool：

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
    "Env":[{"Name":"EXCLUDE_HEADERS","Value":"X-Access-Token"}],
    "Ports":[{"Name":"http","Port":8080,"Protocol":"TCP"}],
    "Resources":{"CPU":"200m","Memory":"500Mi"},
    "Probe":{"HttpGet":{"Path":"/status/200","Port":8080,"Scheme":"HTTP"},"ReadyTimeoutMs":30000,"ProbeTimeoutMs":1000,"ProbePeriodMs":3000,"SuccessThreshold":1,"FailureThreshold":10}
  }' \
  --wait
```

从输出中复制 Tool ID：

```bash
export SESSION_TOOL_ID='sdt-replace-me'
```

创建 `BEST_EFFORT` Deployment。较长的空闲时间便于观察 affinity 复用：

```bash
agr deployment create \
  --region "$AGR_REGION" \
  --deployment-name "$SESSION_DEPLOYMENT_NAME" \
  --tool-id "$SESSION_TOOL_ID" \
  --scaling-configuration '{"MinInstanceCount":0,"MaxInstanceCount":2,"MaxInstanceRequestConcurrency":10}' \
  --lifecycle-configuration '{"IdleTimeoutSeconds":600,"IdleAction":"STOP"}' \
  --affinity-configuration '{"Mode":"BEST_EFFORT","HeaderName":"X-Session-Affinity"}'
```

复制 Deployment ID：

```bash
export SESSION_DEPLOYMENT_ID='dpl-replace-me'
```

## 3. 创建关联 Deployment 的 Session

使用预定义 Metadata Name 保存不透明的 Deployment ID：

```bash
agr api call CreateSession \
  --region "$AGR_REGION" \
  --request '{
    "SpaceId":"'$SESSION_SPACE_ID'",
    "UserId":"'$SESSION_USER_ID'",
    "SessionId":"'$SESSION_ID'",
    "Title":"Deployment session demo",
    "Metadata":[
      {"Name":"ae.tencentcloud.com/hands-deployment-id","Value":"'$SESSION_DEPLOYMENT_ID'"}
    ]
  }' \
  --output json
```

Session 将该 ID 视为不透明值；创建 Session 时不会检查 Deployment 是否真实存在。

## 4. 第一次访问 Deployment

获取 Token：

```bash
agr api call AcquireDeploymentToken \
  --region "$AGR_REGION" \
  --request '{"DeploymentId":"'$SESSION_DEPLOYMENT_ID'"}' \
  --output json
```

复制 `Data.Response.Response.Token`，不要把它输出或提交到其他位置：

```bash
export SESSION_DEPLOYMENT_TOKEN='replace-with-token'
```

第一次请求不携带 affinity header：

```bash
curl --include --silent --show-error \
  --header "X-Access-Token: $SESSION_DEPLOYMENT_TOKEN" \
  "https://8080-$SESSION_DEPLOYMENT_ID.$AGR_REGION.agents.$AGR_DOMAIN/headers"
```

复制响应中的 `X-Session-Affinity`：

```bash
export SESSION_AFFINITY_ID='replace-with-response-header'
```

## 5. 将当前 affinity 保存到 Session

`ModifySession.Metadata` 是全量替换；添加 affinity ID 时必须再次包含 Deployment ID：

```bash
agr api call ModifySession \
  --region "$AGR_REGION" \
  --request '{
    "SpaceId":"'$SESSION_SPACE_ID'",
    "UserId":"'$SESSION_USER_ID'",
    "SessionId":"'$SESSION_ID'",
    "Metadata":[
      {"Name":"ae.tencentcloud.com/hands-deployment-id","Value":"'$SESSION_DEPLOYMENT_ID'"},
      {"Name":"ae.tencentcloud.com/hands-affinity-id","Value":"'$SESSION_AFFINITY_ID'"}
    ]
  }' \
  --output json
```

Hands Affinity 存在时必须同时存在 Hands Deployment。不传 `Metadata` 表示保持不变，传空数组表示清空全部 Metadata；空字符串是保存的值，不表示删除。

## 6. 恢复并复用路由上下文

读取 Session：

```bash
agr api call DescribeSession \
  --region "$AGR_REGION" \
  --request '{"SpaceId":"'$SESSION_SPACE_ID'","UserId":"'$SESSION_USER_ID'","SessionId":"'$SESSION_ID'"}' \
  --output json
```

响应包含两个 Metadata 项。新的应用进程可以恢复这些值，重新获取 Deployment Token，并带回 affinity：

```bash
curl --include --silent --show-error \
  --header "X-Access-Token: $SESSION_DEPLOYMENT_TOKEN" \
  --header "X-Session-Affinity: $SESSION_AFFINITY_ID" \
  "https://8080-$SESSION_DEPLOYMENT_ID.$AGR_REGION.agents.$AGR_DOMAIN/headers"
```

`BEST_EFFORT` 会优先复用原目标；若原目标不可用，也可能返回新的 affinity。返回值发生变化时，应持久化最新值。

## 7. 通过 Deployment 反查 Session

使用 Metadata Filter：

```bash
agr api call DescribeSessions \
  --region "$AGR_REGION" \
  --request '{
    "SpaceId":"'$SESSION_SPACE_ID'",
    "Filters":[
      {"Name":"metadata:ae.tencentcloud.com/hands-deployment-id","Values":["'$SESSION_DEPLOYMENT_ID'"]}
    ],
    "Offset":0,
    "Limit":20
  }' \
  --output json
```

同一 Filter 中多个 Value 是 OR；多个 Filter 之间是 AND；匹配方式为精确匹配。

## 8. 修改或删除关联

切换 Hands Deployment 时，必须删除旧 affinity，或在新请求流程中用不同的新 affinity 替换。只保留当前 Deployment 关联可执行：

```bash
agr api call ModifySession \
  --region "$AGR_REGION" \
  --request '{
    "SpaceId":"'$SESSION_SPACE_ID'",
    "UserId":"'$SESSION_USER_ID'",
    "SessionId":"'$SESSION_ID'",
    "Metadata":[
      {"Name":"ae.tencentcloud.com/hands-deployment-id","Value":"'$SESSION_DEPLOYMENT_ID'"}
    ]
  }' \
  --output json
```

## 9. 清理

删除 Session 不会删除 Deployment，删除 Deployment 也不会删除关联 Session，必须分别清理：

```bash
agr api call DeleteSession \
  --region "$AGR_REGION" \
  --request '{"SpaceId":"'$SESSION_SPACE_ID'","UserId":"'$SESSION_USER_ID'","SessionId":"'$SESSION_ID'"}' \
  --output json

agr deployment delete "$SESSION_DEPLOYMENT_ID" --region "$AGR_REGION" --wait
agr tool delete "$SESSION_TOOL_ID" --region "$AGR_REGION" --yes --wait
```

不要把 Deployment Token 或 affinity ID 写入应用日志、Trace、截图或版本库。

## 常见问题

- `InvalidParameter.Metadata`：检查空 Name、重复 Name、容量限制，或是否存在只有 affinity、没有 Hands Deployment ID 的组合。
- `ResourceNotFound`：确认 SessionSpace、Session、Tool 和 Deployment 属于当前配置的地域与账号。
- Deployment 返回了新 affinity：`BEST_EFFORT` 允许迁移，请保存最新返回值。
- `ModifySession` 删除了无关 Metadata：该接口会替换完整 Metadata 数组，必须先读取、合并，再写回所有需要保留的项。
