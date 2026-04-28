# Skill: NoAuth Sandbox

This example demonstrates **starting a sandbox with `AuthMode=NONE`**, which disables the `X-Access-Token` check on every data-plane request. Only appropriate for internal networks where the data-plane URL is reachable exclusively by trusted callers (see `e2e/basic/noauth_test.go`).

Compared to the default `TOKEN` mode:

| Mode | Behaviour |
|---|---|
| `DEFAULT` / `TOKEN` | Every data-plane request must carry `X-Access-Token: <token>`. Missing or invalid token → 401/403. |
| `NONE` | No authentication on the data plane. Any request reaches the backend. |

> **AKSK-only.** `AuthMode` is a control-plane parameter.

## What this example demonstrates

- **`start_noauth(tool_name, timeout)`** — `StartSandboxInstance` with `AuthMode=NONE`; returns `instance_id` plus pre-built data-plane URLs
- **`probe_noauth(instance_id, path)`** — GET the data plane both with and without a token; proves the `NONE` behaviour by comparing status codes
- **`stop_noauth(instance_id)`** — clean up

## Prerequisites

- Python 3.13 (managed by `uv`)
- `uv` installed
- Valid Tencent Cloud credentials
- A tool image that exposes `/health` on port 9000 (true for `code-interpreter-v1`, `browser-v1`, and `aio-v1`)

## Required environment variables

```bash
export TENCENTCLOUD_SECRET_ID="your_secret_id"
export TENCENTCLOUD_SECRET_KEY="your_secret_key"
export TENCENTCLOUD_REGION="ap-guangzhou"
```

## Install and run

```bash
make setup
make run
```

## Expected output

```
=== Skill Result: start_noauth ===
{
  "instance_id": "sbi-xxxxxxxx",
  "auth_mode": "NONE",
  "nginx_base": "https://9000-sbi-xxxxxxxx.ap-guangzhou.tencentags.com/",
  "uvicorn_execute": "https://49999-sbi-xxxxxxxx.ap-guangzhou.tencentags.com/execute"
}

=== Skill Result: probe_noauth ===
{
  "url": "https://9000-sbi-xxxxxxxx.ap-guangzhou.tencentags.com/health",
  "with_token":    {"status": 200, "body_head": "ok"},
  "without_token": {"status": 200, "body_head": "ok"},
  "same_status": true,
  "token_required_for_access": false
}

=== Skill Result: stop_noauth ===
{"instance_id": "sbi-xxxxxxxx", "stopped": true}
```

The `"same_status": true` + `"token_required_for_access": false` combination is the proof that NoAuth mode is working: the token-less request succeeded.

Run the same skill with the instance started in default `TOKEN` mode (via `skill-sandbox-lifecycle.start_and_get_status` → `probe_noauth`) and you will instead see `without_token.status == 401` and `token_required_for_access: true`.

## Common failure modes

| Symptom | Likely cause |
|---|---|
| `KeyError: 'E2B_API_KEY'` | Not applicable — this skill is AKSK-only |
| Sandbox creation timeout | `E2B_DOMAIN` wrong (only affects other skills) |
| `TencentCloudSDKException` on `StartSandboxInstance` | Invalid credentials, or your tool does not support `AuthMode=NONE` |
| `without_token.status == 401/403` despite `AuthMode=NONE` | Reverse-proxy cached; wait a few seconds and retry, or the instance is still in `STARTING` |
| `httpx.ConnectError` | Data-plane URL not yet reachable — `start_instance` returns before `/health` is ready; add a small sleep |

## Skill interface

```python
start_noauth(tool_name: str = "code-interpreter-v1", timeout: str = "10m") -> dict
probe_noauth(instance_id: str, path: str = "/health", port: int = 9000) -> dict
stop_noauth(instance_id: str) -> dict
```
