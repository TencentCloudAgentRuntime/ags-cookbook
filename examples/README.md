# Examples

This directory contains various usage examples for Agent Sandbox, each with its own independent directory structure.

## Directory Structure

```
examples/
├── browser-agent/         # Browser automation agent
├── custom-image-go-sdk/   # Go SDK custom image startup
├── data-analysis/         # Data analysis
├── html-processing/       # HTML collaboration
├── hybrid-cookbook/        # Go SDK hybrid flow
├── mini-rl/               # Reinforcement learning sandbox
├── mobile-use/            # Mobile automation
├── osworld-ags/           # Public OSWorld AGS overlay
└── shop-assistant/        # Shopping cart automation
```

Each example contains its own `README.md`, `Makefile`, and source code. See per-example README for details.

## Example List

### browser-agent - Browser Automation Agent

Demonstrates how to use AgentSandbox cloud sandbox to run a browser, combined with LLM for intelligent web automation:

- **Cloud Browser**: Browser runs in sandbox, locally controlled via CDP
- **LLM-Driven**: Intelligent browser operation decisions via Function Calling
- **VNC Visualization**: Real-time browser view
- **Rich Toolset**: Navigation, element highlighting, clicking, screenshots, etc.

**Use Cases**:
- Automated form filling
- Web end-to-end testing

**Tech Stack**: playwright

### data-analysis - Data Analysis Example

Demonstrates how to use Agent Sandbox for complex data analysis workflows, including:

- **Multi-Context Environment Isolation**: 3 independent Contexts collaborating on data processing
- **Complete Data Processing Pipeline**: From data cleaning to visualization analysis
- **Real Business Scenario**: 5000-product e-commerce data analysis and optimization

**Use Cases**:
- Projects requiring multi-step data processing
- Collaboration scenarios requiring environment isolation
- Complex business data analysis

**Tech Stack**: pandas, numpy, matplotlib, seaborn, scipy

### html-processing - HTML Collaboration Example

Demonstrates Code and Browser sandbox collaboration capabilities, including:

- **Dual Sandbox Collaboration**: Code sandbox editing + Browser sandbox rendering
- **Visual Comparison**: Before/after screenshot comparison
- **Complete Workflow**: Create → Render → Edit → Re-render
- **File Transfer**: Local ↔ Browser ↔ Code ↔ Browser ↔ Local

**Use Cases**:
- HTML editing and preview in web development
- Automated page content modification
- Visual regression testing
- Batch HTML template processing

**Tech Stack**: playwright, HTML/CSS

### mini-rl - Reinforcement Learning Sandbox Example

Demonstrates how to integrate AgentSandbox sandbox in reinforcement learning scenarios:

- **Complete Flow**: Model outputs ToolCall → Runtime parsing → Sandbox execution → Result backfill
- **RL Perspective**: Complete mapping of State/Action/Environment/Observation/Reward
- **Minimal Example**: Single file demonstrating core concepts

**Use Cases**:
- Integrating sandbox with RL frameworks like VERL
- Code execution for mathematical reasoning tasks
- Agent tool calling training

**Tech Stack**: AgentSandbox

### custom-image-go-sdk - Go SDK Custom Image Example

Demonstrates how to start a custom-image sandbox with Go SDK, including:

- **Control Plane Start**: Start sandbox instance via AGS control-plane API
- **Custom Configuration**: Override runtime image/command/ports/probe via env
- **Data Plane Execution**: Connect and run code through AGS data-plane

**Use Cases**:
- Validate enterprise image startup configuration
- Verify custom command and health probe setup
- Build robust startup automation with environment templates

**Tech Stack**: Go, Tencent Cloud AGS SDK

### hybrid-cookbook - Go SDK Hybrid Flow Example

Demonstrates the minimal “Control Plane + Data Plane” hybrid workflow:

- **Start Sandbox**: Create sandbox with tool template
- **Run Code**: Connect to sandbox and execute code directly
- **Auto Cleanup**: Stop instance on exit to avoid resource leakage

**Use Cases**:
- Quick proof-of-concept for AGS Go SDK integration
- Hybrid workflow onboarding for new contributors

**Tech Stack**: Go, Tencent Cloud AGS SDK

### mobile-use - Mobile Automation Example

Demonstrates how to use AgentSandbox cloud sandbox to run Android devices with Appium for mobile automation:

- **Cloud Android Device**: Android runs in sandbox, locally controlled via Appium
- **Screen Streaming**: Real-time screen viewing via ws-scrcpy
- **Element Operations**: Find and click elements by text or resource-id
- **CLI Tool**: `sandbox_connect.py` for connecting to existing sandboxes
- **Batch Testing**: High-concurrency sandbox testing (multi-process + async)

**Use Cases**:
- Mobile app automated testing
- Mobile UI/UX testing
- High-concurrency mobile testing
- GPS location mocking

**Tech Stack**: Appium, Android, pytest

### osworld-ags - Run OSWorld on AGS

Shows how to run the public OSWorld project on Agent Sandbox by applying a small compatibility overlay:

- **AGS Provider**: Adds `provider_name=ags` support to OSWorld
- **Remote Desktop Access**: Supports noVNC viewing for AGS sandboxes
- **Simple Setup**: Clone OSWorld, apply the overlay, install dependencies, and run

**Use Cases**:
- Run OSWorld on AGS using the overlay published in this cookbook

**Tech Stack**: Python, aiohttp, e2b-code-interpreter, OSWorld

### shop-assistant - Shopping Cart Automation Example

Demonstrates using Browser sandbox with Playwright to complete "Search → Add to Cart → View Cart" automation in logged-in state.

- Login-free Experience: Local Cookie import
- Automation Chain: Search, product page, add to cart, shopping cart
- Remote Debugging: VNC observation of execution process (on-demand)

**Use Cases**:
- E-commerce flow replay and verification
- Key path demonstration with login state
- Remote automation demo

**Tech Stack**: playwright

## Unified Command Interface

All examples provide the same command surface:

```bash
make run
```

- `make run`: executes the main workflow

## Contributing New Examples

We welcome new example contributions! Each example should include:

- `README.md` with feature description, use cases, running steps, expected output
- an entry point or setup script when the example needs one
- `.env.example` listing required environment variables
