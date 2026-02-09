# Examples

This directory contains various usage examples for Agent Sandbox, each with its own independent directory structure.

## Directory Structure

```
examples/
├── README.md              # Examples overview
├── browser-agent/         # Browser automation agent example
│   ├── README.md          # Detailed usage instructions
│   ├── main.py            # LLM-driven browser agent
│   └── pyproject.toml     # Dependency configuration
├── data-analysis/         # Data analysis example
│   ├── README.md          # Detailed usage instructions
│   ├── multi_context_demo.py  # Multi-Context collaboration demo
│   └── requirements.txt   # Dependencies
├── html-processing/       # HTML collaboration example
│   ├── README.md          # Detailed usage instructions
│   ├── html_collaboration_demo.py  # Code+Browser collaboration demo
│   └── requirements.txt   # Dependencies
├── mini-rl/               # Reinforcement learning sandbox example
│   ├── README.md          # Detailed usage instructions
│   ├── main.py            # RL + sandbox minimal example
│   └── pyproject.toml     # Dependency configuration
├── mobile-use/            # Mobile automation example
│   ├── README.md          # Detailed usage instructions
│   ├── quickstart.py      # Quick start example
│   ├── batch.py           # Batch operations (multi-process + async)
│   ├── sandbox_connect.py # Single sandbox connection tool (CLI)
│   └── requirements.txt   # Dependencies
├── shop-assistant/        # Shopping cart automation example
│   ├── README.md          # Detailed usage instructions
│   ├── automation_cart_demo.py  # Shopping flow automation demo
│   └── requirements.txt   # Dependencies
└── swe-agent/             # SWE-agent with AGS integration example
    ├── README.md          # Detailed usage instructions
    ├── README_zh.md       # Chinese documentation
    └── SWE-ReX/           # Modified SWE-ReX for AGS integration

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

### swe-agent - SWE-Agent with AGS Integration Example

Demonstrates how to integrate AgentSandbox sandbox into SWE-agent tasks:

- **Complete Workflow**: Reading SWE instances → remotely starting code sandbox environment → model reasoning in sandbox → generating trajectories
- **Sandbox Isolation**: Safe, reliable, and fast deployment of SWE environments
- **Customizable Environment**: Highly customizable sandbox environment with automated resource management
- **SWE-agent Integration**: Seamless integration with existing SWE-agent workflow

**Use Cases**:
- Automated software engineering and code fixing
- SWE benchmark evaluation
- AI-driven code generation and analysis

**Tech Stack**: SWE-agent, Tencent AGS, Python

## Requirements

1. Install dependencies: `pip install -r ../requirements.txt`
2. Set environment variables:
   ```bash
   export E2B_API_KEY="your-api-key"
   export E2B_DOMAIN="api.e2b.dev"  # Optional
   ```
3. Navigate to specific example directory and run the corresponding script

## Contributing New Examples

We welcome new example contributions! Please follow this structure:

```
examples/your-example-name/
├── README.md              # Example documentation
├── main_script.py         # Main demo script
└── requirements.txt       # Additional dependencies (if needed)
```

Each example's README should include:
- Feature description
- Use cases
- Running steps
- Expected output
- Tech stack description
