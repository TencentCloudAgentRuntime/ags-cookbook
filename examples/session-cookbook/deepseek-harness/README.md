# Persist DeepSeek Harness conversations with Agent Runtime Session

[中文](./README_zh.md)

DeepSeek Harness (DSH) stores conversations in JSONL files on local disk, so deleting the container also deletes the conversation history. This example uses a persistence plugin to write DSH conversations to Agent Runtime Session in the cloud: after you delete the container and start a fresh one, you can still load the original conversation and keep talking.

It covers conversation persistence only. To also keep workspace files and route later requests back to the same workspace, see [Session and workspace association](../../deployment-cookbook/brain-hands-session/README.md).

## Choose a DSH version

DSH has changed its conversation persistence interface between releases, and some versions are not compatible with each other, so the plugin is provided per DSH version. Each version directory is a complete integration example with its own guide, plugin, image files, and verification script; go to that directory and follow its guide.

| DSH version | Notes | Pre-built image | Guide |
| --- | --- | --- | --- |
| **0.2.1-rc.2** (recommended) | Official DSH with no patches; runs locally or in a container, but deploying to AGS needs adaptation first | `ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:v0.2.1-rc.2-session-persistence.2` | [dsh-0.2.1-rc.2](./dsh-0.2.1-rc.2/README.md) |
| 0.1.1-rc.2 | Official DSH plus an AGS adaptation patch; deploys to AGS directly | `ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:v0.1.1-rc.2-ags.4-session-persistence.4` | [dsh-0.1.1-rc.2](./dsh-0.1.1-rc.2/README.md) |

0.2.1-rc.2 uses the official DSH with no patches, so its startup behaviour matches the official release and its restrictions (for example, it rejects `--host 0.0.0.0`) remain; it cannot be deployed to AGS directly. To run on AGS, either adapt it yourself as described in [Deploying to AGS](./dsh-0.2.1-rc.2/README.md#deploying-to-ags), or use 0.1.1-rc.2, which includes the adaptation patch.

Choose in this order:

1. **You already run DSH**: pick the directory matching your DSH version. Run `npm ls -g @deepseek-ai/dsh` where DSH is installed to see it. If your version is not in the table, the plugin cannot be used as is.
2. **You need to run in an AGS sandbox or Deployment**: only 0.1.1-rc.2 currently offers a ready-made deployment. Deploying 0.2.1-rc.2 to AGS needs extra adaptation; see [Deploying to AGS](./dsh-0.2.1-rc.2/README.md#deploying-to-ags) in its guide.
3. **Otherwise**: pick 0.2.1-rc.2.

## Differences between versions

| Aspect | 0.2.1-rc.2 | 0.1.1-rc.2 |
| --- | --- | --- |
| DSH source | The official `@deepseek-ai/dsh@0.2.1-rc.2` from npm | Built from source with an AGS adaptation patch |
| Deploying to AGS | Needs extra adaptation | Supported |
| Web UI sign-in | Through the URL with a token from the startup log | No sign-in |
| Model configuration | In the Cordis patch | `settings.yaml` generated at startup |

Conversations written by the two versions are not visible to each other: 0.2.1-rc.2 does not show conversations written by 0.1.1-rc.2 and does not migrate them.

## Version requirements

The plugin depends on DSH's internal modules, so DSH and those modules must be exactly the versions the plugin is built for. Pin every version as described in "Versions and dependencies" of the guide you choose, and do not install "latest":

- `npm install -g @deepseek-ai/dsh` without a version installs whatever is newest on npm, which may not be the version the plugin targets.
- On a mismatch, DSH fails at startup, for example with `does not provide an export named 'PersistenceCoordinator'`.
