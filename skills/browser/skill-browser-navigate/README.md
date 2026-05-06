# Skill: Browser Action

This example demonstrates **browser automation** as an AGS Skill: spinning up an AGS browser sandbox, connecting via CDP + Playwright, and performing page navigation, element extraction, and screenshots.

## What this example demonstrates

- **`navigate_and_extract`** — open a URL in a remote browser sandbox, wait for a CSS selector, and return the page title and matched element's text
- **`screenshot_page`** — open a URL in a remote browser sandbox and save a full-page PNG screenshot locally

Authentication is auto-detected at runtime by `ags_client.BrowserSandboxSession` — either AKSK control-plane mode or APIKey direct mode — so the skill body is the same across both. In AKSK mode the CDP URL is built from the control-plane returned `(instance_id, token, region)` tuple; in APIKey mode it's built from the e2b-created sandbox.

## Prerequisites

- Python 3.13 (managed by `uv`)
- `uv` installed
- Access to the `browser-v1` sandbox template, authenticated either via an AGS API key **or** Tencent Cloud AKSK

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
make setup   # installs Python deps + Playwright Chromium
make run
```

## Expected output

```
INFO Creating browser sandbox (domain=ap-guangzhou.tencentags.com)…
INFO Sandbox id=<sandbox-id>
INFO Navigating to https://example.com…
INFO Killing sandbox…

=== Skill Result: navigate_and_extract ===
{
  "url": "https://example.com",
  "title": "Example Domain",
  "text": "Example Domain",
  "error": null
}

=== Skill Result: screenshot_page ===
{
  "url": "https://example.com",
  "saved_to": "example_screenshot.png",
  "size_bytes": 34521,
  "error": null
}
```

`example_screenshot.png` is saved in the current working directory.

## Common failure modes

| Symptom | Likely cause |
|---|---|
| `KeyError: 'E2B_API_KEY'` | Environment variable not exported |
| Sandbox creation timeout | Wrong `E2B_DOMAIN` for your region |
| `TencentCloudSDKException` on credential check | Invalid or missing `TENCENTCLOUD_SECRET_ID` / `SECRET_KEY` |
| CDP connection refused | The `browser-v1` template is not available in your AGS account |

## Skill interface

```python
navigate_and_extract(url: str, selector: str = "body") -> dict
screenshot_page(url: str, local_path: str = "screenshot.png") -> dict
```
