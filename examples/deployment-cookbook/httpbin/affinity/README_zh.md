# httpbin Deployment 会话亲和

本教程创建一个共享 httpbin Tool 和两个独立 Deployment，对比共享与独占会话亲和。亲和配置不能通过 `deployment update` 修改，因此每种模式使用独立 Deployment。

开始前，请完成 [httpbin 公共前置条件](../README_zh.md#前置条件)。

| 模式 | 路由行为 | 实例所有权 |
| --- | --- | --- |
| `BEST_EFFORT` | 为同一个 affinity ID 复用共享容量 | 共享 |
| `EXCLUSIVE` | 每个 affinity ID 始终使用自己的专属实例 | 每个 affinity ID 独占一个实例 |

请求与响应使用 `X-Httpbin-Affinity`，响应 header 会显示选中的路由。示例输出中的真实信息均已脱敏。

## 1. 设置环境变量并创建共享 Tool

把所有名称中的 `your-name` 替换为同一个唯一后缀。

```bash
export AGR_REGION=ap-shanghai
export AGR_DOMAIN=tencentags.com
export AGR_ROLE_ARN='qcs::cam::uin/100000000001:roleName/replace-me'
export HTTPBIN_TOOL_NAME='httpbin-affinity-your-name'
export BEST_EFFORT_DEPLOYMENT_NAME='httpbin-best-effort-your-name'
export EXCLUSIVE_DEPLOYMENT_NAME='httpbin-exclusive-your-name'

agr status

agr tool create \
  --region "$AGR_REGION" \
  --tool-name "$HTTPBIN_TOOL_NAME" \
  --tool-type custom \
  --persistent \
  --role-arn "$AGR_ROLE_ARN" \
  --network-configuration '{"NetworkMode":"PUBLIC"}' \
  --custom-configuration '{
    "Image": "ccr.ccs.tencentyun.com/ags.dev/go-httpbin:v2.25.0",
    "ImageRegistryType": "personal",
    "Command": [
      "/bin/go-httpbin"
    ],
    "Args": [
      "-host",
      "0.0.0.0",
      "-port",
      "8080"
    ],
    "Env": [
      {
        "Name": "EXCLUDE_HEADERS",
        "Value": "X-Access-Token"
      }
    ],
    "Ports": [
      {
        "Name": "http",
        "Port": 8080,
        "Protocol": "TCP"
      }
    ],
    "Resources": {
      "CPU": "200m",
      "Memory": "500Mi"
    },
    "Probe": {
      "HttpGet": {
        "Path": "/status/200",
        "Port": 8080,
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

成功输出包含真实 Tool ID：

```text
ID:          sdt-********
Name:        httpbin-affinity-****
Type:        custom
Status:      ACTIVE
Created:     <masked-time>
```

复制 `ID`：

```bash
export HTTPBIN_TOOL_ID='sdt-replace-me'
```

## 2. 创建两个 Deployment

两个 Deployment 使用相同 header 名和 30 秒 `STOP` 空闲策略。`EXCLUSIVE` 最多允许三个独占实例。

```bash
agr deployment create \
  --region "$AGR_REGION" \
  --deployment-name "$BEST_EFFORT_DEPLOYMENT_NAME" \
  --tool-id "$HTTPBIN_TOOL_ID" \
  --scaling-configuration '{
    "MinInstanceCount": 0,
    "MaxInstanceCount": 2,
    "MaxInstanceRequestConcurrency": 10
  }' \
  --lifecycle-configuration '{
    "IdleTimeoutSeconds": 30,
    "IdleAction": "STOP"
  }' \
  --affinity-configuration '{
    "Mode": "BEST_EFFORT",
    "HeaderName": "X-Httpbin-Affinity"
  }'

agr deployment create \
  --region "$AGR_REGION" \
  --deployment-name "$EXCLUSIVE_DEPLOYMENT_NAME" \
  --tool-id "$HTTPBIN_TOOL_ID" \
  --scaling-configuration '{
    "MinInstanceCount": 0,
    "MaxInstanceCount": 3,
    "MaxInstanceRequestConcurrency": 1
  }' \
  --lifecycle-configuration '{
    "IdleTimeoutSeconds": 30,
    "IdleAction": "STOP"
  }' \
  --affinity-configuration '{
    "Mode": "EXCLUSIVE",
    "HeaderName": "X-Httpbin-Affinity"
  }'
```

每次成功输出都包含该 Deployment 的 ID 和亲和配置。例如：

```text
Name:          httpbin-best-effort-****
ID:            dpl-********
Status:        ACTIVE
Affinity:
  Mode:                         BEST_EFFORT
  Header:                       X-Httpbin-Affinity
