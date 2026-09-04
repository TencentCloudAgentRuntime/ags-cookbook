# Integrate DSH Brain and Hands with the Agent Runtime cloud Session service

This runnable example connects a DSH Deployment that runs the agent loop (the Brain role) and the Workspace Deployment it invokes (the Hands role) to Tencent Cloud Agent Runtime Session. The example stores conversation Events and the associated Deployment and affinity information in a Session, then uses that information to return to the original Hands workspace.

In this tutorial, Brain and Hands describe DSH component roles; both run on Agent Runtime Deployment. Brain runs the agent loop, while Hands hosts workspace file operations.

This is an independent integration example for demonstrating associations between Agent Runtime Session and Deployment. It does not replace the full application architecture in [`deepseek-harness/brain-hands`](../deepseek-harness/brain-hands/README.md).

This tutorial uses these terms consistently:

- **DSH conversation**: a conversation started by a user in DSH.
- **Agent Runtime Session**: the cloud Session that stores its Events and Deployment associations. In this example it uses the same ID as the DSH conversation.
- **Deployment affinity ID**: a Deployment data-plane routing identifier. Hands affinity is stored in Agent Runtime Session Metadata so later requests can return to the original workspace.

The included [`SessionPersistence` plugin](./brain/plugin/index.js) demonstrates one way to integrate DSH with Agent Runtime Session. You can use the example image directly, or refer to the plugin when adding Session creation, Event writes, and Deployment routing metadata to your own DSH image.

> This plugin is an integration example for normally completed writes, not a production-ready implementation of the complete DSH PersistenceBackend contract. Stable Event IDs support idempotent retries, but do not provide the transactional batch atomicity required by DSH `appendBatch()`. An interrupted write can leave an empty Session or a partial set of Events.

## Prerequisites

- Install `agr` v0.6.6 or later and configure Tencent Cloud credentials.
- Prepare the CAM role ARN required to create a custom Sandbox Tool.
- Use an account that can manage SessionSpaces, Sessions, Sandbox Tools, and Deployments, and append and read Events.
- Prepare a TokenHub API key. The example image includes provider settings for TokenHub and the `deepseek-v4-flash` model.
- Use Python 3.10 or later and install `jq`.

## 1. Configure the environment

The following example uses the Shanghai region:

```bash
export AGR_REGION=ap-shanghai
export AGR_DOMAIN=tencentags.com
export SESSION_API_ENDPOINT=ags.tencentcloudapi.com
```

These variables specify the deployment region, Deployment data-plane domain, and Agent Runtime Cloud API endpoint. Change `AGR_REGION` when deploying elsewhere.

Set resource names, image, and credentials:

```bash
export AGR_ROLE_ARN='qcs::cam::uin/100000000001:roleName/replace-me'
export SESSION_SPACE_NAME='dsh-brain-session-your-name'
export SESSION_USER_ID='dsh-demo-user'
export DSH_TOOL_NAME='dsh-brain-session-your-name'
export DSH_DEPLOYMENT_NAME='dsh-brain-session-your-name'
export DSH_SESSION_IMAGE='ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:v0.1.1-rc.2-ags.4-session.9'
export HANDS_TOOL_NAME='dsh-hands-session-your-name'
export HANDS_DEPLOYMENT_NAME='dsh-hands-session-your-name'
export HANDS_SESSION_IMAGE='ccr.ccs.tencentyun.com/ags.dev/hands-session:v0.1.0'

export TENCENTCLOUD_SECRET_ID='replace-me'
export TENCENTCLOUD_SECRET_KEY='replace-me'
export TOKENHUB_API_KEY='replace-me'
# Set this only for temporary credentials:
# export TENCENTCLOUD_SESSION_TOKEN='replace-me'

agr status --cloud-endpoint "$SESSION_API_ENDPOINT"
```

