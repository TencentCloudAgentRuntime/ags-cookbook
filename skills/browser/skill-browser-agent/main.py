"""
skill-browser-agent: LLM-driven multi-step browser automation.

This is the Skill-ified version of ``examples/browser-agent``.  It hosts a
generic tool-calling loop around an AGS browser sandbox and delegates the
"what to do next" decision to a caller-supplied ``llm_fn`` callable — that
way the Skill runs with any LLM (Anthropic / Tencent Yuanbao / OpenAI / …)
and even with a deterministic script for tests.

Architecture
------------

::

    browser_task(task, llm_fn, max_steps=10)
      │
      └── launches a browser sandbox once, then for each step:
          1.  build an observation dict (url, title, page snippet)
          2.  call llm_fn(observation, history, task) → next action
          3.  execute action via Playwright
          4.  record the step; stop when llm_fn emits {"done": True} or
              max_steps is reached

Supported actions (kept deliberately small):

    {"tool": "goto",       "url": "..."}
    {"tool": "click",      "selector": "..."}
    {"tool": "fill",       "selector": "...", "text": "..."}
    {"tool": "evaluate",   "expression": "document.title"}
    {"tool": "screenshot", "path": "step-N.png"}
    {"tool": "done",       "answer": "..."}

Skills exposed:
  - browser_task(task, llm_fn, max_steps=10, tool_name="browser-v1", timeout="10m")
  - make_echo_llm(script)   — deterministic test stub that replays a scripted list

The echo LLM is a tiny helper so this skill is **runnable end-to-end without
any external LLM credential**.  For real use, plug in Claude / OpenAI / etc.
"""

import asyncio
import base64
import json
import logging
from pathlib import Path
from typing import Any, Callable

from playwright.async_api import async_playwright

from ags_client import BrowserSandboxSession

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helper: observation construction
# ---------------------------------------------------------------------------

async def _observe(page) -> dict:
    try:
        url = page.url
        title = await page.title()
        text = await page.locator("body").first.inner_text()
    except Exception as e:  # noqa: BLE001
        return {"url": None, "title": None, "text": "", "error": str(e)}
    snippet = (text or "").strip()[:400]
    return {"url": url, "title": title, "text_snippet": snippet, "error": None}


# ---------------------------------------------------------------------------
# Helper: action execution
# ---------------------------------------------------------------------------

async def _execute_action(page, action: dict) -> dict:
    """Apply an LLM-emitted action; return ``{ok, detail}``."""
    tool = action.get("tool")
    try:
        if tool == "goto":
            await page.goto(action["url"], wait_until="domcontentloaded", timeout=30_000)
            return {"ok": True, "detail": f"goto {action['url']}"}
        if tool == "click":
            await page.locator(action["selector"]).first.click(timeout=10_000)
            return {"ok": True, "detail": f"click {action['selector']}"}
        if tool == "fill":
            await page.locator(action["selector"]).first.fill(action["text"], timeout=10_000)
            return {"ok": True, "detail": f"fill {action['selector']} len={len(action['text'])}"}
        if tool == "evaluate":
            value = await page.evaluate(action["expression"])
            return {"ok": True, "detail": {"expression": action["expression"], "value": value}}
        if tool == "screenshot":
            png = await page.screenshot(full_page=True)
            path = action.get("path", "step.png")
            Path(path).write_bytes(png)
            return {"ok": True, "detail": {"saved_to": path, "size": len(png)}}
        if tool == "done":
            return {"ok": True, "detail": {"answer": action.get("answer", "")}}
        return {"ok": False, "detail": f"unknown tool: {tool!r}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "detail": str(e)}


# ---------------------------------------------------------------------------
# Skill: browser_task
# ---------------------------------------------------------------------------

def browser_task(
    task: str,
    llm_fn: Callable[[dict, list[dict], str], dict],
    max_steps: int = 10,
    tool_name: str = "browser-v1",
    timeout: str = "10m",
) -> dict:
    """Drive a browser via ``llm_fn`` to complete ``task``.

    ``llm_fn`` is a function::

        llm_fn(observation: dict, history: list[dict], task: str) -> action_dict

    It should return one of the supported action dicts (see module docstring).
    Emitting ``{"tool": "done", "answer": "..."}`` terminates the loop early.

    Returns ``{"completed", "steps", "final_answer", "history"}``.
    """
    async def _main():
        history: list[dict] = []
        final_answer: str | None = None
        completed = False

        with BrowserSandboxSession(tool_name=tool_name, timeout=timeout) as (instance_id, token, region):
            cdp_url = f"https://9000-{instance_id}.{region}.tencentags.com/cdp"
            async with async_playwright() as pw:
                browser = await pw.chromium.connect_over_cdp(
                    cdp_url,
                    headers={"X-Access-Token": token},
                )
                ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
                page = ctx.pages[0] if ctx.pages else await ctx.new_page()

                for step in range(max_steps):
                    obs = await _observe(page)
                    action = llm_fn(obs, history, task)
                    log.info("step %d: action=%s", step, action.get("tool"))

                    outcome = await _execute_action(page, action)
                    history.append({
                        "step": step,
                        "observation": obs,
                        "action": action,
                        "outcome": outcome,
                    })

                    if action.get("tool") == "done":
                        completed = True
                        final_answer = action.get("answer") or str(outcome["detail"])
                        break

                await browser.close()

        return {
            "task": task,
            "completed": completed,
            "steps": len(history),
            "final_answer": final_answer,
            "history": history,
        }

    return asyncio.run(_main())


# ---------------------------------------------------------------------------
# Helper: an echo LLM that replays a scripted action list (for demos / tests)
# ---------------------------------------------------------------------------

def make_echo_llm(script: list[dict]) -> Callable[[dict, list[dict], str], dict]:
    """Return an ``llm_fn`` that yields ``script[0]``, ``script[1]``, … in order.

    When the script runs out, emits ``{"tool": "done", "answer": "end of script"}``.
    """
    iterator = iter(script)

    def _llm(obs, history, task):
        try:
            return next(iterator)
        except StopIteration:
            return {"tool": "done", "answer": "end of script"}

    return _llm


# ---------------------------------------------------------------------------
# Entry point — demo with a scripted echo LLM (no external model required)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    log.info("=== Demo: scripted browser-agent run against example.com ===")

    script = [
        {"tool": "goto", "url": "https://example.com"},
        {"tool": "evaluate", "expression": "({ title: document.title, h1: document.querySelector('h1').innerText })"},
        {"tool": "screenshot", "path": "browser-agent-demo.png"},
        {"tool": "done", "answer": "captured title + h1 + screenshot"},
    ]

    result = browser_task(
        task="Open example.com, grab the title + h1 and save a full-page screenshot.",
        llm_fn=make_echo_llm(script),
        max_steps=8,
    )
    # Print a trimmed view — history can be long.
    trimmed = {
        **result,
        "history": [
            {**h, "observation": {**h["observation"], "text_snippet": (h["observation"].get("text_snippet") or "")[:120]}}
            for h in result["history"]
        ],
    }
    print("\n=== Skill Result: browser_task ===")
    print(json.dumps(trimmed, indent=2, ensure_ascii=False, default=str))
