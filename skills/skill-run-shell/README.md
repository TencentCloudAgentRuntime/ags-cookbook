# Skill: Run Shell

This example demonstrates **bash command execution** inside an AGS sandbox — the single most frequently used primitive for agentic workflows. It wraps the e2b SDK's `sandbox.commands.run()` API and returns the canonical `(exit_code, stdout, stderr)` triple in a JSON-serialisable dict.

## What this example demonstrates

- **`run_shell`** — execute a single command, return `exit_code`, `stdout`, `stderr`
- **`run_shell_many`** — execute a list of commands sequentially in the *same* sandbox, stopping at the first non-zero exit code; useful for Agent-driven multi-step scripts where each step depends on the previous one succeeding

Authentication is auto-detected at runtime by `ags_client.SandboxSession` — either AKSK control-plane mode or APIKey direct mode.

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

When both variable sets are defined, AKSK mode takes precedence.

## Install and run

```bash
make setup
make run
```

## Expected output

```
=== Skill Result: run_shell ===
{
  "cmd": "echo hello && echo boom >&2 && exit 3",
  "exit_code": 3,
  "stdout": "hello\n",
  "stderr": "boom\n"
}

=== Skill Result: run_shell (pipe) ===
{
  "cmd": "printf 'a\\nb\\nc\\n' | sort -r | head -n2",
  "exit_code": 0,
  "stdout": "c\nb\n",
  "stderr": ""
}

=== Skill Result: run_shell_many ===
{
  "results": [
    {"cmd": "echo step-1", "exit_code": 0, ...},
    {"cmd": "ls /tmp | head -n3", "exit_code": 0, ...},
    {"cmd": "false", "exit_code": 1, "stdout": "", "stderr": ""}
  ],
  "failed_at": 2,
  "ok": false
}
```

A non-zero `exit_code` is not an error from this skill's perspective — it is a normal result reported back to the Agent. An uncaught `TimeoutError` from the SDK is raised when the command exceeds `timeout`.

## Common failure modes

| Symptom | Likely cause |
|---|---|
| `KeyError: 'E2B_API_KEY'` | Environment variable not exported |
| Sandbox creation timeout | Wrong `E2B_DOMAIN` for your region |
| `TencentCloudSDKException` on credential check | Invalid or missing `TENCENTCLOUD_SECRET_ID` / `SECRET_KEY` |
| Command hangs and eventually `TimeoutError` | Command ran longer than `timeout` seconds — raise the limit or run in background |

## Skill interface

```python
run_shell(cmd: str, cwd: str | None = None, envs: dict | None = None, timeout: int = 60) -> dict
run_shell_many(cmds: list[str], timeout: int = 60) -> dict
```
