# HTML Collaboration Demo

This example demonstrates a dual-sandbox AGS workflow: one sandbox edits HTML while another renders it in a browser and captures screenshots.

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

After a successful run, `html_collaboration_output/` should contain:

- `demo.html`
- `demo_edited.html`
- `screenshot_before.png`
- `screenshot_after.png`

## Common failure hints

- If browser or code sandboxes fail to start, check `E2B_API_KEY` and `E2B_DOMAIN`
- If artifacts are missing, rerun after clearing the output directory and watch the sandbox logs

## What it demonstrates

- Browser + code sandbox collaboration
- File transfer between local machine and remote sandboxes
- Visual verification through before/after screenshots
