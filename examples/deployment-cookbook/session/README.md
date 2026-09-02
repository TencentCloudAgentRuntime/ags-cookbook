# Deployment and Session Integration

This tutorial demonstrates how Brain and Hands Deployments work with their own Sessions. The Brain Session records the Brain Deployment ID. The Hands Session records the Hands Deployment ID and current affinity ID so a later request can restore the same Hands routing context.

Session Metadata stores opaque IDs. Sessions and Deployments have independent lifecycles, so deleting one does not delete the other.

## Prerequisites

- Install `agr` v0.6.6 or later. Run `agr version` and `agr status` first.
- Prepare a SessionSpace and copy its ID from the console or API response.
- Prepare a CAM role ARN that allows AGR to pull the example CCR image.
- Use an account that can manage Sandbox Tools, Deployments, and Sessions and acquire Deployment tokens.

Run `make run` in this directory for navigation. The command does not create cloud resources.

## 1. Set environment variables

Replace every placeholder. Keep both Sessions and Deployments in the same region.

```bash
export AGR_REGION=ap-shanghai
export AGR_DOMAIN=tencentags.com
export AGR_ROLE_ARN='qcs::cam::uin/100000000001:roleName/replace-me'
export SESSION_SPACE_ID='space-replace-me'
export SESSION_USER_ID='user-demo'
export BRAIN_SESSION_ID='brain-session-your-name'
export HANDS_SESSION_ID='hands-session-your-name'
export SESSION_TOOL_NAME='httpbin-session-your-name'
export BRAIN_DEPLOYMENT_NAME='httpbin-brain-your-name'
export HANDS_DEPLOYMENT_NAME='httpbin-hands-your-name'

agr status
```

## 2. Create a shared Tool

Both Deployments use one persistent httpbin Tool. `USE_REAL_HOSTNAME` makes `/hostname` return the backend hostname so the Hands routing reuse is visible.

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
    "Env":[
      {"Name":"EXCLUDE_HEADERS","Value":"X-Access-Token"},
      {"Name":"USE_REAL_HOSTNAME","Value":"true"}
    ],
    "Ports":[{"Name":"http","Port":8080,"Protocol":"TCP"}],
    "Resources":{"CPU":"200m","Memory":"500Mi"},
    "Probe":{"HttpGet":{"Path":"/status/200","Port":8080,"Scheme":"HTTP"},"ReadyTimeoutMs":30000,"ProbeTimeoutMs":1000,"ProbePeriodMs":3000,"SuccessThreshold":1,"FailureThreshold":10}
  }' \
  --wait
```

Copy the Tool ID:

```bash
export SESSION_TOOL_ID='sdt-replace-me'
```

## 3. Create Brain and Hands Deployments

Create the Brain Deployment:

```bash
agr deployment create \
  --region "$AGR_REGION" \
  --deployment-name "$BRAIN_DEPLOYMENT_NAME" \
  --tool-id "$SESSION_TOOL_ID" \
  --scaling-configuration '{"MinInstanceCount":0,"MaxInstanceCount":2,"MaxInstanceRequestConcurrency":10}' \
  --lifecycle-configuration '{"IdleTimeoutSeconds":600,"IdleAction":"STOP"}'
```

Create the affinity-enabled Hands Deployment:

```bash
agr deployment create \
  --region "$AGR_REGION" \
  --deployment-name "$HANDS_DEPLOYMENT_NAME" \
  --tool-id "$SESSION_TOOL_ID" \
  --scaling-configuration '{"MinInstanceCount":0,"MaxInstanceCount":2,"MaxInstanceRequestConcurrency":10}' \
  --lifecycle-configuration '{"IdleTimeoutSeconds":600,"IdleAction":"STOP"}' \
  --affinity-configuration '{"Mode":"BEST_EFFORT","HeaderName":"X-Session-Affinity"}'
```

Copy both Deployment IDs:

```bash
export BRAIN_DEPLOYMENT_ID='dpl-replace-me'
export HANDS_DEPLOYMENT_ID='dpl-replace-me'
```

## 4. Create separate Brain and Hands Sessions

Create the Brain Session with its Brain Deployment ID:

```bash
agr api call CreateSession \
  --region "$AGR_REGION" \
  --request '{
    "SpaceId":"'$SESSION_SPACE_ID'",
    "UserId":"'$SESSION_USER_ID'",
    "SessionId":"'$BRAIN_SESSION_ID'",
    "Title":"Brain session demo",
    "Metadata":[
      {"Name":"ae.tencentcloud.com/brain-deployment-id","Value":"'$BRAIN_DEPLOYMENT_ID'"}
    ]
  }' \
  --output json
