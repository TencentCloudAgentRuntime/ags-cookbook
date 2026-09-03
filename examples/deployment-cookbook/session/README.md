# Integrate DSH Brain and Hands with the Agent Runtime cloud Session service

This tutorial shows how to connect a DeepSeek Harness (DSH) Agent Loop running in a Brain Deployment, together with the Hands Deployment it invokes, to Tencent Cloud Agent Runtime Session. One user conversation maps to one Session, which stores the DSH conversation, both Deployment IDs, the Hands affinity, and tool execution Events. The same Session returns to its original workspace, while a new Session receives an isolated workspace.

The included [`SessionPersistence` plugin](./brain/plugin/index.js) creates and restores Sessions, writes Brain and Hands Events, restores DSH conversation context, and routes DSH tool calls to the Hands workspace associated with that Session. You can use the example image directly or integrate the plugin into your own DSH image.

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
export DSH_SESSION_IMAGE='ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:v0.1.1-rc.2-ags.4-session.8'
export HANDS_TOOL_NAME='dsh-hands-session-your-name'
export HANDS_DEPLOYMENT_NAME='dsh-hands-session-your-name'
export HANDS_SESSION_IMAGE='ccr.ccs.tencentyun.com/ags.dev/hands-session:v0.1.0'

export TENCENTCLOUD_SECRET_ID='replace-me'
export TENCENTCLOUD_SECRET_KEY='replace-me'
# Set this only for temporary credentials:
# export TENCENTCLOUD_SESSION_TOKEN='replace-me'

agr status --cloud-endpoint "$SESSION_API_ENDPOINT"
```

| Variable | Required | Description |
| --- | --- | --- |
| `AGR_REGION` | Yes | Region for Session, Tool, and Deployment. All three resource types must use the same region. |
| `AGR_DOMAIN` | Yes | Data-plane domain for the Brain Deployment. |
| `SESSION_API_ENDPOINT` | Yes | Cloud API endpoint used for Session, Tool, and Deployment operations. |
| `AGR_ROLE_ARN` | Yes | CAM role ARN used to create the custom Sandbox Tool. |
| `SESSION_SPACE_NAME` | When creating a SessionSpace | Name of the new SessionSpace. It is not used when you reuse an existing SessionSpace. |
| `SESSION_USER_ID` | Yes | User identifier that owns the example conversation. Keep it consistent when creating, querying, and deleting the Session. |
| `DSH_TOOL_NAME` | Yes | Name of the Sandbox Tool that runs the DSH image. Use a unique name. |
| `DSH_DEPLOYMENT_NAME` | Yes | Name of the Brain Deployment. Use a unique name. |
| `DSH_SESSION_IMAGE` | Yes | DSH image containing the `SessionPersistence` plugin. The default is the public image published for this tutorial. |
| `HANDS_TOOL_NAME` | Yes | Name of the Sandbox Tool that hosts the workspace service image. Use a unique name. |
| `HANDS_DEPLOYMENT_NAME` | Yes | Name of the Hands Deployment. Use a unique name. |
| `HANDS_SESSION_IMAGE` | Yes | Public Hands workspace service image used by this tutorial. |
| `TENCENTCLOUD_SECRET_ID` | Yes | Tencent Cloud SecretId used by the in-container plugin to call the Session Cloud API. It is separate from credentials configured for the local `agr` client. |
| `TENCENTCLOUD_SECRET_KEY` | Yes | SecretKey paired with the SecretId. |
| `TENCENTCLOUD_SESSION_TOKEN` | For temporary credentials | Session Token paired with temporary credentials. Leave it unset when using a long-term key. |

For a compact end-to-end example, this tutorial passes Cloud API credentials to the plugin through Tool environment variables. Use a dedicated sub-account or temporary credentials with only the Session permissions required by this tutorial. Never use root-account credentials or store secrets in the image or repository.

## 2. Create or reuse a SessionSpace

A SessionSpace is the isolation boundary for Sessions. To reuse an existing SessionSpace:

```bash
export SESSION_SPACE_ID='space-replace-me'
```

Otherwise create a dedicated SessionSpace:

```bash
agr api call CreateSessionSpace \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --request '{
    "Name":"'$SESSION_SPACE_NAME'",
    "Description":"DSH Brain conversations"
  }' \
  --output json

