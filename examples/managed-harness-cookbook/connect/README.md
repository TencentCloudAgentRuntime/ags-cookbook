# Connect to a managed harness: prompt, acp, proxy, endpoint, and web

This tutorial creates its own DSH harness and connects in five ways: four use the Streamable HTTP transport of [ACP (Agent Client Protocol)](https://agentclientprotocol.com), and one opens the native DSH Web console.

Complete the shared [prerequisites](../README.md#prerequisites) and [configuration](../README.md#configuration) before starting.

| Scenario | Command | Notes |
| --- | --- | --- |
| Quick checks in a terminal, scripts | `agr harness prompt` | One turn at a time, streamed output, JSON and NDJSON |
| Editors, acpx, and other clients that launch agents as subprocesses | `agr harness acp` | Turns the remote harness into a local stdio agent |
| Local debugging with browsers, IDE plugins, ACP SDKs | `agr harness proxy` | Local HTTP address that adds the token and affinity |
| Direct connection from your own service | `agr harness endpoint` | Prints the real ACP URL and headers; your client owns the connection |
| Native DSH console in a browser | `agr harness web` | Opens the Deployment's HTTPS Webview; no local proxy needed |

Sample output masks real values.

## 1. Set environment variables and create the harness

```bash
set -a
source ../.env
set +a
bash ../scripts/preflight.sh connect &&

export MODEL_PROVIDER_NAME="harness-connect-$HARNESS_NAME_SUFFIX" &&
export HARNESS_NAME="harness-connect-$HARNESS_NAME_SUFFIX" &&

MODEL_PROVIDER_ID=$(python3 ../scripts/resources.py create connect model-provider \
  --name "$MODEL_PROVIDER_NAME" \
  --tokenhub-api-key-id "$TOKENHUB_API_KEY_ID" \
  --model hy3) && export MODEL_PROVIDER_ID
```

This tutorial uses `dsh@0.2.1-rc.2` so it can also demonstrate the native Web console. Check the available versions in your region first:

```bash
agr harness engine list --region "$AGR_REGION"
```

Use the DSH version listed for your region if it differs, then create the harness with the saved model provider ID and check the ACP endpoint:

```bash
HARNESS_ID=$(python3 ../scripts/resources.py create connect harness \
  --name "$HARNESS_NAME" \
  --engine dsh \
  --engine-version 0.2.1-rc.2 \
  --model "$MODEL_PROVIDER_ID:hy3" \
  --role-arn "$AGR_ROLE_ARN" \
  --subnet-id "$HARNESS_SUBNET_ID" \
  --security-group-id "$HARNESS_SECURITY_GROUP_ID" \
  --wait) && export HARNESS_ID
```

```bash
agr harness endpoint "$HARNESS_ID" --region "$AGR_REGION" --check
```

The `Check` line should read `reachable in <n>ms`.

## 2. `prompt`: multi-turn conversations

Every `prompt` run opens a new ACP connection. To continue in the same session, pass back two values from the previous turn:

- `SessionId`: the ACP session ID.
- `AffinityId`: a platform-issued affinity value that routes requests to the instance holding the session. `SessionId` cannot replace it.

Get both values from the first turn with `-o json`:

```bash
agr harness prompt "$HARNESS_ID" --region "$AGR_REGION" -o json \
  'Remember the code word "cedar". Reply only with "OK".'
```

```json
{
  "Status": "succeeded",
  "Data": {
    "HarnessId": "hns-********",
    "SessionId": "<masked-session-id>",
    "AffinityId": "<masked-affinity-id>",
    "Reply": "OK",
    "ToolCalls": [],
    "StopReason": "end_turn",
    "DurationMs": 2380
  }
}
```

You can also extract them with `--jq`. Store both values and ask the second turn:

```bash
export HARNESS_SESSION_ID='replace-with-session-id'
export HARNESS_AFFINITY_ID='replace-with-affinity-id'

agr harness prompt "$HARNESS_ID" --region "$AGR_REGION" \
  --session-id "$HARNESS_SESSION_ID" \
  --affinity-id "$HARNESS_AFFINITY_ID" \
  'What was the code word?'
```

The reply should contain `cedar`. Without `--affinity-id`, the request may land on another instance; without a session space, the new instance cannot find the old session. See [scaling-session](../scaling-session/README.md) for keeping sessions across instances.

Other common forms:

```bash
# Read the prompt from stdin
echo 'List the files in the current directory.' | agr harness prompt "$HARNESS_ID" --region "$AGR_REGION" -

# One event per line, for agents that process output incrementally
agr harness prompt "$HARNESS_ID" --region "$AGR_REGION" -o ndjson 'Say hello.'
```

The first NDJSON line is `started` (with `SessionId`); each ACP `session/update` becomes one `update` line whose `Data` is the raw ACP content; the last line is `completed` and carries the same `Data` as `-o json`:

```text
{"SchemaVersion":"agr.events.v1","Type":"started","Data":{"HarnessId":"hns-********","SessionId":"<masked>"}}
{"SchemaVersion":"agr.events.v1","Type":"update","Data":{"sessionUpdate":"agent_message_chunk","content":{"type":"text","text":"Hello"}}}
{"SchemaVersion":"agr.events.v1","Type":"completed","Data":{"HarnessId":"hns-********","SessionId":"<masked>","Reply":"Hello!","StopReason":"end_turn",...}}
```

`prompt` cannot approve tool calls on a person's behalf; it answers every permission request with `cancelled`. `Ctrl+C` sends `session/cancel`, and an unfinished turn is never resent.

## 3. `acp`: editors and acpx

`agr harness acp` bridges ACP JSON-RPC on stdin/stdout to the remote harness, refreshing the token and keeping the affinity for the whole process. Stdout carries only ACP messages; diagnostics go to stderr.

Launch the bridge with `-o text` to select raw ACP output and override any configured JSON or NDJSON default. Stdout still carries ACP JSON-RPC messages.

The bridge forwards the client's `cwd` unchanged; it does not map paths or sync local files. Creating or restoring a session requires an existing, accessible absolute directory inside the sandbox. This optional Unix smoke test requires Node.js 22.13 or newer and runs [acpx](https://github.com/openclaw/acpx) 0.22.0 through `npx`. Install them before running this example; `prompt`, `proxy` and `endpoint` do not need them. It uses `/tmp`, which exists both locally and in the managed image:

```bash
npx --yes acpx@0.22.0 --cwd /tmp --agent "agr harness acp $HARNESS_ID --region $AGR_REGION -o text" exec 'Summarize what you can do in one sentence.'
```

Editors such as Zed normally send the local project path as `cwd`. The configuration below requires that same absolute path to exist on the target instance; it does not prepare a remote project directory. If the path does not exist there, use `agr harness prompt` (whose remote `cwd` defaults to `/workspace`), or a client that can map the working directory to an existing remote path.

Once that directory requirement is met, add a custom ACP agent to Zed's `settings.json`:

```json
{
  "agent_servers": {
    "managed-harness": {
      "type": "custom",
      "command": "agr",
      "args": ["harness", "acp", "hns-replace-me", "--region", "ap-chongqing", "-o", "text"],
      "env": {}
    }
  }
}
```

Other editors use the same command `agr` with the arguments `harness acp <harness-id> --region <region> -o text`. The editor starts the subprocess when needed. To return to the instance of an earlier session, append `--affinity-id <affinity-id>` to `args`.

## 4. `proxy`: a local debugging address

`proxy` serves a credential-free ACP address on your machine. It adds and refreshes the token and keeps the affinity. It occupies the current terminal:

```bash
agr harness proxy "$HARNESS_ID" --region "$AGR_REGION" --port 18080
```

Expected output:

```text
ACP endpoint: http://127.0.0.1:18080/acp
Forwarding to https://8080-dpl-********.ap-chongqing.agents.tencentags.com/acp (Deployment dpl-********). Local testing only.
Press Ctrl+C to stop.
Affinity ID: <masked-affinity-id>
```

`Affinity ID` appears after the first request returns. Point an ACP SDK or browser client at `http://127.0.0.1:18080/acp`, for example the HTTP transport of the official TypeScript SDK.

When an agent starts the proxy in the background, use a random port and NDJSON, and read the address from the first line:

```bash
agr harness proxy "$HARNESS_ID" --region "$AGR_REGION" --port 0 -o ndjson
```

```text
{"SchemaVersion":"agr.events.v1","Type":"ready","Data":{"AcpURL":"http://127.0.0.1:54321/acp","RemoteAcpURL":"https://8080-dpl-********.ap-chongqing.agents.tencentags.com/acp","HarnessId":"hns-********","DeploymentId":"dpl-********","AffinityHeader":"X-Tencent-Agr-Affinity-Id"}}
```

The proxy is for local debugging only and listens on `127.0.0.1` by default. Press `Ctrl+C` to stop it.

## 5. `endpoint`: direct connection from your own service

A production service should call `AcquireDeploymentToken` for a short-lived token and connect to the ACP URL directly. `endpoint` prints the URL and the headers you must send; `--show-token` also issues a token for manual testing.

```bash
agr harness endpoint "$HARNESS_ID" --region "$AGR_REGION" --show-token -o json \
  --jq '.Data | {AcpURL, AffinityHeader, DeploymentId, ExpiresAt, Headers}'
```

```json
{"AcpURL":"https://8080-dpl-********.ap-chongqing.agents.tencentags.com/acp","AffinityHeader":"X-Tencent-Agr-Affinity-Id","DeploymentId":"dpl-********","ExpiresAt":"<masked-expiration>","Headers":{"X-Access-Token":"<masked-deployment-token>"}}
```

The CLI does not refresh tokens for external programs. A long-running service should call `AcquireDeploymentToken` itself before `ExpiresAt`. Read the Deployment ID saved during creation:

```bash
HARNESS_DEPLOYMENT_ID=$(python3 ../scripts/resources.py get connect DeploymentId) && export HARNESS_DEPLOYMENT_ID

agr api call AcquireDeploymentToken \
  --region "$AGR_REGION" \
  --request '{"DeploymentId":"'$HARNESS_DEPLOYMENT_ID'"}' \
  --output json
```

The token is at `Data.Response.Response.Token`.

### Walk through ACP Streamable HTTP with `curl`

The following steps complete one conversation by hand with `curl` to show how the protocol works. In production, use an official ACP SDK, which already handles these details.

Protocol summary:

1. Every request carries `X-Access-Token`.
2. `initialize` returns the JSON result directly and an `Acp-Connection-Id` response header. Send that header on every later request.
3. Echo the affinity header from responses (default `X-Tencent-Agr-Affinity-Id`) on every later request, so all requests of one connection reach the same instance.
4. Later POSTs return `202 Accepted`. Results and updates arrive on SSE streams opened with GET: one connection stream, and one session stream per session with `Acp-Session-Id`.
5. Close the connection with DELETE.

The following steps use three terminals. Write the variables to `acp.env`, and run `source acp.env` first in every new terminal. Copy the URL and token from the previous step's output:

```bash
cat > acp.env <<'EOF'
export ACP_URL='https://8080-dpl-replace-me.ap-chongqing.agents.tencentags.com/acp'
export ACP_TOKEN='replace-with-token'
EOF
source acp.env
```

The token stops working at `ExpiresAt`. When it does, run `endpoint --show-token` from the previous step again and update `acp.env`.

**Step 1: initialize.** `--include` shows the response headers:

```bash
curl --include --silent --show-error -X POST "$ACP_URL" \
  --header "X-Access-Token: $ACP_TOKEN" \
  --header 'Content-Type: application/json' \
  --header 'Accept: application/json, text/event-stream' \
  --data '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":1,"clientCapabilities":{}}}'
```

```http
HTTP/2 200
content-type: application/json
acp-connection-id: <masked-connection-id>
x-tencent-agr-affinity-id: <masked-affinity-id>

{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":1,"agentCapabilities":{"loadSession":true,...},"agentInfo":{...}}}
```

Append both response headers to `acp.env`:

```bash
cat >> acp.env <<'EOF'
export ACP_CONNECTION_ID='replace-with-connection-id'
export ACP_AFFINITY_ID='replace-with-affinity-id'
EOF
source acp.env
```

**Step 2: open the connection SSE stream.** Open a second terminal in the same directory and keep it running; the `session/new` result arrives here:

```bash
source acp.env

curl --no-buffer --silent --show-error "$ACP_URL" \
  --header "X-Access-Token: $ACP_TOKEN" \
  --header "Acp-Connection-Id: $ACP_CONNECTION_ID" \
  --header "X-Tencent-Agr-Affinity-Id: $ACP_AFFINITY_ID" \
  --header 'Accept: text/event-stream'
```

**Step 3: create a session.** Back in the first terminal:

```bash
curl --include --silent --show-error -X POST "$ACP_URL" \
  --header "X-Access-Token: $ACP_TOKEN" \
  --header "Acp-Connection-Id: $ACP_CONNECTION_ID" \
  --header "X-Tencent-Agr-Affinity-Id: $ACP_AFFINITY_ID" \
  --header 'Content-Type: application/json' \
  --header 'Accept: application/json, text/event-stream' \
  --data '{"jsonrpc":"2.0","id":2,"method":"session/new","params":{"cwd":"/workspace","mcpServers":[]}}'
```

The POST returns `HTTP/2 202`. The result appears in the SSE terminal:

```text
data: {"jsonrpc":"2.0","id":2,"result":{"sessionId":"<masked-session-id>",...}}
```

Append the session ID to `acp.env`:

```bash
echo "export ACP_SESSION_ID='replace-with-session-id'" >> acp.env
source acp.env
```

**Step 4: open the session SSE stream.** Open a third terminal in the same directory. Reply chunks (`session/update`) and the final `session/prompt` result arrive here:

```bash
source acp.env

curl --no-buffer --silent --show-error "$ACP_URL" \
  --header "X-Access-Token: $ACP_TOKEN" \
  --header "Acp-Connection-Id: $ACP_CONNECTION_ID" \
  --header "Acp-Session-Id: $ACP_SESSION_ID" \
  --header "X-Tencent-Agr-Affinity-Id: $ACP_AFFINITY_ID" \
  --header 'Accept: text/event-stream'
```

**Step 5: send a prompt.**

```bash
curl --include --silent --show-error -X POST "$ACP_URL" \
  --header "X-Access-Token: $ACP_TOKEN" \
  --header "Acp-Connection-Id: $ACP_CONNECTION_ID" \
  --header "Acp-Session-Id: $ACP_SESSION_ID" \
  --header "X-Tencent-Agr-Affinity-Id: $ACP_AFFINITY_ID" \
  --header 'Content-Type: application/json' \
  --header 'Accept: application/json, text/event-stream' \
  --data '{"jsonrpc":"2.0","id":3,"method":"session/prompt","params":{"sessionId":"'"$ACP_SESSION_ID"'","prompt":[{"type":"text","text":"Say hello in five words."}]}}'
```

The session SSE terminal shows reply chunks followed by the final result:

```text
data: {"jsonrpc":"2.0","method":"session/update","params":{"sessionId":"<masked>","update":{"sessionUpdate":"agent_message_chunk","content":{"type":"text","text":"Hello"}}}}
...
data: {"jsonrpc":"2.0","id":3,"result":{"stopReason":"end_turn"}}
```

**Step 6: close the connection.** Press `Ctrl+C` in both SSE terminals, then:

```bash
curl --include --silent --show-error -X DELETE "$ACP_URL" \
  --header "X-Access-Token: $ACP_TOKEN" \
  --header "Acp-Connection-Id: $ACP_CONNECTION_ID" \
  --header "X-Tencent-Agr-Affinity-Id: $ACP_AFFINITY_ID"
```

Platform errors are returned as JSON. For example, when the underlying Tool is unavailable:

```json
{"code":"sandbox_tool_unavailable","message":"sandbox tool is unavailable; tool status: NOT_FOUND","request_id":"<masked-request-id>"}
```

Through `agr` commands, these errors are classified as `ACP_UNAVAILABLE`, with the platform code in `Failure.Details.PlatformCode`.

## 6. `web`: open the native DSH console

The harness must have a **PUBLISHED DSH revision** and an **ACTIVE Deployment**. The command checks the published revision, so changing only the draft engine is not enough. If you previously ran this scenario with pi, clean up those resources before creating the DSH harness in step 1.

On a machine with a browser:

```bash
agr harness web "$HARNESS_ID" --region "$AGR_REGION" -o text
```

The command acquires a short-lived Deployment token, requests a browser launch on the machine running the CLI, and exits. It opens the HTTPS Webview root on service port **3080**; ACP still uses port **8080** and `/acp`. No local proxy or persistent CLI process is needed. `Browser launch requested: true` means the launch was requested; it does not prove the page is ready. The browser visit can start an instance, so the first page load may take longer.

Once the page opens:

1. If the preview notice appears, choose **Continue**.
2. Choose **Select workspace**, edit the path to `/workspace`, press Enter, then choose **Open**. This is a directory inside the sandbox; local files are not uploaded automatically.
3. The model selector should show the published `hy3` model. You do not need to enter a TokenHub API key in the page. Send `Reply only with WEB-OK.` and confirm the reply is `WEB-OK`.

To inspect the safe URL without opening a browser or acquiring a token:

```bash
agr harness web "$HARNESS_ID" --region "$AGR_REGION" --no-open -o json
```

```json
{
  "Status": "succeeded",
  "Data": {
    "HarnessId": "hns-********",
    "DeploymentId": "dpl-********",
    "Revision": 1,
    "WebURL": "https://3080-dpl-********-webview.ap-chongqing.agents.tencentags.com/",
    "Opened": false
  }
}
```

For SSH or a machine without a browser, explicitly acquire a login link and copy `AccessURL` to your browser:

```bash
agr harness web "$HARNESS_ID" --region "$AGR_REGION" --no-open --show-token -o json \
  --jq '.Data | {AccessURL, ExpiresAt}'
```

`WebURL` never contains a token. `AccessURL` contains a token and is returned only with `--show-token`; treat it as a credential and keep it out of shared logs. If the token or browser authentication expires, run the command again for a new link.

To request the instance affinity obtained in step 2 when entering the console:

```bash
agr harness web "$HARNESS_ID" --region "$AGR_REGION" --affinity-id "$HARNESS_AFFINITY_ID" -o text
```

`--affinity-id` sets `affinity_id` on the initial URL; the gateway then maintains browser affinity through a cookie. Tabs on the same Webview host share that cookie and do not provide instance isolation. This identifies an instance, not an ACP SessionId.

## 7. Clean up

Close the Web console tab and stop the local proxy from step 4 with `Ctrl+C`, then delete the resources saved for this scenario. The helper reads the IDs, region and endpoint from `.state/`, waits for deletion, and verifies the result. You can run it again after an interrupted cleanup.

```bash
python3 ../scripts/resources.py cleanup connect --yes
rm -f acp.env
```

## Common issues

| Symptom | Cause and fix |
| --- | --- |
| `ACP_UNAVAILABLE` with a `PlatformCode` saying the instance is not ready | The instance is still starting. Wait a moment and retry `endpoint --check` |
| `ACP_UNAVAILABLE` with `PlatformCode` `sandbox_tool_unavailable` | The underlying Tool was deleted or is unavailable, and the harness does not recreate it. Delete the harness and create a new one |
| `ACP_AUTH_FAILED` | The token is invalid or expired. Acquire a new one; with `agr` commands, check `--domain` and the `AcquireDeploymentToken` permission |
| `SESSION_RESTORE_FAILED` | The old session is not on the current instance. Pass the `--affinity-id` and `--cwd` used when the session was created, or configure a session space |
| `PROMPT_TIMEOUT` | No reply within `--timeout`; `session/cancel` was sent. Raise `--timeout`, or continue with `--session-id` and `--affinity-id` |
| `PROXY_BIND_FAILED` | The local port is in use. Choose another `--port`, or use `--port 0` for a free one |
| `HARNESS_WEB_UNSUPPORTED_ENGINE` | The published revision is not DSH. A DSH draft alone is insufficient; create and publish a DSH revision and replace old instances, or start with the DSH harness in step 1 |
| `HARNESS_NOT_PUBLISHED` or `HARNESS_NOT_DEPLOYED` | Check `harness status` and finish publishing a DSH revision before opening the console |
| `DEPLOYMENT_NOT_ACTIVE` | Check `deployment get` and wait for the Deployment to become `ACTIVE` |
| `BROWSER_OPEN_FAILED` | The CLI could not start a browser on that machine. Use `--no-open --show-token` and copy `AccessURL` to your browser |
