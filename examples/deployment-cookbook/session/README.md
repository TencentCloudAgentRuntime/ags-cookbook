# Deployment and Session Integration

This tutorial associates a Session with a stateful Deployment by storing the Deployment ID and the current affinity ID in Session Metadata. It then restores both values from the Session and uses them for a later Deployment request.

Session does not own or validate the referenced Deployment. Metadata stores opaque IDs only, and deleting either resource does not delete the other.

## Prerequisites

- Install `agr` v0.6.6 or later. Run `agr version` and `agr status` first.
- Prepare a SessionSpace and copy its ID from the console or API response.
- Prepare a CAM role ARN that allows AGR to pull the example CCR image.
- Use an account that can manage Sandbox Tools, Deployments, and Sessions and acquire Deployment tokens.

Run `make run` in this directory for navigation. The command does not create cloud resources.

## 1. Set environment variables

Replace every placeholder. Keep the Session and Deployment in the same region.

```bash
export AGR_REGION=ap-shanghai
export AGR_DOMAIN=tencentags.com
export AGR_ROLE_ARN='qcs::cam::uin/100000000001:roleName/replace-me'
export SESSION_SPACE_ID='space-replace-me'
export SESSION_USER_ID='user-demo'
export SESSION_ID='session-demo-your-name'
export SESSION_TOOL_NAME='httpbin-session-your-name'
export SESSION_DEPLOYMENT_NAME='httpbin-session-your-name'

agr status
```

## 2. Create an affinity-enabled Deployment

Create a persistent httpbin Tool:

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
    "Env":[{"Name":"EXCLUDE_HEADERS","Value":"X-Access-Token"}],
    "Ports":[{"Name":"http","Port":8080,"Protocol":"TCP"}],
    "Resources":{"CPU":"200m","Memory":"500Mi"},
    "Probe":{"HttpGet":{"Path":"/status/200","Port":8080,"Scheme":"HTTP"},"ReadyTimeoutMs":30000,"ProbeTimeoutMs":1000,"ProbePeriodMs":3000,"SuccessThreshold":1,"FailureThreshold":10}
  }' \
  --wait
```

Copy the Tool ID from the output:

```bash
export SESSION_TOOL_ID='sdt-replace-me'
```

Create a `BEST_EFFORT` Deployment. The long idle timeout makes the affinity reuse easy to observe:

```bash
agr deployment create \
  --region "$AGR_REGION" \
  --deployment-name "$SESSION_DEPLOYMENT_NAME" \
  --tool-id "$SESSION_TOOL_ID" \
  --scaling-configuration '{"MinInstanceCount":0,"MaxInstanceCount":2,"MaxInstanceRequestConcurrency":10}' \
  --lifecycle-configuration '{"IdleTimeoutSeconds":600,"IdleAction":"STOP"}' \
  --affinity-configuration '{"Mode":"BEST_EFFORT","HeaderName":"X-Session-Affinity"}'
```

Copy the Deployment ID:

```bash
export SESSION_DEPLOYMENT_ID='dpl-replace-me'
```

## 3. Create a Session linked to the Deployment

The predefined Metadata name gives the opaque Deployment ID platform semantics:

```bash
agr api call CreateSession \
  --region "$AGR_REGION" \
  --request '{
    "SpaceId":"'$SESSION_SPACE_ID'",
    "UserId":"'$SESSION_USER_ID'",
    "SessionId":"'$SESSION_ID'",
    "Title":"Deployment session demo",
    "Metadata":[
      {"Name":"ae.tencentcloud.com/hands-deployment-id","Value":"'$SESSION_DEPLOYMENT_ID'"}
    ]
  }' \
  --output json
```

Session accepts the ID as an opaque value. Creating the Session does not check that the Deployment exists.

## 4. Make the first Deployment request

Acquire a token:

```bash
agr api call AcquireDeploymentToken \
  --region "$AGR_REGION" \
  --request '{"DeploymentId":"'$SESSION_DEPLOYMENT_ID'"}' \
  --output json
```

Copy `Data.Response.Response.Token` without printing or committing it elsewhere:

```bash
export SESSION_DEPLOYMENT_TOKEN='replace-with-token'
```

Make the first request without an affinity header:

```bash
curl --include --silent --show-error \
  --header "X-Access-Token: $SESSION_DEPLOYMENT_TOKEN" \
  "https://8080-$SESSION_DEPLOYMENT_ID.$AGR_REGION.agents.$AGR_DOMAIN/headers"
