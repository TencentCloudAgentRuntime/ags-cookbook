# Example Run Report: html-processing

- Status: pass
- Started: 2026-03-21T02:46:10+08:00
- Directory: `examples/html-processing`

## Commands Planned

```bash
uv sync
export E2B_DOMAIN=ap-guangzhou.tencentags.com
make run
```

## Findings

- Ran with explicit `E2B_DOMAIN=ap-guangzhou.tencentags.com` to avoid the known invalid default-domain issue.
- `uv sync` succeeded.
- `make run` succeeded.
- The example successfully validated:
  - browser sandbox creation
  - code-interpreter sandbox creation
  - HTML upload to browser sandbox
  - screenshot generation before and after edit
  - HTML editing inside code sandbox
  - edited HTML download back to local output directory
- Output files were generated under `examples/html-processing/html_collaboration_output/`.
- Node emitted a Playwright-side deprecation warning about `url.parse()`; this did not block execution.

## Fixes Attempted

- Domain override in shell only.
- Logging wrapper bug identified: using backticks inside double-quoted shell `echo` triggered command substitution against the log path. This is unrelated to the example itself.

## Final Outcome

- Exit status: 0
- Result: pass

## Logs

- Main log file: reports/example-runs/html-processing.log
