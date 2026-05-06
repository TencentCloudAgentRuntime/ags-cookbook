# Skill: Data Pipeline

This example is a Skill-ified version of the `examples/data-analysis` cookbook example: a **multi-stage pipeline** where each stage runs in its own isolated Python code context (variables do not leak between stages) but all stages **share the sandbox filesystem**, so artefacts written by stage N are visible to stage N+1.

This is the canonical "multi-context" pattern AGS exposes and is the best way for an Agent to coordinate a load → transform → chart workflow without spawning multiple sandboxes.

## What this example demonstrates

- **`run_pipeline(stages, downloads=None)`** — execute a list of `{name, code, writes?}` stages in one sandbox; optionally download declared artefacts at the end; stops on the first failed stage but still downloads any artefacts that made it

Variable isolation is guaranteed by `sbx.create_code_context()` per stage (the same primitive used by `skill-code-interpreter.run_code_multi_context`); filesystem sharing is via `/tmp/*` in the sandbox.

Authentication is auto-detected by `ags_client.SandboxSession`.

## Prerequisites

- Python 3.13 (managed by `uv`)
- `uv` installed
- Either an AGS API key **or** Tencent Cloud AKSK credentials
- Stage code needs whatever libraries are pre-installed in the sandbox template (e.g. `code-interpreter-v1` ships pandas + matplotlib)

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
=== Skill Result: run_pipeline ===
{
  "stages": [
    {"i": 0, "name": "load",      "writes": ["/tmp/raw.csv"],       "stdout": ["[load] wrote 6 rows\n"], "error": null},
    {"i": 1, "name": "transform", "writes": ["/tmp/summary.json"],  "stdout": ["[transform] top category: ('Electronics', 24800)\n"], "error": null},
    {"i": 2, "name": "chart",     "writes": ["/tmp/chart.png"],     "stdout": ["[chart] saved chart\n"], "error": null}
  ],
  "downloads": [
    {"remote": "/tmp/summary.json", "saved_to": "summary.json", "size": 150, "error": null},
    {"remote": "/tmp/chart.png",    "saved_to": "chart.png",    "size": 25431, "error": null}
  ],
  "ok": true
}
```

`summary.json` and `chart.png` are saved in the current working directory.

## Common failure modes

| Symptom | Likely cause |
|---|---|
| `KeyError: 'E2B_API_KEY'` | Environment variable not exported |
| Sandbox creation timeout | Wrong `E2B_DOMAIN` for your region |
| `TencentCloudSDKException` on credential check | Invalid or missing `TENCENTCLOUD_SECRET_ID` / `SECRET_KEY` |
| Later stage fails with `FileNotFoundError` | An earlier stage did not actually write the declared `writes` path; `writes` is metadata-only, not enforced |
| Later stage raises `NameError` | Remember that **variables are NOT shared** between stages — only files are |

## Skill interface

```python
run_pipeline(
    stages: list[dict],            # [{"name": str, "code": str, "writes": [str]?}, ...]
    downloads: list[str] | None = None,
    tool_name: str = "code-interpreter-v1",
    timeout: str = "10m",
) -> dict
```
