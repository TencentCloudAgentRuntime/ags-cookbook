# Connect Hands Deployment sessions to the Agent Runtime cloud Session service

This tutorial shows how an application stores Hands Deployment session routing information in Tencent Cloud Agent Runtime Session. The example creates Session A and writes a file, routes back to the original workspace using only the Session A ID, and then creates Session B to verify that different Sessions use isolated workspaces. Before calling Hands, the client reads the Deployment ID and affinity from Session Metadata; afterward, it stores the latest affinity and execution Events. Workspace data remains in the Hands instance.

## Prerequisites

- Install `agr` v0.6.6 or later and configure Tencent Cloud credentials.
- Prepare the CAM role ARN required to create a custom Sandbox Tool.
- Use an account that can manage SessionSpaces, Sessions, Events, Sandbox Tools, and Deployments.
- Install Python 3.10 or later.

## 1. Configure the environment

This example uses Shanghai. Change `AGR_REGION` when deploying elsewhere:

```bash
export AGR_REGION=ap-shanghai
export AGR_DOMAIN=tencentags.com
export SESSION_API_ENDPOINT=ags.tencentcloudapi.com

export AGR_ROLE_ARN='qcs::cam::uin/100000000001:roleName/replace-me'
export SESSION_SPACE_NAME='hands-session-your-name'
export SESSION_USER_ID='hands-demo-user'
export HANDS_TOOL_NAME='hands-session-your-name'
export HANDS_DEPLOYMENT_NAME='hands-session-your-name'
export HANDS_SESSION_IMAGE='ccr.ccs.tencentyun.com/ags.dev/hands-session:v0.1.0'

agr status --cloud-endpoint "$SESSION_API_ENDPOINT"
```

| Variable | Required | Description |
| --- | --- | --- |
| `AGR_REGION` | Yes | Region for Session, Tool, and Deployment. All three resource types must use the same region. |
| `AGR_DOMAIN` | Yes | Data-plane domain for the Hands Deployment. |
| `SESSION_API_ENDPOINT` | Yes | Cloud API endpoint used for Session, Tool, and Deployment operations. |
| `AGR_ROLE_ARN` | Yes | CAM role ARN used to create the custom Sandbox Tool. |
| `SESSION_SPACE_NAME` | When creating a SessionSpace | Name of the new SessionSpace; unused when reusing an existing one. |
| `SESSION_USER_ID` | Yes | User identifier shared by both example Sessions. Keep it consistent when creating, restoring, and querying them. |
| `HANDS_TOOL_NAME` | Yes | Name of the Sandbox Tool that hosts the workspace service image. Use a unique name. |
| `HANDS_DEPLOYMENT_NAME` | Yes | Name of the Hands Deployment. Use a unique name. |
| `HANDS_SESSION_IMAGE` | Yes | Workspace service image used by this tutorial. The default image is published under `ags.dev`. |

Later steps set these resource IDs from command output:

| Variable | Source | Purpose |
| --- | --- | --- |
| `SESSION_SPACE_ID` | Created or selected SessionSpace | Selects the isolation space for Sessions. |
| `HANDS_TOOL_ID` | Tool creation output | Creates the Hands Deployment. |
| `HANDS_DEPLOYMENT_ID` | Deployment creation output | Makes the first Hands call and is stored in Session Metadata. |
| `HANDS_SESSION_A_ID` | Output of `hands_demo.py start` | Restores Session A's workspace. |
| `HANDS_SESSION_B_ID` | Output of `hands_demo.py isolate` | Queries and cleans up Session B created by the isolation check. |

## 2. Create or reuse a SessionSpace

To reuse an existing SessionSpace:

```bash
export SESSION_SPACE_ID='space-replace-me'
```

Otherwise create one for this tutorial:

```bash
agr api call CreateSessionSpace \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --request '{
    "Name":"'$SESSION_SPACE_NAME'",
    "Description":"Hands workspace sessions"
  }' \
  --output json

export SESSION_SPACE_ID='space-copy-from-response'
export SESSION_SPACE_CREATED_BY_TUTORIAL=1
```

## 3. Create the Hands Tool and Deployment

The example image provides a minimal workspace service that writes and reads files in instance-local storage:

```bash
agr tool create \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --tool-name "$HANDS_TOOL_NAME" \
  --tool-type custom \
  --persistent \
  --role-arn "$AGR_ROLE_ARN" \
  --network-configuration '{"NetworkMode":"PUBLIC"}' \
  --custom-configuration '{
    "Image":"'$HANDS_SESSION_IMAGE'",
    "ImageRegistryType":"personal",
    "Command":["python3","/opt/hands/workspace_server.py"],
    "Args":[],
    "Env":[],
    "Ports":[{"Name":"http","Port":8080,"Protocol":"TCP"}],
    "Resources":{"CPU":"200m","Memory":"500Mi"},
    "Probe":{"HttpGet":{"Path":"/health","Port":8080,"Scheme":"HTTP"},"ReadyTimeoutMs":30000,"ProbeTimeoutMs":1000,"ProbePeriodMs":3000,"SuccessThreshold":1,"FailureThreshold":10}
  }' \
  --wait

export HANDS_TOOL_ID='sdt-copy-from-response'
```

