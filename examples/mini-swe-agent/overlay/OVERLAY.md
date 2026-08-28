# Overlay File Reference

This document lists every file in the `overlay/` directory, explains what it does, and whether it is a new file or replaces an existing upstream file.

## SWE-ReX Overlay (`overlay/SWE-ReX/`)

### New Files

| File | Description |
|------|-------------|
| `src/swerex/deployment/ags.py` | `TencentAGSDeployment` — manages AGS sandbox instance lifecycle (create, connect, token refresh, destroy) |
| `src/swerex/runtime/ags.py` | `AGSRuntime` — HTTP client for AGS data plane with `X-Access-Token` auth, SSL skip, and 404-to-`EnvironmentExpiredError` mapping |


### Replaced Files

| File | What Changed | Why |
|------|-------------|-----|
| `src/swerex/deployment/config.py` | Added `TencentAGSDeploymentConfig` class and added it to the `DeploymentConfig` union type | Registers AGS as a deployment backend so `get_deployment()` factory works |
| `src/swerex/runtime/config.py` | Added `AGSRuntimeConfig` class and added it to the `RuntimeConfig` union type | Registers AGS as a runtime backend |
| `src/swerex/exceptions.py` | Added `EnvironmentUnavailableError` and `EnvironmentExpiredError` | AGS runtime maps 404 responses to these exceptions for clean error handling |
| `src/swerex/utils/log.py` | Added `set_console()`, `_get_console()`, and `set_stream_level()` functions | Allows batch runners to share a Console with Rich Live and control log verbosity |
| `pyproject.toml` | Added `ags` extras: `tencentcloud-sdk-python-common`, `tencentcloud-sdk-python-ags` | Installs AGS SDK dependencies with `pip install swe-rex[ags]` |

## mini-swe-agent Overlay (`overlay/mini-swe-agent/`)

### New Files

| File | Description |
|------|-------------|
| `src/minisweagent/environments/extra/swerex_ags.py` | `SwerexAgsEnvironment` — AGS environment wrapper that manages deployment lifecycle, executes commands, and handles credentials |
| `src/minisweagent/config/benchmarks/swebench_ags.yaml` | AGS benchmark configuration template (prompt templates, timeouts, AGS endpoint defaults) |


### Replaced Files

| File | What Changed | Why |
|------|-------------|-----|
| `src/minisweagent/environments/__init__.py` | Added `"swerex_ags"` to the environment registry | Registers the AGS environment so it can be selected via config |
| `src/minisweagent/utils/log.py` | Replaced direct `RichHandler` with `QueueHandler`/`QueueListener` pattern; added `setup_logging()`, `shutdown_logging()`, `set_stream_level()` | Prevents ABBA deadlock between `Handler._lock` and `Console._lock` when Rich Live is active in batch mode |
| `src/minisweagent/run/benchmarks/swebench.py` | Added shared Console setup, SWE-ReX log level control, LiteLLM `suppress_debug_info`, AGS image name derivation, `shutdown_logging()` call | Thread-safe logging, deadlock prevention, AGS image support |
| `src/minisweagent/run/benchmarks/utils/batch_progress.py` | `Lock` -> `RLock`, moved `renderables[1]` assignment inside lock, `print()` -> `logger.info()` | Fixes race conditions in progress display; avoids `print()` interfering with Rich Live |
| `pyproject.toml` | Added `ags` extras: `swe-rex[ags]` | Installs AGS dependencies with `pip install mini-swe-agent[ags]` |

## Potential Merge Conflicts

When updating to a newer upstream, these files are most likely to have changed:

- **`pyproject.toml`** (both repos) — dependency version bumps
- **`swebench.py`** — batch runner is actively developed
- **`config.py`** (SWE-ReX) — new deployment backends may be added

New files (ags.py, swerex_ags.py, etc.) are unlikely to conflict since they are additions, not modifications.
