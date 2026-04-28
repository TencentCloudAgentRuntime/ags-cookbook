# Skill: Run Shell (streaming)

This example demonstrates **real-time streaming command execution**: long-running shell commands push chunks of `stdout` / `stderr` to a caller-supplied callback as the output is produced, rather than buffering everything until the command exits.

The flow mirrors the `ExecCommandStream` helper in the AGS e2e test framework (`e2e/basic/sandbox_operations_test.go` → "Streaming Output"), where streaming is verified by checking that chunks arrive across multiple seconds.

## What this example demonstrates

- **`run_shell_stream`** — invoke `on_chunk` for every chunk of `stdout` / `stderr` as it arrives; callback signature is `{"type", "data", "t"}`
- **`run_shell_collect_chunks`** — buffered convenience wrapper that returns the chunk list, chunk count, and how many distinct wall-clock seconds the chunks span (a proxy for "yes, this really streamed")

Authentication is auto-detected at runtime by `ags_client.SandboxSession`.

## Prerequisites

- Python 3.13 (managed by `uv`)
- `uv` installed
- Either an AGS API key **or** a pair of Tencent Cloud credentials

## Required environment variables

Pick one of the two modes:

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
[stdout@0.0s] tick 1
[stdout@1.0s] tick 2
[stdout@2.0s] tick 3
[stdout@3.0s] tick 4
[stdout@4.0s] tick 5

=== Skill Result: run_shell_stream ===
{
  "cmd": "for i in 1 2 3 4 5; do echo tick $i; sleep 1; done",
  "exit_code": 0,
  "duration_s": 5.123
}

=== Skill Result: run_shell_collect_chunks (truncated) ===
{
  "cmd": "…",
  "exit_code": 0,
  "duration_s": 3.1,
  "chunks": [
    {"type": "stdout", "data": "out-1\n", "t": 0.01},
    {"type": "stderr", "data": "err-1\n", "t": 0.02},
    ...
  ],
  "chunk_count": 6,
  "distinct_seconds": 3
}
```

`distinct_seconds ≥ 2` indicates the output was streamed, not delivered as a single blob at the end.

## Common failure modes

| Symptom | Likely cause |
|---|---|
| `KeyError: 'E2B_API_KEY'` | Environment variable not exported |
| Sandbox creation timeout | Wrong `E2B_DOMAIN` for your region |
| `TencentCloudSDKException` on credential check | Invalid or missing `TENCENTCLOUD_SECRET_ID` / `SECRET_KEY` |
| Chunks arrive all at once at the end | The command is not flushing (e.g. Python without `-u`); or SDK buffering; try `stdbuf -o0 …` |

## Skill interface

```python
run_shell_stream(cmd: str, on_chunk: Callable[[dict], None], cwd=None, envs=None, timeout=300) -> dict
run_shell_collect_chunks(cmd: str, cwd=None, envs=None, timeout=300) -> dict
```

Each chunk is `{"type": "stdout"|"stderr", "data": str, "t": seconds_since_start}`.
