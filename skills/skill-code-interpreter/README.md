# Skill: Code Interpreter

This example demonstrates **sandboxed code execution** as an AGS Skill that an Agent can invoke as a tool.

## What this example demonstrates

- **`run_code`** — execute an arbitrary Python snippet inside a fresh AGS sandbox and return `stdout` and any errors as a structured dict
- **`run_code_multi_context`** — run multiple snippets inside a **single** sandbox, each in its own isolated execution context; proves that Python state (variables) does not leak between contexts while the filesystem (`/tmp`) is shared

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
INFO SandboxSession: mode=apikey tool=code-interpreter-v1 timeout=10m
INFO APIKey sandbox created (template=code-interpreter-v1, timeout=300s).
INFO APIKey sandbox killed.

=== Skill Result: run_code ===
{
  "stdout": ["2^10 = 1024\n", "Python 3.x.x …\n"],
  "text_results": [],
  "error": null
}

=== Skill Result: run_code_multi_context ===
{
  "contexts": [
    {"context_index": 0, "stdout": ["[ctx0] ctx A secret: context-A-only\n"], "error": null},
    {"context_index": 1, "stdout": ["[ctx1] ctx B: secret is NOT visible — isolation confirmed\n"], "error": null}
  ]
}
```

In AKSK mode the log prefix reads `mode=aksk` and the instance id is a real AGS sandbox id.

## Common failure modes

| Symptom | Likely cause |
|---|---|
| `KeyError: 'E2B_API_KEY'` | Environment variable not exported |
| Sandbox creation timeout | Wrong `E2B_DOMAIN` for your region |
| `TencentCloudSDKException` on credential check | Invalid or missing `TENCENTCLOUD_SECRET_ID` / `SECRET_KEY` |

## Skill interface

```python
run_code(code: str) -> dict
run_code_multi_context(snippets: list[str]) -> dict
```

Both return JSON-serialisable dicts suitable for direct consumption by an Agent.
