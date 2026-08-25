# Session affinity for httpbin Deployments

This tutorial creates one shared httpbin Tool and three independent Deployments to compare every session-affinity mode. Affinity configuration cannot be changed with `deployment update`, so each mode uses a separate Deployment.

| Mode | When the target instance is unavailable | Instance ownership |
| --- | --- | --- |
| `BEST_EFFORT` | Another instance may be selected | Shared |
| `STRICT` | The request fails; it does not migrate | Shared |
| `EXCLUSIVE` | It does not migrate | One instance is dedicated to each affinity ID |

Requests and responses use `X-Httpbin-Affinity`. The example observes routing through response headers and HTTP status. It does not expose real hostnames or use extraction, validation, or polling scripts. Real values in sample output are masked.

## 1. Set variables and create the shared Tool

Replace `your-name` in every name with the same unique suffix.

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
  --custom-configuration '{"Image":"ccr.ccs.tencentyun.com/ags.dev/go-httpbin:v2.25.0","ImageRegistryType":"personal","Command":["/bin/go-httpbin"],"Args":["-host","0.0.0.0","-port","8080"],"Env":[{"Name":"EXCLUDE_HEADERS","Value":"X-Access-Token"}],"Ports":[{"Name":"http","Port":8080,"Protocol":"TCP"}],"Resources":{"CPU":"200m","Memory":"500Mi"},"Probe":{"HttpGet":{"Path":"/status/200","Port":8080,"Scheme":"HTTP"},"ReadyTimeoutMs":30000,"ProbeTimeoutMs":1000,"ProbePeriodMs":3000,"SuccessThreshold":1,"FailureThreshold":10}}' \
  --wait
```

A successful response contains the real Tool ID:

```text
ID:          sdt-********
Name:        httpbin-affinity-****
Type:        custom
Status:      ACTIVE
Created:     <masked-time>
```

Copy `ID`:

```bash
export HTTPBIN_TOOL_ID='sdt-replace-me'
```

## 2. Create three Deployments

All three Deployments use the same header name and a 30-second `STOP` idle policy so you can observe what happens when a target instance becomes unavailable. `EXCLUSIVE` permits at most three dedicated instances.

```bash
agr deployment create --region "$AGR_REGION" --deployment-name "$BEST_EFFORT_DEPLOYMENT_NAME" --tool-id "$HTTPBIN_TOOL_ID" --scaling-configuration '{"MinInstanceCount":0,"MaxInstanceCount":2,"MaxInstanceRequestConcurrency":10}' --lifecycle-configuration '{"IdleTimeoutSeconds":30,"IdleAction":"STOP"}' --affinity-configuration '{"Mode":"BEST_EFFORT","HeaderName":"X-Httpbin-Affinity"}'

agr deployment create --region "$AGR_REGION" --deployment-name "$STRICT_DEPLOYMENT_NAME" --tool-id "$HTTPBIN_TOOL_ID" --scaling-configuration '{"MinInstanceCount":0,"MaxInstanceCount":2,"MaxInstanceRequestConcurrency":10}' --lifecycle-configuration '{"IdleTimeoutSeconds":30,"IdleAction":"STOP"}' --affinity-configuration '{"Mode":"STRICT","HeaderName":"X-Httpbin-Affinity"}'

agr deployment create --region "$AGR_REGION" --deployment-name "$EXCLUSIVE_DEPLOYMENT_NAME" --tool-id "$HTTPBIN_TOOL_ID" --scaling-configuration '{"MinInstanceCount":0,"MaxInstanceCount":3,"MaxInstanceRequestConcurrency":1}' --lifecycle-configuration '{"IdleTimeoutSeconds":30,"IdleAction":"STOP"}' --affinity-configuration '{"Mode":"EXCLUSIVE","HeaderName":"X-Httpbin-Affinity"}'
```

Each successful response contains that Deployment's ID and affinity configuration. For example:

```text
Name:          httpbin-best-effort-****
ID:            dpl-********
Status:        ACTIVE
Affinity:
  Mode:                         BEST_EFFORT
  Header:                       X-Httpbin-Affinity