| Variable | Required | Description |
| --- | --- | --- |
| `AGR_REGION` | Yes | Region for Session, Tool, and Deployment. All three resource types must use the same region. |
| `AGR_DOMAIN` | Yes | Deployment data-plane domain. |
| `SESSION_API_ENDPOINT` | Yes | Cloud API endpoint used for Session, Tool, and Deployment operations. |
| `AGR_ROLE_ARN` | Yes | CAM role ARN used to create the custom Sandbox Tool. |
| `SESSION_SPACE_NAME` | When creating a SessionSpace | Name of the new SessionSpace. It is not used when you reuse an existing SessionSpace. |
| `SESSION_USER_ID` | Yes | User identifier that owns the example conversation. Keep it consistent when creating, querying, and deleting the Session. |
| `DSH_TOOL_NAME` | Yes | Name of the Sandbox Tool that runs the DSH image. Use a unique name. |
| `DSH_DEPLOYMENT_NAME` | Yes | Name of the Deployment that runs the DSH agent loop. Use a unique name. |
| `DSH_SESSION_IMAGE` | Yes | DSH image containing the Session example plugin. The default is the public image published for this tutorial. |
| `HANDS_TOOL_NAME` | Yes | Name of the Sandbox Tool that hosts the workspace service image. Use a unique name. |
| `HANDS_DEPLOYMENT_NAME` | Yes | Name of the Deployment that hosts the Hands workspace. Use a unique name. |
| `HANDS_SESSION_IMAGE` | Yes | Public Hands workspace service image used by this tutorial. |
| `TENCENTCLOUD_SECRET_ID` | Yes | Tencent Cloud SecretId used by the in-container plugin to call the Session Cloud API. It is separate from credentials configured for the local `agr` client. |
| `TENCENTCLOUD_SECRET_KEY` | Yes | SecretKey paired with the SecretId. |
| `TENCENTCLOUD_SESSION_TOKEN` | For temporary credentials | Session Token paired with temporary credentials. Leave it unset when using a long-term key. |
| `TOKENHUB_API_KEY` | Yes | TokenHub API key used by DSH to call the example model. |

For a compact end-to-end example, this tutorial passes Cloud API credentials to the plugin through Tool environment variables. Use a dedicated sub-account or temporary credentials with only the Session permissions required by this tutorial. Never use root-account credentials or store secrets in the image or repository.

## 2. Create or reuse a SessionSpace

A SessionSpace is the isolation boundary for Sessions. To reuse an existing SessionSpace:

```bash
export SESSION_SPACE_ID='space-replace-me'
```

Otherwise create a dedicated SessionSpace:

```bash
SESSION_SPACE_ID="$(
  agr api call CreateSessionSpace \
    --region "$AGR_REGION" \
    --cloud-endpoint "$SESSION_API_ENDPOINT" \
    --request '{
      "Name":"'$SESSION_SPACE_NAME'",
      "Description":"DSH Brain conversations"
    }' \
    --output json \
    --jq '.Data.Response.Response.SessionSpace.SpaceId'
)"
export SESSION_SPACE_ID
export SESSION_SPACE_CREATED_BY_TUTORIAL=1
echo "$SESSION_SPACE_ID"
```

## 3. Use the example image or your own DSH image

To run this tutorial, use the public example images specified by `DSH_SESSION_IMAGE` and `HANDS_SESSION_IMAGE`. The DSH image includes the tutorial's [`SessionPersistence` example plugin](./brain/plugin/index.js), which writes DSH Events and Deployment routing information to Agent Runtime Session.

If you use your own DSH image, refer to the plugin when connecting the DSH conversation lifecycle to Session creation, Event writes, and routing metadata persistence. Before using this approach in production, add failure recovery appropriate for your consistency requirements and satisfy the complete DSH PersistenceBackend contract.

## 4. Create the Workspace and DSH Deployments

First create the Hands Tool that hosts the workspace service:

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
    "Resources":{"CPU":"1","Memory":"1Gi"},
    "Probe":{"HttpGet":{"Path":"/health","Port":8080,"Scheme":"HTTP"},"ReadyTimeoutMs":30000,"ProbeTimeoutMs":3000,"ProbePeriodMs":3000,"SuccessThreshold":1,"FailureThreshold":10}
  }' \
  --wait

