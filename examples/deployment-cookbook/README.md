# Deployment Cookbook

This directory introduces `agr` Deployment management through independently runnable examples. The examples use httpbin as the workload: first complete the shortest deployment path, then observe scaling, idle lifecycle, and session affinity separately.

## Prerequisites

- Install `agr` and run `agr status` to confirm that credentials and the region are configured.
- Install Jupyter Notebook. The notebooks use IPython `%env` and `!` to run commands directly.
- Ensure that `ccr.ccs.tencentyun.com/ags.dev/go-httpbin:v2.25.0` is reachable.
- Prepare a CAM role ARN that allows AGR to pull this CCR image, and set it as `AGR_ROLE_ARN` in the notebook.
- Use an account that can create and delete Sandbox Tools and Deployments and acquire Deployment tokens.

Each notebook creates its own resources. Resource IDs are not extracted automatically: copy each ID from the command output and set the environment variable requested by the next step. Always run the cleanup section after completing or interrupting an example so that resources are not left behind.

## Examples

| Example | Description |
| --- | --- |
| [httpbin/simple](./httpbin/simple/httpbin-simple_en.ipynb) | Create a Tool and Deployment, access httpbin through a local proxy and the production domain, and clean up. |
| [httpbin/scaling](./httpbin/scaling/httpbin-scaling_en.ipynb) | Move from on-demand startup to warm capacity and understand full-replacement scaling updates. |
| [httpbin/lifecycle](./httpbin/lifecycle/httpbin-lifecycle_en.ipynb) | Observe the `STOP` and `PAUSE` idle actions in sequence. |
| [httpbin/affinity](./httpbin/affinity/httpbin-affinity_en.ipynb) | Compare `BEST_EFFORT`, `STRICT`, and `EXCLUSIVE` session affinity. |

Chinese notebooks omit the `_en` suffix. See [httpbin/dockerfiles](./httpbin/dockerfiles/README.md) for the source, build, and publication process of the httpbin image.
