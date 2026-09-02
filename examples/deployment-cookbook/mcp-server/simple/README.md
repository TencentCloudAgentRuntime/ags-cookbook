# Deploy the Everything MCP Server on AGR

This example runs the official Everything MCP Server on AGR and connects to it with the official Python MCP SDK. The example client automatically sends the AGS token and `BEST_EFFORT` affinity.

You will:

- run `initialize → tools/list → echo` against the production endpoint;
- watch active capacity move from `0 → N → 0`;
- reuse the saved AGS affinity after idle `STOP`, while opening a fresh MCP session.

The example retains AGS affinity between runs and opens a fresh MCP session after the instance stops.

## Prerequisites

- Install `agr` **v0.6.6 or later**. If the CLI is not configured yet, follow the [official AGR CLI credential guide](https://github.com/TencentCloudAgentRuntime/ags-cli#initialize-cli-credentials), then run `agr status` and `agr doctor`.
- Install [`uv`](https://docs.astral.sh/uv/).
- Follow the official [custom Sandbox role and permission guide](https://cloud.tencent.com/document/product/1814/129691) to create an Agent Runtime CAM role, and grant your CLI identity `cam:PassRole` for that role. The published image below is public; add repository pull permission only if you replace it with an image from your own private CCR or TCR repository.
- Use a CLI identity that can create and delete Sandbox Tools and Deployments, list and delete Instances, and acquire Deployment tokens.

Use the published image:

```text
ccr.ccs.tencentyun.com/ags.dev/mcp-everything:2026.8.31-ags.1
```

You can use this published example image directly. To build and push a copy to your own registry, see [dockerfiles](./dockerfiles/README.md).

Run every command from this `simple` directory. Copy real resource IDs from command output; step 4 loads the Deployment token directly into the current shell. Sample resource IDs are placeholders.

## 1. Configure local variables

Use unique resource-name suffixes and replace the role ARN. This tutorial sets Shanghai through `AGR_REGION` and also passes `--region` to every cloud command, so you do not need to change the CLI's global region.

```bash
export AGR_REGION=ap-shanghai
export AGR_DOMAIN=tencentags.com
export AGR_ROLE_ARN='qcs::cam::uin/100000000001:roleName/replace-me'
export MCP_TOOL_NAME='mcp-everything-simple-your-name'
export MCP_DEPLOYMENT_NAME='mcp-everything-simple-your-name'
export MCP_STATE_DIR="${TMPDIR:-/tmp}/ags-cookbook-$MCP_TOOL_NAME"
export MCP_AFFINITY_STATE="$MCP_STATE_DIR/smoke-affinity.json"

mkdir -p "$MCP_STATE_DIR"
chmod 700 "$MCP_STATE_DIR"

agr status
agr doctor
uv sync --project client --locked
```

`MCP_STATE_DIR` stores the AGS affinity used by the example client.

## 2. Create the Sandbox Tool

Port `3001` serves MCP, while port `3000` provides the readiness check. The command below uses the published example image. If you built your own copy, paste its full URI into `Image` and set `ImageRegistryType` to `personal` for CCR or `enterprise` for TCR.

```bash
agr tool create \
  --region "$AGR_REGION" \
  --tool-name "$MCP_TOOL_NAME" \
  --tool-type custom \
  --persistent \
  --role-arn "$AGR_ROLE_ARN" \
  --network-configuration '{"NetworkMode":"SANDBOX"}' \
  --custom-configuration '{
    "Image": "ccr.ccs.tencentyun.com/ags.dev/mcp-everything:2026.8.31-ags.1",
    "ImageRegistryType": "personal",
    "Command": [
      "node",
      "entrypoint.mjs"
    ],
    "Ports": [
      {
        "Name": "mcp",
        "Port": 3001,
        "Protocol": "TCP"
      }
    ],
    "Resources": {
      "CPU": "500m",
      "Memory": "1Gi"
    },
    "Probe": {
      "HttpGet": {
        "Path": "/healthz",
        "Port": 3000,
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

Successful output contains the real Tool ID. Copy it:

```bash
export MCP_TOOL_ID='sdt-replace-me'
```

## 3. Create the Deployment

The official SDK keeps a GET event stream open while sending POST and DELETE requests, so this example sets per-instance request concurrency to `2`.

```bash
agr deployment create \
  --region "$AGR_REGION" \
  --deployment-name "$MCP_DEPLOYMENT_NAME" \
  --tool-id "$MCP_TOOL_ID" \
  --scaling-configuration '{
    "MinInstanceCount": 0,
    "MaxInstanceCount": 3,
    "MaxInstanceRequestConcurrency": 2
  }' \
  --lifecycle-configuration '{
    "IdleTimeoutSeconds": 60,
    "IdleAction": "STOP"
  }' \
  --affinity-configuration '{
    "Mode": "BEST_EFFORT",
    "HeaderName": "X-Tencent-Agr-Affinity-Id"
  }'
```

Copy the Deployment ID and form its production URL:

```bash
export MCP_DEPLOYMENT_ID='dpl-replace-me'
export MCP_DEPLOYMENT_URL="https://3001-$MCP_DEPLOYMENT_ID.$AGR_REGION.agents.$AGR_DOMAIN/mcp"

agr deployment get "$MCP_DEPLOYMENT_ID" --region "$AGR_REGION"
agr instance list --tool-id "$MCP_TOOL_ID" --region "$AGR_REGION"
```

Before the first request, there should be no `RUNNING` instance.

## 4. Acquire a short-lived token

Acquire a Deployment token directly into the current shell:

```bash
MCP_DEPLOYMENT_TOKEN="$(
  agr api call AcquireDeploymentToken \
    --region "$AGR_REGION" \
    --request '{"DeploymentId":"'$MCP_DEPLOYMENT_ID'"}' \
    --output json \
    --jq '.Data.Response.Response.Token'
)"
export MCP_DEPLOYMENT_TOKEN
```

The example client reads this token from `MCP_DEPLOYMENT_TOKEN` and stores AGS affinity in `MCP_AFFINITY_STATE`.

## 5. Test the production endpoint

The client uses the official Python MCP SDK with the token and affinity configured above.

```bash
uv run --project client --locked python client/mcp_client.py smoke \
  --url "$MCP_DEPLOYMENT_URL" \
  --transport direct \
  --state-file "$MCP_AFFINITY_STATE"
```

The command should complete `initialize`, `tools/list`, and `echo`. With the published image, expect server name `mcp-servers/everything`, version `2.0.0`, protocol `2025-11-25`, and 13 tools. The client checks that `echo` and `trigger-long-running-operation` are available and that the `echo` result is `Echo: ags-cookbook`.

## 6. Observe `0 → N → 0`

First close all MCP clients and wait until no instance is `RUNNING`. Reclamation is asynchronous and can take several minutes even with a 60-second idle timeout:

```bash
agr instance list --tool-id "$MCP_TOOL_ID" --region "$AGR_REGION"
```

In the first terminal, hold one native MCP call for 90 seconds:

```bash
uv run --project client --locked python client/mcp_client.py hold \
  --url "$MCP_DEPLOYMENT_URL" \
  --transport direct \
  --state-dir "$MCP_STATE_DIR/hold" \
  --workers 1 \
  --duration 90
```

While the `trigger-long-running-operation` call is active, use a second terminal:

```bash
agr instance list --tool-id "$MCP_TOOL_ID" --region "$AGR_REGION"
```

Count the `RUNNING` rows and call that number `N`. You should see `1 <= N <= 3`. Count the rows rather than deriving `N` from the number of clients.

After the client exits, do not access the Deployment. Wait at least 60 seconds, then list instances again until the asynchronous transition converges; this can take several minutes. The active count must eventually return to zero; historical `STOPPED` rows may remain visible.

## 7. Verify `BEST_EFFORT` with a fresh MCP session

After the instance used by the smoke test is `STOPPED`, reuse its saved AGS affinity with a completely new official MCP transport and session:

```bash
uv run --project client --locked python client/mcp_client.py resume \
  --url "$MCP_DEPLOYMENT_URL" \
  --transport direct \
  --state-file "$MCP_AFFINITY_STATE"
```

The command should again complete `initialize`, `tools/list`, and `echo`. The affinity fingerprint may stay the same or change; when it changes, the client saves the new value.

## 8. Clean up

Delete the Deployment and list its instances:

```bash
agr deployment delete "$MCP_DEPLOYMENT_ID" --region "$AGR_REGION" --wait
agr instance list --tool-id "$MCP_TOOL_ID" --region "$AGR_REGION"
```

Copy each current `RUNNING` or `PAUSED` instance ID and run the delete command for each one:

```bash
export MCP_INSTANCE_ID='replace-with-instance-id'
agr instance delete "$MCP_INSTANCE_ID" --region "$AGR_REGION" --yes --wait
```

Delete the Tool, local state, and shell token:

```bash
agr tool delete "$MCP_TOOL_ID" --region "$AGR_REGION" --yes --wait
rm -r -- "$MCP_STATE_DIR"
unset MCP_DEPLOYMENT_TOKEN
```

## Checklist

- `uv sync --project client --locked` succeeds.
- One direct native smoke completes.
- Active capacity is observed as `0 → N → 0` with `N >= 1`.
- `resume` succeeds after the original instance stops.
- The Deployment, current instances, Tool, affinity state directory, and `MCP_DEPLOYMENT_TOKEN` are removed during cleanup.

The [httpbin scaling](../../httpbin/scaling/README.md), [lifecycle](../../httpbin/lifecycle/README.md), and [affinity](../../httpbin/affinity/README.md) tutorials cover the platform concepts in isolation.
