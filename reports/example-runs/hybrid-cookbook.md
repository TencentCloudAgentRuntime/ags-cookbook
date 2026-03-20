# Example Run Report: hybrid-cookbook

- Status: pass
- Started: 2026-03-21T02:52:00+08:00
- Directory: `examples/hybrid-cookbook`

## Commands Planned

```bash
export TENCENTCLOUD_SECRET_ID=...
export TENCENTCLOUD_SECRET_KEY=...
export TENCENTCLOUD_REGION=ap-guangzhou
export AGS_TOOL_NAME=code-interpreter-v1
make run
```

## Findings

- Exported `TENCENTCLOUD_SECRET_ID` / `TENCENTCLOUD_SECRET_KEY` / `TENCENTCLOUD_REGION` for the example run.
- `make run` succeeded.
- Verified end-to-end hybrid flow:
  - control plane started sandbox instance
  - data plane connected successfully
  - code execution returned `hello from hybrid cookbook`
  - control plane list call succeeded
- The example path itself is healthy; the main DX takeaway was to keep credential names aligned with Tencent Cloud conventions.

## Fixes Attempted

- No code patch was needed for execution; later repository cleanup normalized docs and examples around `TENCENTCLOUD_*` naming.

## Final Outcome

- Exit status: 0
- Result: pass

## Logs

- Main log file: reports/example-runs/hybrid-cookbook.log
