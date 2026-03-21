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
| `mobile-use` | Python + mobile sandbox + Appium | Android automation |
| `osworld-ags` | Python 3.10 + OSWorld overlay | Heavy setup; requires an OSWorld-capable tool |
| `shop-assistant` | Python + browser sandbox | E-commerce search / add-to-cart demo |

See `examples/README.md` for per-example details and a starter/advanced/heavy picker.

## Important DX notes

- Prefer `uv sync` + `uv run ...` for Python examples
- Do not assume root README defaults apply to every example; always check each example's README and `.env.example`
- AGS domains are region-specific; set `E2B_DOMAIN` explicitly for the region you want to use
- Some examples require pre-provisioned tools/templates in your AGS account

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md).

## License

Apache 2.0. See [LICENSE-Agent Sandbox Cookbook.txt](./LICENSE-Agent%20Sandbox%20Cookbook.txt).
