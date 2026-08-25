# 使用 `agr` 部署 httpbin：最短完整链路

本教程创建一个自定义 Sandbox Tool 和一个 Deployment，分别通过本地调试代理与生产数据面域名访问 httpbin，最后删除资源。弹性、生命周期和会话亲和由相邻教程独立讲解。

所有命令都直接在终端执行。资源 ID 不会自动提取；请从输出中复制真实值，并在下一步设置环境变量。示例输出中的账号、资源 ID、时间和请求 ID均已脱敏。

## 1. 检查 AGR 配置

把角色 ARN 和资源名称替换为自己的值。名称中的后缀应保持唯一。

```bash
export AGR_REGION=ap-shanghai
export AGR_DOMAIN=tencentags.com
export AGR_ROLE_ARN='qcs::cam::uin/100000000001:roleName/replace-me'
export HTTPBIN_TOOL_NAME='httpbin-simple-your-name'
export HTTPBIN_DEPLOYMENT_NAME='httpbin-simple-your-name'

agr status
```

预期输出格式如下：

```text
Region:       <local-default-region>
Domain:       tencentags.com
Output:       text
Config file:  <masked>/.agr/config.toml
Config load:  true

Auth:
  Secret ID:  configured (source: <masked>)
  Secret Key: configured (source: <masked>)
  Token:      not configured
```

## 2. 创建 httpbin Sandbox Tool

Tool 使用固定版本镜像，并向 Deployment 暴露容器的 `8080` 端口。镜像来源与构建方法见 [dockerfiles](../dockerfiles/README_zh.md)。

```bash
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
Name:        httpbin-simple-****
Type:        custom
Status:      ACTIVE
NetworkMode: PUBLIC
Created:     <masked-time>
RoleArn:     qcs::cam::uin/************:roleName/****
```

复制 `ID` 后设置环境变量：

```bash
export HTTPBIN_TOOL_ID='sdt-replace-me'
```

## 3. 创建并查询 Deployment

省略可选配置时，Deployment 使用服务默认的伸缩与生命周期设置。

```bash
agr deployment create \
  --region "$AGR_REGION" \
  --deployment-name "$HTTPBIN_DEPLOYMENT_NAME" \
  --tool-id "$HTTPBIN_TOOL_ID"
```

成功输出包含真实 Deployment ID：

```text
Name:          httpbin-simple-****
ID:            dpl-********
Tool:          sdt-********
Status:        ACTIVE
Created:       <masked-time>
```

复制 `ID`，再查询完整配置：

```bash
export HTTPBIN_DEPLOYMENT_ID='dpl-replace-me'

agr deployment get "$HTTPBIN_DEPLOYMENT_ID" --region "$AGR_REGION"
agr deployment list --region "$AGR_REGION"
```

## 4. 通过本地 proxy 调试

`proxy` 只适合本地调试。它会占用当前终端并监听 `127.0.0.1:18080`：

```bash
agr deployment proxy "$HTTPBIN_DEPLOYMENT_ID" 18080:8080 --region "$AGR_REGION"
```

预期输出格式如下：

```text
<masked-time> Proxy listening on 127.0.0.1:18080 (forwarding to https://8080-dpl-********.ap-shanghai.agents.tencentags.com)
Deployment proxy is recommended only for local debugging.
Forwarding from 127.0.0.1:18080 -> 8080
  Local:  http://127.0.0.1:18080
  Remote: https://8080-dpl-********.ap-shanghai.agents.tencentags.com

Press Ctrl+C to stop.
Affinity ID: <masked-affinity-id>
```

在另一个终端访问 httpbin：

```bash
curl --fail-with-body --silent --show-error http://127.0.0.1:18080/get
```

响应应具有 httpbin 的标准结构，实际 header 和地址会不同：

```json
{
  "args": {},
  "headers": {
    "Accept": "*/*",
    "Host": "<masked-host>",
    "User-Agent": "curl/<version>"
  },
  "origin": "<masked-address>",
  "url": "https://<masked-host>/get"
}
```

验证后回到 proxy 终端按 `Ctrl+C`。

## 5. 通过生产数据面访问

生产客户端应调用 `AcquireDeploymentToken` 获取短期 Token，再直接访问 Deployment 数据面。HTTP 端口的域名规则为：

```text
https://{port}-{deployment-id}.{region}.agents.{data-plane-domain}
```

默认数据面域名为 `tencentags.com`，本例端口为 `8080`。

```bash
agr api call AcquireDeploymentToken \
  --region "$AGR_REGION" \
  --request '{"DeploymentId":"'$HTTPBIN_DEPLOYMENT_ID'"}' \
  --output json
```

返回格式如下：

```json
{
  "Data": {
    "Response": {
      "Response": {
        "Token": "<masked-deployment-token>",
        "ExpiresAt": "<masked-expiration>"
      },
      "RequestId": "<masked-request-id>"
    }
  }
}
```

复制 `Data.Response.Response.Token` 后发起请求。Tool 已配置 httpbin 不回显 `X-Access-Token`。

```bash
export HTTPBIN_DEPLOYMENT_TOKEN='replace-with-token'

curl --fail-with-body --silent --show-error \
  --header "X-Access-Token: $HTTPBIN_DEPLOYMENT_TOKEN" \
  "https://8080-$HTTPBIN_DEPLOYMENT_ID.$AGR_REGION.agents.$AGR_DOMAIN/get"
```

响应结构应与本地 proxy 请求一致。

## 6. 清理资源

```bash
agr deployment delete "$HTTPBIN_DEPLOYMENT_ID" --region "$AGR_REGION"
agr instance list --tool-id "$HTTPBIN_TOOL_ID" --region "$AGR_REGION"
```

若仍有非 `STOPPED` 实例，逐个复制实例 ID 并删除：

```bash
export HTTPBIN_INSTANCE_ID='replace-with-instance-id'
agr instance delete "$HTTPBIN_INSTANCE_ID" --region "$AGR_REGION" --yes --wait
```

最后删除 Tool：

```bash
agr tool delete "$HTTPBIN_TOOL_ID" --region "$AGR_REGION" --yes --wait
```
