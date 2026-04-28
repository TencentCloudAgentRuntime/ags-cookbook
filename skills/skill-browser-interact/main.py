"""
skill-browser-interact: interactive browser automation inside an AGS browser sandbox.

Complements :mod:`skill-browser-action` (navigate / screenshot / text extraction)
with the primitives an Agent needs to actually *drive* a page:

  * click elements
  * fill form inputs
  * run arbitrary JavaScript
  * grab the full rendered page text
  * open multiple tabs
  * inject / read cookies
  * build a NoVNC URL so a human operator can watch the live session

All functions are async-wrapped but expose a synchronous entry point via
``asyncio.run`` so an Agent can tool-call them directly.

Skills exposed:
  - click(url, selector, timeout_ms=10000)
  - fill(url, selector, text, timeout_ms=10000)
  - get_page_text(url, selector="body")
  - evaluate_js(url, expression)
  - multi_tab(urls)
  - inject_cookies(url, cookies)
  - get_vnc_url(timeout="10m")
"""

import asyncio
import json
import logging
from typing import Any

from playwright.async_api import async_playwright

from ags_client import BrowserSandboxSession, build_port_url

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared browser session helper
# ---------------------------------------------------------------------------

async def _with_browser(task, tool_name: str = "browser-v1", timeout: str = "10m"):
    """Start a browser sandbox, connect via CDP, run ``task(browser, ctx)``, stop."""
    with BrowserSandboxSession(tool_name=tool_name, timeout=timeout) as (instance_id, token, region):
        cdp_url = f"https://9000-{instance_id}.{region}.tencentags.com/cdp"
        log.info("Connecting CDP: %s", cdp_url)
        async with async_playwright() as pw:
            browser = await pw.chromium.connect_over_cdp(
                cdp_url,
                headers={"X-Access-Token": token},
            )
            ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
            try:
                return await task(browser, ctx, instance_id, token, region)
            finally:
                await browser.close()


async def _first_page(ctx):
    return ctx.pages[0] if ctx.pages else await ctx.new_page()


# ---------------------------------------------------------------------------
# Skill 1: click
# ---------------------------------------------------------------------------

def click(url: str, selector: str, timeout_ms: int = 10_000) -> dict:
    """Open ``url``, click the first element matching ``selector``."""
    async def _task(browser, ctx, iid, tok, rgn):
        page = await _first_page(ctx)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            await page.locator(selector).first.click(timeout=timeout_ms)
            return {"url": page.url, "clicked": selector, "error": None}
        except Exception as e:  # noqa: BLE001
            return {"url": page.url, "clicked": selector, "error": str(e)}

    return asyncio.run(_with_browser(_task))


# ---------------------------------------------------------------------------
# Skill 2: fill
# ---------------------------------------------------------------------------

def fill(url: str, selector: str, text: str, timeout_ms: int = 10_000) -> dict:
    """Open ``url``, type ``text`` into the input matching ``selector``."""
    async def _task(browser, ctx, iid, tok, rgn):
        page = await _first_page(ctx)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            await page.locator(selector).first.fill(text, timeout=timeout_ms)
            current = await page.locator(selector).first.input_value()
            return {"url": page.url, "selector": selector, "value": current, "error": None}
        except Exception as e:  # noqa: BLE001
            return {"url": page.url, "selector": selector, "value": None, "error": str(e)}

    return asyncio.run(_with_browser(_task))


# ---------------------------------------------------------------------------
# Skill 3: get_page_text
# ---------------------------------------------------------------------------

def get_page_text(url: str, selector: str = "body") -> dict:
    """Return ``.inner_text()`` of ``selector`` after DOM is ready.

    Unlike :func:`skill-browser-action.navigate_and_extract` (which limits to 2000
    chars), this returns the full text so the Agent can chunk / summarise.
    """
    async def _task(browser, ctx, iid, tok, rgn):
        page = await _first_page(ctx)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            text = await page.locator(selector).first.inner_text()
            return {"url": page.url, "length": len(text), "text": text, "error": None}
        except Exception as e:  # noqa: BLE001
            return {"url": page.url, "length": 0, "text": None, "error": str(e)}

    return asyncio.run(_with_browser(_task))


# ---------------------------------------------------------------------------
# Skill 4: evaluate_js
# ---------------------------------------------------------------------------

