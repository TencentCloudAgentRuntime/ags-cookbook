# Skill: Data Analysis

This example demonstrates **sandboxed data analysis and chart generation** as an AGS Skill: uploading a CSV, running pandas aggregations and matplotlib chart generation inside a sandbox, and returning both summary statistics and a local PNG file.

## What this example demonstrates

- **`analyse_csv`** — upload a CSV string into a sandbox, compute grouped `sum / mean / count` of a numeric column, generate a bar chart via matplotlib, download the PNG locally, and return the summary as a list of records

Authentication is auto-detected at runtime by `ags_client.SandboxSession` — either AKSK control-plane mode or APIKey direct mode — so the skill body is the same across both.

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

When both variable sets are defined, AKSK mode takes precedence (see `ags_client.credential_mode()`).

## Install and run

```bash
make setup
make run
```

## Expected output

```
INFO analyse_csv: group_by=category value_col=revenue
INFO Uploaded 256 bytes to /tmp/input.csv
INFO Chart saved to revenue_by_category.png (42351 bytes)
INFO analyse_csv: done, error=None

=== Skill Result: analyse_csv ===
{
  "summary": [
    {"category": "Electronics", "sum": 24800.0, "mean": 12400.0, "count": 2},
    {"category": "Home",        "sum": 15900.0, "mean":  7950.0, "count": 2},
    …
  ],
  "chart_path": "revenue_by_category.png",
  "stdout": ["…", "chart saved"],
  "error": null
}
```

`revenue_by_category.png` is saved in the current working directory.

## Common failure modes

| Symptom | Likely cause |
|---|---|
| `KeyError: 'E2B_API_KEY'` | Environment variable not exported |
| Sandbox creation timeout | Wrong `E2B_DOMAIN` for your region |
| `TencentCloudSDKException` on credential check | Invalid or missing `TENCENTCLOUD_SECRET_ID` / `SECRET_KEY` |
| `KeyError: <column>` in sandbox | `group_by` or `value_col` does not exist in the CSV header |

## Skill interface

```python
analyse_csv(
    csv_text: str,
    group_by: str,
    value_col: str,
    chart_path: str = "chart.png",
) -> dict
```

Returns `summary` (list of dicts), `chart_path` (local PNG path), `stdout`, and `error`.
