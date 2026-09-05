# Examples

This directory contains runnable AGS examples. Each example keeps its own README and Makefile so users can enter a single directory and follow one local path.

## How to choose an example

### Starter

- `mini-rl` — minimal code-sandbox tool-calling flow
- `hybrid-cookbook` — minimal Go control-plane + data-plane flow
- `html-processing` — dual-sandbox collaboration with visible output artifacts

### Advanced

- `browser-agent` — browser automation agent with an OpenAI-compatible LLM backend
- `local-service-tunnel` — custom sandbox workload accessing a user-managed local or private service through a WebSocket tunnel
- `data-analysis` — multi-context data workflow with multiple generated artifacts
- [`deployment-cookbook`](./deployment-cookbook/README.md) — Deployment management with `agr`, from httpbin basics and a native MCP server to a persistent agent workspace
- `dind` — self-starting Docker-in-Docker Tool that runs a real Terminal-Bench Compose task with Harbor Oracle
- `envd-oci-env` — preserve OCI image environment variables when envd is PID 1
- `harness-nix-volume` — package a self-contained Harness runtime with Nix and mount it into a custom image
- `mini-swe-agent` — SWE-bench evaluation with AGS SWE sandbox and SWE-ReX runtime
- `mobile-use` — Android / Appium automation in AGS
- `openclaw-cookbook` — run OpenClaw in AGS with official image, local management UI and COS persistence
- `shop-assistant` — browser shopping-flow automation with optional cookies
- `custom-image-go-sdk` — custom-image startup and data-plane execution in Go

### Heavy / external-dependent

- `osworld-ags` — overlay for upstream OSWorld; requires a separate checkout, Python 3.12.12, and an OSWorld-capable AGS tool
- `waa-ags` — overlay for upstream Windows Agent Arena; requires a separate checkout, a WAA-compatible AGS sandbox template, and an OpenAI-compatible model endpoint

## Shared local contract

Where practical, each example provides:

- `make setup` for dependency bootstrap
- `make run` for the primary local execution path
- `README.md` for prerequisites, environment variables, run steps, and expected results

Some heavier or externally overlaid examples are exceptions, but they should still document a single primary local path.

## Example list

| Example | Classification | Primary stack | Primary command | Notes |
|---|---|---|---|---|
| `browser-agent` | advanced | Python + browser sandbox + LLM | `make run` | Requires OpenAI-compatible LLM backend env vars |
| `local-service-tunnel` | advanced | Go/Python + custom sandbox + image volume | `make run` | Keeps service credentials local and forwards sandbox workload traffic through a user-managed WebSocket tunnel |
| `custom-image-go-sdk` | advanced | Go | `make run` | Requires custom tool/image setup in AGS account |
| `data-analysis` | advanced | Python + code sandbox | `make run` | Generates multiple output files |
| [`deployment-cookbook`](./deployment-cookbook/README.md) | advanced | agr CLI + Markdown + Python | Follow a scenario README | Covers deployment, scaling, lifecycle, affinity, a native MCP server, and a persistent agent workspace |
| `dind` | advanced | Docker + Compose + envd + Harbor + agr | `make run` | Creates a DinD Tool and runs a real Terminal-Bench Compose task with Harbor Oracle |
| `envd-oci-env` | advanced | Bash + Docker + agr | `make run` | Reproduces and validates envd OCI environment inheritance |
| `harness-nix-volume` | advanced | Nix + custom image + image volume | `make build-images` then `make run` | Mount self-contained Harness dependencies into a main image |
| `html-processing` | starter | Python + browser/code sandboxes | `make run` | Good visual intro to dual-sandbox flow |
| `hybrid-cookbook` | starter | Go | `make run` | Minimal Go integration path |
| `mini-rl` | starter | Python + code sandbox | `make run` | Smallest Python example |
| `mini-swe-agent` | advanced | Python + SWE sandbox + LLM | `make run` | SWE-bench evaluation; requires mini-swe-agent and SWE-ReX repos |
| `mobile-use` | advanced | Python + mobile sandbox + Appium | `make run` | Heavy runtime dependencies and long-running device flow |
| `openclaw-cookbook` | advanced | Node.js + custom image + COS | `make run` | Run OpenClaw in AGS with official image; includes local management UI |
| `osworld-ags` | heavy | Python 3.12.12 + OSWorld overlay | `make setup` then `make run` | External checkout and template/tool requirements |
| `shop-assistant` | advanced | Python + browser sandbox | `make run` | Cookie-free guest mode now supported |
| `waa-ags` | heavy | Python + Windows sandbox + LLM | `make setup` then `make run` | External WAA checkout, WAA-compatible AGS sandbox template, and OpenAI-compatible model endpoint required |

From the repository root, you can use:

```bash
make examples-list
make example-setup EXAMPLE=<name>
make example-run EXAMPLE=<name>
```
