# DeepSeek Harness Deployment Cookbook

This directory shows how to deploy [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) to AGR.

Choose one topology:

- [all-in-one](./all-in-one/README.md) runs DSH Web, Agent Host, and command execution in one persistent Sandbox Instance.
- [brain-hands](./brain-hands/README.md) runs DSH Web and inference on stateless Brain replicas with shared state in MySQL. The first Chat in a Workspace creates separate Hands for its selected OS, and AGS retains the complete Hands filesystem.

The examples use these published images:

- all-in-one: `ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:v0.1.1-rc.2-ags.4`
- Brain: `ccr.ccs.tencentyun.com/ags.dev/deepseek-harness-brain:v0.1.1-rc.2-ags.4`
- Ubuntu Hands: `ccr.ccs.tencentyun.com/ags.dev/deepseek-harness-hands-ubuntu:v0.6.13`
- Alpine Hands: `ccr.ccs.tencentyun.com/ags.dev/deepseek-harness-hands-alpine:v0.6.13`

Both topologies use `ap-shanghai` and an OpenAI-compatible model endpoint. Each directory contains its own Dockerfiles, deployment steps, and optional build instructions.
