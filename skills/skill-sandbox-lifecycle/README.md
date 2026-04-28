# Skill: Sandbox Lifecycle

This example demonstrates **full control-plane lifecycle management** of AGS sandbox instances: start, pause (Full / Disk), resume, describe, list, stop. These are the APIs that let a production Agent reuse a single warm sandbox across many tool calls and save costs by pausing idle instances.

The flow mirrors `e2e/basic/auto_pause_resume_test.go` and `e2e/framework/pause_resume.go`.

> **AKSK-only.** This skill talks to the Tencent Cloud AGS control plane directly and never opens a data-plane session. If only `E2B_API_KEY` is set, every function raises `RuntimeError` with a clear message.

## What this example demonstrates

- **`start_and_get_status`** — `StartSandboxInstance` (with optional `AutoPause` / `AutoResume`) + `DescribeSandboxInstanceList` in one call
- **`pause_and_resume`** — `PauseSandboxInstance` (`Full` / `Disk` mode), poll for `PAUSED`, then `ResumeSandboxInstance`, poll for `RUNNING`; returns the observed status transitions so the Agent can verify what happened
- **`list_instances`** — `DescribeSandboxInstanceList`, optionally filtered by `ToolName` / `ToolId`
- **`get_instance_status`** — single-instance status lookup
- **`stop`** — `StopSandboxInstance`

## Prerequisites

- Python 3.13 (managed by `uv`)
- `uv` installed
- Valid Tencent Cloud credentials

## Required environment variables

```bash
export TENCENTCLOUD_SECRET_ID="your_secret_id"
export TENCENTCLOUD_SECRET_KEY="your_secret_key"
export TENCENTCLOUD_REGION="ap-guangzhou"
```

The APIKey variables (`E2B_API_KEY` / `E2B_DOMAIN`) are **ignored** by this skill.

## Install and run

```bash
make setup
make run
```

## Expected output

```
=== Skill Result: start_and_get_status ===
{
  "instance_id": "sbi-xxxxxxxx",
  "status": "RUNNING",
  "auto_pause": true,
  "auto_resume": true
}

=== Skill Result: pause_and_resume ===
{
  "instance_id": "sbi-xxxxxxxx",
  "ok": true,
  "pause_mode": "Full",
  "last_status": "RUNNING",
  "transitions": [
    {"t": 1234567890.12, "status": "RUNNING"},
    {"t": 1234567891.14, "status": "PAUSING"},
    {"t": 1234567898.25, "status": "PAUSED"},
    {"t": 1234567898.26, "status": "RESUMING"},
    {"t": 1234567905.30, "status": "RUNNING"}
  ]
}

=== Skill Result: list_instances (truncated) ===
{"count": 3, "first": [...]}

=== Skill Result: stop ===
{"instance_id": "sbi-xxxxxxxx", "stopped": true}
```

Status strings follow the AGS convention: `STARTING` / `RUNNING` / `PAUSING` / `PAUSED` / `RESUMING` / `STOPPED` / `FAILED`.

## Common failure modes

| Symptom | Likely cause |
|---|---|
| `KeyError: 'E2B_API_KEY'` | Not applicable — this skill is AKSK-only |
| Sandbox creation timeout | Wrong `E2B_DOMAIN` for your region (affects only the other skills) |
| `TencentCloudSDKException` on credential check | Invalid or missing `TENCENTCLOUD_SECRET_ID` / `SECRET_KEY` |
| `RuntimeError: pause_instance requires AKSK mode` | Running without AKSK env vars |
| `pause_and_resume.ok == false, step: "pause"` | Pause did not reach `PAUSED` within `wait_s`; the instance may be stuck or the tool image does not support pausing |

## Skill interface

```python
start_and_get_status(tool_name="code-interpreter-v1", timeout="10m", auto_pause=False, auto_resume=False) -> dict
pause_and_resume(instance_id: str, mode: str = "Full", wait_s: int = 60) -> dict
list_instances(tool_name: str | None = None, tool_id: str | None = None) -> dict
get_instance_status(instance_id: str) -> dict
stop(instance_id: str) -> dict
```
