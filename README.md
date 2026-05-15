# Agent Sandbox Cookbook

Examples, tutorials, and utilities for building on Tencent Cloud Agent Sandbox / AGS.

## What this repo contains

- **Tutorials**: SDK and notebook-based onboarding
- **Examples**: runnable browser, code, mobile, Go, and OSWorld demos
- **Benchmarks**: k6 stress scripts
- **Utils**: debugging helpers such as ttyd

## Repository requirements

### Local tools

- `uv` for Python examples
- `python3` for local scripts
- `go` for Go examples
- `git`
- Docker is useful for some workflows, but not required for every example

### Python versions

- Most Python examples in `examples/` require **Python >= 3.12**
- `examples/osworld-ags` currently requires **Python 3.10**

`uv` can manage both interpreters.

## Common environment variables

### AGS / E2B-compatible runtime

```bash
export E2B_API_KEY="your_ags_api_key"
export E2B_DOMAIN="ap-guangzhou.tencentags.com"
```

### Tencent Cloud control-plane examples

Some Go examples use Tencent Cloud API credentials:

```bash
export TENCENTCLOUD_SECRET_ID="your_secret_id"
export TENCENTCLOUD_SECRET_KEY="your_secret_key"
export TENCENTCLOUD_REGION="ap-guangzhou"
```


## Quick start

### 1. Browse available examples

```bash
make examples-list
```

### 2. Run a specific example

Most examples provide a local `make run` target:

```bash
make example-setup EXAMPLE=mini-rl
make example-run EXAMPLE=mini-rl
```

You can also enter an example directory directly and run its local `make setup` / `make run` targets.

## Example overview

| Example | Stack | Notes |
|---|---|---|
| `browser-agent` | Python + browser sandbox + LLM | Browser automation agent |
| `custom-image-go-sdk` | Go | Custom-image / custom-tool startup |
| `data-analysis` | Python + code sandbox | Multi-context data workflow |
| `html-processing` | Python + browser/code sandboxes | Dual-sandbox HTML pipeline |
| `hybrid-cookbook` | Go | Minimal control-plane + data-plane flow |
| `mini-rl` | Python + code sandbox | Minimal RL tool-calling example |
| `mini-swe-agent` | Python + SWE sandbox + LLM | SWE-bench evaluation with AGS SWE sandbox |
| `mobile-use` | Python + mobile sandbox + Appium | Android automation |
| `openclaw-cookbook` | Node.js + custom image + COS | Run OpenClaw in AGS with official image |
| `osworld-ags` | Python 3.10 + OSWorld overlay | Heavy setup; requires an OSWorld-capable tool |
| `shop-assistant` | Python + browser sandbox | E-commerce search / add-to-cart demo |

See `examples/README.md` for per-example details and a starter/advanced/heavy picker.

## Important DX notes

- Prefer `uv sync` + `uv run ...` for Python examples
- Do not assume root README defaults apply to every example; always check each example's README and `.env.example`
- AGS domains are region-specific; set `E2B_DOMAIN` explicitly for the region you want to use
- Some examples require pre-provisioned tools/templates in your AGS account

## Troubleshooting

Below are common issues across all cookbook examples and how to resolve them. For tool-specific troubleshooting, see:
- [AGS CLI Troubleshooting](https://github.com/TencentCloudAgentRuntime/ags-cli/blob/main/docs/troubleshooting.md)
- [AGS Go SDK Troubleshooting](https://github.com/TencentCloudAgentRuntime/ags-go-sdk/blob/main/docs/troubleshooting.md)

### Authentication Failures

**Symptom:** `E2B_API_KEY is not set` or sandbox creation fails with 401/403 errors.

**Fix:**
1. Copy the example environment file and fill in your credentials:
   ```bash
   cp .env.example .env
   # Edit .env with your actual keys
   ```
2. Ensure the correct environment variables are exported:
   ```bash
   # For E2B-compatible examples (most Python examples)
   export E2B_API_KEY="your_ags_api_key"
   export E2B_DOMAIN="ap-guangzhou.tencentags.com"

   # For Tencent Cloud examples (Go examples)
   export TENCENTCLOUD_SECRET_ID="your_secret_id"
   export TENCENTCLOUD_SECRET_KEY="your_secret_key"
   export TENCENTCLOUD_REGION="ap-guangzhou"
   ```
3. Some examples load `.env` files automatically; verify the file is in the example directory.

### Network / Region Issues

**Symptom:** `ConnectionError`, `TimeoutError`, or `dial tcp: i/o timeout` when creating sandboxes.

**Fix:**
1. Verify connectivity to the AGS endpoint:
   ```bash
   curl -I https://api.ap-guangzhou.tencentags.com
   ```
2. Confirm `E2B_DOMAIN` uses the correct region (e.g., `ap-guangzhou.tencentags.com`).
3. If behind a corporate proxy, set `HTTP_PROXY` / `HTTPS_PROXY`.
4. AGS domains are region-specific — resources created in one region are not visible in another.

### Sandbox / Tool Not Found

**Symptom:** `tool not found`, `sandbox not found`, or `Failed to check image availability`.

**Fix:**
1. Ensure the tool/template referenced in the example exists in your AGS account and region.
2. Some examples require pre-provisioned tools — check the example README for prerequisites.
3. For custom-image examples, verify the image is available as a system image or has been uploaded.

### Sandbox Expired or Timed Out

**Symptom:** `404 Not Found`, `EnvironmentExpiredError`, or operations fail after the sandbox was previously working.

**Fix:**
1. Sandboxes have a limited lifetime. Increase the timeout in the example config if supported.
2. Create a new sandbox instance and re-run the example.

### Command Timeout

**Symptom:** `CommandTimeoutError` — a command exceeded its configured timeout.

**Fix:**
1. Increase the command timeout in the example configuration (check the example README for details).
2. Ensure the sandbox has sufficient resources for the workload.

### LLM Backend Issues (Agent Examples)

**Symptom:** LLM API call times out or returns errors in agent-based examples (`browser-agent`, `mini-swe-agent`, `shop-assistant`).

**Fix:**
1. Verify your LLM API credentials (e.g., `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`) are set correctly.
2. Reduce conversation context length if hitting token limits.
3. Check the LLM provider's status page for outages.

### Python Dependency Issues

**Symptom:** `ModuleNotFoundError` or `uv` sync failures.

**Fix:**
1. Always use `uv` to manage dependencies:
   ```bash
   make setup    # or: uv sync
   make run      # or: uv run python main.py
   ```
2. Ensure you have the correct Python version (most examples need >= 3.12; `osworld-ags` needs 3.10).
3. If `uv` is not installed: `curl -LsSf https://astral.sh/uv/install.sh | sh`

### Still Stuck?

- Check the specific example's README for "Common failure hints" or "Common Failure Modes" sections.
- Open an issue on [GitHub](https://github.com/TencentCloudAgentRuntime/ags-cookbook/issues) with the full error output and example name.

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md).

## License

Apache 2.0. See [LICENSE-Agent Sandbox Cookbook.txt](./LICENSE-Agent%20Sandbox%20Cookbook.txt).
