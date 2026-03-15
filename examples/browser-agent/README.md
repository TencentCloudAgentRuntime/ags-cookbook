# Browser Agent: Cloud Sandbox-Based Browser Automation

This example demonstrates how to use AgentSandbox cloud sandbox to run a browser, combined with LLM for intelligent web automation tasks.

## Architecture

```
┌─────────────┐     Tool Call     ┌─────────────┐      CDP       ┌─────────────┐
│     LLM     │ ───────────────▶  │   Browser   │ ─────────────▶ │  AgentSandbox  │
│  (GLM-4.7)  │                   │    Agent    │                │   (browser) │
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

## Quick Start

### 1. Install Dependencies

```bash
uv sync
```

### 2. Configure API Keys

Set environment variables before running:

```bash
export E2B_API_KEY="your_ags_api_key"           # AgentSandbox API Key
export LLM_API_KEY="your_llm_api_key"           # LLM API Key
export LLM_API_URL="https://your-llm-api/v1/chat/completions"
export LLM_MODEL="glm4.7"                       # Optional, defaults to glm4.7
export E2B_DOMAIN="ap-guangzhou.tencentags.com" # Optional
```

### 3. Run Example

```bash
uv run main.py
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

## Dependencies

- Python >= 3.12
- e2b >= 2.9.0
- playwright >= 1.57.0
- requests >= 2.32.5

## Quick Start

```bash
make run
```

