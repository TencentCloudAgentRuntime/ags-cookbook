# DeepSeek Harness Deployment Cookbook

本目录演示如何把 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) 作为长驻 Agent 工作区部署到 AGR。

请选择一种拓扑：

- [all-in-one](./all-in-one/README_zh.md)：Web UI、Agent Host 和命令执行环境运行在同一个持久 Sandbox Instance 中。
- [brain-hands](./brain-hands/README_zh.md)：DSH Web 与 API 运行在多个使用 MySQL 保存 session 的无状态 Brain 副本上，并通过 E2B/envd 访问由 AGS 保留完整文件系统的独立 Hands 实例。

示例使用下列已发布镜像：

- all-in-one：`ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:v0.1.1-rc.2-ags.4`
- Brain：`ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:brain-v0.1.0-rc.8-ags.6`
- Hands：`ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:hands-envd-v0.6.13-ags.1`

两种拓扑均使用：

- region：`ap-shanghai`
- 模型服务：腾讯云 TokenHub 的 OpenAI 兼容接口

每种拓扑都在自己的目录中提供 Dockerfile 与构建说明；部署教程默认使用已发布镜像。