```

按创建顺序复制两个 ID：

```bash
export BEST_EFFORT_DEPLOYMENT_ID='dpl-replace-me'
export EXCLUSIVE_DEPLOYMENT_ID='dpl-replace-me'
```

## 3. 获取两个 Deployment Token

Token 只适用于目标 Deployment，不能跨 Deployment 使用。

```bash
agr api call AcquireDeploymentToken --region "$AGR_REGION" --request '{"DeploymentId":"'$BEST_EFFORT_DEPLOYMENT_ID'"}' --output json
agr api call AcquireDeploymentToken --region "$AGR_REGION" --request '{"DeploymentId":"'$EXCLUSIVE_DEPLOYMENT_ID'"}' --output json
```

分别复制两个响应中的 `Data.Response.Response.Token`：

```bash
export BEST_EFFORT_TOKEN='replace-with-token'
export EXCLUSIVE_TOKEN='replace-with-token'
```

## 4. `BEST_EFFORT`：复用共享容量

第一次请求不带 affinity header：

```bash
curl --include --silent --show-error \
  --header "X-Access-Token: $BEST_EFFORT_TOKEN" \
  "https://8080-$BEST_EFFORT_DEPLOYMENT_ID.$AGR_REGION.agents.$AGR_DOMAIN/headers"
```

响应 header 中包含服务分配的 affinity ID：

```http
HTTP/2 200
content-type: application/json
x-httpbin-affinity: <masked-affinity-id>

{"headers":{"Accept":"*/*","Host":"<masked-host>","User-Agent":"curl/<version>"}}
```

复制 `X-Httpbin-Affinity` 的值，再带回同一个 ID：

```bash
export BEST_EFFORT_AFFINITY_ID='replace-with-response-header'

curl --include --silent --show-error \
  --header "X-Access-Token: $BEST_EFFORT_TOKEN" \
  --header "X-Httpbin-Affinity: $BEST_EFFORT_AFFINITY_ID" \
  "https://8080-$BEST_EFFORT_DEPLOYMENT_ID.$AGR_REGION.agents.$AGR_DOMAIN/headers"
```

第二次请求应返回 HTTP `200` 并继续携带同一个 affinity ID，确认该 ID 可用于后续请求。

## 5. `EXCLUSIVE`：一个 affinity ID 独占一个实例

连续发送两次不带 affinity header 的请求：

```bash
curl --include --silent --show-error --header "X-Access-Token: $EXCLUSIVE_TOKEN" "https://8080-$EXCLUSIVE_DEPLOYMENT_ID.$AGR_REGION.agents.$AGR_DOMAIN/headers"
curl --include --silent --show-error --header "X-Access-Token: $EXCLUSIVE_TOKEN" "https://8080-$EXCLUSIVE_DEPLOYMENT_ID.$AGR_REGION.agents.$AGR_DOMAIN/headers"
```

两个响应应包含不同的 affinity ID。分别复制后带回：

```bash
export EXCLUSIVE_AFFINITY_ID_A='replace-with-first-response-header'
export EXCLUSIVE_AFFINITY_ID_B='replace-with-second-response-header'

curl --include --silent --show-error --header "X-Access-Token: $EXCLUSIVE_TOKEN" --header "X-Httpbin-Affinity: $EXCLUSIVE_AFFINITY_ID_A" "https://8080-$EXCLUSIVE_DEPLOYMENT_ID.$AGR_REGION.agents.$AGR_DOMAIN/headers"
curl --include --silent --show-error --header "X-Access-Token: $EXCLUSIVE_TOKEN" --header "X-Httpbin-Affinity: $EXCLUSIVE_AFFINITY_ID_B" "https://8080-$EXCLUSIVE_DEPLOYMENT_ID.$AGR_REGION.agents.$AGR_DOMAIN/headers"
```

这两个 ID 现在可用于两个独立的 `EXCLUSIVE` 会话；实例上限也限制可同时存在的独占会话数。

## 6. 清理资源

```bash
agr deployment delete "$BEST_EFFORT_DEPLOYMENT_ID" --region "$AGR_REGION" --wait
agr deployment delete "$EXCLUSIVE_DEPLOYMENT_ID" --region "$AGR_REGION" --wait
agr instance list --tool-id "$HTTPBIN_TOOL_ID" --region "$AGR_REGION"
```

复制每个当前处于 `RUNNING` 或 `PAUSED` 状态的实例 ID，并逐个执行删除命令：

```bash
export HTTPBIN_INSTANCE_ID='replace-with-instance-id'
agr instance delete "$HTTPBIN_INSTANCE_ID" --region "$AGR_REGION" --yes --wait
```

删除共享 Tool：

```bash
agr tool delete "$HTTPBIN_TOOL_ID" --region "$AGR_REGION" --yes --wait
```