export SESSION_SPACE_ID='space-copy-from-response'
export SESSION_SPACE_CREATED_BY_TUTORIAL=1
```

## 3. Use the example image or your own DSH image

To run this tutorial, use the public example images specified by `DSH_SESSION_IMAGE` and `HANDS_SESSION_IMAGE`. The DSH image includes the tutorial's [`SessionPersistence` plugin](./brain/plugin/index.js), which persists DSH multi-turn conversations and routes model-initiated file operations to the Hands Deployment.

If you use your own DSH image, integrate the `SessionPersistence` plugin provided by this tutorial into that image. The plugin creates and restores Sessions, writes Events, and lets DSH restore multi-turn conversation context from the cloud Session service. After integrating it, configure and deploy the image by following the remaining steps.

## 4. Create the Hands and Brain Deployments

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

Create the Hands Deployment. `EXCLUSIVE` affinity gives each Session an isolated workspace:

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
    --arg hands "$HANDS_DEPLOYMENT_ID" \
    --arg sid "$TENCENTCLOUD_SECRET_ID" \
    --arg skey "$TENCENTCLOUD_SECRET_KEY" \
    --arg token "${TENCENTCLOUD_SESSION_TOKEN:-}" \
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
        {Name:"HANDS_DEPLOYMENT_ID",Value:$hands},
        {Name:"TENCENTCLOUD_SECRET_ID",Value:$sid},
        {Name:"TENCENTCLOUD_SECRET_KEY",Value:$skey},
        {Name:"TENCENTCLOUD_SESSION_TOKEN",Value:$token}
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

Create a Brain Deployment with exclusive affinity so the DSH Web UI and conversation requests continue to reach the same stateful instance. The Brain affinity ID is used only for Deployment routing and is not stored in Session Metadata:

```bash
agr deployment create \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --deployment-name "$DSH_DEPLOYMENT_NAME" \
  --tool-id "$DSH_TOOL_ID" \
  --scaling-configuration '{"MinInstanceCount":0,"MaxInstanceCount":1,"MaxInstanceRequestConcurrency":100}' \
  --lifecycle-configuration '{"IdleTimeoutSeconds":600,"IdleAction":"PAUSE"}' \
  --affinity-configuration '{"Mode":"EXCLUSIVE","HeaderName":"X-Tencent-Agr-Affinity-Id"}'

export DSH_DEPLOYMENT_ID='dpl-copy-from-response'
```

Add the new Brain Deployment ID to the Tool configuration. The plugin uses it to associate every Session created afterward:

```bash
export DSH_CUSTOM_CONFIGURATION="$(
  jq --arg deployment "$DSH_DEPLOYMENT_ID" \
    '.Env += [{Name:"BRAIN_DEPLOYMENT_ID",Value:$deployment}]' \
    <<<"$DSH_CUSTOM_CONFIGURATION"
)"

agr tool update "$DSH_TOOL_ID" \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --custom-configuration "$DSH_CUSTOM_CONFIGURATION" \
  --wait

unset DSH_CUSTOM_CONFIGURATION
```

## 5. Configure the DSH Agent

Start a local proxy:

```bash
agr deployment proxy "$DSH_DEPLOYMENT_ID" 18080:3080 \
  --region "$AGR_REGION" \
  --domain "$AGR_DOMAIN" \
  --cloud-endpoint "$SESSION_API_ENDPOINT"
