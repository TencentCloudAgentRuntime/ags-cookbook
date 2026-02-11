# SWE-Bench with AgentSandbox

Demonstrates how to use AgentSandbox (AGS) cloud sandbox to complete SWE-Bench code repair tasks, covering both inference and reinforcement learning training.

AGS creates isolated Linux container environments on-demand for each SWE-Bench task. The agent edits code and runs tests inside the sandbox, with test pass/fail results serving as the reward signal.

## Sub-examples

| Directory | Description | Key Dependencies |
|-----------|-------------|------------------|
| [inference/](inference/) | Single-task inference with LLM API + R2E-Gym | R2E-Gym, ags_tool, LLM API |
| [rl-training/](rl-training/) | Distributed PPO training with rLLM + verl | rLLM, verl, R2E-Gym, vLLM |

## Prerequisites

| Item | Requirement |
|------|-------------|
| **AGS Credentials** | `E2B_API_KEY`, `TENCENTCLOUD_SECRET_ID`, `TENCENTCLOUD_SECRET_KEY` |
| **AGS Sandbox Tools** | Sandbox tools created for docker images in the dataset (see [ags_tool docs](https://github.com/lirong-lirong/ags_tool)) |
| **Network** | Access to HuggingFace (or HF mirror) for dataset download |

See each sub-example's README for additional prerequisites.

## Tech Stack

- [R2E-Gym](https://github.com/R2E-Gym/R2E-Gym) — SWE-Bench environment and datasets
- [ags_tool](https://github.com/lirong-lirong/ags_tool) — AGS sandbox Python wrapper
- [rLLM](https://github.com/rllm-org/rllm) — Agent RL training framework (rl-training)
- [verl](https://github.com/volcengine/verl) — Distributed PPO training engine (rl-training)
- AgentSandbox — Cloud sandbox execution backend
