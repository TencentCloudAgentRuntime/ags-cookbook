# Persist multi-turn agent conversations from a Brain Deployment with Session

This tutorial shows how to connect a DeepSeek Harness (DSH) Agent Loop running in a Brain Deployment to Tencent Cloud Agent Runtime Session. After running the example, three conversation turns share the same context, with the conversation and execution events continuously persisted to Session. You can then use the Brain Deployment ID to find the associated Sessions and Events.

The included [`SessionPersistence` plugin](./plugin/index.js) creates and restores Sessions, writes Events, and lets DSH restore context from Session. It is both a runnable DSH implementation and a reference for integrating other Agents with Session. To use another Agent framework, adapt the plugin to its conversation lifecycle interfaces.

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

These variables specify the deployment region, Deployment data-plane domain, and Session Cloud API endpoint. Change `AGR_REGION` when deploying elsewhere.

Set resource names, image, and credentials:

```bash
export AGR_ROLE_ARN='qcs::cam::uin/100000000001:roleName/replace-me'
export SESSION_SPACE_NAME='dsh-brain-session-your-name'
export SESSION_USER_ID='dsh-demo-user'
export DSH_TOOL_NAME='dsh-brain-session-your-name'
export DSH_DEPLOYMENT_NAME='dsh-brain-session-your-name'
export DSH_SESSION_IMAGE='ccr.ccs.tencentyun.com/ags.dev/dsh-session:v0.1.1'

export TENCENTCLOUD_SECRET_ID='replace-me'
export TENCENTCLOUD_SECRET_KEY='replace-me'
# Set this only for temporary credentials:
# export TENCENTCLOUD_SESSION_TOKEN='replace-me'

agr status
```

| Variable | Required | Description |
| --- | --- | --- |
| `AGR_ROLE_ARN` | Yes | CAM role ARN used to create the custom Sandbox Tool. |
| `SESSION_SPACE_NAME` | When creating a SessionSpace | Name of the new SessionSpace. It is not used when you reuse an existing SessionSpace. |
| `SESSION_USER_ID` | Yes | User identifier that owns the example conversation. Keep it consistent when creating, querying, and deleting the Session. |
| `DSH_TOOL_NAME` | Yes | Name of the Sandbox Tool that runs the DSH image. Use a unique name. |
| `DSH_DEPLOYMENT_NAME` | Yes | Name of the Brain Deployment. Use a unique name. |
| `DSH_SESSION_IMAGE` | Yes | DSH image containing the `SessionPersistence` plugin. The default is the public image published for this tutorial. |
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
  --request '{
    "Name":"'$SESSION_SPACE_NAME'",
    "Description":"DSH Brain conversations"
  }' \
  --output json

export SESSION_SPACE_ID='space-copy-from-response'
export SESSION_SPACE_CREATED_BY_TUTORIAL=1
```

## 3. Use the DSH Session image

The main workflow uses the example image published under `ags.dev`. It extends the standard DSH image with this tutorial's `SessionPersistence` plugin, so DSH stores conversations and execution events in Agent Runtime Session instead of local container files. The image also includes non-secret TokenHub provider and model settings.

You do not need to build an image to run this tutorial.

### Custom image (optional)

To modify the plugin or integrate it into your own Agent image, install Docker, prepare a CCR repository, and run:

```bash
export DSH_SESSION_IMAGE='ccr.ccs.tencentyun.com/your-namespace/dsh-session:latest'

docker build \
  --platform linux/amd64 \
  --file dockerfiles/Dockerfile \
  --tag "$DSH_SESSION_IMAGE" \
  .

docker push "$DSH_SESSION_IMAGE"
```

The remaining steps use the customized `DSH_SESSION_IMAGE` directly and require no other changes.

## 4. Create the Brain Tool and Deployment

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
  --tool-name "$DSH_TOOL_NAME" \
  --tool-type custom \
  --persistent \
  --role-arn "$AGR_ROLE_ARN" \
  --network-configuration '{"NetworkMode":"PUBLIC"}' \
  --custom-configuration "$DSH_CUSTOM_CONFIGURATION" \
  --wait

export DSH_TOOL_ID='sdt-copy-from-response'
```

Create a Brain Deployment with exclusive affinity so the DSH Web UI and conversation requests continue to reach the same stateful instance. The affinity ID is used only for Deployment routing and is not stored in Session Metadata:

```bash
agr deployment create \
  --region "$AGR_REGION" \
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
  --custom-configuration "$DSH_CUSTOM_CONFIGURATION" \
  --wait

unset DSH_CUSTOM_CONFIGURATION
```

## 5. Configure the DSH Agent

Start a local proxy:

```bash
agr deployment proxy "$DSH_DEPLOYMENT_ID" 18080:3080 \
  --region "$AGR_REGION"
```

