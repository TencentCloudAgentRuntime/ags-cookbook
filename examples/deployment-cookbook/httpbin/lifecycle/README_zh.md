# httpbin Deployment 空闲生命周期

本教程独立创建一个 httpbin Deployment，先观察空闲后的 `STOP`，再通过完整配置更新切换到 `PAUSE`。`STOP` 释放 Sandbox Instance；`PAUSE` 保留实例状态以供恢复。httpbin 是无状态服务，因此本例验证实例状态与请求恢复，不把响应内容当作状态持久性的证明。

所有命令都直接在终端执行。请手工复制资源 ID 和 Token，并自行计时等待；文档不使用提取、轮询或等待脚本。示例输出中的真实信息均已脱敏。

## 1. 设置环境变量并创建 Tool

```bash
export AGR_REGION=ap-shanghai
export AGR_DOMAIN=tencentags.com
export AGR_ROLE_ARN='qcs::cam::uin/100000000001:roleName/replace-me'
export HTTPBIN_TOOL_NAME='httpbin-lifecycle-your-name'
export HTTPBIN_DEPLOYMENT_NAME='httpbin-lifecycle-your-name'

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
Name:        httpbin-lifecycle-****
Type:        custom
Status:      ACTIVE
Created:     <masked-time>
```

复制 `ID`：

```bash
export HTTPBIN_TOOL_ID='sdt-replace-me'
```

## 2. 配置空闲后停止

`MinInstanceCount=0` 允许实例在空闲后离开活跃容量；连续空闲 30 秒后，`STOP` 释放实例。

```bash
agr deployment create \
  --region "$AGR_REGION" \
  --deployment-name "$HTTPBIN_DEPLOYMENT_NAME" \
  --tool-id "$HTTPBIN_TOOL_ID" \
  --scaling-configuration '{
    "MinInstanceCount": 0,
    "MaxInstanceCount": 1,
    "MaxInstanceRequestConcurrency": 10
  }' \
  --lifecycle-configuration '{
    "IdleTimeoutSeconds": 30,
    "IdleAction": "STOP"
  }'
```

成功输出应包含：

```text
Name:          httpbin-lifecycle-****
ID:            dpl-********
Status:        ACTIVE
Scaling:
  Min Instances:                0
  Max Instances:                1
  Max Requests per Instance:    10
Lifecycle:
  Idle Action:                  STOP
  Idle Timeout:                 30s
```

复制 Deployment ID，并获取短期 Token：

```bash
export HTTPBIN_DEPLOYMENT_ID='dpl-replace-me'

agr api call AcquireDeploymentToken \
  --region "$AGR_REGION" \
  --request '{"DeploymentId":"'$HTTPBIN_DEPLOYMENT_ID'"}' \
  --output json
```

```bash
export HTTPBIN_DEPLOYMENT_TOKEN='replace-with-token'
```

## 3. 激活实例并观察 `STOP`

发送一次请求以启动实例：

```bash
curl --fail-with-body --silent --show-error \
  --header "X-Access-Token: $HTTPBIN_DEPLOYMENT_TOKEN" \
  "https://8080-$HTTPBIN_DEPLOYMENT_ID.$AGR_REGION.agents.$AGR_DOMAIN/get"

agr instance list --tool-id "$HTTPBIN_TOOL_ID" --region "$AGR_REGION"
```

请求成功后，列表中会出现活跃实例：

```text
ID                    TOOL                         STATUS   TIMEOUT  EXPIRES  MOUNTS  CREATED
<masked-instance-id>  httpbin-lifecycle-****       RUNNING  0s       -        -       <masked-time>
```

停止访问至少 30 秒，再查询实例。回收是异步过程，实际时间可能略长于配置值：

```bash
agr instance list --tool-id "$HTTPBIN_TOOL_ID" --region "$AGR_REGION"
```

原实例最终进入 `STOPPED`：

```text
ID                    TOOL                         STATUS   TIMEOUT  EXPIRES  MOUNTS  CREATED
<masked-instance-id>  httpbin-lifecycle-****       STOPPED  0s       -        -       <masked-time>
```

再次请求时，Deployment 会按需启动容量：

```bash
curl --fail-with-body --silent --show-error \
  --header "X-Access-Token: $HTTPBIN_DEPLOYMENT_TOKEN" \
  "https://8080-$HTTPBIN_DEPLOYMENT_ID.$AGR_REGION.agents.$AGR_DOMAIN/get"
```

## 4. 切换为空闲后暂停

生命周期对象在更新时会被完整替换，因此同时提供超时与动作。更新后请求一次，使实例在新策略下处于活跃状态。

```bash
agr deployment update "$HTTPBIN_DEPLOYMENT_ID" \
  --region "$AGR_REGION" \
  --lifecycle-configuration '{
    "IdleTimeoutSeconds": 30,
    "IdleAction": "PAUSE"
  }'

agr deployment get "$HTTPBIN_DEPLOYMENT_ID" --region "$AGR_REGION"

curl --fail-with-body --silent --show-error \
  --header "X-Access-Token: $HTTPBIN_DEPLOYMENT_TOKEN" \
  "https://8080-$HTTPBIN_DEPLOYMENT_ID.$AGR_REGION.agents.$AGR_DOMAIN/get"
```

查询结果应显示新策略：

```text
Lifecycle:
  Idle Action:                  PAUSE
  Idle Timeout:                 30s
```

再次停止访问至少 30 秒，然后查询实例：

```bash
agr instance list --tool-id "$HTTPBIN_TOOL_ID" --region "$AGR_REGION"
```

实例最终进入 `PAUSED`：

```text
ID                    TOOL                         STATUS  TIMEOUT  EXPIRES  MOUNTS  CREATED
<masked-instance-id>  httpbin-lifecycle-****       PAUSED  0s       -        -       <masked-time>
```

再次发送同一请求，Deployment 会恢复可用容量。`PAUSE` 保证保留实例状态，但不承诺固定恢复延迟。

```bash
curl --fail-with-body --silent --show-error \
  --header "X-Access-Token: $HTTPBIN_DEPLOYMENT_TOKEN" \
  "https://8080-$HTTPBIN_DEPLOYMENT_ID.$AGR_REGION.agents.$AGR_DOMAIN/get"
```

## 5. 清理资源

```bash
agr deployment delete "$HTTPBIN_DEPLOYMENT_ID" --region "$AGR_REGION" --wait
agr instance list --tool-id "$HTTPBIN_TOOL_ID" --region "$AGR_REGION"
```

`PAUSE` 实验后可能仍能看到暂停实例。逐个复制非 `STOPPED` 实例 ID 并删除：

```bash
export HTTPBIN_INSTANCE_ID='replace-with-instance-id'
agr instance delete "$HTTPBIN_INSTANCE_ID" --region "$AGR_REGION" --yes --wait
```

最后删除 Tool：

```bash
agr tool delete "$HTTPBIN_TOOL_ID" --region "$AGR_REGION" --yes --wait
```