```

Copy the returned `X-Session-Affinity` header:

```bash
export SESSION_AFFINITY_ID='replace-with-response-header'
```

## 5. Persist the current affinity in the Session

`ModifySession.Metadata` is a full replacement. Include the Deployment ID again when adding the affinity ID:

```bash
agr api call ModifySession \
  --region "$AGR_REGION" \
  --request '{
    "SpaceId":"'$SESSION_SPACE_ID'",
    "UserId":"'$SESSION_USER_ID'",
    "SessionId":"'$SESSION_ID'",
    "Metadata":[
      {"Name":"ae.tencentcloud.com/hands-deployment-id","Value":"'$SESSION_DEPLOYMENT_ID'"},
      {"Name":"ae.tencentcloud.com/hands-affinity-id","Value":"'$SESSION_AFFINITY_ID'"}
    ]
  }' \
  --output json
```

An affinity ID may exist only when the Hands Deployment ID also exists. Omitting `Metadata` keeps it unchanged; an empty array clears all Metadata; an empty string is a stored value, not a deletion instruction.

## 6. Restore and reuse the routing context

Read the Session:

```bash
agr api call DescribeSession \
  --region "$AGR_REGION" \
  --request '{"SpaceId":"'$SESSION_SPACE_ID'","UserId":"'$SESSION_USER_ID'","SessionId":"'$SESSION_ID'"}' \
  --output json
```

The response contains both Metadata entries. A new application process can restore these values, acquire a fresh Deployment token, and send the affinity back:

```bash
curl --include --silent --show-error \
  --header "X-Access-Token: $SESSION_DEPLOYMENT_TOKEN" \
  --header "X-Session-Affinity: $SESSION_AFFINITY_ID" \
  "https://8080-$SESSION_DEPLOYMENT_ID.$AGR_REGION.agents.$AGR_DOMAIN/headers"
```

With `BEST_EFFORT`, the platform prefers the previous target but may return a new affinity if that target is unavailable. Persist the newly returned value whenever it changes.

## 7. Find Sessions linked to a Deployment

Use a Metadata Filter to implement the reverse lookup:

```bash
agr api call DescribeSessions \
  --region "$AGR_REGION" \
  --request '{
    "SpaceId":"'$SESSION_SPACE_ID'",
    "Filters":[
      {"Name":"metadata:ae.tencentcloud.com/hands-deployment-id","Values":["'$SESSION_DEPLOYMENT_ID'"]}
    ],
    "Offset":0,
    "Limit":20
  }' \
  --output json
```

Values within one Filter are OR conditions; multiple Filters are AND conditions. Matching is exact.

## 8. Change or remove the association

When switching to another Hands Deployment, remove the old affinity or replace it with a different affinity belonging to the new request flow. To retain only the current Deployment association:

```bash
agr api call ModifySession \
  --region "$AGR_REGION" \
  --request '{
    "SpaceId":"'$SESSION_SPACE_ID'",
    "UserId":"'$SESSION_USER_ID'",
    "SessionId":"'$SESSION_ID'",
    "Metadata":[
      {"Name":"ae.tencentcloud.com/hands-deployment-id","Value":"'$SESSION_DEPLOYMENT_ID'"}
    ]
  }' \
  --output json
```

## 9. Clean up

Deleting a Session does not delete its Deployment, and deleting a Deployment does not delete linked Sessions. Clean up both explicitly:

```bash
agr api call DeleteSession \
  --region "$AGR_REGION" \
  --request '{"SpaceId":"'$SESSION_SPACE_ID'","UserId":"'$SESSION_USER_ID'","SessionId":"'$SESSION_ID'"}' \
  --output json

agr deployment delete "$SESSION_DEPLOYMENT_ID" --region "$AGR_REGION" --wait
agr tool delete "$SESSION_TOOL_ID" --region "$AGR_REGION" --yes --wait
```

Do not put Deployment tokens or affinity IDs in application logs, traces, screenshots, or committed files.

## Common failures

- `InvalidParameter.Metadata`: check for duplicate/empty names, size limits, or an affinity without a Hands Deployment ID.
- `ResourceNotFound`: verify that SessionSpace, Session, Tool, and Deployment IDs belong to the configured region and account.
- Deployment request returns a new affinity: this is allowed by `BEST_EFFORT`; persist the latest returned value.
- `ModifySession` removes an unrelated Metadata item: the API replaces the whole Metadata array, so read/merge/write all entries that must remain.
