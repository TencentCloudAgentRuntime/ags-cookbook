# Example Run Report: custom-image-go-sdk

- Status: fixed-pass
- Started: 2026-03-21T02:53:30+08:00
- Directory: `examples/custom-image-go-sdk`

## Commands Planned

1. Try `AGS_TOOL_NAME=custom-dev`
2. If unavailable or unhealthy, retry with `AGS_TOOL_NAME=code-interpreter-v1`

## Findings

- The example expects Tencent Cloud credentials via `TENCENTCLOUD_*` environment variables.
- First attempt with `AGS_TOOL_NAME=custom-dev` started a sandbox successfully, but data-plane code execution returned `500 Internal Server Error`.
- This indicates the account likely has a `custom-dev` tool configured, but its runtime path is not healthy enough for this demo as currently provisioned.
- Fallback attempt with `AGS_TOOL_NAME=code-interpreter-v1` succeeded end-to-end.
- Therefore the example code path is valid, but the documented default tool assumption (`custom-dev`) is not portable and should not be treated as reliably runnable across environments.

## Fixes Attempted

- First attempt with `AGS_TOOL_NAME=custom-dev`
- Fallback attempt with `AGS_TOOL_NAME=code-interpreter-v1`
- No code patch applied during validation; the main issue is environmental/tooling assumption rather than immediate repository logic.

## Final Outcome

- Result: fixed-pass (fallback tool)
- `custom-dev` path remains a real issue to document as environment-specific / requires pre-provisioned healthy custom tool.

## Logs

- First attempt: reports/example-runs/custom-image-go-sdk.try-custom-dev.log
- Fallback attempt: reports/example-runs/custom-image-go-sdk.try-code-interpreter.log
