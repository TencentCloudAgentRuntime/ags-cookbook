# Examples

This directory contains runnable AGS examples. Each example keeps its own README and Makefile so users can enter a single directory and follow one local path.

## How to choose an example

### Starter

- `mini-rl` — minimal code-sandbox tool-calling flow
- `hybrid-cookbook` — minimal Go control-plane + data-plane flow
- `html-processing` — dual-sandbox collaboration with visible output artifacts

### Advanced

- `browser-agent` — browser automation agent with an OpenAI-compatible LLM backend
- `data-analysis` — multi-context data workflow with multiple generated artifacts
- `mobile-use` — Android / Appium automation in AGS
- `openclaw-cookbook` — run OpenClaw in AGS with official image, local management UI and COS persistence
- `shop-assistant` — browser shopping-flow automation with optional cookies
- `custom-image-go-sdk` — custom-image startup and data-plane execution in Go

### Heavy / external-dependent

- `osworld-ags` — overlay for upstream OSWorld; requires a separate checkout, Python 3.10, and an OSWorld-capable AGS tool

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
| `custom-image-go-sdk` | advanced | Go | `make run` | Requires custom tool/image setup in AGS account |
| `data-analysis` | advanced | Python + code sandbox | `make run` | Generates multiple output files |
| `html-processing` | starter | Python + browser/code sandboxes | `make run` | Good visual intro to dual-sandbox flow |
| `hybrid-cookbook` | starter | Go | `make run` | Minimal Go integration path |
| `mini-rl` | starter | Python + code sandbox | `make run` | Smallest Python example |
| `mobile-use` | advanced | Python + mobile sandbox + Appium | `make run` | Heavy runtime dependencies and long-running device flow |
| `openclaw-cookbook` | advanced | Node.js + custom image + COS | `make run` | Run OpenClaw in AGS with official image; includes local management UI |
| `osworld-ags` | heavy | Python 3.10 + OSWorld overlay | `make setup` then `make run` | External checkout and template/tool requirements |
| `shop-assistant` | advanced | Python + browser sandbox | `make run` | Cookie-free guest mode now supported |

From the repository root, you can use:

```bash
make examples-list
make example-setup EXAMPLE=<name>
make example-run EXAMPLE=<name>
```
