# Create a managed harness with `agr`: the shortest complete workflow

This tutorial registers a TokenHub model, creates a managed harness on the `pi` engine and waits for revision 1 to publish, checks the ACP endpoint, sends one prompt, and then removes every resource. The adjacent tutorials cover changes and rollback, connection options, and scaling and session persistence separately.

Complete the shared [prerequisites](../README.md#prerequisites) and [configuration](../README.md#configuration) before starting.

Run commands from this scenario directory. Creation commands save resource IDs automatically for the following steps and cleanup. Sample output masks account numbers, resource IDs, timestamps, and request IDs.

## 1. Set environment variables

Load the shared `.env` configured in the prerequisites and check the CLI before creating resources. The suffix in `.env` keeps this example's names unique.

```bash
set -a
source ../.env
set +a
bash ../scripts/preflight.sh simple &&

export MODEL_PROVIDER_NAME="harness-simple-$HARNESS_NAME_SUFFIX" &&
export HARNESS_NAME="harness-simple-$HARNESS_NAME_SUFFIX"
```

Preflight prints `agr status` and `agr doctor` results, then `Preflight passed`. The status section looks like this; commands use the region from `.env`:

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
MODEL_PROVIDER_ID=$(python3 ../scripts/resources.py create simple model-provider \
  --name "$MODEL_PROVIDER_NAME" \
  --tokenhub-api-key-id "$TOKENHUB_API_KEY_ID" \
  --model hy3) && export MODEL_PROVIDER_ID
```

Read the model connection:

```bash
agr model-provider get "$MODEL_PROVIDER_ID" --region "$AGR_REGION" -o text
```

Expected output format:

```text
Model provider:  mp-********
Name:            harness-simple-****
Source:          TokenHub (ApiKeyId ak-********)
Models:          hy3[TEXT]
Tags:            -
Updated:         <masked-time>
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

Create it with `--wait`; the helper captures the returned ID:

```bash
HARNESS_ID=$(python3 ../scripts/resources.py create simple harness \
  --name "$HARNESS_NAME" \
  --engine "$HARNESS_ENGINE" \
  --engine-version "$HARNESS_ENGINE_VERSION" \
  --model "$MODEL_PROVIDER_ID:hy3" \
  --system-prompt 'You are a concise assistant. Answer in one short paragraph.' \
  --role-arn "$AGR_ROLE_ARN" \
  --subnet-id "$HARNESS_SUBNET_ID" \
  --security-group-id "$HARNESS_SECURITY_GROUP_ID" \
  --wait) && export HARNESS_ID
```

The helper saves the Harness, Tool and Deployment IDs in `.state/simple.json`. Check the published revision:

```bash
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
HARNESS_ID=$(python3 ../scripts/resources.py get simple HarnessId) && export HARNESS_ID
agr harness revision get "$HARNESS_ID" 1 --region "$AGR_REGION"
```

The `Status reason` line names the failed step. For an external cause that can be corrected without changing the saved initialization configuration, such as role permissions or VPC egress, fix it and retry the same revision:

```bash
agr harness revision publish "$HARNESS_ID" 1 --region "$AGR_REGION" --wait
```

An incorrect subnet ID or a region mismatch requires a new Harness with corrected initialization parameters. `harness update` cannot change the saved initialization configuration, so retrying this revision reuses the wrong values. Delete the failed Harness first and clean up any recorded Sandbox Tool as described in step 7.

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

Delete the resources saved for this scenario. The helper reads the IDs and region from `.state/`, waits for deletion, and verifies the result. You can run it again after an interrupted cleanup.

```bash
python3 ../scripts/resources.py cleanup simple --yes
```
