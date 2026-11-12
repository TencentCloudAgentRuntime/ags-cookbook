# Create a managed harness with `agr`: the shortest complete workflow

This tutorial registers a TokenHub model, creates a managed harness on the `pi` engine and waits for revision 1 to publish, checks the ACP endpoint, sends one prompt, and then removes every resource. The adjacent tutorials cover changes and rollback, connection options, and scaling and session persistence separately.

Complete the shared [Managed Harness Cookbook prerequisites](../README.md#prerequisites) before starting.

Run every command directly in a terminal and copy each resource ID from the output into the environment variable shown in the next step. Sample output masks account numbers, resource IDs, timestamps, and request IDs.

## 1. Set environment variables

Replace the role ARN, subnet, security group, ApiKeyId, and resource names with your own values. Names may contain only lowercase letters, digits, `-` and `.`; keep the suffix unique.

```bash
export AGR_REGION=ap-chongqing
export AGR_ROLE_ARN='qcs::cam::uin/100000000001:roleName/replace-me'
export HARNESS_SUBNET_ID='subnet-replace-me'
export HARNESS_SECURITY_GROUP_ID='sg-replace-me'
export TOKENHUB_API_KEY_ID='ak-replace-me'
export MODEL_PROVIDER_NAME='harness-simple-your-name'
export HARNESS_NAME='harness-simple-your-name'

agr status
```

Expected output format. Every command in this tutorial passes `--region`, so the default region shown here does not matter:

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

## 2. List the available engines

A Harness Engine is an agent runtime provided by the platform. A harness must use an engine and version offered in the current region.

```bash
agr harness engine list --region "$AGR_REGION"
```

Expected output format; actual versions depend on the region:

```text
ENGINE  VERSIONS
dsh     0.2.1-rc.2
pi      1.3.0
```

This tutorial uses `pi`:

```bash
export HARNESS_ENGINE=pi
export HARNESS_ENGINE_VERSION=1.3.0
```

## 3. Register a model connection

A model provider records one model service source and its registered models. `--model hy3` registers a text-only model; write `--model <id>:TEXT,IMAGE` for a model that accepts images.

```bash
agr model-provider create \
  --region "$AGR_REGION" \
  --name "$MODEL_PROVIDER_NAME" \
  --tokenhub-api-key-id "$TOKENHUB_API_KEY_ID" \
  --model hy3
```

The successful output contains the real model provider ID:

```text
Model provider:  mp-********
Name:            harness-simple-****
Source:          TokenHub (ApiKeyId ak-********)
Models:          hy3[TEXT]
Tags:            -
Updated:         <masked-time>
Next: agr harness create --model mp-********:<model-id> ...
```

Copy `Model provider` into an environment variable:

```bash
export MODEL_PROVIDER_ID='mp-replace-me'
```

## 4. Create the harness and wait for revision 1

`harness create` saves the draft, creates revision 1, and publishes it asynchronously: the platform creates a Sandbox Tool and then a Deployment. `--wait` blocks until revision 1 is `PUBLISHED` or `PUBLISH_FAILED`, which usually takes a few minutes.

`--model <provider-id>:<model-id>` selects a model; with a single model it is also the default. The role, subnet, and security group cannot be changed after create.

First preview the request with `--dry-run`. This step creates nothing:

```bash
agr harness create \
  --region "$AGR_REGION" \
  --name "$HARNESS_NAME" \
  --engine "$HARNESS_ENGINE" \
  --engine-version "$HARNESS_ENGINE_VERSION" \
  --model "$MODEL_PROVIDER_ID:hy3" \
  --system-prompt 'You are a concise assistant. Answer in one short paragraph.' \
  --role-arn "$AGR_ROLE_ARN" \
  --subnet-id "$HARNESS_SUBNET_ID" \
  --security-group-id "$HARNESS_SECURITY_GROUP_ID" \
  --dry-run -o json
```

`Data.Request` is the final request and shows what each shortcut flag expands to:

```json
{
  "Data": {
    "Action": "CreateHarness",
    "DryRun": true,
    "Request": {
      "HarnessName": "harness-simple-****",
      "HarnessEngine": "pi",
      "HarnessEngineVersion": "1.3.0",
      "SystemPrompt": "You are a concise assistant. Answer in one short paragraph.",
      "ModelProviders": [{"ModelProviderId": "mp-********", "Models": ["hy3"]}],
      "DefaultModel": {"ModelProviderId": "mp-********", "Model": "hy3"},
      "InitializeConfiguration": {
        "SandboxTool": {
          "RoleArn": "qcs::cam::uin/************:roleName/****",
          "NetworkConfiguration": {
            "NetworkMode": "VPC",
            "VpcConfig": {"SubnetIds": ["subnet-********"], "SecurityGroupIds": ["sg-********"]}
          }
        }
      }
    }
  }
}
```

Remove `--dry-run -o json` and add `--wait` to create it:

```bash
agr harness create \
  --region "$AGR_REGION" \
  --name "$HARNESS_NAME" \
  --engine "$HARNESS_ENGINE" \
  --engine-version "$HARNESS_ENGINE_VERSION" \
  --model "$MODEL_PROVIDER_ID:hy3" \
  --system-prompt 'You are a concise assistant. Answer in one short paragraph.' \
  --role-arn "$AGR_ROLE_ARN" \
  --subnet-id "$HARNESS_SUBNET_ID" \
  --security-group-id "$HARNESS_SECURITY_GROUP_ID" \
  --wait
```

The successful output contains the real harness ID and the final state of revision 1:

```text
Harness:        hns-********
Name:           harness-simple-****
Status:         ACTIVE
Engine:         pi@1.3.0
Models:         mp-********:hy3 (default)
System prompt:  You are a concise assistant. Answer in one short paragraph.
Skills:         -
Plugins:        -
MCP servers:    -
Sandbox tool:   -
Deployment:     -
Tags:           -
Updated:        <masked-time>

Revision 1 is PUBLISHED.
Next: agr harness endpoint hns-******** --check
```

The upper part is the harness record returned by the create request, before publishing started, so `Sandbox tool` and `Deployment` are `-`; `Revision 1 is PUBLISHED.` below is the result when the wait ends. Copy `Harness` and check the current state:

```bash
export HARNESS_ID='hns-replace-me'

agr harness status "$HARNESS_ID" --region "$AGR_REGION"
```

```text
Harness:    hns-******** (harness-simple-****)  ACTIVE
Live:       revision 1 (v1)  PUBLISHED  pi@1.3.0
Draft:      same as live revision
Resources:  tool=sdt-******** deployment=dpl-********
```

If `--wait` returns `WAIT_FAILED`, the revision ended in `PUBLISH_FAILED`. Read the reason:

```bash
agr harness revision get "$HARNESS_ID" 1 --region "$AGR_REGION"
```

The `Status reason` line names the failed step. After fixing the cause, such as role permissions or the subnet, retry the same revision:

```bash
agr harness revision publish "$HARNESS_ID" 1 --region "$AGR_REGION" --wait
```

## 5. Check the ACP endpoint

`PUBLISHED` means the platform resources are ready, not that an instance can already chat. `--check` acquires a short-lived token and sends one `initialize` request to the ACP endpoint:

```bash
agr harness endpoint "$HARNESS_ID" --region "$AGR_REGION" --check
```

Expected output format:

```text
ACP URL:      https://8080-dpl-********.ap-chongqing.agents.tencentags.com/acp
Transport:    ACP Streamable HTTP
Auth header:  X-Access-Token   (add --show-token to issue one)
Affinity:     X-Tencent-Agr-Affinity-Id   (echo the value returned in responses)
Deployment:   dpl-********
Check:        reachable in <masked>ms
Local proxy:  agr harness proxy hns-********
```

The first check may wait for an instance to start. If it returns `ACP_UNAVAILABLE`, wait a moment and retry.

## 6. Send one prompt

`prompt` opens an ACP session, sends one turn, and streams the reply to the terminal. Tool calls appear as progress lines starting with `⋯` on stderr.

```bash
agr harness prompt "$HARNESS_ID" --region "$AGR_REGION" \
  'What is an AI agent harness? Reply in two sentences.'
```

Expected output format; the actual reply differs:

```text
An agent harness is the runtime around a language model that gives it tools, memory and a loop ...

[end_turn] session <masked-session-id> affinity <masked-affinity-id>
```

The session and affinity on the last line continue the conversation; see [connect](../connect/README.md).

## 7. Clean up

`harness delete` removes the Deployment and the harness records but **keeps the Sandbox Tool and the model provider**. Record the Tool ID first:

```bash
agr harness get "$HARNESS_ID" --region "$AGR_REGION" -o json --jq '.Data.Harness.ResourceInfo.ToolId'
```

```bash
export HARNESS_TOOL_ID='sdt-replace-me'

agr harness delete "$HARNESS_ID" --region "$AGR_REGION" --yes --wait
```

Expected output:

```text
Harness hns-******** deleted.
Kept: the Sandbox Tool, model providers, session spaces, Registry assets and credentials.
Next: agr tool delete sdt-********   # only if the Sandbox Tool is no longer needed
```

Delete instances of that Tool that are still running or paused:

```bash
agr instance list --tool-id "$HARNESS_TOOL_ID" --region "$AGR_REGION"
```

Copy each instance ID currently in `RUNNING` or `PAUSED`, and delete them one by one:

```bash
export HARNESS_INSTANCE_ID='replace-with-instance-id'
agr instance delete "$HARNESS_INSTANCE_ID" --region "$AGR_REGION" --yes --wait
```

Delete the Tool and the model provider. A model provider can be deleted only when no harness references it:

```bash
agr tool delete "$HARNESS_TOOL_ID" --region "$AGR_REGION" --yes --wait
agr model-provider delete "$MODEL_PROVIDER_ID" --region "$AGR_REGION" --yes
```
