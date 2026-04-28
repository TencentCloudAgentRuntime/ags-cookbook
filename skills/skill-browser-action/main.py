"""
skill-browser-action: browser automation skill via AGS browser sandbox.

Authentication is auto-detected by ``ags_client.BrowserSandboxSession``:

  * ``TENCENTCLOUD_SECRET_ID`` / ``TENCENTCLOUD_SECRET_KEY`` set → AKSK mode.
  * Otherwise ``E2B_API_KEY`` / ``E2B_DOMAIN`` must be set → APIKey mode.

In both modes the skill connects to the sandbox via CDP + Playwright using
the access token returned by the session.

Demonstrates:
  1. Connecting via CDP + Playwright using the session-provided access token
  2. Navigating to a URL and extracting page title / element text
  3. Taking a full-page screenshot and saving it locally

Skills exposed:
  - navigate_and_extract(url, selector)
  - screenshot_page(url, local_path)
"""

import asyncio
import json
import logging
import os
from pathlib import Path

from playwright.async_api import async_playwright

from ags_client import BrowserSandboxSession

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Skill 1: navigate_and_extract
# ---------------------------------------------------------------------------

def navigate_and_extract(url: str, selector: str = "body") -> dict:
    """Open *url* in a remote AGS browser sandbox and extract text from *selector*.

    ``BrowserSandboxSession`` handles sandbox lifecycle and returns the tuple
    ``(instance_id, token, region)`` used to build the CDP URL; the credential
    mode (AKSK vs APIKey) is auto-detected at runtime.
    """
    async def _task(page):
        log.info("Navigating to %s…", url)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            title = await page.title()
            text = (await page.locator(selector).first.inner_text(timeout=10_000)).strip()[:2000]
            return {"url": url, "title": title, "text": text, "error": None}
        except Exception as exc:
            log.error("navigate_and_extract failed: %s", exc)
            return {"url": url, "title": None, "text": None, "error": str(exc)}

    return asyncio.run(_run_in_browser(_task))


# ---------------------------------------------------------------------------
# Skill 2: screenshot_page
# ---------------------------------------------------------------------------

def screenshot_page(url: str, local_path: str = "screenshot.png") -> dict:
    """Open *url* in a remote AGS browser sandbox and save a full-page screenshot."""
    async def _task(page):
        log.info("Navigating to %s for screenshot…", url)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            png_bytes: bytes = await page.screenshot(full_page=True)
            Path(local_path).write_bytes(png_bytes)
            log.info("Screenshot saved to %s (%d bytes)", local_path, len(png_bytes))
            return {"url": url, "saved_to": local_path, "size_bytes": len(png_bytes), "error": None}
        except Exception as exc:
            log.error("screenshot_page failed: %s", exc)
            return {"url": url, "saved_to": None, "size_bytes": 0, "error": str(exc)}

    return asyncio.run(_run_in_browser(_task))


# ---------------------------------------------------------------------------
# Internal: start browser sandbox, connect CDP, run coro, stop sandbox
# ---------------------------------------------------------------------------

async def _run_in_browser(coro):
    with BrowserSandboxSession(tool_name="browser-v1", timeout="10m") as (instance_id, token, region):
        cdp_url = f"https://9000-{instance_id}.{region}.tencentags.com/cdp"
        log.info("Connecting CDP: %s", cdp_url)
        async with async_playwright() as pw:
            browser = await pw.chromium.connect_over_cdp(
                cdp_url,
                headers={"X-Access-Token": token},
            )
            ctx = browser.contexts[0]
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            result = await coro(page)
            await browser.close()
        return result


# ---------------------------------------------------------------------------
# Entry point — demo both skills
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    log.info("=== Demo 1: navigate_and_extract ===")
    result1 = navigate_and_extract("https://example.com", "h1")
    print("\n=== Skill Result: navigate_and_extract ===")
    print(json.dumps(result1, indent=2, ensure_ascii=False))

    log.info("=== Demo 2: screenshot_page ===")
    result2 = screenshot_page("https://example.com", local_path="example_screenshot.png")
    print("\n=== Skill Result: screenshot_page ===")
    print(json.dumps(result2, indent=2, ensure_ascii=False))
