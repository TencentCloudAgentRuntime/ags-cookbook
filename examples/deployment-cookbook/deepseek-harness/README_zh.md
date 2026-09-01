# DeepSeek Harness Deployment Cookbook

本目录演示如何把 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness/tree/dsh-v0.1.1-rc.2) 作为长驻 Agent 工作区部署到 AGR。

请选择一种拓扑：

- [all-in-one](./all-in-one/README_zh.md)：Web UI、Agent Host 和命令执行环境运行在同一个持久 Sandbox Instance 中。
- [brain-hands](./brain-hands/README_zh.md)：多个无状态 Brain 副本使用 MySQL 保存 DSH session，并通过 E2B/envd 访问由 AGS 保留 workspace 的独立 Hands。

all-in-one 示例固定使用：

- DeepSeek Harness tag：`dsh-v0.1.1-rc.2`
- AGR 镜像：`ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:v0.1.1-rc.2-ags.4`
- region：`ap-shanghai`
- 模型服务：腾讯云 TokenHub 的 OpenAI 兼容接口

每种拓扑都在自己的目录中提供 Dockerfile 与构建说明。
