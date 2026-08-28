# Idle lifecycle for an httpbin Deployment

This tutorial creates an independent httpbin Deployment, observes idle `STOP`, and then switches to `PAUSE` with a full configuration update. `STOP` releases the Sandbox Instance; `PAUSE` preserves instance state for resumption. Because httpbin is stateless, the example verifies instance state and request resumption rather than treating response content as proof of persistence.

Run every command directly in a terminal. Copy resource IDs and tokens manually, and time each wait yourself; the document contains no extraction, polling, or waiting scripts. Real values in sample output are masked.

## 1. Set variables and create the Tool

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

A successful response contains the real Tool ID:

```text
ID:          sdt-********
Name:        httpbin-lifecycle-****
Type:        custom
Status:      ACTIVE
Created:     <masked-time>
```

Copy `ID`:

```bash
export HTTPBIN_TOOL_ID='sdt-replace-me'
```

## 2. Stop after idling

`MinInstanceCount=0` lets an idle instance leave active capacity. After 30 idle seconds, `STOP` releases it.

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

The successful response should include:

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

Copy the Deployment ID and acquire a short-lived token:

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

## 3. Activate an instance and observe `STOP`

Send one request to start an instance:

```bash
curl --fail-with-body --silent --show-error \
  --header "X-Access-Token: $HTTPBIN_DEPLOYMENT_TOKEN" \
  "https://8080-$HTTPBIN_DEPLOYMENT_ID.$AGR_REGION.agents.$AGR_DOMAIN/get"

agr instance list --tool-id "$HTTPBIN_TOOL_ID" --region "$AGR_REGION"
```

After the request succeeds, the list contains an active instance:

```text
ID                    TOOL                         STATUS   TIMEOUT  EXPIRES  MOUNTS  CREATED
<masked-instance-id>  httpbin-lifecycle-****       RUNNING  0s       -        -       <masked-time>
```

Stop accessing the Deployment for at least 30 seconds, then inspect the instances. Reclamation is asynchronous and may take slightly longer than the configured timeout:

```bash
agr instance list --tool-id "$HTTPBIN_TOOL_ID" --region "$AGR_REGION"
```

The original instance eventually becomes `STOPPED`:

```text
ID                    TOOL                         STATUS   TIMEOUT  EXPIRES  MOUNTS  CREATED
<masked-instance-id>  httpbin-lifecycle-****       STOPPED  0s       -        -       <masked-time>
```

Another request starts capacity on demand:

```bash
curl --fail-with-body --silent --show-error \
  --header "X-Access-Token: $HTTPBIN_DEPLOYMENT_TOKEN" \
  "https://8080-$HTTPBIN_DEPLOYMENT_ID.$AGR_REGION.agents.$AGR_DOMAIN/get"
```

## 4. Switch to pausing after idle

A lifecycle update replaces the object in full, so supply both the timeout and the action. After the update, send a request so the instance is active under the new policy.

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

The query should show the new policy:

```text
Lifecycle:
  Idle Action:                  PAUSE
  Idle Timeout:                 30s
```

Stop accessing the Deployment again for at least 30 seconds, then inspect the instances:

```bash
agr instance list --tool-id "$HTTPBIN_TOOL_ID" --region "$AGR_REGION"
```

The instance eventually becomes `PAUSED`:

```text
ID                    TOOL                         STATUS  TIMEOUT  EXPIRES  MOUNTS  CREATED
<masked-instance-id>  httpbin-lifecycle-****       PAUSED  0s       -        -       <masked-time>
```

Send the same request again to restore available capacity. `PAUSE` preserves instance state but does not guarantee fixed resume latency.

```bash
curl --fail-with-body --silent --show-error \
  --header "X-Access-Token: $HTTPBIN_DEPLOYMENT_TOKEN" \
  "https://8080-$HTTPBIN_DEPLOYMENT_ID.$AGR_REGION.agents.$AGR_DOMAIN/get"
```

## 5. Clean up

```bash
agr deployment delete "$HTTPBIN_DEPLOYMENT_ID" --region "$AGR_REGION" --wait
agr instance list --tool-id "$HTTPBIN_TOOL_ID" --region "$AGR_REGION"
```

A paused instance may remain visible after the `PAUSE` experiment. Copy and delete each non-`STOPPED` instance ID:

```bash
export HTTPBIN_INSTANCE_ID='replace-with-instance-id'
agr instance delete "$HTTPBIN_INSTANCE_ID" --region "$AGR_REGION" --yes --wait
```

Finally, delete the Tool:

```bash
agr tool delete "$HTTPBIN_TOOL_ID" --region "$AGR_REGION" --yes --wait
```
