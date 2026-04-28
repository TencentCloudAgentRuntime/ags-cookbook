# Skill: File Sandbox

This example demonstrates **sandbox filesystem I/O** as an AGS Skill: uploading data into a sandbox, transforming it with in-sandbox code, and downloading the result — all in a single skill call.

## What this example demonstrates

- **`upload_and_run`** — write text content into a sandbox path, execute a Python transform that reads and writes files inside the sandbox, then download and return the result file content
- **`list_sandbox_dir`** — return the directory listing of a given path inside a fresh sandbox

Authentication is auto-detected at runtime by `ags_client.SandboxSession` — either AKSK control-plane mode or APIKey direct mode — so the skill body is the same across both.

## Prerequisites

- Python 3.13 (managed by `uv`)
- `uv` installed
- Either an AGS API key **or** a pair of Tencent Cloud credentials

## Required environment variables

Pick one of the two modes:

```bash
# Option A — APIKey mode (direct sandbox connection)
export E2B_API_KEY="your_ags_api_key"
export E2B_DOMAIN="ap-guangzhou.tencentags.com"
```

```bash
# Option B — AKSK mode (Tencent Cloud control-plane)
export TENCENTCLOUD_SECRET_ID="your_secret_id"
export TENCENTCLOUD_SECRET_KEY="your_secret_key"
export TENCENTCLOUD_REGION="ap-guangzhou"
```

When both variable sets are defined, AKSK mode takes precedence (see `ags_client.credential_mode()`).

## Install and run

```bash
make setup
make run
```

## Expected output

```
INFO upload_and_run: creating sandbox…
INFO uploaded 52 bytes → /tmp/scores.csv
INFO downloaded 128 bytes ← /tmp/ranked.json
INFO upload_and_run: sandbox closed.

=== Skill Result: upload_and_run ===
{
  "uploaded": "/tmp/scores.csv",
  "stdout": ["sorted 3 rows"],
  "result_content": "[\n  {\"name\": \"Charlie\", \"score\": \"95\"},\n  …\n]",
  "error": null
}

=== Skill Result: list_sandbox_dir ===
{
  "path": "/tmp",
  "entries": ["…"],
  "error": null
}
```

## Common failure modes

| Symptom | Likely cause |
|---|---|
| `KeyError: 'E2B_API_KEY'` | Environment variable not exported |
| Sandbox creation timeout | Wrong `E2B_DOMAIN` for your region |
| `TencentCloudSDKException` on credential check | Invalid or missing `TENCENTCLOUD_SECRET_ID` / `SECRET_KEY` |

## Skill interface

```python
upload_and_run(local_text: str, remote_path: str, transform_code: str, result_path: str) -> dict
list_sandbox_dir(path: str = "/tmp") -> dict
```
