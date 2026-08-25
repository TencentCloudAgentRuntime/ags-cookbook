# DeepSeek Harness Deployment Cookbook

本目录演示如何把 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness/tree/dsh-v0.1.1-rc.2) 作为长驻 Agent 工作区部署到 AGR。

当前提供 [all-in-one](./all-in-one/README_zh.md) 示例：Web UI、Agent Host 和命令执行环境运行在同一个 Sandbox Instance 中。它适合先验证完整链路，也适合不需要为 Agent 的思考与执行分别扩缩容的场景。

示例固定使用：

- DeepSeek Harness tag：`dsh-v0.1.1-rc.2`
- AGR 镜像：`ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:v0.1.1-rc.2-ags.3`
- region：`ap-shanghai`
- 模型服务：腾讯云 TokenHub 的 OpenAI 兼容接口

镜像的 Dockerfile、兼容性 patch 和构建说明位于 [all-in-one/dockerfiles](./all-in-one/dockerfiles/README_zh.md)。
