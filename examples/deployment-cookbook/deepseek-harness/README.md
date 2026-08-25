# DeepSeek Harness Deployment Cookbook

This directory shows how to deploy [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness/tree/dsh-v0.1.1-rc.2) to AGR as a persistent agent workspace.

The current [all-in-one](./all-in-one/README.md) example runs the Web UI, Agent Host, and command-execution environment in one Sandbox Instance. It is a direct way to validate the complete workflow and fits workloads that do not need independent scaling for reasoning and execution.

The example pins:

- DeepSeek Harness tag: `dsh-v0.1.1-rc.2`
- AGR image: `ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:v0.1.1-rc.2-ags.3`
- region: `ap-shanghai`
- model service: the OpenAI-compatible Tencent Cloud TokenHub API

The Dockerfile, compatibility patch, and build instructions are under [all-in-one/dockerfiles](./all-in-one/dockerfiles/README.md).
