# Skill: Multi-Language Code Execution (AIO)

This example demonstrates **multi-language code execution** via the uvicorn `/execute` endpoint that AIO sandbox images bundle on port 49999. Unlike code-interpreter (Python only), AIO accepts `python`, `javascript`, `bash`, `r`, and `java` snippets in a single HTTP request and returns an NDJSON stream of `stdout` / `result` / `error` events.

The contract mirrors `e2e/aio/aio_dataplane_test.go` → the uvicorn test section.

## What this example demonstrates

- **`run_code(code, language)`** — one-shot execution; returns `{stdout, result, error}`
- **`run_many(snippets)`** — many snippets against the same AIO sandbox (stateless — language state does not persist across calls; use `skill-code-repl` for persistent Python)
- **`get_host_info()`** — introspect the sandbox URLs so an Agent can fan out custom requests to `/execute`, `/contexts`, `/novnc/`, `/vscode/` etc.

## Prerequisites

- Python 3.13 (managed by `uv`)
- `uv` installed
- Access to an AIO sandbox template (default `aio-v1`); authenticate via either AGS API key or Tencent Cloud AKSK

## Required environment variables

```bash
# Option A — APIKey mode
export E2B_API_KEY="your_ags_api_key"
export E2B_DOMAIN="ap-guangzhou.tencentags.com"
```

```bash
# Option B — AKSK mode
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
=== Skill Result: run_code (python) ===
{
  "instance_id": "sbi-xxxxxxxx",
  "language": "python",
  "status_code": 200,
  "stdout": "hello from python\n5050\n",
  "result": "",
  "error": null
}

=== Skill Result: run_code (javascript) ===
{"language": "javascript", "stdout": "hello from js\n6\n", "result": "", "error": null, ...}

=== Skill Result: run_code (bash) ===
{"language": "bash", "stdout": "hello from bash\n12\n", "result": "", "error": null, ...}
```

Each language's output style is that language's native `print` equivalent; R's `cat()` does not add newlines automatically, and Java requires a `public class`.

## Common failure modes

| Symptom | Likely cause |
|---|---|
| `KeyError: 'E2B_API_KEY'` | Environment variable not exported |
| Sandbox creation timeout | Wrong `E2B_DOMAIN` for your region |
| `TencentCloudSDKException` on credential check | Invalid or missing `TENCENTCLOUD_SECRET_ID` / `SECRET_KEY` |
| `status_code == 404` | Your tool image is not AIO — use `aio-v1` (or whichever AIO template your account provides) |
| `httpx.ReadTimeout` | Code ran longer than the 120s client timeout; split into smaller snippets |
| `error.name == "SyntaxError"` | Server-side interpreter rejected your code; see `error.traceback` |

## Skill interface

```python
run_code(code: str, language: str = "python", tool_name: str = "aio-v1", timeout: str = "10m") -> dict
run_many(snippets: list[dict], tool_name: str = "aio-v1", timeout: str = "10m") -> dict
get_host_info(tool_name: str = "aio-v1", timeout: str = "10m") -> dict
```
