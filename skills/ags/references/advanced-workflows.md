# Advanced AGR Workflows

Load this file only when the user asks for browser/mobile sandboxes, API keys, raw Cloud API calls, image pre-cache, interactive login, or port access. For custom-image services, read [custom-images.md](custom-images.md).

## Browser

Create a browser Tool and show its VNC URL:

```bash
browser_tool_id=$(agr tool create \
  --tool-name "browser-$(date +%s)-$$" \
  --tool-type browser \
  --network-configuration '{"NetworkMode":"PUBLIC"}' \
  -o json --jq '.Data.ToolId')

browser_id=$(agr instance create \
  --tool-id "$browser_tool_id" \
  --timeout 30m \
  -o json --jq '.Data.InstanceId')

agr instance browser vnc "$browser_id" -o json
```

`browser vnc` returns JSON. Local Playwright/CDP details belong in SDK reference docs only when the user asks for SDK/browser automation code.

## Mobile

Create a mobile Tool and connect ADB to a short-lived Instance:

```bash
mobile_tool_id=$(agr tool create \
  --tool-name "mobile-$(date +%s)-$$" \
  --tool-type mobile \
  --network-configuration '{"NetworkMode":"PUBLIC"}' \
  -o json --jq '.Data.ToolId')

mobile_id=$(agr instance create \
  --tool-id "$mobile_tool_id" \
  --timeout 30m \
  -o json --jq '.Data.InstanceId')

agr instance get "$mobile_id" -o json
agr instance mobile connect "$mobile_id" -o json
```

After connecting:

```bash
agr instance mobile connect "$instance_id" -o json
agr instance mobile list -o json
agr instance mobile adb "$instance_id" -o json -- shell getprop ro.product.model
agr instance mobile disconnect "$instance_id" -o json
agr instance mobile disconnect --all -o json
agr instance mobile tunnel "$instance_id"  # manage tunnels directly
```

`mobile adb` requires an active tunnel from `mobile connect`.

## Interactive Proxy And Login

```bash
agr instance proxy "$instance_id" 3000:8080 --address 127.0.0.1
agr instance login "$instance_id" --user root
agr instance login "$instance_id" --mode webshell  # browser-based shell instead of PTY
```

`--mode` accepts `pty` (default, native terminal) or `webshell` (browser mode).

These commands are interactive and do not support JSON output. Do not run them in unattended scripts unless the user explicitly wants an interactive session.

`instance login` propagates the remote shell exit code (like `ssh`). If the PTY/envd session fails, it now reports the specific failure rather than a generic error.

## API Keys

API keys are for E2B SDK / MCP access, not for Cloud API management:

```bash
key_id=$(agr apikey create \
  --name "agent-key-$(date +%s)" \
  -o json --jq '.Data.KeyId')

agr apikey list -o json
agr apikey delete "$key_id" -o json
```

Do not print newly created API key secrets into logs or docs.

## Raw Cloud API

Use typed `agr tool`, `agr instance`, `agr apikey`, and `agr pre-cache-image-task` commands first. Use `agr api call` only when typed commands do not cover the operation.

```bash
agr api call DescribeSandboxInstanceList --request '{"Limit":1}' -o json
agr api call DescribeSystemImages --request '{"Keyword":"python","Limit":20}' -o json
agr api call StartSandboxInstance --request @start.json -o json
```

Server-side errors now include `RequestId` alongside `Code` and `Message` in CLI output, useful for filing support tickets.

## Image Pre-Cache

```bash
digest=$(agr pre-cache-image-task create \
  --image "ccr.ccs.tencentyun.com/team/runtime:v1" \
  --image-registry-type enterprise \
  -o json --jq '.Data.ImageDigest')

agr pre-cache-image-task get "$digest" \
  --image "ccr.ccs.tencentyun.com/team/runtime:v1" \
  --image-registry-type enterprise \
  -o json
```

Supported registry types are `enterprise` and `personal`. Check `agr pre-cache-image-task create --help` before using in automation.
