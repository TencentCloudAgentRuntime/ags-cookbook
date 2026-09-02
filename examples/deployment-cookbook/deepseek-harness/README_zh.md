# DeepSeek Harness Deployment Cookbook

本目录演示如何把 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) 部署到 AGR。

请选择一种拓扑：

- [all-in-one](./all-in-one/README_zh.md)：DSH Web、Agent Host 和命令执行环境运行在同一个持久 Sandbox Instance 中。
- [brain-hands](./brain-hands/README_zh.md)：DSH Web 与推理运行在无状态 Brain 副本中，MySQL 保存共享状态；Workspace 在第一次 Chat 时按所选 OS 创建独立 Hands，AGS 保留 Hands 的完整文件系统。

示例使用下列已发布镜像：

- all-in-one：`ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:v0.1.1-rc.2-ags.4`
- Brain：`ccr.ccs.tencentyun.com/ags.dev/deepseek-harness-brain:v0.1.1-rc.2-ags.4`
- Ubuntu Hands：`ccr.ccs.tencentyun.com/ags.dev/deepseek-harness-hands-ubuntu:v0.6.13`
- Alpine Hands：`ccr.ccs.tencentyun.com/ags.dev/deepseek-harness-hands-alpine:v0.6.13`

两个拓扑均使用 `ap-shanghai` 和 OpenAI 兼容模型接口。每个目录都包含自己的 Dockerfile、部署步骤与可选构建说明。
