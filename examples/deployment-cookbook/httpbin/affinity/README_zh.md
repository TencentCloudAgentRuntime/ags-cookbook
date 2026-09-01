# httpbin Deployment 会话亲和

本教程创建一个共享 httpbin Tool 和三个独立 Deployment，对比全部会话亲和模式。亲和配置不能通过 `deployment update` 修改，因此每种模式使用独立 Deployment。

| 模式 | 目标实例不可用时 | 实例所有权 |
| --- | --- | --- |
| `BEST_EFFORT` | 可以选择其他实例 | 共享 |
| `STRICT` | 请求失败，不迁移 | 共享 |
| `EXCLUSIVE` | 不迁移 | 每个 affinity ID 独占一个实例 |

请求与响应使用 `X-Httpbin-Affinity`。本例通过响应 header 和 HTTP 状态观察路由契约，不开启真实 hostname，也不使用提取、验证或轮询脚本。示例输出中的真实信息均已脱敏。

## 1. 设置环境变量并创建共享 Tool

把所有名称中的 `your-name` 替换为同一个唯一后缀。

```bash
export AGR_REGION=ap-shanghai
export AGR_DOMAIN=tencentags.com
export AGR_ROLE_ARN='qcs::cam::uin/100000000001:roleName/replace-me'
export HTTPBIN_TOOL_NAME='httpbin-affinity-your-name'
export BEST_EFFORT_DEPLOYMENT_NAME='httpbin-best-effort-your-name'
export STRICT_DEPLOYMENT_NAME='httpbin-strict-your-name'
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

## 2. 创建三个 Deployment

三个 Deployment 使用相同 header 名和 30 秒 `STOP` 空闲策略，以便手工观察目标实例不可用后的差异。`EXCLUSIVE` 最多允许三个独占实例。

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
  --deployment-name "$STRICT_DEPLOYMENT_NAME" \
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
    "Mode": "STRICT",
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

按创建顺序复制三个 ID：

```bash
export BEST_EFFORT_DEPLOYMENT_ID='dpl-replace-me'
export STRICT_DEPLOYMENT_ID='dpl-replace-me'
export EXCLUSIVE_DEPLOYMENT_ID='dpl-replace-me'
```

## 3. 获取三个 Deployment Token

Token 只适用于目标 Deployment，不能跨 Deployment 使用。

```bash
agr api call AcquireDeploymentToken --region "$AGR_REGION" --request '{"DeploymentId":"'$BEST_EFFORT_DEPLOYMENT_ID'"}' --output json
agr api call AcquireDeploymentToken --region "$AGR_REGION" --request '{"DeploymentId":"'$STRICT_DEPLOYMENT_ID'"}' --output json
agr api call AcquireDeploymentToken --region "$AGR_REGION" --request '{"DeploymentId":"'$EXCLUSIVE_DEPLOYMENT_ID'"}' --output json
```

分别复制三个响应中的 `Data.Response.Response.Token`：

```bash
export BEST_EFFORT_TOKEN='replace-with-token'
export STRICT_TOKEN='replace-with-token'
export EXCLUSIVE_TOKEN='replace-with-token'
```

## 4. `BEST_EFFORT`：优先复用，允许迁移

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

保持空闲至少 30 秒使目标实例停止，再执行同一请求。`BEST_EFFORT` 可以改选其他实例继续执行，因此仍应得到成功响应；返回的 affinity ID 可能变化。

## 5. `STRICT`：必须复用，不允许迁移

先获取并复制 affinity ID：

```bash
curl --include --silent --show-error \
  --header "X-Access-Token: $STRICT_TOKEN" \
  "https://8080-$STRICT_DEPLOYMENT_ID.$AGR_REGION.agents.$AGR_DOMAIN/headers"
```

```bash
export STRICT_AFFINITY_ID='replace-with-response-header'

curl --include --silent --show-error \
  --header "X-Access-Token: $STRICT_TOKEN" \
  --header "X-Httpbin-Affinity: $STRICT_AFFINITY_ID" \
  "https://8080-$STRICT_DEPLOYMENT_ID.$AGR_REGION.agents.$AGR_DOMAIN/headers"
```

保持空闲至少 30 秒，使目标实例停止；再次执行相同请求。`STRICT` 会返回非 2xx 响应，而不是选择新实例。具体状态码和错误文本可能随服务版本变化，响应格式类似：

```http
HTTP/2 <non-2xx-status>
content-type: application/json

{"Response":{"Error":{"Code":"<masked-code>","Message":"<masked-message>"},"RequestId":"<masked-request-id>"}}
```

## 6. `EXCLUSIVE`：一个 affinity ID 独占一个实例

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

两个 ID 对应两个互不共享、不可迁移的实例；实例上限也因此限制可同时存在的独占会话数。

## 7. 清理资源

```bash
agr deployment delete "$BEST_EFFORT_DEPLOYMENT_ID" --region "$AGR_REGION" --wait
agr deployment delete "$STRICT_DEPLOYMENT_ID" --region "$AGR_REGION" --wait
agr deployment delete "$EXCLUSIVE_DEPLOYMENT_ID" --region "$AGR_REGION" --wait
agr instance list --tool-id "$HTTPBIN_TOOL_ID" --region "$AGR_REGION"
```

若仍有非 `STOPPED` 实例，逐个复制 ID 并删除：

```bash
export HTTPBIN_INSTANCE_ID='replace-with-instance-id'
agr instance delete "$HTTPBIN_INSTANCE_ID" --region "$AGR_REGION" --yes --wait
```

最后删除共享 Tool：

```bash
agr tool delete "$HTTPBIN_TOOL_ID" --region "$AGR_REGION" --yes --wait
```
