# SWE-Bench Inference with AGS

Demonstrates using R2E-Gym Python API with AGS cloud sandbox to complete SWE-Bench code repair tasks via LLM inference.

AGS creates isolated Linux container environments on-demand for each SWE-Bench task. The agent reads code, edits files, and runs tests inside the sandbox. Test results serve as the reward signal (pass = 1.0, fail = 0.0).

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                     SWE-Bench Inference                       │
│                                                              │
│  ┌──────────┐    ┌──────────────┐    ┌───────────────────┐  │
│  │ SWE-Bench│───>│   LLM API    │───>│   EditAgent       │  │
│  │  Dataset  │    │ (generate    │    │ (parse as tool    │  │
│  │          │    │  code edits) │    │  calls)           │  │
│  └──────────┘    └──────────────┘    └─────────┬─────────┘  │
│                                                │             │
│                                                ▼             │
│                                       ┌────────────────┐    │
│                                       │  AGS Sandbox   │    │
│                                       │  - execute edits│    │
│                                       │  - run tests    │    │
│                                       └────────┬───────┘    │
│                                                │             │
│                                                ▼             │
│  ┌──────────┐    ┌──────────────┐    ┌────────────────┐     │
│  │  Save    │<───│   Reward     │<───│ Test pass/fail │     │
│  │Trajectory│    │   0 or 1     │    │ (in sandbox)   │     │
│  └──────────┘    └──────────────┘    └────────────────┘     │
└──────────────────────────────────────────────────────────────┘
```

Core flow:

1. Load SWE-Bench dataset from HuggingFace (contains GitHub issues and corresponding Docker images)
2. AGS creates a cloud sandbox from the image (replacing local Docker)
3. Agent executes code edits in the sandbox (str_replace_editor, execute_bash, etc.)
4. Sandbox runs the project test suite, calculates reward (all pass = 1.0, otherwise = 0.0)
5. Save trajectory (contains full agent action sequence and reward)

## Prerequisites

| Item | Requirement |
|------|-------------|
| **Python** | >= 3.10 |
| **AGS Credentials** | `E2B_API_KEY`, `TENCENTCLOUD_SECRET_ID`, `TENCENTCLOUD_SECRET_KEY` |
| **AGS Sandbox Tools** | Sandbox tools created for docker images in the dataset (see below) |
| **LLM API** | OpenAI-compatible LLM service (e.g., model deployed via vLLM) |
| **Network** | Access to HuggingFace (or HF mirror) for dataset download |

### About AGS Sandbox Tools

AGS uses "sandbox tools" as container templates. Before use, you need to:

1. Push Docker images from the SWE-Bench dataset to TCR (Tencent Container Registry)
2. Create corresponding sandbox tools based on the pushed TCR images

For convenience, sandbox tools have been pre-created for the first 10 images in the `R2E-Gym/SWE-Bench-Lite` dataset. The ags_tool will automatically find the corresponding sandbox tool based on the original image name.

To create more sandbox tools, see `example/swe_bench_ags_tool.ipynb` in the [ags_tool docs](https://github.com/lirong-lirong/ags_tool).

## Quick Start

Follow the Jupyter Notebook [`swe-bench-ags-python.ipynb`](swe-bench-ags-python.ipynb), which walks through 5 steps:

1. **Install Dependencies** — Clone and install R2E-Gym and ags_tool
2. **Configure Environment Variables** — Set LLM API, AGS credentials, HuggingFace mirror
3. **Load Dataset** — Load SWE-Bench-Lite from HuggingFace, select task range
4. **Run Agent** — Create sandbox, run EditAgent, calculate reward, save trajectory
5. **View Results** — Inspect trajectory and log files

## Parameters

### Dataset Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `START_IDX` | 0 | Starting index in the dataset |
| `K` | 1 | Number of tasks to run |

### Agent Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_steps` | 60 | Max agent interaction steps |
| `temperature` | 1.0 | LLM sampling temperature |
| `max_steps_absolute` | 100 | Absolute max step limit |
| `max_token_limit` | 65536 | Context token limit |
| `use_fn_calling` | False | Whether to use function calling mode (this example uses text parsing) |
| `scaffold` | "r2egym" | Agent scaffold type |

### Reward Calculation

| Parameter | Default | Description |
|-----------|---------|-------------|
| `timeout` | 300 | Test execution timeout (seconds) |

Reward logic: runs the project test suite in the sandbox, automatically selecting evaluation method based on dataset type:

- **SWE-Bench**: Uses swebench official grading module to evaluate FAIL_TO_PASS and PASS_TO_PASS
- **R2E-Edit**: Compares test output with expected_output_json
- **SWE-Smith**: Checks if FAIL_TO_PASS tests pass without PASS_TO_PASS regression

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| AGS connection 401/403 | Wrong credentials or region mismatch | Check `E2B_API_KEY`, Secret ID/Key; verify `AGS_REGION` matches sandbox tool region |
| `Sandbox tool not found for image ...` | Sandbox tool not created | Run `ags_tool_sync.py` or manually create sandbox tools (see ags_tool docs) |
| `ags_tool is required for AGS runtime` | ags_tool not installed | `pip install -e './ags_tool[e2b]'` |
| Dataset download failure | HF unreachable | Set `HF_ENDPOINT` to an available mirror |
| LLM errors during agent run | LLM API URL or key misconfigured | Check `LLM_BASE_URL` and `OPENAI_API_KEY` |
| Test timeout | Project test suite takes too long | Increase `timeout` parameter (default 300s) |
| `Numba needs NumPy 2.2 or less` | NumPy version too high | `pip install 'numpy<2.3'` |

## Tech Stack

- [R2E-Gym](https://github.com/R2E-Gym/R2E-Gym) — SWE-Bench environment wrapper and datasets
- [ags_tool](https://github.com/lirong-lirong/ags_tool) — AGS sandbox Python wrapper
- [swebench](https://github.com/princeton-nlp/SWE-bench) — SWE-Bench official evaluation tool
- AgentSandbox — Cloud sandbox execution backend