export HANDS_TOOL_ID='sdt-copy-from-response'
```

Create the Workspace Deployment that serves the Hands role. The example stores a distinct `EXCLUSIVE` affinity for each Session so later requests return to its workspace. This is not a user or tenant security boundary:

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

Create the Sandbox Tool that runs DSH:

```bash
export DSH_CUSTOM_CONFIGURATION="$(
  jq -n \
    --arg image "$DSH_SESSION_IMAGE" \
    --arg region "$AGR_REGION" \
    --arg domain "$AGR_DOMAIN" \
    --arg endpoint "$SESSION_API_ENDPOINT" \
    --arg space "$SESSION_SPACE_ID" \
    --arg user "$SESSION_USER_ID" \
    --arg deploymentName "$DSH_DEPLOYMENT_NAME" \
    --arg hands "$HANDS_DEPLOYMENT_ID" \
    --arg sid "$TENCENTCLOUD_SECRET_ID" \
    --arg skey "$TENCENTCLOUD_SECRET_KEY" \
    --arg token "${TENCENTCLOUD_SESSION_TOKEN:-}" \
    --arg tokenhub "$TOKENHUB_API_KEY" \
    '{
      Image:$image,
      ImageRegistryType:"personal",
      Command:["/opt/dsh/entrypoint.sh"],
      Args:[],
      Env:[
        {Name:"AGR_REGION",Value:$region},
        {Name:"AGR_DOMAIN",Value:$domain},
        {Name:"SESSION_API_ENDPOINT",Value:$endpoint},
        {Name:"SESSION_SPACE_ID",Value:$space},
        {Name:"SESSION_USER_ID",Value:$user},
        {Name:"DSH_DEPLOYMENT_NAME",Value:$deploymentName},
        {Name:"HANDS_DEPLOYMENT_ID",Value:$hands},
        {Name:"TENCENTCLOUD_SECRET_ID",Value:$sid},
        {Name:"TENCENTCLOUD_SECRET_KEY",Value:$skey},
        {Name:"TENCENTCLOUD_SESSION_TOKEN",Value:$token},
        {Name:"TOKENHUB_API_KEY",Value:$tokenhub}
      ],
      Ports:[{Name:"web",Port:3080,Protocol:"TCP"}],
      Resources:{CPU:"2",Memory:"4Gi"},
      Probe:{HttpGet:{Path:"/",Port:3080,Scheme:"HTTP"},ReadyTimeoutMs:30000,ProbeTimeoutMs:3000,ProbePeriodMs:3000,SuccessThreshold:1,FailureThreshold:10}
    }'
)"

agr tool create \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --tool-name "$DSH_TOOL_NAME" \
  --tool-type custom \
  --persistent \
  --role-arn "$AGR_ROLE_ARN" \
  --network-configuration '{"NetworkMode":"PUBLIC"}' \
  --custom-configuration "$DSH_CUSTOM_CONFIGURATION" \
  --wait

export DSH_TOOL_ID='sdt-copy-from-response'
```

Create the stateless DSH Deployment for the Brain role. It does not use affinity; the plugin resolves its ID from the configured Deployment name and writes it to Session Metadata:

```bash
agr deployment create \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --deployment-name "$DSH_DEPLOYMENT_NAME" \
  --tool-id "$DSH_TOOL_ID" \
  --scaling-configuration '{"MinInstanceCount":1,"MaxInstanceCount":4,"MaxInstanceRequestConcurrency":100}' \
  --lifecycle-configuration '{"IdleTimeoutSeconds":600,"IdleAction":"STOP"}'

export DSH_DEPLOYMENT_ID='dpl-copy-from-response'
```

Agent Runtime Session stores DSH conversation state, so the DSH Deployment does not depend on Brain affinity.

## 5. Configure the DSH Agent

Start a local proxy:

```bash
agr deployment proxy "$DSH_DEPLOYMENT_ID" 18080:3080 \
  --region "$AGR_REGION" \
  --domain "$AGR_DOMAIN" \
  --cloud-endpoint "$SESSION_API_ENDPOINT"
```

Open <http://127.0.0.1:18080>, start a new conversation, and confirm that the selected model is `tokenhub/deepseek-v4-flash`. The TokenHub API key is provided through the Tool environment, so every Brain replica uses the same model configuration. From this point on, every DSH conversation created through either the Web UI or the example script creates an Agent Runtime Session with the same ID, writes Events, and records the Brain Deployment ID automatically.

## 6. Validate Session association and Hands workspace recovery

You can operate the example manually through the Web UI or run the example script. The validation focuses on reading Deployment and affinity information from a Session and using it to return to the original Hands workspace.

### Trigger through the Web UI and verify from the command line

The Web UI creates the DSH conversation and triggers the Hands tool call. The following command-line steps simulate an application restoring Deployment routing information from Agent Runtime Session.

#### Trigger the task in the Web UI

Send this message in a new conversation:

```text
What is 37 + 58? Use hands_write_file to store the numerical answer in session-value.txt, then answer with only the number.
```

Expect `95` and a `hands_write_file` call in the trace. This call creates `session-value.txt` in the Hands workspace and writes the DSH and Workspace Deployment IDs, Hands affinity, and related Events to the corresponding Agent Runtime Session.

#### Verify the Session association in a terminal

After sending the message, use `DSH_DEPLOYMENT_ID` and `SESSION_USER_ID` in a terminal to find the newest Session associated with this DSH conversation:

```bash
DSH_SESSION_ID="$(
  agr api call DescribeSessions \
    --region "$AGR_REGION" \
    --cloud-endpoint "$SESSION_API_ENDPOINT" \
    --request '{
      "SpaceId":"'$SESSION_SPACE_ID'",
      "UserIds":["'$SESSION_USER_ID'"],
      "Filters":[{
        "Name":"metadata:example.com/brain-deployment-id",
        "Values":["'$DSH_DEPLOYMENT_ID'"]
      }],
      "Offset":0,
      "Limit":100
    }' \
    --output json \
    --jq '.Data.Response.Response.Sessions | max_by(.CreateTime) | .SessionId'
)"
export DSH_SESSION_ID
echo "$DSH_SESSION_ID"
```

Read the Session and extract its Workspace Deployment ID and Hands affinity from Metadata:

```bash
DSH_SESSION_JSON="$(
  agr api call DescribeSession \
    --region "$AGR_REGION" \
    --cloud-endpoint "$SESSION_API_ENDPOINT" \
    --request '{
      "SpaceId":"'$SESSION_SPACE_ID'",
      "UserId":"'$SESSION_USER_ID'",
      "SessionId":"'$DSH_SESSION_ID'"
    }' \
    --output json
)"

