# httpbin Deployment 弹性伸缩

本教程独立创建 httpbin Tool 和 Deployment，先用 `MinInstanceCount=0` 观察按需启动，再更新为两个常驻实例，并同时调整实例上限与单实例请求并发租约。它用于观察配置与实例状态，不是压力测试。

所有命令都直接在终端执行。请手工复制资源 ID 和 Token；文档不使用提取或轮询脚本。示例输出中的真实信息均已脱敏。

## 1. 设置环境变量并创建 Tool

```bash
export AGR_REGION=ap-shanghai
export AGR_DOMAIN=tencentags.com
export AGR_ROLE_ARN='qcs::cam::uin/100000000001:roleName/replace-me'
export HTTPBIN_TOOL_NAME='httpbin-scaling-your-name'
export HTTPBIN_DEPLOYMENT_NAME='httpbin-scaling-your-name'

agr status

agr tool create \
  --region "$AGR_REGION" \
  --tool-name "$HTTPBIN_TOOL_NAME" \
  --tool-type custom \
  --persistent \
  --role-arn "$AGR_ROLE_ARN" \
  --network-configuration '{"NetworkMode":"PUBLIC"}' \
  --custom-configuration '{"Image":"ccr.ccs.tencentyun.com/ags.dev/go-httpbin:v2.25.0","ImageRegistryType":"personal","Command":["/bin/go-httpbin"],"Args":["-host","0.0.0.0","-port","8080"],"Env":[{"Name":"EXCLUDE_HEADERS","Value":"X-Access-Token"}],"Ports":[{"Name":"http","Port":8080,"Protocol":"TCP"}],"Resources":{"CPU":"200m","Memory":"500Mi"},"Probe":{"HttpGet":{"Path":"/status/200","Port":8080,"Scheme":"HTTP"},"ReadyTimeoutMs":30000,"ProbeTimeoutMs":1000,"ProbePeriodMs":3000,"SuccessThreshold":1,"FailureThreshold":10}}' \
  --wait
```

成功输出包含真实 Tool ID：

```text
ID:          sdt-********
Name:        httpbin-scaling-****
Type:        custom
Status:      ACTIVE
NetworkMode: PUBLIC
Created:     <masked-time>
```

复制 `ID`：

```bash
export HTTPBIN_TOOL_ID='sdt-replace-me'
```

## 2. 从零实例开始

初始配置允许没有活跃实例，最多扩到三个实例，每个实例一次只持有一个 Deployment 请求或连接 Lease。首次请求会触发按需启动。

```bash
agr deployment create \
  --region "$AGR_REGION" \
  --deployment-name "$HTTPBIN_DEPLOYMENT_NAME" \
  --tool-id "$HTTPBIN_TOOL_ID" \
  --scaling-configuration '{"MinInstanceCount":0,"MaxInstanceCount":3,"MaxInstanceRequestConcurrency":1}' \
  --lifecycle-configuration '{"IdleTimeoutSeconds":60,"IdleAction":"STOP"}'
```

成功输出中的伸缩摘要应为：

```text
Name:          httpbin-scaling-****
ID:            dpl-********
Status:        ACTIVE
Scaling:
  Min Instances:                0
  Max Instances:                3
  Max Requests per Instance:    1
Lifecycle:
  Idle Action:                  STOP
  Idle Timeout:                 1m
```

复制 Deployment ID：

```bash
export HTTPBIN_DEPLOYMENT_ID='dpl-replace-me'
```

## 3. 触发按需启动

先获取短期 Token：

```bash
agr api call AcquireDeploymentToken \
  --region "$AGR_REGION" \
  --request '{"DeploymentId":"'$HTTPBIN_DEPLOYMENT_ID'"}' \
  --output json
```

复制响应中的 `Data.Response.Response.Token`，然后发起请求并查询 Deployment：

```bash
export HTTPBIN_DEPLOYMENT_TOKEN='replace-with-token'

curl --fail-with-body --silent --show-error \
  --header "X-Access-Token: $HTTPBIN_DEPLOYMENT_TOKEN" \
  "https://8080-$HTTPBIN_DEPLOYMENT_ID.$AGR_REGION.agents.$AGR_DOMAIN/get"

agr deployment get "$HTTPBIN_DEPLOYMENT_ID" --region "$AGR_REGION"
```

第一次请求可能包含实例启动延迟。成功后，httpbin 返回类似结构：

```json
{
  "args": {},
  "headers": {
    "Host": "<masked-host>",
    "User-Agent": "curl/<version>"
  },
  "origin": "<masked-address>",
  "url": "https://<masked-host>/get"
}
```

## 4. 切换为常驻容量

`deployment update` 会完整替换伸缩对象，因此必须同时提供三个字段。下面把实例下限改为 `2`、上限改为 `4`，并允许每个实例同时持有 `10` 个请求或连接 Lease。

```bash
agr deployment update "$HTTPBIN_DEPLOYMENT_ID" \
  --region "$AGR_REGION" \
  --scaling-configuration '{"MinInstanceCount":2,"MaxInstanceCount":4,"MaxInstanceRequestConcurrency":10}'

agr deployment get "$HTTPBIN_DEPLOYMENT_ID" --region "$AGR_REGION"
```

配置会立即反映在查询结果中，实例容量则异步收敛：

```text
Scaling:
  Min Instances:                2
  Max Instances:                4
  Max Requests per Instance:    10
```

三个字段的含义是：

- `MinInstanceCount`：活跃实例下限；`0` 表示允许按需缩至零。
- `MaxInstanceCount`：活跃实例上限，不能小于下限。
- `MaxInstanceRequestConcurrency`：单个活跃实例同时持有的 Deployment 请求或连接 Lease 上限，不是整个 Deployment 的全局并发上限。

## 5. 清理资源

```bash
agr deployment delete "$HTTPBIN_DEPLOYMENT_ID" --region "$AGR_REGION"
agr instance list --tool-id "$HTTPBIN_TOOL_ID" --region "$AGR_REGION"
```

若仍有非 `STOPPED` 实例，逐个复制 ID 并删除：

```bash
export HTTPBIN_INSTANCE_ID='replace-with-instance-id'
agr instance delete "$HTTPBIN_INSTANCE_ID" --region "$AGR_REGION" --yes --wait
```

最后删除 Tool：

```bash
agr tool delete "$HTTPBIN_TOOL_ID" --region "$AGR_REGION" --yes --wait
```
