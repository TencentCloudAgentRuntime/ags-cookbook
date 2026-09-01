# DeepSeek Harness Deployment Cookbook

This directory shows how to deploy [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness/tree/dsh-v0.1.1-rc.2) to AGR as a persistent agent workspace.

Choose one topology:

- [all-in-one](./all-in-one/README.md) runs the Web UI, Agent Host, and command-execution environment in one persistent Sandbox Instance.
- [brain-hands](./brain-hands/README.md) runs multiple stateless Brain replicas with MySQL-backed DSH sessions and separate E2B/envd Hands workspaces retained by AGS.

The all-in-one example pins:

- DeepSeek Harness tag: `dsh-v0.1.1-rc.2`
- AGR image: `ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:v0.1.1-rc.2-ags.4`
- region: `ap-shanghai`
- model service: the OpenAI-compatible Tencent Cloud TokenHub API

Each topology contains its own Dockerfiles and build notes.
