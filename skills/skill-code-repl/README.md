# Skill: Code REPL

This example demonstrates **persistent Python REPL contexts** that survive across Agent tool calls. Where `skill-code-interpreter` spins up a fresh sandbox per call (so variables never persist), this skill caches the sandbox + code context keyed by a `repl_id` string — the Agent holds the id between turns and replays it.

## What this example demonstrates

- **`create_repl`** — start a sandbox and a code context; return a `repl_id`
- **`run_in_repl(repl_id, code)`** — execute code in the cached context, with optional `on_stdout` callback; variables defined in turn N are visible in turn N+1
- **`close_repl(repl_id)`** — release the sandbox
- **`list_repls()`** — enumerate every live REPL

Caching is **process-local** (a plain dict). For multi-process Agent deployments, wrap these functions with your own shared registry (Redis, a database, etc.) keyed on `repl_id`.

Authentication is auto-detected by `ags_client.SandboxSession`.

## Prerequisites

- Python 3.13 (managed by `uv`)
- `uv` installed
- Either an AGS API key **or** Tencent Cloud AKSK credentials

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
=== Skill Result: create_repl ===
{"repl_id": "repl-abc123def456", "timeout": "30m"}

=== Skill Result: run_in_repl (turn 1) ===
{"repl_id": "...", "turn": 1, "stdout": ["x=7\n"], "text_results": [], "error": null}

=== Skill Result: run_in_repl (turn 2) ===
{"repl_id": "...", "turn": 2, "stdout": ["7! = 5040\n"], "text_results": [], "error": null}

=== Skill Result: run_in_repl (turn 3) ===
{"repl_id": "...", "turn": 3, "stdout": ["['math', 'x', 'y']\n"], "text_results": [], "error": null}

=== Skill Result: close_repl ===
{"repl_id": "...", "closed": true, "turns": 3}
```

Turns 2 and 3 read `x` and `math` defined in turn 1 — the hallmark of a persistent REPL.

## Common failure modes

| Symptom | Likely cause |
|---|---|
| `KeyError: 'E2B_API_KEY'` | Environment variable not exported |
| Sandbox creation timeout | Wrong `E2B_DOMAIN` for your region |
| `TencentCloudSDKException` on credential check | Invalid or missing `TENCENTCLOUD_SECRET_ID` / `SECRET_KEY` |
| `"error": "unknown repl_id"` | You called `run_in_repl` with an id from a previous process; REPLs are process-local |
| Sandbox silently killed mid-session | Idle `timeout` elapsed — raise the `timeout` arg to `create_repl` |

## Skill interface

```python
create_repl(timeout: str = "30m") -> dict            # {"repl_id": str, "timeout": str}
run_in_repl(repl_id: str, code: str, on_stdout=None) -> dict
close_repl(repl_id: str) -> dict
list_repls() -> dict
```