RESTORED_HANDS_DEPLOYMENT_ID="$(
  jq -r '.Data.Response.Response.Session.Metadata[]
    | select(.Name == "example.com/hands-deployment-id")
    | .Value' <<<"$DSH_SESSION_JSON"
)"
RESTORED_HANDS_AFFINITY_ID="$(
  jq -r '.Data.Response.Response.Session.Metadata[]
    | select(.Name == "example.com/hands-affinity-id")
    | .Value' <<<"$DSH_SESSION_JSON"
)"
export RESTORED_HANDS_DEPLOYMENT_ID RESTORED_HANDS_AFFINITY_ID
```

Confirm that both Deployments can be queried:

```bash
agr deployment get "$DSH_DEPLOYMENT_ID" \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT"

agr deployment get "$RESTORED_HANDS_DEPLOYMENT_ID" \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT"
```

Use the Workspace Deployment ID and affinity read from Session to request the Workspace Deployment directly and read the original file:

```bash
RESTORED_HANDS_TOKEN="$(
  agr api call AcquireDeploymentToken \
    --region "$AGR_REGION" \
    --cloud-endpoint "$SESSION_API_ENDPOINT" \
    --request '{"DeploymentId":"'$RESTORED_HANDS_DEPLOYMENT_ID'"}' \
    --output json \
    --jq '.Data.Response.Response.Token'
)"

curl --fail-with-body \
  -H "X-Access-Token: $RESTORED_HANDS_TOKEN" \
  -H "X-Tencent-Agr-Affinity-Id: $RESTORED_HANDS_AFFINITY_ID" \
  "https://8080-$RESTORED_HANDS_DEPLOYMENT_ID.$AGR_REGION.agents.$AGR_DOMAIN/files/read?path=session-value.txt"
```

Expect `exists: true` and `content: "95"`. This direct request comes from the command line, not the Web UI. It simulates an application using routing information stored in Session and proves that the request returns to the original Hands workspace.

Finally inspect the Events and confirm the same Session through the Workspace Deployment ID:

```bash
agr api call DescribeEvents \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --request '{
    "SpaceId":"'$SESSION_SPACE_ID'",
    "UserId":"'$SESSION_USER_ID'",
    "SessionId":"'$DSH_SESSION_ID'",
    "Offset":0,
    "Limit":100
  }' \
  --output json

agr api call DescribeSessions \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --request '{
    "SpaceId":"'$SESSION_SPACE_ID'",
    "Filters":[{
      "Name":"metadata:example.com/hands-deployment-id",
      "Values":["'$RESTORED_HANDS_DEPLOYMENT_ID'"]
    }],
    "Offset":0,
    "Limit":20
  }' \
  --output json
