# Agent Sandbox Cookbook

Examples, tutorials, and utilities for building on Tencent Cloud Agent Sandbox / AGS.

## What this repo contains

- **Skills**: reference Agent Skill example for AGS; see [`skills/README.md`](./skills/README.md)
- **Tutorials**: SDK and notebook-based onboarding
- **Examples**: runnable browser, code, mobile, Go, and OSWorld demos
- **Benchmarks**: k6 stress scripts
- **Utils**: debugging helpers and validated runtime source components such as envd

## Repository requirements

### Local tools

- `uv` for Python examples
- `python3` for local scripts
- `go` for Go examples
- `git`
- Docker is useful for some workflows, but not required for every example

### Python versions

- Most Python examples in `examples/` require **Python >= 3.12**
- `examples/osworld-ags` uses **Python 3.12.12**
- `uv` manages the required interpreter for each example.

### agr CLI

The `ags` reference Skill example uses the `agr` CLI:

```bash
# One-line install (macOS / Linux)
curl -fsSL https://github.com/TencentCloudAgentRuntime/ags-cli/releases/latest/download/install.sh | sh

# Or via go install
go install github.com/TencentCloudAgentRuntime/ags-cli/cmd/agr@latest

agr version -o json
```

For first-time credential setup, follow the
[official AGR CLI configuration guide](https://github.com/TencentCloudAgentRuntime/ags-cli#initialize-cli-credentials),
then run `agr status` and `agr doctor` before starting an example.

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
| [`deployment-cookbook`](./examples/deployment-cookbook/README.md) | agr CLI + Markdown + Python | Deployment, scaling, lifecycle, affinity, native MCP server, and persistent agent workspace scenarios |
| `envd-oci-env` | Bash + Docker + agr | Preserve OCI image environment variables when envd is PID 1 |
| `harness-nix-volume` | Nix + custom image + image volume | Self-contained Harness dependency mount |
| `html-processing` | Python + browser/code sandboxes | Dual-sandbox HTML pipeline |
| `hybrid-cookbook` | Go | Minimal control-plane + data-plane flow |
| `mini-rl` | Python + code sandbox | Minimal RL tool-calling example |
| `mini-swe-agent` | Python + SWE sandbox + LLM | SWE-bench evaluation with AGS SWE sandbox |
| `mobile-use` | Python + mobile sandbox + Appium | Android automation |
| `openclaw-cookbook` | Node.js + custom image + COS | Run OpenClaw in AGS with official image |
| `osworld-ags` | Python 3.12.12 + OSWorld overlay | Heavy setup; requires an OSWorld-capable tool |
| `shop-assistant` | Python + browser sandbox | E-commerce search / add-to-cart demo |
| `waa-ags` | Python + Windows sandbox + LLM | Run Windows Agent Arena on AGS via a small overlay |

See [examples/README.md](./examples/README.md) for per-example details and a starter/advanced/heavy picker.

## Skills overview

The **`ags`** skill is a reference Agent Skill example for AGS. It demonstrates CLI-first AGS workflows with `agr`.

| Skill | Path | What it covers |
|---|---|---|
| `ags` | [`skills/ags/SKILL.md`](./skills/ags/SKILL.md) | CLI-first AGS workflows with `agr`: tools, instances, code/shell execution, files, browser/mobile, storage mounts, API keys, debug instances, tool fork, and raw API fallback. |

Add from GitHub with the `skills` CLI:

```bash
npx skills add TencentCloudAgentRuntime/ags-cookbook --skill ags
```

See [`skills/README.md`](./skills/README.md) for the skill index and the progressive disclosure structure.

## Important DX notes

- Prefer `uv sync` + `uv run ...` for Python examples
- Do not assume root README defaults apply to every example; always check each example's README and `.env.example`
- AGS domains are region-specific; set `E2B_DOMAIN` explicitly for the region you want to use
- Some examples require pre-provisioned tools/templates in your AGS account

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md).

## License

Apache 2.0. See [LICENSE-Agent Sandbox Cookbook.txt](./LICENSE-Agent%20Sandbox%20Cookbook.txt).
