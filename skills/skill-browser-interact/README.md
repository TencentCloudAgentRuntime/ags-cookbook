# Skill: Browser Interact

This example complements `skill-browser-action` (navigate / screenshot / text extraction) with the primitives an Agent needs to actually **drive** a page: click, fill, run JavaScript, open multi-tab, inject cookies, and obtain a NoVNC URL so a human can watch the session live.

All skills connect to an AGS browser sandbox via CDP + Playwright; authentication is auto-detected by `ags_client.BrowserSandboxSession`.

## What this example demonstrates

- **`click(url, selector)`** — click the first matching element
- **`fill(url, selector, text)`** — type into a form input
- **`get_page_text(url, selector="body")`** — full `inner_text()` (no 2000-char cap)
- **`evaluate_js(url, expression)`** — run JS and return the value
- **`multi_tab(urls)`** — open each URL in a separate tab, collect titles
- **`inject_cookies(url, cookies)`** — pre-load cookies, navigate, read back
- **`get_vnc_url()`** — build a `https://9000-<id>.<region>.tencentags.com/novnc/` URL + token for human viewing; the sandbox stays alive until you stop it explicitly

## Prerequisites

- Python 3.13 (managed by `uv`)
- `uv` installed
- Access to the `browser-v1` sandbox template, authenticated via either AGS API key or Tencent Cloud AKSK

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
make setup     # installs Python deps + Playwright Chromium
make run
```

## Expected output

```
=== Skill Result: get_page_text (trimmed) ===
{"url": "https://example.com/", "length": 173, "text": "Example Domain\nThis domain…", "error": null}

=== Skill Result: evaluate_js ===
{
  "url": "https://example.com/",
  "expression": "({ title: document.title, links: document.querySelectorAll('a').length })",
  "value": {"title": "Example Domain", "links": 1},
  "error": null
}

=== Skill Result: multi_tab ===
{
  "count": 2,
  "tabs": [
    {"url": "https://example.com/", "title": "Example Domain", "error": null},
    {"url": "https://example.org/", "title": "Example Domain", "error": null}
  ]
}
```

## Common failure modes

| Symptom | Likely cause |
|---|---|
| `KeyError: 'E2B_API_KEY'` | Environment variable not exported |
| Sandbox creation timeout | Wrong `E2B_DOMAIN` for your region |
| `TencentCloudSDKException` on credential check | Invalid or missing `TENCENTCLOUD_SECRET_ID` / `SECRET_KEY` |
| `playwright._impl._errors.TimeoutError` | Selector did not appear within `timeout_ms`; widen the selector or raise the timeout |
| NoVNC URL 401 | The `X-Access-Token` header was not attached by your browser; use `?token=` query-string form if your nginx supports it |

## Skill interface

```python
click(url: str, selector: str, timeout_ms: int = 10000) -> dict
fill(url: str, selector: str, text: str, timeout_ms: int = 10000) -> dict
get_page_text(url: str, selector: str = "body") -> dict
evaluate_js(url: str, expression: str) -> dict
multi_tab(urls: list[str]) -> dict
inject_cookies(url: str, cookies: list[dict]) -> dict
get_vnc_url(tool_name: str = "browser-v1", timeout: str = "10m") -> dict
```