```

Create the Hands Session with its Hands Deployment ID:

```bash
agr api call CreateSession \
  --region "$AGR_REGION" \
  --request '{
    "SpaceId":"'$SESSION_SPACE_ID'",
    "UserId":"'$SESSION_USER_ID'",
    "SessionId":"'$HANDS_SESSION_ID'",
    "Title":"Hands session demo",
    "Metadata":[
      {"Name":"ae.tencentcloud.com/hands-deployment-id","Value":"'$HANDS_DEPLOYMENT_ID'"}
    ]
  }' \
  --output json
```

Creating either Session does not check that the referenced Deployment exists.

## 5. Access the Brain Deployment

Acquire and copy the Brain Deployment token:

```bash
agr api call AcquireDeploymentToken \
  --region "$AGR_REGION" \
  --request '{"DeploymentId":"'$BRAIN_DEPLOYMENT_ID'"}' \
  --output json

export BRAIN_DEPLOYMENT_TOKEN='replace-with-token'
```

Call the Brain Deployment:

```bash
curl --silent --show-error \
  --header "X-Access-Token: $BRAIN_DEPLOYMENT_TOKEN" \
  "https://8080-$BRAIN_DEPLOYMENT_ID.$AGR_REGION.agents.$AGR_DOMAIN/hostname"
```

The response identifies the Brain backend, for example:

```json
{"hostname":"brain-backend-a"}
```

## 6. Access Hands and persist its affinity

Acquire and copy the Hands Deployment token:

```bash
agr api call AcquireDeploymentToken \
  --region "$AGR_REGION" \
  --request '{"DeploymentId":"'$HANDS_DEPLOYMENT_ID'"}' \
  --output json

export HANDS_DEPLOYMENT_TOKEN='replace-with-token'
```

Make the first Hands request without an affinity header:

```bash
curl --include --silent --show-error \
  --header "X-Access-Token: $HANDS_DEPLOYMENT_TOKEN" \
  "https://8080-$HANDS_DEPLOYMENT_ID.$AGR_REGION.agents.$AGR_DOMAIN/hostname"
```

Record both values from the response:

```text
X-Session-Affinity: <first-affinity-id>
{"hostname":"hands-backend-a"}
```

Copy the affinity ID:

```bash
export HANDS_AFFINITY_ID='replace-with-response-header'
```

`ModifySession.Metadata` is a full replacement. Include the Hands Deployment ID again when adding the affinity ID:

```bash
agr api call ModifySession \
  --region "$AGR_REGION" \
  --request '{
    "SpaceId":"'$SESSION_SPACE_ID'",
    "UserId":"'$SESSION_USER_ID'",
    "SessionId":"'$HANDS_SESSION_ID'",
    "Metadata":[
      {"Name":"ae.tencentcloud.com/hands-deployment-id","Value":"'$HANDS_DEPLOYMENT_ID'"},
      {"Name":"ae.tencentcloud.com/hands-affinity-id","Value":"'$HANDS_AFFINITY_ID'"}
    ]
  }' \
  --output json
```

Hands affinity may exist only when the Hands Deployment ID also exists. Omitting `Metadata` keeps it unchanged; an empty array clears all Metadata; an empty string is a stored value, not a deletion instruction.

## 7. Restore both Sessions and demonstrate Hands reuse

Read the Brain Session and restore `BRAIN_DEPLOYMENT_ID`:

```bash
agr api call DescribeSession \
  --region "$AGR_REGION" \
  --request '{"SpaceId":"'$SESSION_SPACE_ID'","UserId":"'$SESSION_USER_ID'","SessionId":"'$BRAIN_SESSION_ID'"}' \
  --output json
```

Read the Hands Session and restore `HANDS_DEPLOYMENT_ID` and `HANDS_AFFINITY_ID`:

```bash
agr api call DescribeSession \
  --region "$AGR_REGION" \
  --request '{"SpaceId":"'$SESSION_SPACE_ID'","UserId":"'$SESSION_USER_ID'","SessionId":"'$HANDS_SESSION_ID'"}' \
  --output json
