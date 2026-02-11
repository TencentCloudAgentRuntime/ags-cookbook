# SWE-Bench RL Training with AGS

Demonstrates using AgentSandbox (AGS) as the execution backend for distributed PPO training on SWE-Bench code repair tasks.

AGS creates isolated Linux container environments on-demand for each SWE-Bench task. The agent edits code and runs tests inside the sandbox, with test results serving as reward signals for PPO training.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      PPO Training Loop                      │
│                                                             │
│  ┌──────────┐    ┌──────────────┐    ┌──────────────────┐  │
│  │ SWE-Bench│───>│  vLLM Rollout│───>│    SWEAgent      │  │
│  │   Data   │    │ (generate    │    │ (parse as tool   │  │
│  │          │    │  code edits) │    │  calls)          │  │
│  └──────────┘    └──────────────┘    └────────┬─────────┘  │
│                                               │             │
│                                               ▼             │
│                                      ┌────────────────┐    │
│                                      │  AGS Sandbox   │    │
│                                      │  (execute edits│    │
│                                      │   & run tests) │    │
│                                      └────────┬───────┘    │
│                                               │             │
│                                               ▼             │
│  ┌──────────┐    ┌──────────────┐    ┌────────────────┐    │
│  │ PPO      │<───│   Reward     │<───│ Test pass/fail │    │
│  │ Update   │    │   Signal     │    │ = reward 0/1   │    │
│  └──────────┘    └──────────────┘    └────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

**Key setting**: `+rllm.env.env_args.backend=ags` specifies AGS cloud sandbox, replacing local Docker or Kubernetes.

## Prerequisites

| Item | Requirement |
|------|-------------|
| **GPU** | H20 x 8 (adjust config based on model size) |
| **AGS Credentials** | `E2B_API_KEY`, `TENCENTCLOUD_SECRET_ID`, `TENCENTCLOUD_SECRET_KEY` |
| **AGS Sandbox Tools** | Sandbox tools created for docker images in the dataset (see [ags_tool docs](https://github.com/lirong-lirong/ags_tool)) |
| **Model Weights** | This demo uses Qwen3-8B, must be downloaded to a local path |
| **Network** | Access to HuggingFace (or HF mirror) for dataset download |

## Quick Start

Follow the Jupyter Notebook [`rllm_with_ags.ipynb`](rllm_with_ags.ipynb), which walks through 4 steps:

1. **Install Dependencies** — Clone and install rLLM, verl, R2E-Gym, ags_tool
2. **Configure Environment Variables** — Set AGS credentials, vLLM runtime, MLflow monitoring, etc.
3. **Prepare Datasets** — Download SWE-Bench-Lite (validation) and R2E-Gym-Subset (training) from HuggingFace, sorted by `docker_image`
4. **Configure and Start Training** — Set PPO parameters via Hydra overrides, launch with `AgentTrainer.train()`

## Configuration Parameters

Training is configured via Hydra overrides, based on `agent_ppo_trainer.yaml`:

| Parameter Group | Purpose | Key Settings |
|-----------------|---------|--------------|
| `algorithm.*` | PPO/RLOO algorithm | `adv_estimator=rloo`, `kl_coef=0.001` |
| `data.*` | Batch size, sequence length | `train_batch_size=4`, `max_response_length=32768` |
| `actor_rollout_ref.*` | Model, optimizer, vLLM inference | `model.path=Qwen3-8B`, `rollout.n=4`, `gpu_memory_utilization=0.5` |
| `rllm.*` | Agent/Environment settings | **`env.env_args.backend=ags`** (enable AGS) |
| `trainer.*` | Logging, checkpoints, GPU topology | `n_gpus_per_node=8`, `total_epochs=2` |

Notes:
- `ppo_max_token_len_per_gpu` must be greater than `max_prompt_length + max_response_length`
- `rollout.n=4` means 4 samples per data point (4 independent sandboxes per question); training reinforces high-scoring trajectories and suppresses low-scoring ones
- `train_batch_size x rollout.n` must be divisible by `n_gpus_per_node` (this demo: 4 x 4 = 16, 16 / 8 = 2)
- Total sandboxes created = data_samples x epochs x rollout.n

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| AGS connection 401/403 | Wrong credentials or region mismatch | Check `E2B_API_KEY`, Secret ID/Key; verify `AGS_REGION` matches sandbox tool region |
| `Numba needs NumPy 2.2 or less` | NumPy version too high | `pip install 'numpy<2.3'` |
| `must be called with a dataclass type or instance` | datasets version too low | `pip install 'datasets>=4.5.0'` |
| vLLM OOM | Insufficient GPU memory | Reduce `gpu_memory_utilization`, `max_response_length`, or use a smaller model |
| Ray initialization failure | Stale Ray processes | `ray stop --force` then retry |
| Dataset download failure | HF unreachable | Set `HF_ENDPOINT` to an available mirror |

## Tech Stack

- [rLLM](https://github.com/rllm-org/rllm) — Agent RL training framework
- [verl](https://github.com/volcengine/verl) — Distributed PPO training engine
- [R2E-Gym](https://github.com/R2E-Gym/R2E-Gym) — SWE-Bench environment and datasets
- [vLLM](https://github.com/vllm-project/vllm) — LLM inference engine
- AgentSandbox — Cloud sandbox execution backend
