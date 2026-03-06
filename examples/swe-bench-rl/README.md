# SWE-Bench with AgentSandbox

Demonstrates how to use AgentSandbox (AGS) cloud sandbox to complete SWE-Bench code repair tasks, covering both inference and reinforcement learning training.

AGS creates isolated Linux container environments on-demand for each SWE-Bench task. The agent edits code and runs tests inside the sandbox, with test pass/fail results serving as the reward signal.

## Directory Structure

```
swe-bench-rl/
├── README.md
├── README_zh.md
├── patches/                          # Patch files for upstream repos
│   └── r2e-gym-ags-clean.patch     # R2E-Gym AGS runtime patch (based on 0d94c4e)
├── ags_tool/                         # AGS sandbox tool (included directly)
│   ├── pyproject.toml
│   ├── README.md
│   ├── src/ags_tool/
│   ├── example/
│   └── tcr_image_tool/
├── inference/                        # LLM inference on SWE-Bench tasks
│   ├── README.md
│   ├── README_zh.md
│   └── swe-bench-ags-python.ipynb
└── rl-training/                      # Distributed PPO training
    ├── README.md
    ├── README_zh.md
    ├── train.py
    └── rllm_with_ags.ipynb
```

## Sub-examples

| Directory | Description | Key Dependencies |
|-----------|-------------|------------------|
| [inference/](inference/) | Single-task inference with LLM API + R2E-Gym | R2E-Gym, ags_tool, LLM API |
| [rl-training/](rl-training/) | Distributed PPO training with rLLM + verl | rLLM, verl, R2E-Gym, vLLM |

## Dependency Management

This example uses **official upstream repositories + patch files** instead of third-party forks to improve reproducibility:

- **R2E-Gym**: Cloned from [R2E-Gym/R2E-Gym](https://github.com/R2E-Gym/R2E-Gym), then `patches/r2e-gym-ags-clean.patch` is applied on commit `0d94c4e` to add AGS runtime support.
- **rllm**: Cloned from [rllm-org/rllm](https://github.com/rllm-org/rllm) (rl-training only).
- **ags_tool**: Included directly in `ags_tool/` — an AGS sandbox Python wrapper (no upstream dependency).
- **verl**: Cloned as-is (no patch needed).

## Prerequisites

| Item | Requirement |
|------|-------------|
| **AGS Credentials** | `E2B_API_KEY`, `TENCENTCLOUD_SECRET_ID`, `TENCENTCLOUD_SECRET_KEY` |
| **AGS Sandbox Tools** | Sandbox tools created for docker images in the dataset (see [ags_tool docs](ags_tool/README.md)) |
| **Network** | Access to HuggingFace (or HF mirror) for dataset download |

See each sub-example's README for additional prerequisites.

## Tech Stack

- [R2E-Gym](https://github.com/R2E-Gym/R2E-Gym) — SWE-Bench environment and datasets
- [ags_tool](ags_tool/) — AGS sandbox Python wrapper (included in this repo)
- [rLLM](https://github.com/rllm-org/rllm) — Agent RL training framework (rl-training)
- [verl](https://github.com/volcengine/verl) — Distributed PPO training engine (rl-training)
- AgentSandbox — Cloud sandbox execution backend