Copy the affinity ID from the proxy output so the example client reaches the same DSH instance:

```bash
export DSH_AFFINITY_ID='copy-from-proxy-output'
```

Open <http://127.0.0.1:18080>. If the first-run API key dialog appears, close it; that dialog configures DSH's built-in DeepSeek provider rather than the TokenHub provider used by this tutorial.

Go to **Settings → Models**, find **Tencent Cloud TokenHub**, and select **Edit**. Enter the TokenHub API key and save it. Confirm that the provider shows **API key configured**, then start a new conversation and confirm that the selected model is `tokenhub/deepseek-v4-flash`. From this point on, the plugin persists Sessions and Events created through either the Web UI or the example script and records the Brain Deployment ID automatically.

## 6. Validate a multi-turn conversation

You can validate manually through the Web UI or run the example script for automatic validation. Both paths use the same plugin to create an Agent Runtime Session, persist Events, and record the Brain Deployment ID.

### Validate through the Web UI

Send these messages in a new conversation, in order:

```text
What is 37 + 58? Answer with only the number.
Multiply the previous answer by 3. Answer with only the number.
What arithmetic question was contained in my first message? Exclude any answer-format instructions. Return only this JSON object: {"first_question":"<exact first question>","answer":<number>}
```

Expect `95`, `285`, and a JSON object containing the first question and its answer. This confirms that all three messages used the same conversation context. Next, run the query in section 7, find the Session whose title matches the first question, and set its ID:

```bash
export DSH_SESSION_ID='copy-from-DescribeSessions-response'
```

### Validate with the example script

Export the same variables in another terminal, then run:

```bash
python3 session_demo.py
```

The example performs the following operations:

1. Create a DSH conversation and its corresponding Agent Runtime Session through the plugin.
2. Let the plugin store the Brain Deployment ID in Session Metadata to associate the Deployment with the Session.
3. Run three turns that validate a direct answer, use of the previous result, and recall of the first prompt.
4. Confirm that Events were persisted and find the Session by Brain Deployment ID.

Expected output:

```text
Session: <session-id>
  user: What is 37 + 58? Answer with only the number.
  assistant: 95
  user: Multiply the previous answer by 3. Answer with only the number.
  assistant: 285
  user: What arithmetic question was contained in my first message? Exclude any answer-format instructions. Return only this JSON object: ...
  assistant: {"first_question":"What is 37 + 58?","answer":95}
Agent Runtime persisted <count> DSH events
Three-turn recall, Brain Deployment lookup, and Event inspection passed
```

Copy the Session ID printed by the script:

```bash
export DSH_SESSION_ID='copy-from-output'
```

## 7. Inspect the associated Session and Events

Find Sessions associated with the Brain Deployment:

```bash
agr api call DescribeSessions \
  --region "$AGR_REGION" \
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

Inspect the DSH Events:

```bash
agr api call DescribeEvents \
  --region "$AGR_REGION" \
  --request '{
    "SpaceId":"'$SESSION_SPACE_ID'",
    "UserId":"'$SESSION_USER_ID'",
    "SessionId":"'$DSH_SESSION_ID'",
    "Offset":0,
    "Limit":100
  }' \
  --output json
```

`DescribeEvents` supports pagination through `Offset` and `Limit`. `session_demo.py` automatically reads all Events produced by this validation run.

The plugin populates standard fields according to Event semantics:

| DSH Event | Standard Session fields |
| --- | --- |
| User and assistant messages | `Author`, `Content` |
| Streaming text and reasoning chunks | `Content`, `Partial` |
| Tool calls and results | `FunctionCall`, `FunctionResponse` |
| Configuration state changes | `Actions.StateDelta` |
| Turn completion, interruption, and errors | `TurnComplete`, `Interrupted`, `ErrorCode`, `ErrorMessage` |

The original DSH data for every Event is retained in `Extensions.dshEvent` for lossless restoration.

## 8. Clean up

```bash
agr api call DeleteSession \
  --region "$AGR_REGION" \
  --request '{"SpaceId":"'$SESSION_SPACE_ID'","UserId":"'$SESSION_USER_ID'","SessionId":"'$DSH_SESSION_ID'"}' \
  --output json

agr deployment delete "$DSH_DEPLOYMENT_ID" --region "$AGR_REGION" --wait
agr tool delete "$DSH_TOOL_ID" --region "$AGR_REGION" --yes --wait
```

Delete the SessionSpace only if this tutorial created it:

```bash
if [ "${SESSION_SPACE_CREATED_BY_TUTORIAL:-0}" = 1 ]; then
  agr api call DeleteSessionSpace \
    --region "$AGR_REGION" \
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
