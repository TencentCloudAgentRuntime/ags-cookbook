# Deployment Cookbook

This directory introduces `agr` Deployment management through independently runnable examples. The httpbin examples teach platform behavior from the shortest deployment path; the DeepSeek Harness example then demonstrates a persistent agent workspace.

## Prerequisites

- Install `agr` and run `agr status` to confirm that credentials and the region are configured.
- Prepare a CAM role ARN that allows AGR to pull the example CCR images.
- Use an account that can create and delete Sandbox Tools and Deployments and acquire Deployment tokens.

The httpbin examples also require Jupyter Notebook and run commands directly through IPython `%env` and `!`. The DeepSeek Harness example uses standard Markdown and terminal commands and additionally requires a Tencent Cloud TokenHub API key.

Each example creates its own resources. Resource IDs are not extracted automatically: copy each ID from the command output and set the environment variable requested by the next step. Always run the cleanup section after completing or interrupting an example so that resources are not left behind.

## Examples

| Example | Description |
| --- | --- |
| [httpbin/simple](./httpbin/simple/httpbin-simple_en.ipynb) | Create a Tool and Deployment, access httpbin through a local proxy and the production domain, and clean up. |
| [httpbin/scaling](./httpbin/scaling/httpbin-scaling_en.ipynb) | Move from on-demand startup to warm capacity and understand full-replacement scaling updates. |
| [httpbin/lifecycle](./httpbin/lifecycle/httpbin-lifecycle_en.ipynb) | Observe the `STOP` and `PAUSE` idle actions in sequence. |
| [httpbin/affinity](./httpbin/affinity/httpbin-affinity_en.ipynb) | Compare `BEST_EFFORT`, `STRICT`, and `EXCLUSIVE` session affinity. |
| [deepseek-harness/all-in-one](./deepseek-harness/all-in-one/README.md) | Deploy all-in-one DeepSeek Harness, complete a coding task through TokenHub, and verify exclusive-session pause and resume. |

Chinese notebooks omit the `_en` suffix. See [httpbin/dockerfiles](./httpbin/dockerfiles/README.md) for the source, build, and publication process of the httpbin image.