Create a Hands Deployment that can host two exclusive workspaces:

```bash
agr deployment create \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --deployment-name "$HANDS_DEPLOYMENT_NAME" \
  --tool-id "$HANDS_TOOL_ID" \
  --scaling-configuration '{"MinInstanceCount":0,"MaxInstanceCount":2,"MaxInstanceRequestConcurrency":1}' \
  --lifecycle-configuration '{"IdleTimeoutSeconds":600,"IdleAction":"PAUSE"}' \
  --affinity-configuration '{"Mode":"EXCLUSIVE","HeaderName":"X-Tencent-Agr-Affinity-Id"}'

export HANDS_DEPLOYMENT_ID='dpl-copy-from-response'
```

`EXCLUSIVE` assigns a dedicated instance to each affinity, isolating workspaces across Sessions. The client stores the Hands Deployment ID and returned affinity in `ae.tencentcloud.com/hands-deployment-id` and `ae.tencentcloud.com/hands-affinity-id`.

## 4. Session A: create a workspace

Run the first client process:

```bash
python3 hands_demo.py start
```

The process creates Session A, calls Hands to write `session-value.txt`, persists the returned affinity, and appends the call and result as Events. Copy its Session ID:

```bash
export HANDS_SESSION_A_ID='copy-from-output'
```

## 5. Session A: restore from a new process

Run the script again with only the Session A ID, without the Hands Deployment ID or affinity:

```bash
env -u HANDS_DEPLOYMENT_ID python3 hands_demo.py resume \
  --session-id "$HANDS_SESSION_A_ID"
```

The program restores both values from Session Metadata, reads `95` from the original workspace, and appends the read operation to the same Session. `Workspace recovery passed` confirms success.

## 6. Session B: verify an isolated workspace

Create Session B and make its first request to the same Hands Deployment without an affinity:

```bash
python3 hands_demo.py isolate \
  --reference-session-id "$HANDS_SESSION_A_ID"
```

Copy the new Session ID:

```bash
export HANDS_SESSION_B_ID='copy-from-output'
```

The program verifies that Session B receives a different affinity and cannot see Session A's file. `Workspace isolation passed` confirms success.

```text
Hands Deployment
├── Session A → affinity A → workspace A (session-value.txt exists)
└── Session B → affinity B → workspace B (session-value.txt does not exist)
```

## 7. Inspect associated Sessions and Events

Find both Sessions through the Hands Deployment ID:

```bash
agr api call DescribeSessions \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --request '{
    "SpaceId":"'$SESSION_SPACE_ID'",
    "Filters":[{
      "Name":"metadata:ae.tencentcloud.com/hands-deployment-id",
      "Values":["'$HANDS_DEPLOYMENT_ID'"]
    }],
    "Offset":0,
    "Limit":20
  }' \
  --output json
```

Both Sessions contain the same Hands Deployment ID and their own affinity. Inspect Session A's file calls and results:

```bash
agr api call DescribeEvents \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --request '{
    "SpaceId":"'$SESSION_SPACE_ID'",
    "UserId":"'$SESSION_USER_ID'",
    "SessionId":"'$HANDS_SESSION_A_ID'",
    "Offset":0,
    "Limit":100
  }' \
  --output json
```

`FunctionCall` and `FunctionResponse` in the Events record each file operation and its result.

## 8. Clean up

Delete both Sessions before deleting the Deployment and Tool:

```bash
for session_id in "$HANDS_SESSION_A_ID" "$HANDS_SESSION_B_ID"; do
  agr api call DeleteSession \
    --region "$AGR_REGION" \
    --cloud-endpoint "$SESSION_API_ENDPOINT" \
    --request '{"SpaceId":"'$SESSION_SPACE_ID'","UserId":"'$SESSION_USER_ID'","SessionId":"'$session_id'"}' \
    --output json
done

agr deployment delete "$HANDS_DEPLOYMENT_ID" \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --wait

agr instance list \
  --tool-id "$HANDS_TOOL_ID" \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --output json \
  --jq '.Data.Items[].InstanceId' | while read -r instance_id; do
    agr instance delete "$instance_id" \
      --region "$AGR_REGION" \
      --cloud-endpoint "$SESSION_API_ENDPOINT" \
      --yes \
      --wait
  done

agr tool delete "$HANDS_TOOL_ID" \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --yes \
  --wait
```

Delete the SessionSpace only if this tutorial created it:

```bash
if [ "${SESSION_SPACE_CREATED_BY_TUTORIAL:-0}" = 1 ]; then
  agr api call DeleteSessionSpace \
    --region "$AGR_REGION" \
    --cloud-endpoint "$SESSION_API_ENDPOINT" \
    --request '{"SpaceId":"'$SESSION_SPACE_ID'"}' \
    --output json
fi
```

## Troubleshooting

- Session A cannot restore the file: verify that Session Metadata contains both the Hands Deployment ID and affinity.
- Session B has no capacity: confirm that `MaxInstanceCount` is at least 2 and wait for Session A's first request to finish.
- Associated Sessions are missing: query with the Hands Deployment Metadata name, not the Brain Deployment Metadata name.
- SessionSpace deletion fails: delete its Sessions first.
