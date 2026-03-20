# Example Run Report: mobile-use

- Status: fixed-pass
- Started: 2026-03-21T02:54:10+08:00
- Directory: `examples/mobile-use`

## Commands Planned

```bash
uv sync
export E2B_DOMAIN=ap-guangzhou.tencentags.com
export SANDBOX_TEMPLATE=mobile-v1
make run
```

## Findings

- `uv sync` succeeded.
- Initial run proved the full mobile path works, including:
  - sandbox creation
  - Appium connection
  - APK download
  - chunked APK upload
  - app install + launch for both 应用宝 and WeChat
  - GPS mock location setup and verification
- The initial run then entered a built-in 3000-second long-running stage intended for endurance observation.
- That behavior is useful for manual demos but blocks automated validation and degrades DX.
- I patched the script so long-running duration, screenshot interval, and heartbeat interval are configurable via env vars.
- A second run with `LONG_RUN_SECONDS=0` completed successfully and exercised all key functionality before clean shutdown.
- Cleanup worked correctly and produced final screenshot plus logcat dump.

## Fixes Attempted

- Added env-configurable long-run controls:
  - `LONG_RUN_SECONDS`
  - `LONG_RUN_RESERVE_SECONDS`
  - `SCREENSHOT_INTERVAL_SECONDS`
  - `HEARTBEAT_INTERVAL_SECONDS`
- Re-ran with:

```bash
export LONG_RUN_SECONDS=0
uv run quickstart.py
```

## Final Outcome

- Exit status: 0
- Result: fixed-pass

## Logs

- Initial long-run log: reports/example-runs/mobile-use.log
- Successful bounded run: reports/example-runs/mobile-use.final.log
