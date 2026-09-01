# Deploy a native MCP server client flow on AGR

This tutorial deploys the official Everything MCP Server and validates it with the official Python MCP SDK. AGS authentication and `BEST_EFFORT` affinity are added through HTTP hooks; the client does not reimplement Streamable HTTP or suppress the SDK's native GET stream.

The tutorial proves these results separately:

- one production client completes `initialize → tools/list → echo`;
- native MCP traffic moves active capacity from `0 → N → 0`, where `N` is observed rather than predicted from the client count;
- after idle `STOP`, a retained AGS affinity can be sent with a fresh MCP session and may be replaced by AGS.

The official Everything server keeps MCP session state in one process. `MCP-Session-Id` and AGS affinity are therefore different kinds of state. Never reuse an old MCP session after instance replacement.

## Prerequisites

- Install `agr` **v0.6.6 or later**, then run `agr status`.
- Install [`uv`](https://docs.astral.sh/uv/).
- Prepare a CAM role ARN that lets AGR pull the pinned CCR image.
- Use an account that can create and delete Sandbox Tools, Deployments, and Instances and acquire Deployment tokens.
- Keep local port `18080` free only if you want to try the optional proxy diagnostics.

The prebuilt image is:

```text
ccr.ccs.tencentyun.com/ags.dev/mcp-everything:2026.8.31-ags.1
```

Published OCI index digest:

```text
sha256:3e708366c19c13516b508ac8c58580b060df7cfba4197005070cc433b98c07d3
```

Its reproducible source, license, pinned dependency graph, and publication procedure are in [dockerfiles](./dockerfiles/README.md).

Run every command from this `simple` directory. Copy real resource IDs and the short-lived Deployment token from command output; sample values are placeholders.

## 1. Configure local variables

Use unique resource-name suffixes and replace the role ARN:

```bash
export AGR_REGION=ap-shanghai
export AGR_DOMAIN=tencentags.com
export AGR_ROLE_ARN='qcs::cam::uin/100000000001:roleName/replace-me'
export MCP_TOOL_NAME='mcp-everything-simple-your-name'
export MCP_DEPLOYMENT_NAME='mcp-everything-simple-your-name'
export MCP_STATE_DIR="$(mktemp -d)"
export MCP_AFFINITY_STATE="$MCP_STATE_DIR/smoke-affinity.json"

agr status
uv sync --project client --locked

(
  cd client
  uv run --locked python -m unittest discover -s tests -v
)
```

`MCP_STATE_DIR` contains only AGS affinity state. The client creates files with mode `0600`; it never writes the Deployment token or `MCP-Session-Id`.

The client project configures the Tencent PyPI mirror as its default `uv` index, and `uv.lock` pins the resolved artifacts and hashes.

## 2. Create the Sandbox Tool

The runtime needs no outbound Internet access. Port `3001` serves MCP, while the operational readiness endpoint uses the container-only port `3000`.

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

The Custom Tool API requires an explicit `Command` even though the image also carries the same entry point. `ReadyTimeoutMs=30000` is the API maximum.

Successful output contains the real Tool ID. Copy it:

```bash
export MCP_TOOL_ID='sdt-replace-me'
```

## 3. Create the Deployment

The official SDK maintains a GET event stream while also issuing POST and DELETE requests. A per-instance request-concurrency lease of `2` is the compatibility floor verified for one native client. It does not reserve two leases permanently or imply a fixed client-to-instance mapping.

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

A data-plane request without a Deployment token is rejected. This GET is only an authentication check; it is not an MCP protocol operation:

```bash
curl --include --silent --show-error "$MCP_DEPLOYMENT_URL"
```

Expect HTTP `401`. Acquire a token:

```bash
agr api call AcquireDeploymentToken \
  --region "$AGR_REGION" \
  --request '{"DeploymentId":"'$MCP_DEPLOYMENT_ID'"}' \
  --output json
```

Copy `Data.Response.Response.Token` into the current shell only:

```bash
export MCP_DEPLOYMENT_TOKEN='replace-with-token'
```

Do not write this token to the affinity state file, a command-line option, or logs.

## 5. Run the authoritative native smoke

The client uses `mcp.client.streamable_http.streamable_http_client` and `mcp.ClientSession` directly. An `httpx2.AsyncClient` request hook injects the latest AGS affinity, and a response hook stores a replacement value when the gateway returns one.

```bash
uv run --project client --locked python client/mcp_client.py smoke \
  --url "$MCP_DEPLOYMENT_URL" \
  --transport direct \
  --state-file "$MCP_AFFINITY_STATE"
```

Successful JSON-line events include:

```json
{"affinity":"<sha256-prefix>","event":"initialize","protocol":"2025-11-25","server":"mcp-servers/everything","server_version":"2.0.0","worker":"worker-1"}
{"event":"tools_list","required_present":true,"tool_count":13,"worker":"worker-1"}
{"event":"tool_call","result":"ok","tool":"echo","worker":"worker-1"}
{"command":"smoke","event":"command_done","failed":0,"succeeded":1}
```

The pinned image reports server name `mcp-servers/everything`, version `2.0.0`, and 13 tools. It must report protocol `2025-11-25`, expose both `echo` and `trigger-long-running-operation`, and return `Echo: ags-cookbook`.

Logs show only a SHA-256 prefix for affinity values.

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

Record the number of `RUNNING` rows as `N`. The supported assertion is `1 <= N <= 3`. Do not infer `N` from the number of clients.

After the client exits, do not access the Deployment. Wait at least 60 seconds, then list instances again until the asynchronous transition converges; this can take several minutes. The active count must eventually return to zero; historical `STOPPED` rows may remain visible.

You may repeat `hold` with `--workers 3` to observe packing or scale-out. That is diagnostic only: under `BEST_EFFORT`, clients may share instances or migrate, and a multi-worker run may report a 400 or 429 rather than mapping one client to one instance.

## 7. Verify `BEST_EFFORT` with a fresh MCP session

After the instance used by the smoke test is `STOPPED`, reuse its saved AGS affinity with a completely new official MCP transport and session:

```bash
uv run --project client --locked python client/mcp_client.py resume \
  --url "$MCP_DEPLOYMENT_URL" \
  --transport direct \
  --state-file "$MCP_AFFINITY_STATE"
```

The command must again complete `initialize`, `tools/list`, and `echo`. The affinity fingerprint may stay the same or change. A changed value is valid `BEST_EFFORT` behavior and replaces the value in the state file.

The client never replays the previous process-local `MCP-Session-Id`. It also never retries an arbitrary failed tool call automatically, because the original call may already have executed.

## 8. Optional local proxy diagnostics

`agr deployment proxy` is useful for inspecting a Deployment, but it is not the acceptance path for this stateful server and native SDK combination. The proxy injects the token and manages affinity, so the client omits both:

```bash
agr deployment proxy "$MCP_DEPLOYMENT_ID" 18080:3001 --region "$AGR_REGION"
```

In another terminal:

```bash
uv run --project client --locked python client/mcp_client.py smoke \
  --url http://127.0.0.1:18080/mcp \
  --transport proxy
```

A cold start can exceed the proxy response-header timeout and return 502. Inspect instance readiness and use the direct production flow for the authoritative result. Do not weaken production acceptance because this optional path fails.

## Failure modes

| Symptom | Meaning and recovery |
| --- | --- |
| HTTP 401 | The Deployment token is missing or expired. Acquire a new token and update `MCP_DEPLOYMENT_TOKEN`. |
| HTTP 400 after migration | The request reached a process that does not own the old MCP session. Close the transport and initialize a fresh official MCP session. |
| HTTP 429 | All request or connection leases are occupied. Close abandoned clients or reduce concurrent workers. |
| Proxy 502 | Cold-start response headers exceeded the local proxy timeout. Inspect instance readiness and use direct production access. |
| Affinity fingerprint changes | This is permitted by `BEST_EFFORT`; use the newly returned value. |
| Instance remains `RUNNING` | Ensure every SDK and HTTP context is closed. If it remains active after convergence time, delete it explicitly. |
| Some multi-worker calls fail | This is a known stateful-session compatibility boundary, not a deterministic scaling contract. The one-client smoke remains authoritative. |

## 9. Clean up

Delete the Deployment first:

```bash
agr deployment delete "$MCP_DEPLOYMENT_ID" --region "$AGR_REGION" --wait
agr instance list --tool-id "$MCP_TOOL_ID" --region "$AGR_REGION"
```

Delete every instance that is not `STOPPED`:

```bash
export MCP_INSTANCE_ID='replace-with-non-stopped-instance-id'
agr instance delete "$MCP_INSTANCE_ID" --region "$AGR_REGION" --yes --wait
```

Delete the Tool, local state, and shell token:

```bash
agr tool delete "$MCP_TOOL_ID" --region "$AGR_REGION" --yes --wait
test -n "$MCP_STATE_DIR" && rm -r -- "$MCP_STATE_DIR"
unset MCP_DEPLOYMENT_TOKEN
```

Historical `STOPPED` instance rows may remain after their Tool is deleted. They are not active capacity and are not a cleanup failure.

## Acceptance checklist

- `uv sync --project client --locked` succeeds.
- The client tests pass.
- The locally built image returns 200 from `/healthz` and passes native `smoke`.
- The versioned CCR image has both `linux/amd64` and `linux/arm64` manifests.
- A fresh Shanghai Deployment rejects an unauthenticated request with 401.
- One direct native smoke completes.
- Active capacity is observed as `0 → N → 0` with `N >= 1`.
- `resume` succeeds after the original instance stops.
- No Deployment, Tool, non-stopped instance, token file, or affinity state file remains after cleanup.

The [httpbin scaling](../../httpbin/scaling/README.md), [lifecycle](../../httpbin/lifecycle/README.md), and [affinity](../../httpbin/affinity/README.md) tutorials cover the platform concepts in isolation.
