# Mini-SWE-Agent: SWE-bench Evaluation with AGS SWE Sandbox

This example demonstrates how to run [SWE-bench Verified](https://huggingface.co/datasets/princeton-nlp/SWE-Bench_Verified) evaluations using [mini-swe-agent](https://github.com/SWE-agent/mini-SWE-agent) with Tencent Cloud AGS SWE Sandbox.

It works by applying a small overlay onto official upstream repositories. The overlay adds AGS sandbox support without requiring any private forks.

## How It Works

```
Official upstream repos          AGS overlay (this cookbook)
┌────────────────────┐          ┌────────────────────┐
│ SWE-agent/         │          │ overlay/            │
│   mini-SWE-agent   │  ← cp ──│   mini-swe-agent/   │  (AGS environment, logging fixes)
│ SWE-agent/         │          │   SWE-ReX/          │  (AGS deployment + runtime)
│   SWE-ReX          │  ← cp ──│                     │
└────────────────────┘          └────────────────────┘
```

The overlay adds:
- AGS SWE sandbox environment wrapper for mini-swe-agent
- AGS deployment provider and runtime for SWE-ReX
- Thread-safe logging to avoid deadlocks with Rich Live progress display
- SWE-bench AGS benchmark configuration

See [overlay/OVERLAY.md](overlay/OVERLAY.md) for a detailed list of every overlaid file.

## Prerequisites

- Python >= 3.10 (3.12 recommended; used by default in `make setup`. Override with `make setup PYTHON_VERSION=3.10`)
- [uv](https://github.com/astral-sh/uv) — Python package manager
- Tencent Cloud account with AGS access (`SecretId` and `SecretKey`)
- An AGS SWE sandbox tool (see Step 1 below)
- An LLM API key (OpenAI, Anthropic, or any OpenAI-compatible endpoint)

## Quick Start

### 1. Create SWE Sandbox Tool (one-time)

1. Log in to the [Tencent Cloud AGS Console](https://console.cloud.tencent.com/ags).
2. Go to **Environment Tools** > **SWE Sandbox**.
3. Click **Create Sandbox Tool**, leave tool configuration empty, choose public network, and submit.
4. Record the **Tool ID** (e.g., `sdt-xxxxxxxx`).

This only needs to be done once — all sandbox instances reuse the same tool ID.

### 2. Configure Environment Variables

```bash
cp .env.example .env
# Edit .env with your Tencent Cloud credentials
```

### 3. Install (clone + overlay + install)

```bash
make setup
```

This will:
- Check that `uv` is installed
- Clone (if needed) and install [SWE-ReX](https://github.com/SWE-agent/SWE-ReX) in editable mode with AGS SDK dependencies (`tencentcloud-sdk-python-common`, `tencentcloud-sdk-python-ags`)
- Clone (if needed) and install [mini-swe-agent](https://github.com/SWE-agent/mini-SWE-agent) in editable mode with full dependencies
- Apply the AGS overlay from `overlay/`

### 4. Create Local Config

Create `my_config.yaml` with your credentials and LLM settings:

```yaml
environment:
  tool_id: "sdt-xxxxxxxx"                    # Tool ID from Step 1
  region: "ap-chongqing"                     # AGS region (default: ap-chongqing)

model:
  model_name: "anthropic/claude-sonnet-4-5"
  model_kwargs:
    api_key: "sk-ant-xxxxx"
```

Security note: `my_config.yaml` is intended to stay local. Prefer environment variables for API keys when possible.

**Region Configuration**: The default region is `ap-chongqing`. If your AGS tool was created in a different region, update the `region` field. Check your [AGS Console](https://console.cloud.tencent.com/ags/sandbox/tool) to find the correct region.

For custom API endpoints (e.g., self-hosted or proxy models), the `model_name` must follow [litellm's provider/model format](https://docs.litellm.ai/docs/providers). Since custom models are not in litellm's cost registry, set `cost_tracking: "ignore_errors"`:

```yaml
model:
  model_name: "openai/your-model-name"
  cost_tracking: "ignore_errors"
  model_kwargs:
    api_base: "https://your-api-endpoint.com/v1"
    api_key: "your-key"
```

### 5. Run

**Run a single instance (interactive mode):**

```bash
make run
```

This runs one SWE-bench Verified instance in interactive mode, showing each agent step in real-time. Trajectory is saved to `results/interactive.traj.json`.

**Run full benchmark with concurrency:**

```bash
make run-full
```

This runs all 500 SWE-bench Verified instances with 4 concurrent workers. Override with `make run-full WORKERS=8`.

## Run Commands

| Command | Description |
|---------|-------------|
| `make setup` | Clone official repos, apply overlay, install dependencies |
| `make run` | Run a single instance in interactive mode (default `-i 0 -y`) |
| `make run-full` | Run all 500 SWE-bench Verified instances (default: `WORKERS=4`) |
| `make logs` | Tail the debug log file (run after `make run-full`) |
| `make tail` | Pretty-print the most recently updated trajectory JSON |
| `make clean` | Remove cloned repos and results |

## Results

Results are saved to the `results/` directory:

```
results/
├── interactive.traj.json                          # Trajectory from `make run`
├── minisweagent.log                              # Run log from `make run-full`
├── preds.json                                    # Predictions from `make run-full`
├── exit_statuses_*.yaml                          # Exit status summary
└── <instance_id>/
    └── <instance_id>.traj.json                   # Per-instance trajectory
```

## Configuration

The evaluation uses a layered config system. Multiple `-c` configs are merged in order:

| Config | Purpose |
|--------|---------|
| `swebench_ags` | Built-in base config: prompt templates, timeouts, AGS endpoint defaults |
| `my_config.yaml` | Your credentials, tool ID, and LLM settings |

Key parameters in the base config (`swebench_ags`):

| Parameter | Default | Description |
|-----------|---------|-------------|
| `environment.tool_id` | (required) | AGS SWE sandbox tool ID from console |
| `environment.region` | `"ap-chongqing"` | AGS region where your tool is deployed |
| `environment.timeout` | `60` | Per-command execution timeout in seconds |
| `environment.startup_timeout` | `120` | Sandbox instance startup timeout in seconds |
| `environment.runtime_timeout` | `60` | SWE-ReX HTTP request timeout in seconds |
| `environment.timeout_duration` | `"1h"` | Sandbox instance total lifetime |
| `agent.step_limit` | `250` | Max agent steps per instance |
| `agent.cost_limit` | `3.0` | Max LLM cost per instance (USD) |

**Timeout details:**

- **`timeout`** (60s = 1 min): The maximum time a single bash command can run inside the sandbox. If the agent issues a command (e.g., running tests) that exceeds this limit, it is killed and a `CommandTimeoutError` is raised.
- **`startup_timeout`** (120s = 2 min): How long to wait for a new AGS sandbox instance to be created and become ready. This includes image pull and container initialization on the AGS side.
- **`runtime_timeout`** (60s = 1 min): The HTTP request timeout for each SWE-ReX API call (e.g., `is_alive`, `execute`). This does **not** limit command execution time — it only limits the network round-trip. If the AGS gateway is slow to respond, increase this value.
- **`timeout_duration`** ("1h"): The total lifetime of the sandbox instance on the AGS side. After this period, AGS automatically reclaims the instance. Any subsequent API calls will receive a 404 and raise `EnvironmentExpiredError`. For long-running instances with many agent steps, increase to `"2h"` or more.

All timeout values can be overridden in `my_config.yaml`:

```yaml
environment:
  timeout: 120           # 2 min per command
  startup_timeout: 300   # 5 min for instance creation
  runtime_timeout: 120   # 2 min HTTP timeout
  timeout_duration: "2h" # 2 hour instance lifetime
```

## AGS System Images

AGS provides **system images** — pre-built and pre-warmed container images hosted within the AGS platform. These images are ready to use out of the box, with no need to pull or build them yourself.

When you create a sandbox instance with a system image, it starts significantly faster because the image layers are already cached locally.

In this example, mini-swe-agent automatically derives the image name from each SWE-bench instance and passes it to AGS as a system image:

```json
{
    "ToolId": "sdt-xxxxxxxx",
    "ClientToken": "unique-request-id",
    "Timeout": "1h",
    "CustomConfiguration": {
        "Image": "swebench/sweb.eval.x86_64.django__django-16379:latest",
        "ImageRegistryType": "system"
    }
}
```

You can browse available system images on the [AGS System Image Management page](https://console.cloud.tencent.com/ags/sandbox/template).

> **Note**: Not all 500 SWE-bench Verified images are available as system images. Check the dashboard and use `--filter` to run only supported instances.

## Common Failure Modes

### `Failed to check image availability`

The SWE-bench image for this instance is not available as a system image in AGS. Check the [AGS System Image Management page](https://console.cloud.tencent.com/ags/sandbox/template) and use `--filter` to run only supported instances.

### `CommandTimeoutError: Timeout (60s) exceeded`

A single command took longer than `environment.timeout`. Increase it in your config:

```yaml
environment:
  timeout: 120  # 2 minutes
```

### `404 Not Found` / `EnvironmentExpiredError`

The AGS sandbox instance has expired or was stopped. SWE-ReX raises an `EnvironmentExpiredError` immediately. The instance is marked as a failed environment task.

If this happens frequently, increase the sandbox lifetime:

```yaml
environment:
  timeout_duration: "2h"
```

### `Error calculating cost for model`

Add `cost_tracking: "ignore_errors"` to your model config.

### `RuntimeError: SandboxTool sdt-xxx not found`

Verify the tool ID, region, and tool status on the [AGS Console](https://console.cloud.tencent.com/ags).

## Updating When Upstream Changes

Since the overlay is applied on top of official upstream repos, you can update by:

```bash
make clean
make setup
```

If the upstream has changed files that the overlay also modifies, you may need to update the overlay files. See [overlay/OVERLAY.md](overlay/OVERLAY.md) for details on each overlaid file.

## Notes

- This is not an official upstream mini-swe-agent or SWE-ReX release.
- The AGS integration is distributed as a cookbook overlay.
- Upstream projects: [SWE-agent/mini-SWE-agent](https://github.com/SWE-agent/mini-SWE-agent), [SWE-agent/SWE-ReX](https://github.com/SWE-agent/SWE-ReX)
