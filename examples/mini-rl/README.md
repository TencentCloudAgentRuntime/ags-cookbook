# Mini-RL: Reinforcement Learning + AgentSandbox Minimal Example

This example demonstrates how to integrate AgentSandbox sandbox in reinforcement learning scenarios, implementing the complete flow of "Model outputs ToolCall → Runtime parsing → Sandbox execution → Result backfill".

## Core Concepts

```
┌─────────────┐     ToolCall      ┌─────────────┐     Execute      ┌─────────────┐
│   Policy    │ ───────────────▶  │    VERL     │ ───────────────▶ │  AgentSandbox   │
│   (Model)   │                   │   Runtime   │                  │   Sandbox   │
└─────────────┘                   └─────────────┘                  └─────────────┘
                                        │                                │
                                        │◀───────────────────────────────┘
                                        │         Observation
                                        ▼
                                  ┌─────────────┐
                                  │   Reward    │
                                  │ Calculation │
                                  └─────────────┘
```

**Key Point**: The sandbox is started by Runtime, not directly called by the model.

## Quick Start

### 1. Configure API Key

Set environment variables before running:

```bash
export E2B_API_KEY="your_ags_api_key"  # provided by Tencent Cloud Agent Sandbox product
export E2B_DOMAIN="ap-guangzhou.tencentags.com"
```

### 2. Run Example

```bash
make setup
make run
```

### Expected Output

```
=== Rollout Result ===
Question: Calculate: 23 × 17 − 19
Sandbox Result: 372
Reward: 1.0
```

## Code Structure

| Function | Description |
|----------|-------------|
| `model_generate()` | Simulates model outputting ToolCall (Policy behavior) |
| `parse_tool_call()` | Parses tool call from model output |
| `verl_parse_and_execute()` | Runtime parses and triggers sandbox execution |
| `stitch_context()` | Backfills sandbox result into context |
| `rollout_one_episode()` | One complete RL trajectory |

## Reinforcement Learning Perspective

| RL Concept | Corresponding Element |
|------------|----------------------|
| State | Question + historical context |
| Action | ToolCall output by model |
| Environment | AgentSandbox sandbox |
| Observation | Sandbox execution result |
| Reward | Answer correctness judgment |

## Dependencies

- Python >= 3.12
- e2b-code-interpreter >= 2.4.1

## Quick Start

```bash
make run
```