```

### Validate with the example script

Script validation does not depend on the Web UI or local proxy. Set these variables to the actual values created in sections 1–4:

```bash
export AGR_REGION='ap-shanghai'
export AGR_DOMAIN='tencentags.com'
export SESSION_API_ENDPOINT='ags.tencentcloudapi.com'
export SESSION_SPACE_ID='space-copy-from-response'
export SESSION_USER_ID='dsh-demo-user'
export DSH_DEPLOYMENT_ID='dpl-copy-from-dsh-response'
export HANDS_DEPLOYMENT_ID='dpl-copy-from-workspace-response'
```

Keep `AGR_REGION`, `AGR_DOMAIN`, and `SESSION_API_ENDPOINT` consistent with the values used to create the resources. The `agr` client also needs locally configured Tencent Cloud credentials for control-plane API calls. Then run the command from `examples/deployment-cookbook/session`:

```bash
python3 session_demo.py
```

The example performs the following operations:

1. Create a Session through DSH and invoke Hands to write a file.
2. Confirm that Session Metadata contains the Brain and Hands Deployment IDs and Hands affinity.
3. Query the same Session through both the DSH and Workspace Deployment IDs.
4. Query both Deployments and confirm that the resources recorded in Metadata exist.
5. Read the file directly with the Hands Deployment ID and affinity obtained from Session, confirming that the request returns to the original workspace.
6. Check actual `FunctionCall` and `FunctionResponse` Events in the Session.

Expected output:

```text
Session: <session-id>
  user: What is 37 + 58? Use hands_write_file to store ...
  assistant: 95
Agent Runtime persisted <count> DSH events
Hands Deployment: <deployment-id>
Restored session metadata routed the request to the original Hands workspace
```

## 7. Understand the validation result

This example uses `example.com/*` as customizable Metadata keys. Session stores the Brain Deployment ID, Hands Deployment ID, and Hands affinity. A caller can use the Hands Deployment ID and affinity read from Session on a later Hands request to route back to the corresponding workspace. Session stores the association; Deployment affinity performs the routing.

Hands workspace files live in the Hands Sandbox, not in Agent Runtime Session. `PAUSE` preserves that Sandbox filesystem. If the Sandbox is deleted, cannot be restored after `STOP`, or loses its underlying filesystem, Session Metadata can restore only the routing information; it cannot rebuild the workspace files.

The plugin populates standard fields according to Event semantics:

| DSH Event | Standard Session fields |
| --- | --- |
| User and assistant messages | `Author`, `Content` |
| Streaming text and reasoning chunks | `Content`, `Partial` |
| Tool calls and results | `FunctionCall`, `FunctionResponse` |
| Configuration state changes | `Actions.StateDelta` |
| Turn completion, interruption, and errors | `TurnComplete`, `Interrupted`, `ErrorCode`, `ErrorMessage` |

Successfully written DSH Events retain their raw data in `Extensions.dshEvent`. Hands Events use `FunctionCall` and `FunctionResponse` to record file operations and results. Both Event types belong to the same Session.

## 8. Clean up

```bash
delete_sessions_for_deployment() {
  metadata_name="$1"
  deployment_id="$2"
  agr api call DescribeSessions \
    --region "$AGR_REGION" \
    --cloud-endpoint "$SESSION_API_ENDPOINT" \
    --request '{"SpaceId":"'$SESSION_SPACE_ID'","Filters":[{"Name":"metadata:'"$metadata_name"'","Values":["'"$deployment_id"'"]}],"Offset":0,"Limit":100}' \
    --output json \
    --jq '.Data.Response.Response.Sessions[].SessionId' | while read -r session_id; do
      agr api call DeleteSession \
        --region "$AGR_REGION" \
        --cloud-endpoint "$SESSION_API_ENDPOINT" \
        --request '{"SpaceId":"'$SESSION_SPACE_ID'","UserId":"'$SESSION_USER_ID'","SessionId":"'"$session_id"'"}' \
        --output json
    done
}

delete_sessions_for_deployment \
  'example.com/brain-deployment-id' "$DSH_DEPLOYMENT_ID"

agr deployment delete "$DSH_DEPLOYMENT_ID" \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --wait

agr deployment delete "$HANDS_DEPLOYMENT_ID" \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --wait

for tool_id in "$DSH_TOOL_ID" "$HANDS_TOOL_ID"; do
  agr instance list \
    --tool-id "$tool_id" \
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
done

agr tool delete "$DSH_TOOL_ID" \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --yes \
  --wait

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

- Session writes fail with an authentication error: verify the `TENCENTCLOUD_*` variables in the Tool. Temporary credentials also require the Session Token.
- The SessionSpace does not exist: make sure `SESSION_SPACE_ID` and `AGR_REGION` belong to the same account and region.
- The Deployment or Session API is unreachable: check `AGR_REGION`, `AGR_DOMAIN`, and `SESSION_API_ENDPOINT`, and confirm that the Tool uses `PUBLIC` network mode.
- Model authentication fails: confirm that the TokenHub API key is valid and can access the selected model.
- The Deployment filter returns no Session: confirm that `session_demo.py` completed successfully and that Session Metadata contains the Brain Deployment ID.
- The DSH conversation times out: check the model configuration in the DSH Web UI and the Deployment status.
