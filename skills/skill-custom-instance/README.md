# Skill: Custom Instance

This example demonstrates **creating a sandbox tool from a user-supplied container image**. Use this when the stock `code-interpreter-v1` / `browser-v1` / `aio-v1` images do not ship the binaries or runtime your Agent needs.

The flow mirrors `e2e/basic/custom/custom_tool_test.go`:

1. `CreateSandboxTool(ToolType="custom", CustomConfiguration={Image, Command, Args, Ports, Resources, Probe, Env}, RoleArn=…)`
2. `StartSandboxInstance(ToolId=<new tool>)`
3. Talk to the instance on one of the exposed ports (URL: `https://<port>-<instanceId>.<region>.tencentags.com/…` with `X-Access-Token` header)
4. `StopSandboxInstance`
5. Optionally `DeleteSandboxTool`

> **AKSK-only.** Custom images require `RoleArn` and control-plane access.

## What this example demonstrates

- **`start_custom(image, command, ports, resources, probe, env, role_arn, …)`** — create tool + start instance in one call; returns `tool_id`, `instance_id`, and a map of port-name → data-plane URL
- **`stop_custom(instance_id, tool_id=None, delete_tool_after=False)`** — teardown

## Prerequisites

- Python 3.13 (managed by `uv`)
- `uv` installed
- Valid Tencent Cloud credentials
- A `RoleArn` authorised to pull the image you specify
- (Optional) A tested image reference — demo defaults are illustrative; replace with what your account owns

## Required environment variables

```bash
export TENCENTCLOUD_SECRET_ID="your_secret_id"
export TENCENTCLOUD_SECRET_KEY="your_secret_key"
export TENCENTCLOUD_REGION="ap-guangzhou"

# Required for custom images
export AGS_ROLE_ARN="qcs::cam::uin/<your-uin>:roleName/<role>"

# Optional — override the demo image
export AGS_DEMO_CUSTOM_IMAGE="ags-sandbox-image-pub/python-general:latest"
export AGS_DEMO_CUSTOM_REGISTRY_TYPE="system"    # enterprise | personal | system
```

## Install and run

```bash
make setup
make run
```

## Expected output

```
=== Skill Result: start_custom ===
{
  "tool_id":   "tool-xxxxxxxx",
  "tool_name": "agsskill-custom-…",
  "instance_id": "sbi-xxxxxxxx",
  "image":  "ags-sandbox-image-pub/python-general:latest",
  "ports":  [{"Name": "envd", "Port": 49983, "Protocol": "TCP"}],
  "data_plane_urls": {
    "envd": "https://49983-sbi-xxxxxxxx.ap-guangzhou.tencentags.com/"
  }
}

=== Skill Result: stop_custom ===
{
  "instance_id": "sbi-xxxxxxxx",
  "stopped": true,
  "tool_id": "tool-xxxxxxxx",
  "tool_deleted": true
}
```

## Common failure modes

| Symptom | Likely cause |
|---|---|
| `KeyError: 'E2B_API_KEY'` | Not applicable — this skill is AKSK-only |
| Sandbox creation timeout | `E2B_DOMAIN` wrong (only affects other skills) |
| `TencentCloudSDKException` with `InvalidParameter` on CreateSandboxTool | Missing `RoleArn`, wrong `ImageRegistryType`, or the image is not accessible from your account |
| Instance stuck in `STARTING` | Probe failing — check the `Probe.HttpGet.{Path,Port,Scheme}` values match the image's real readiness endpoint |
| Forbidden on port URL | Your nginx/proxy may require tokens; attach `X-Access-Token` to the request |

## Skill interface

```python
start_custom(
    image: str,
    command: list[str],
    role_arn: str | None = None,          # falls back to AGS_ROLE_ARN env
    args: list[str] | None = None,
    ports: list[dict] | None = None,      # [{"Name": "http", "Port": 8000, "Protocol": "TCP"}]
    resources: dict | None = None,        # {"CPU": "1000m", "Memory": "500Mi"}
    probe: dict | None = None,            # {"HttpGet": {"Path": "/health", "Port": 8000, "Scheme": "HTTP"}, ...}
    env: list[dict] | None = None,        # [{"Name": "FOO", "Value": "bar"}]
    image_registry_type: str = "enterprise",
    tool_name: str | None = None,
    timeout: str = "10m",
) -> dict

stop_custom(instance_id: str, tool_id: str | None = None, delete_tool_after: bool = False) -> dict
```
