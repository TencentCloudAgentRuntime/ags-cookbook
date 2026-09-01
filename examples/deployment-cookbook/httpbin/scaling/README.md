# Scaling an httpbin Deployment

This tutorial creates an independent httpbin Tool and Deployment, starts with `MinInstanceCount=0` to observe on-demand startup, and then updates the Deployment to keep two instances warm while changing the instance ceiling and per-instance request-concurrency lease. It demonstrates configuration and instance state; it is not a load test.

Run every command directly in a terminal. Copy resource IDs and tokens manually; the document contains no extraction or polling scripts. Real values in sample output are masked.

## 1. Set variables and create the Tool

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
Name:        httpbin-scaling-****
Type:        custom
Status:      ACTIVE
NetworkMode: PUBLIC
Created:     <masked-time>
```

Copy `ID`:

```bash
export HTTPBIN_TOOL_ID='sdt-replace-me'
```

## 2. Start with zero instances

The initial configuration permits zero active instances, scales to at most three, and lets each instance hold one Deployment request or connection lease at a time. The first request triggers on-demand startup.

```bash
agr deployment create \
  --region "$AGR_REGION" \
  --deployment-name "$HTTPBIN_DEPLOYMENT_NAME" \
  --tool-id "$HTTPBIN_TOOL_ID" \
  --scaling-configuration '{
    "MinInstanceCount": 0,
    "MaxInstanceCount": 3,
    "MaxInstanceRequestConcurrency": 1
  }' \
  --lifecycle-configuration '{
    "IdleTimeoutSeconds": 60,
    "IdleAction": "STOP"
  }'
```

The successful response should contain this scaling summary:

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

Copy the Deployment ID:

```bash
export HTTPBIN_DEPLOYMENT_ID='dpl-replace-me'
```

## 3. Trigger on-demand startup

Acquire a short-lived token:

```bash
agr api call AcquireDeploymentToken \
  --region "$AGR_REGION" \
  --request '{"DeploymentId":"'$HTTPBIN_DEPLOYMENT_ID'"}' \
  --output json
```

Copy `Data.Response.Response.Token`, then send a request and inspect the Deployment:

```bash
export HTTPBIN_DEPLOYMENT_TOKEN='replace-with-token'

curl --fail-with-body --silent --show-error \
  --header "X-Access-Token: $HTTPBIN_DEPLOYMENT_TOKEN" \
  "https://8080-$HTTPBIN_DEPLOYMENT_ID.$AGR_REGION.agents.$AGR_DOMAIN/get"

agr deployment get "$HTTPBIN_DEPLOYMENT_ID" --region "$AGR_REGION"
```

The first request may include instance startup latency. A successful response has this shape:

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

## 4. Switch to warm capacity

`deployment update` replaces the scaling object in full, so all three fields must be supplied. The following update raises the instance floor to `2`, the ceiling to `4`, and the per-instance request or connection lease to `10`.

```bash
agr deployment update "$HTTPBIN_DEPLOYMENT_ID" \
  --region "$AGR_REGION" \
  --scaling-configuration '{
    "MinInstanceCount": 2,
    "MaxInstanceCount": 4,
    "MaxInstanceRequestConcurrency": 10
  }'

agr deployment get "$HTTPBIN_DEPLOYMENT_ID" --region "$AGR_REGION"
```

The query reflects the configuration immediately; instance capacity converges asynchronously:

```text
Scaling:
  Min Instances:                2
  Max Instances:                4
  Max Requests per Instance:    10
```

The fields mean:

- `MinInstanceCount`: active-instance floor; `0` permits scale-to-zero.
- `MaxInstanceCount`: active-instance ceiling, which cannot be lower than the floor.
- `MaxInstanceRequestConcurrency`: simultaneous Deployment request or connection leases per active instance, not a global concurrency limit for the Deployment.

## 5. Clean up

```bash
agr deployment delete "$HTTPBIN_DEPLOYMENT_ID" --region "$AGR_REGION" --wait
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
