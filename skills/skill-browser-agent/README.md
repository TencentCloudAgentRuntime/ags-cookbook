# Skill: Browser Agent

This example is the Skill-ified version of `examples/browser-agent`: a generic **LLM-driven multi-step browser tool loop** that runs inside an AGS browser sandbox. The skill owns the Playwright/CDP plumbing; *you* plug in any LLM that can emit structured action dicts.

## Architecture

```
browser_task(task, llm_fn, max_steps=10)
  │
  └── launches a browser sandbox once, then for each step:
      1. build an observation dict (url, title, text snippet)
      2. call llm_fn(observation, history, task) → next action
      3. execute action via Playwright
      4. record the step; stop when llm_fn emits {"tool": "done"} or max_steps reached
```

## Supported actions

```python
{"tool": "goto",       "url": "..."}
{"tool": "click",      "selector": "..."}
{"tool": "fill",       "selector": "...", "text": "..."}
{"tool": "evaluate",   "expression": "document.title"}
{"tool": "screenshot", "path": "step-N.png"}
{"tool": "done",       "answer": "..."}
```

The set is deliberately small; extend `_execute_action` in `main.py` for additional tools (tab handling, cookies, etc. — see `skill-browser-interact`).

## What this example demonstrates

- **`browser_task(task, llm_fn, max_steps)`** — full tool loop, returns `{completed, steps, final_answer, history}`
- **`make_echo_llm(script)`** — deterministic test stub that replays a scripted list of actions; lets you run the skill end-to-end without any LLM credential

## Prerequisites

- Python 3.13 (managed by `uv`)
- `uv` installed
- Access to the `browser-v1` sandbox template
- (For real LLM use) your LLM client of choice — wrap its response in a function that returns the action dict

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

The built-in demo uses `make_echo_llm` with a fixed 4-step script against `https://example.com`:

```
=== Skill Result: browser_task ===
{
  "task": "Open example.com, grab the title + h1 and save a full-page screenshot.",
  "completed": true,
  "steps": 4,
  "final_answer": "captured title + h1 + screenshot",
  "history": [
    {"step": 0, "action": {"tool": "goto", "url": "https://example.com"}, "outcome": {"ok": true, "detail": "goto https://example.com"}},
    {"step": 1, "action": {"tool": "evaluate", ...}, "outcome": {"ok": true, "detail": {"value": {"title": "Example Domain", "h1": "Example Domain"}}}},
    {"step": 2, "action": {"tool": "screenshot", "path": "browser-agent-demo.png"}, "outcome": {"ok": true, "detail": {"saved_to": "browser-agent-demo.png", "size": 34521}}},
    {"step": 3, "action": {"tool": "done", ...}, "outcome": {"ok": true, "detail": {"answer": "..."}}}
  ]
}
```

`browser-agent-demo.png` is saved in the current working directory.

## Plugging in a real LLM

```python
def my_llm(observation: dict, history: list[dict], task: str) -> dict:
    # Build a prompt describing observation + history + task.
    prompt = f"Task: {task}\nObservation: {observation}\nHistory: {history[-3:]}"
    reply = my_llm_client.generate(prompt)     # your code
    return json.loads(reply)                   # must be an action dict

browser_task("Find the price of the cheapest N95 mask on example-shop.com",
             llm_fn=my_llm, max_steps=15)
```

The skill is oblivious to which LLM you use as long as the callback returns a well-formed action dict. If the LLM emits an unknown `tool`, the step records `{"ok": false, "detail": "unknown tool: ..."}` and the loop continues.

## Common failure modes

| Symptom | Likely cause |
|---|---|
| `KeyError: 'E2B_API_KEY'` | Environment variable not exported |
| Sandbox creation timeout | Wrong `E2B_DOMAIN` for your region |
| `TencentCloudSDKException` on credential check | Invalid or missing `TENCENTCLOUD_SECRET_ID` / `SECRET_KEY` |
| Loop finishes with `completed: false` | LLM never emitted `done`, or `max_steps` was too small |
| Every step has `"ok": false, "detail": "unknown tool"` | `llm_fn` returned malformed action dicts — double-check JSON shape |
| `playwright._impl._errors.TimeoutError` | Target selector never appeared; feed the LLM richer observations, or raise timeouts in `_execute_action` |

## Skill interface

```python
browser_task(
    task: str,
    llm_fn: Callable[[dict, list[dict], str], dict],
    max_steps: int = 10,
    tool_name: str = "browser-v1",
    timeout: str = "10m",
) -> dict

make_echo_llm(script: list[dict]) -> Callable[[dict, list[dict], str], dict]
```