```

Send the restored affinity back to Hands:

```bash
curl --include --silent --show-error \
  --header "X-Access-Token: $HANDS_DEPLOYMENT_TOKEN" \
  --header "X-Session-Affinity: $HANDS_AFFINITY_ID" \
  "https://8080-$HANDS_DEPLOYMENT_ID.$AGR_REGION.agents.$AGR_DOMAIN/hostname"
```

Compare the two Hands responses:

```text
                       First request       Restored request
X-Session-Affinity     <affinity-a>        <affinity-a>
hostname               hands-backend-a     hands-backend-a
```

Matching affinity and hostname show that the restored routing context reached the same Hands backend. With `BEST_EFFORT`, the platform may select a new target if the old one becomes unavailable; persist the newly returned affinity whenever it changes.

## 8. Find Sessions linked to each Deployment

Find the Brain Session:

```bash
agr api call DescribeSessions \
  --region "$AGR_REGION" \
  --request '{
    "SpaceId":"'$SESSION_SPACE_ID'",
    "Filters":[{"Name":"metadata:ae.tencentcloud.com/brain-deployment-id","Values":["'$BRAIN_DEPLOYMENT_ID'"]}],
    "Offset":0,
    "Limit":20
  }' \
  --output json
```

Find the Hands Session:

```bash
agr api call DescribeSessions \
  --region "$AGR_REGION" \
  --request '{
    "SpaceId":"'$SESSION_SPACE_ID'",
    "Filters":[{"Name":"metadata:ae.tencentcloud.com/hands-deployment-id","Values":["'$HANDS_DEPLOYMENT_ID'"]}],
    "Offset":0,
    "Limit":20
  }' \
  --output json
```

Values within one Filter are OR conditions; multiple Filters are AND conditions. Matching is exact.

## 9. Remove the current Hands affinity

To retain the Hands Deployment association while removing the affinity, replace the full Metadata array:

```bash
agr api call ModifySession \
  --region "$AGR_REGION" \
  --request '{
    "SpaceId":"'$SESSION_SPACE_ID'",
    "UserId":"'$SESSION_USER_ID'",
    "SessionId":"'$HANDS_SESSION_ID'",
    "Metadata":[
      {"Name":"ae.tencentcloud.com/hands-deployment-id","Value":"'$HANDS_DEPLOYMENT_ID'"}
    ]
  }' \
  --output json
```

When switching to another Hands Deployment, remove the old affinity or replace it with a different affinity obtained from the new request flow.

## 10. Clean up

Delete both Sessions, both Deployments, and the shared Tool explicitly:

```bash
agr api call DeleteSession \
  --region "$AGR_REGION" \
  --request '{"SpaceId":"'$SESSION_SPACE_ID'","UserId":"'$SESSION_USER_ID'","SessionId":"'$BRAIN_SESSION_ID'"}' \
  --output json

agr api call DeleteSession \
  --region "$AGR_REGION" \
  --request '{"SpaceId":"'$SESSION_SPACE_ID'","UserId":"'$SESSION_USER_ID'","SessionId":"'$HANDS_SESSION_ID'"}' \
  --output json

agr deployment delete "$BRAIN_DEPLOYMENT_ID" --region "$AGR_REGION" --wait
agr deployment delete "$HANDS_DEPLOYMENT_ID" --region "$AGR_REGION" --wait
agr tool delete "$SESSION_TOOL_ID" --region "$AGR_REGION" --yes --wait
```

Do not put Deployment tokens or affinity IDs in application logs, traces, screenshots, or committed files.

## Common failures

- `InvalidParameter.Metadata`: check for duplicate/empty names, size limits, or a Hands affinity without a Hands Deployment ID.
- `ResourceNotFound`: verify that SessionSpace, Sessions, Tool, and Deployments belong to the configured region and account.
- The Hands request returns a new affinity or hostname: `BEST_EFFORT` allows migration when the previous target is unavailable; persist the latest affinity.
- `ModifySession` removes an unrelated Metadata item: the API replaces the whole Metadata array, so read, merge, and write every item that must remain.
