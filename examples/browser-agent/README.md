# Browser Agent: Cloud Sandbox-Based Browser Automation

This example demonstrates how to use AgentSandbox cloud sandbox to run a browser, combined with LLM for intelligent web automation tasks.

## Architecture

```
┌─────────────┐     Tool Call     ┌─────────────┐      CDP       ┌─────────────┐
│     LLM     │ ───────────────▶  │   Browser   │ ─────────────▶ │  AgentSandbox  │
│     LLM     │                   │    Agent    │                │   (browser) │
└─────────────┘                   └─────────────┘                └─────────────┘
      ▲                                 │                              │
      │                                 │◀─────────────────────────────┘
      │                                 │      Page State / Result
      └─────────────────────────────────┘
              Observation
```

**Core Features**:
- Browser runs in cloud sandbox, locally controlled via CDP protocol
- Supports VNC for real-time browser view
- LLM drives browser operations via Function Calling

## Prerequisites

- Python >= 3.12
- `uv`
- `E2B_API_KEY`
- OpenAI-compatible backend variables (`OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`)

## Local commands

```bash
make setup
make run
```

## Required environment variables

Set environment variables before running:

```bash
export E2B_API_KEY="your_ags_api_key"           # AgentSandbox API Key
export OPENAI_API_KEY="your_llm_api_key"           # LLM API Key
export OPENAI_BASE_URL="https://your-openai-compatible-api/v1"
export OPENAI_MODEL="your-model-name"              # Required model name
export E2B_DOMAIN="ap-guangzhou.tencentags.com"
```

After running, a VNC link will be output, allowing you to watch the automation process in real-time in your browser.

## Available Tools

| Tool | Description |
|------|-------------|
| `navigate` | Navigate to specified URL |
| `highlight_elements` | Highlight interactive elements on page and return numbers |
| `click_element` | Click element by number |
| `click_text` | Click element containing specified text |
| `get_page_text` | Get page text content |
| `scroll_down` | Scroll page down |
| `screenshot` | Take page screenshot |
| `task_complete` | Mark task as complete |

## Workflow

1. **Create Sandbox**: Start cloud sandbox with `browser-v1` template
2. **Connect Browser**: Connect to Chromium in sandbox via CDP protocol
3. **LLM Decision**: LLM selects tool calls based on page state
4. **Execute Operation**: Agent executes browser operations and returns results
5. **Loop Iteration**: Until task completes or max steps reached

## Expected result

A successful run should create a browser sandbox, print a VNC/debug URL, navigate the target site, and finish by calling `task_complete`.

## Common failure hints

- If the LLM backend times out, reduce context size or confirm `OPENAI_BASE_URL` / `OPENAI_API_KEY` / `OPENAI_MODEL`
- If browser startup fails, verify `E2B_API_KEY` and `E2B_DOMAIN`
