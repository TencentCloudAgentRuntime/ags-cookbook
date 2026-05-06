# Skill: Tencent Cloud API

This example demonstrates **Tencent Cloud control-plane calls** as an AGS Skill using `tencentcloud-sdk-python`.

## What this example demonstrates

- **`get_caller_identity`** — verify Tencent Cloud credentials via STS `GetCallerIdentity` and return the caller's `AccountId`, `ARN`, and `UserId`
- **`list_sandbox_images`** — list available AGS sandbox image templates in a given region via the AGS API; falls back gracefully to a representative static list when the API endpoint is not yet accessible

> **Note** — Unlike the other skills in this directory, `skill-tencent-cloud-api` is **AKSK-only**: its value is demonstrating control-plane calls that are inherently scoped to a Tencent Cloud account. Therefore it does not use `ags_client.SandboxSession` (no sandbox is created) and the APIKey-mode fallback does not apply.

## Prerequisites

- Python 3.13 (managed by `uv`)
- `uv` installed
- Valid Tencent Cloud credentials (`TENCENTCLOUD_SECRET_ID` / `SECRET_KEY`)

## Required environment variables

```bash
export TENCENTCLOUD_SECRET_ID="your_secret_id"
export TENCENTCLOUD_SECRET_KEY="your_secret_key"
export TENCENTCLOUD_REGION="ap-guangzhou"

# Optional — only used by list_sandbox_images if AGS API is accessible
export E2B_API_KEY="your_ags_api_key"
export E2B_DOMAIN="ap-guangzhou.tencentags.com"
```

## Install and run

```bash
make setup
make run
```

## Expected output

```
INFO get_caller_identity: verifying credentials (region=ap-guangzhou)…
INFO Credential OK — AccountId=100xxxxxxxxx

=== Skill Result: get_caller_identity ===
{
  "account_id": "100xxxxxxxxx",
  "arn": "qcs::cam::uin/100xxxxxxxxx:root",
  "user_id": "100xxxxxxxxx",
  "error": null
}

=== Skill Result: list_sandbox_images ===
{
  "region": "ap-guangzhou",
  "images": [
    {"image_id": "code-interpreter-v1", "name": "Code Interpreter v1", "type": "builtin"},
    …
  ],
  "source": "api",
  "error": null
}
```

When the AGS API module is not yet available, `source` will be `"static_fallback"` and `error` will contain the import or SDK error message.

## Common failure modes

| Symptom | Likely cause |
|---|---|
| `KeyError: 'E2B_API_KEY'` | Environment variable not exported |
| Sandbox creation timeout | Wrong `E2B_DOMAIN` for your region |
| `TencentCloudSDKException` on credential check | Invalid or missing `TENCENTCLOUD_SECRET_ID` / `SECRET_KEY` |

## Skill interface

```python
get_caller_identity() -> dict
list_sandbox_images(region: str | None = None) -> dict
```