def evaluate_js(url: str, expression: str) -> dict:
    """Navigate to ``url``, then ``page.evaluate(expression)``; return the value.

    ``expression`` must be a JavaScript expression that returns a JSON-serialisable
    value (``document.title``, ``{count: document.querySelectorAll('a').length}``).
    """
    async def _task(browser, ctx, iid, tok, rgn):
        page = await _first_page(ctx)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            value = await page.evaluate(expression)
            return {"url": page.url, "expression": expression, "value": value, "error": None}
        except Exception as e:  # noqa: BLE001
            return {"url": page.url, "expression": expression, "value": None, "error": str(e)}

    return asyncio.run(_with_browser(_task))


# ---------------------------------------------------------------------------
# Skill 5: multi_tab
# ---------------------------------------------------------------------------

def multi_tab(urls: list[str]) -> dict:
    """Open each URL in its own tab; return titles and final URLs."""
    async def _task(browser, ctx, iid, tok, rgn):
        results: list[dict[str, Any]] = []
        for u in urls:
            page = await ctx.new_page()
            try:
                await page.goto(u, wait_until="domcontentloaded", timeout=30_000)
                results.append({"url": page.url, "title": await page.title(), "error": None})
            except Exception as e:  # noqa: BLE001
                results.append({"url": u, "title": None, "error": str(e)})
            finally:
                await page.close()
        return {"count": len(results), "tabs": results}

    return asyncio.run(_with_browser(_task))


# ---------------------------------------------------------------------------
# Skill 6: inject_cookies
# ---------------------------------------------------------------------------

def inject_cookies(url: str, cookies: list[dict]) -> dict:
    """Add ``cookies`` to the browser context, navigate to ``url`` with them,
    and return the cookies the server sets back.

    Each cookie follows Playwright's shape: ``{name, value, domain, path, ...}``.
    """
    async def _task(browser, ctx, iid, tok, rgn):
        page = await _first_page(ctx)
        try:
            await ctx.add_cookies(cookies)
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            all_cookies = await ctx.cookies()
            return {"url": page.url, "set_in": len(cookies), "after": all_cookies, "error": None}
        except Exception as e:  # noqa: BLE001
            return {"url": page.url, "set_in": len(cookies), "after": [], "error": str(e)}

    return asyncio.run(_with_browser(_task))


# ---------------------------------------------------------------------------
# Skill 7: get_vnc_url
# ---------------------------------------------------------------------------

def get_vnc_url(tool_name: str = "browser-v1", timeout: str = "10m") -> dict:
    """Start a browser sandbox and return a NoVNC URL + token for human viewing.

    The URL is built from :func:`ags_client.build_port_url`; the access token
    must be attached as the ``X-Access-Token`` header.  The sandbox is NOT
    stopped here — it must be released explicitly by the Agent (e.g. via
    :mod:`skill-sandbox-lifecycle.stop`).

    NoVNC is served by nginx on port 9000 at ``/novnc/``.
    """
    # Open the session but do NOT close it here; return identifiers so the
    # Agent can display the URL and later tear the sandbox down.
    session = BrowserSandboxSession(tool_name=tool_name, timeout=timeout)
    instance_id, token, region = session.__enter__()
    # NOTE: the session is kept alive via a strong reference in the returned
    # dict.  When the caller no longer needs the VNC link, they should stop
    # the instance_id through the lifecycle skill (AKSK mode) or kill the
    # e2b Sandbox directly.
    url = build_port_url(instance_id, 9000, "/novnc/")
    return {
        "instance_id": instance_id,
        "novnc_url": url,
        "cdp_url": f"https://9000-{instance_id}.{region}.tencentags.com/cdp",
        "access_token": token,
        "region": region,
        "_session_keepalive": session,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    log.info("=== Demo 1: get_page_text ===")
    r1 = get_page_text("https://example.com", "body")
    print("\n=== Skill Result: get_page_text (trimmed) ===")
    print(json.dumps({**r1, "text": (r1["text"] or "")[:200] + "…"}, indent=2, ensure_ascii=False))

    log.info("=== Demo 2: evaluate_js ===")
    r2 = evaluate_js("https://example.com", "({ title: document.title, links: document.querySelectorAll('a').length })")
    print("\n=== Skill Result: evaluate_js ===")
    print(json.dumps(r2, indent=2, ensure_ascii=False))

    log.info("=== Demo 3: multi_tab ===")
    r3 = multi_tab(["https://example.com", "https://example.org"])
    print("\n=== Skill Result: multi_tab ===")
    print(json.dumps(r3, indent=2, ensure_ascii=False))
