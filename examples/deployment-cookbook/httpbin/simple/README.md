# Deploy httpbin with `agr`: the shortest complete workflow

This tutorial creates a custom Sandbox Tool and one Deployment, accesses httpbin through both a local debugging proxy and the production data-plane domain, and then removes the resources. The adjacent tutorials cover scaling, lifecycle, and session affinity separately.

Run every command directly in a terminal. Resource IDs are not extracted automatically: copy each real value from the output and set it as an environment variable before the next command. Account numbers, resource IDs, timestamps, and request IDs in sample output are masked.

## 1. Check the AGR configuration

Replace the role ARN and resource names. Keep the name suffix unique.

```bash
export AGR_REGION=ap-shanghai
export AGR_DOMAIN=tencentags.com
export AGR_ROLE_ARN='qcs::cam::uin/100000000001:roleName/replace-me'
export HTTPBIN_TOOL_NAME='httpbin-simple-your-name'
export HTTPBIN_DEPLOYMENT_NAME='httpbin-simple-your-name'

agr status
```

Expected output format:

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

## 2. Create the httpbin Sandbox Tool

The Tool uses a pinned image and exposes container port `8080` to Deployments. See [dockerfiles](../dockerfiles/README.md) for the image source and build instructions.

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

A successful response contains the real Tool ID:

```text
ID:          sdt-********
Name:        httpbin-simple-****
Type:        custom
Status:      ACTIVE
NetworkMode: PUBLIC
Created:     <masked-time>
RoleArn:     qcs::cam::uin/************:roleName/****
```

Copy `ID` and set it:

```bash
export HTTPBIN_TOOL_ID='sdt-replace-me'
```

## 3. Create and inspect the Deployment

Omitting optional configuration uses the service defaults for scaling and lifecycle.

```bash
agr deployment create \
  --region "$AGR_REGION" \
  --deployment-name "$HTTPBIN_DEPLOYMENT_NAME" \
  --tool-id "$HTTPBIN_TOOL_ID"
```

A successful response contains the real Deployment ID:

```text
Name:          httpbin-simple-****
ID:            dpl-********
Tool:          sdt-********
Status:        ACTIVE
Created:       <masked-time>
```

Copy `ID`, then inspect the configuration:

```bash
export HTTPBIN_DEPLOYMENT_ID='dpl-replace-me'

agr deployment get "$HTTPBIN_DEPLOYMENT_ID" --region "$AGR_REGION"
agr deployment list --region "$AGR_REGION"
```

## 4. Debug through a local proxy

`proxy` is only for local debugging. It occupies the current terminal and listens on `127.0.0.1:18080`:

```bash
agr deployment proxy "$HTTPBIN_DEPLOYMENT_ID" 18080:8080 --region "$AGR_REGION"
```

Expected output format:

```text
<masked-time> Proxy listening on 127.0.0.1:18080 (forwarding to https://8080-dpl-********.ap-shanghai.agents.tencentags.com)
Deployment proxy is recommended only for local debugging.
Forwarding from 127.0.0.1:18080 -> 8080
  Local:  http://127.0.0.1:18080
  Remote: https://8080-dpl-********.ap-shanghai.agents.tencentags.com

Press Ctrl+C to stop.
Affinity ID: <masked-affinity-id>
```

Call httpbin from another terminal:

```bash
curl --fail-with-body --silent --show-error http://127.0.0.1:18080/get
```

The response has httpbin's standard structure; actual headers and addresses vary:

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

After verification, press `Ctrl+C` in the proxy terminal.

## 5. Access the production data plane

Production clients should call `AcquireDeploymentToken` for a short-lived token and then access the Deployment data plane directly. The domain rule for an HTTP port is:

```text
https://{port}-{deployment-id}.{region}.agents.{data-plane-domain}
```

The default data-plane domain is `tencentags.com`; this example uses port `8080`.

```bash
agr api call AcquireDeploymentToken \
  --region "$AGR_REGION" \
  --request '{"DeploymentId":"'$HTTPBIN_DEPLOYMENT_ID'"}' \
  --output json
```

Response format:

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

Copy `Data.Response.Response.Token` and send a request. The Tool configures httpbin not to echo `X-Access-Token`.

```bash
export HTTPBIN_DEPLOYMENT_TOKEN='replace-with-token'

curl --fail-with-body --silent --show-error \
  --header "X-Access-Token: $HTTPBIN_DEPLOYMENT_TOKEN" \
  "https://8080-$HTTPBIN_DEPLOYMENT_ID.$AGR_REGION.agents.$AGR_DOMAIN/get"
```

The response should match the structure from the local proxy request.

## 6. Clean up

```bash
agr deployment delete "$HTTPBIN_DEPLOYMENT_ID" --region "$AGR_REGION"
agr instance list --tool-id "$HTTPBIN_TOOL_ID" --region "$AGR_REGION"
```

If any instance is not `STOPPED`, copy and delete each instance ID:

```bash
export HTTPBIN_INSTANCE_ID='replace-with-instance-id'
agr instance delete "$HTTPBIN_INSTANCE_ID" --region "$AGR_REGION" --yes --wait
```

Finally, delete the Tool:

```bash
agr tool delete "$HTTPBIN_TOOL_ID" --region "$AGR_REGION" --yes --wait
```