```

Copy the affinity ID from the proxy output so the example client reaches the same DSH instance:

```bash
export DSH_AFFINITY_ID='copy-from-proxy-output'
```

Open <http://127.0.0.1:18080>. If the first-run API key dialog appears, close it; that dialog configures DSH's built-in DeepSeek provider rather than the TokenHub provider used by this tutorial.

Go to **Settings → Models**, find **Tencent Cloud TokenHub**, and select **Edit**. Enter the TokenHub API key and save it. Confirm that the provider shows **API key configured**, then start a new conversation and confirm that the selected model is `tokenhub/deepseek-v4-flash`. From this point on, the plugin persists Sessions and Events created through either the Web UI or the example script and records the Brain Deployment ID automatically.

## 6. Validate that Brain and Hands share one Session

You can validate manually through the Web UI or run the example script. Both paths write the DSH conversation, both Deployment IDs, the Hands affinity, and tool execution Events to the same Session.

### Validate through the Web UI

Send these messages in a new conversation, in order:

```text
What is 37 + 58? Use hands_write_file to store the numerical answer in session-value.txt, then answer with only the number.
Use hands_read_file to read session-value.txt. Multiply the stored number by 3, then answer with only the result.
What arithmetic question was contained in my first message? Exclude any answer-format instructions. Return only this JSON object: {"first_question":"<exact first question>","answer":<number>}
```

Expect `95`, `285`, and a JSON object containing the first question and its answer. The first turn calls `hands_write_file`; the second calls `hands_read_file`, showing that the same Session returned to its original workspace through the stored affinity.

Start a new DSH conversation and send:

```text
Use hands_read_file to read session-value.txt. If it does not exist, answer only MISSING.
```

Expect `MISSING`, showing that the new Session received a new affinity and an isolated workspace. Then run the query in section 7, find the Session you want to inspect, and set its ID:

```bash
export DSH_SESSION_ID='copy-from-DescribeSessions-response'
```

### Validate with the example script

Export the same variables in another terminal, then run:

```bash
python3 session_demo.py
```

The example performs the following operations:

1. Create a Session and automatically record the Brain Deployment ID.
2. Run three turns that invoke Hands through DSH tools to write and read a file.
3. Store the Hands Deployment ID, affinity, and execution Events in the same Session.
4. Create a new Session and confirm that it cannot read the original workspace.
5. Find the same Session through either the Brain or Hands Deployment ID.

Expected output:

```text
Session: <session-id>
  user: What is 37 + 58? Use hands_write_file to store ...
  assistant: 95
  user: Use hands_read_file to read session-value.txt. Multiply ...
  assistant: 285
  user: What arithmetic question was contained in my first message? Exclude any answer-format instructions. Return only this JSON object: ...
  assistant: {"first_question":"What is 37 + 58?","answer":95}
Agent Runtime persisted <count> DSH events
Isolated Session: <session-id>
Brain conversation persistence, Hands workspace continuity, and isolation passed
```

Copy the Session ID printed by the script:

```bash
export DSH_SESSION_ID='copy-from-output'
```

## 7. Inspect the complete Session

Find the Session through the Brain Deployment ID:

```bash
agr api call DescribeSessions \
  --region "$AGR_REGION" \
  --cloud-endpoint "$SESSION_API_ENDPOINT" \
  --request '{
    "SpaceId":"'$SESSION_SPACE_ID'",
    "Filters":[{
      "Name":"metadata:ae.tencentcloud.com/brain-deployment-id",
      "Values":["'$DSH_DEPLOYMENT_ID'"]
    }],
    "Offset":0,
    "Limit":20
  }' \
  --output json
```

Inspect all Events in the Session:

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
```

The Hands Deployment ID finds the same Session:

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

Session Metadata stores the Brain Deployment ID, Hands Deployment ID, and Hands affinity together. The same Session continues to use the same affinity; a new Session receives a new affinity. `DescribeEvents` supports pagination through `Offset` and `Limit`; the example script checks both Event types automatically.

The plugin populates standard fields according to Event semantics:

| DSH Event | Standard Session fields |
| --- | --- |
| User and assistant messages | `Author`, `Content` |
| Streaming text and reasoning chunks | `Content`, `Partial` |
| Tool calls and results | `FunctionCall`, `FunctionResponse` |
| Configuration state changes | `Actions.StateDelta` |
| Turn completion, interruption, and errors | `TurnComplete`, `Interrupted`, `ErrorCode`, `ErrorMessage` |

Raw DSH Event data is retained in `Extensions.dshEvent` for lossless Brain restoration. Hands Events use `FunctionCall` and `FunctionResponse` to record file operations and results. Both Event types belong to the same Session.

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
  'ae.tencentcloud.com/brain-deployment-id' "$DSH_DEPLOYMENT_ID"
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
- The three-turn conversation times out: check the model configuration in the DSH Web UI and the Deployment status.
