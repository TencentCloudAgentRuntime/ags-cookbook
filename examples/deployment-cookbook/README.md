# Deployment Cookbook

This directory introduces `agr` Deployment management through independently runnable examples. The httpbin examples teach platform behavior from the shortest deployment path, the MCP example runs a native Streamable HTTP client flow, and the DeepSeek Harness example demonstrates a persistent agent workspace.

## Prerequisites

- Install `agr` **v0.6.6 or later**. For first-time setup, follow the [official AGR CLI credential guide](https://github.com/TencentCloudAgentRuntime/ags-cli#initialize-cli-credentials), then run `agr status` and `agr doctor`.
- Follow the official [custom Sandbox role and permission guide](https://cloud.tencent.com/document/product/1814/129691) to create an Agent Runtime CAM role, and grant your CLI identity `cam:PassRole` for that role. The published example images are public; repository-specific pull permission is needed only when you replace them with images from your own private CCR or TCR repository.
- Use a CLI identity that can create and delete Sandbox Tools and Deployments, list and delete Instances, and acquire Deployment tokens.

All examples use standard Markdown and run commands directly in a terminal. The DeepSeek Harness example additionally requires a Tencent Cloud TokenHub API key.

Each example creates its own resources. Copy each ID from the command output into the environment variable requested by the next step, and run the cleanup section when finished.

Run `make run` in this directory to list the available scenarios, then follow the selected scenario README. The target only prints navigation help and does not create cloud resources.

## Examples

| Example | Description |
| --- | --- |
| [httpbin/simple](./httpbin/simple/README.md) | Create a Tool and Deployment, access httpbin through a local proxy and the production domain, and clean up. |
| [httpbin/scaling](./httpbin/scaling/README.md) | Move from on-demand startup to warm capacity and understand full-replacement scaling updates. |
| [httpbin/lifecycle](./httpbin/lifecycle/README.md) | Observe the `STOP` and `PAUSE` idle actions in sequence. |
| [httpbin/affinity](./httpbin/affinity/README.md) | Compare shared `BEST_EFFORT` and dedicated `EXCLUSIVE` session affinity. |
| [mcp-server/simple](./mcp-server/simple/README.md) | Deploy the official Everything MCP Server, use the native Python SDK, and observe `0 → N → 0` plus a fresh session after scale-to-zero. |
| [deepseek-harness/all-in-one](./deepseek-harness/all-in-one/README.md) | Deploy all-in-one DeepSeek Harness, complete a coding task through TokenHub, and verify exclusive-session pause and resume. |
| [deepseek-harness/brain-hands](./deepseek-harness/brain-hands/README.md) | Run multi-replica stateless DSH Brain against MySQL and persistent E2B/envd Hands workspaces. |
| [session](./session/README.md) | Integrate DSH Brain and Hands with one Agent Runtime cloud Session, validating multi-turn conversations, tool calls, workspace continuity, and isolation. |

Each scenario directory uses `README.md` for English and `README_zh.md` for Chinese. Deployment guides use published images by default and link to the matching image-source and build notes when those are needed.
