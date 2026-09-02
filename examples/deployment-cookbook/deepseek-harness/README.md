# DeepSeek Harness Deployment Cookbook

This directory shows how to deploy [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) to AGR as a persistent agent workspace.

Choose one topology:

- [all-in-one](./all-in-one/README.md) runs the Web UI, Agent Host, and command-execution environment in one persistent Sandbox Instance.
- [brain-hands](./brain-hands/README.md) runs DSH Web and the API on multiple stateless Brain replicas with MySQL-backed sessions, plus separate E2B/envd Hands instances whose complete filesystems are retained by AGS.

The examples use these published images:

- all-in-one: `ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:v0.1.1-rc.2-ags.4`
- Brain: `ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:brain-v0.1.0-rc.8-ags.6`
- Hands: `ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:hands-envd-v0.6.13-ags.1`

Both topologies use:

- region: `ap-shanghai`
- model service: the OpenAI-compatible Tencent Cloud TokenHub API

Each topology contains its own Dockerfiles and build notes; deployment guides use the published images by default.
