# Deployment Cookbook

This directory introduces `agr` Deployment management through independently runnable examples. The httpbin examples teach platform behavior from the shortest deployment path; the DeepSeek Harness example then demonstrates a persistent agent workspace.

## Prerequisites

- Install `agr` **v0.6.6 or later**. Run `agr version` to check the installed version, then run `agr status` to confirm that credentials and the region are configured.
- Prepare a CAM role ARN that allows AGR to pull the example CCR images.
- Use an account that can create and delete Sandbox Tools and Deployments and acquire Deployment tokens.

All examples use standard Markdown and run commands directly in a terminal. The DeepSeek Harness example additionally requires a Tencent Cloud TokenHub API key.

Each example creates its own resources. Resource IDs are not extracted automatically: copy each ID from the command output and set the environment variable requested by the next step. Always run the cleanup section after completing or interrupting an example so that resources are not left behind.

Run `make run` in this directory to list the available scenarios, then follow the selected scenario README. The target only prints navigation help and does not create cloud resources.

## Examples

| Example | Description |
| --- | --- |
| [httpbin/simple](./httpbin/simple/README.md) | Create a Tool and Deployment, access httpbin through a local proxy and the production domain, and clean up. |
| [httpbin/scaling](./httpbin/scaling/README.md) | Move from on-demand startup to warm capacity and understand full-replacement scaling updates. |
| [httpbin/lifecycle](./httpbin/lifecycle/README.md) | Observe the `STOP` and `PAUSE` idle actions in sequence. |
| [httpbin/affinity](./httpbin/affinity/README.md) | Compare `BEST_EFFORT`, `STRICT`, and `EXCLUSIVE` session affinity. |
| [session](./session/README.md) | Associate separate Brain and Hands Sessions with their Deployments, restore Hands routing context, and demonstrate backend reuse. |
| [deepseek-harness/all-in-one](./deepseek-harness/all-in-one/README.md) | Deploy all-in-one DeepSeek Harness, complete a coding task through TokenHub, and verify exclusive-session pause and resume. |

Each scenario directory uses `README.md` for English and `README_zh.md` for Chinese. See [httpbin/dockerfiles](./httpbin/dockerfiles/README.md) for the source, build, and publication process of the httpbin image.