```

Copy the three IDs in create order:

```bash
export BEST_EFFORT_DEPLOYMENT_ID='dpl-replace-me'
export STRICT_DEPLOYMENT_ID='dpl-replace-me'
export EXCLUSIVE_DEPLOYMENT_ID='dpl-replace-me'
```

## 3. Acquire three Deployment tokens

A token is scoped to its target Deployment and cannot be shared across Deployments.

```bash
agr api call AcquireDeploymentToken --region "$AGR_REGION" --request '{"DeploymentId":"'$BEST_EFFORT_DEPLOYMENT_ID'"}' --output json
agr api call AcquireDeploymentToken --region "$AGR_REGION" --request '{"DeploymentId":"'$STRICT_DEPLOYMENT_ID'"}' --output json
agr api call AcquireDeploymentToken --region "$AGR_REGION" --request '{"DeploymentId":"'$EXCLUSIVE_DEPLOYMENT_ID'"}' --output json
```

Copy `Data.Response.Response.Token` from each response:

```bash
export BEST_EFFORT_TOKEN='replace-with-token'
export STRICT_TOKEN='replace-with-token'
export EXCLUSIVE_TOKEN='replace-with-token'
```

## 4. `BEST_EFFORT`: prefer reuse, allow migration

The first request omits the affinity header:

```bash
curl --include --silent --show-error \
  --header "X-Access-Token: $BEST_EFFORT_TOKEN" \
  "https://8080-$BEST_EFFORT_DEPLOYMENT_ID.$AGR_REGION.agents.$AGR_DOMAIN/headers"
```

The response headers contain the affinity ID assigned by the service:

```http
HTTP/2 200
content-type: application/json
x-httpbin-affinity: <masked-affinity-id>

{"headers":{"Accept":"*/*","Host":"<masked-host>","User-Agent":"curl/<version>"}}
```

Copy `X-Httpbin-Affinity` and return the same ID:

```bash
export BEST_EFFORT_AFFINITY_ID='replace-with-response-header'

curl --include --silent --show-error \
  --header "X-Access-Token: $BEST_EFFORT_TOKEN" \
  --header "X-Httpbin-Affinity: $BEST_EFFORT_AFFINITY_ID" \
  "https://8080-$BEST_EFFORT_DEPLOYMENT_ID.$AGR_REGION.agents.$AGR_DOMAIN/headers"
```

Idle for at least 30 seconds so the target instance stops, then repeat the request. `BEST_EFFORT` may select another instance and should still return success; the returned affinity ID may change.

## 5. `STRICT`: require reuse, forbid migration

Acquire and copy an affinity ID:

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

Idle for at least 30 seconds so the target instance stops, then repeat the same request. `STRICT` returns a non-2xx response instead of choosing a new instance. The exact status and error text may vary by service version; the response has this shape:

```http
HTTP/2 <non-2xx-status>
content-type: application/json

{"Response":{"Error":{"Code":"<masked-code>","Message":"<masked-message>"},"RequestId":"<masked-request-id>"}}
```

## 6. `EXCLUSIVE`: one dedicated instance per affinity ID

Send two requests without affinity headers:

```bash
curl --include --silent --show-error --header "X-Access-Token: $EXCLUSIVE_TOKEN" "https://8080-$EXCLUSIVE_DEPLOYMENT_ID.$AGR_REGION.agents.$AGR_DOMAIN/headers"
curl --include --silent --show-error --header "X-Access-Token: $EXCLUSIVE_TOKEN" "https://8080-$EXCLUSIVE_DEPLOYMENT_ID.$AGR_REGION.agents.$AGR_DOMAIN/headers"
```

The two responses should contain different affinity IDs. Copy and return each one:

```bash
export EXCLUSIVE_AFFINITY_ID_A='replace-with-first-response-header'
export EXCLUSIVE_AFFINITY_ID_B='replace-with-second-response-header'

curl --include --silent --show-error --header "X-Access-Token: $EXCLUSIVE_TOKEN" --header "X-Httpbin-Affinity: $EXCLUSIVE_AFFINITY_ID_A" "https://8080-$EXCLUSIVE_DEPLOYMENT_ID.$AGR_REGION.agents.$AGR_DOMAIN/headers"
curl --include --silent --show-error --header "X-Access-Token: $EXCLUSIVE_TOKEN" --header "X-Httpbin-Affinity: $EXCLUSIVE_AFFINITY_ID_B" "https://8080-$EXCLUSIVE_DEPLOYMENT_ID.$AGR_REGION.agents.$AGR_DOMAIN/headers"
```

The IDs own separate, non-shared, non-migrating instances. The instance ceiling therefore also limits simultaneous exclusive sessions.

## 7. Clean up

```bash
agr deployment delete "$BEST_EFFORT_DEPLOYMENT_ID" --region "$AGR_REGION"
agr deployment delete "$STRICT_DEPLOYMENT_ID" --region "$AGR_REGION"
agr deployment delete "$EXCLUSIVE_DEPLOYMENT_ID" --region "$AGR_REGION"
agr instance list --tool-id "$HTTPBIN_TOOL_ID" --region "$AGR_REGION"
```

If any instance is not `STOPPED`, copy and delete each instance ID:

```bash
export HTTPBIN_INSTANCE_ID='replace-with-instance-id'
agr instance delete "$HTTPBIN_INSTANCE_ID" --region "$AGR_REGION" --yes --wait
```

Finally, delete the shared Tool:

```bash
agr tool delete "$HTTPBIN_TOOL_ID" --region "$AGR_REGION" --yes --wait
```
