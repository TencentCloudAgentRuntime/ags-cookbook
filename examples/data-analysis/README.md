# Data Analysis Example

This example demonstrates a multi-context AGS data workflow: data cleaning, analysis, and visualization are performed in isolated contexts that exchange artifacts through the sandbox filesystem.

## Prerequisites

- Python >= 3.12
- `uv`
- `E2B_API_KEY`
- Required `E2B_DOMAIN`

## Required environment variables

```bash
export E2B_API_KEY="your_ags_api_key"
export E2B_DOMAIN="ap-guangzhou.tencentags.com"
```

## Local commands

```bash
make setup
make run
```

## Expected output

After a successful run, `enhanced_demo_output/` should contain generated charts and reports such as:

- `data_cleaning_comparison.png`
- `advanced_dashboard.png`
- `correlation_heatmap.png`
- `analysis_report.json`

## Common failure hints

- If sandbox creation fails, verify `E2B_API_KEY` and `E2B_DOMAIN`
- If your account is region-scoped, prefer an explicit region domain instead of relying on historical defaults

## What it demonstrates

- True context isolation across multiple AGS execution contexts
- Artifact handoff through the filesystem
- A more realistic multi-step data pipeline than a single-script demo
