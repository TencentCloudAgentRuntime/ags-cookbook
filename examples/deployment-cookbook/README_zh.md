# Deployment Cookbook

本目录通过可独立运行的示例介绍如何使用 `agr` 管理 Deployment。httpbin 示例从最短部署链路讲解平台能力；MCP 示例运行原生 Streamable HTTP 客户端链路；DeepSeek Harness 示例进一步演示长驻 Agent 工作区。

## 前置条件

- 已安装 **v0.6.6 或更高版本**的 `agr`。首次使用时，按[AGR CLI 官方 GitHub 凭证配置说明](https://github.com/TencentCloudAgentRuntime/ags-cli/blob/main/README-zh.md#初始化-cli-凭证)完成初始化，再运行 `agr status` 和 `agr doctor`。
- 按官方[自定义沙箱角色与权限指南](https://cloud.tencent.com/document/product/1814/129691)创建 Agent Runtime CAM 角色，并向 CLI 使用的身份授予该角色的 `cam:PassRole` 权限。已发布的示例镜像是公共镜像；只有改用自己私有 CCR 或 TCR 仓库中的镜像时，才需要额外授予仓库拉取权限。
- CLI 使用的身份可以创建和删除 Sandbox Tool 与 Deployment、查询和删除 Instance，并能获取 Deployment Token。

全部示例都使用标准 Markdown，并直接在终端执行命令。DeepSeek Harness 示例另需腾讯云 TokenHub API Key。

每个示例都会创建独立资源。请从命令输出中复制 ID，并在下一步按提示设置环境变量；完成后执行清理章节。

在本目录运行 `make run` 可列出可选场景，随后请按所选场景的 README 操作。该命令只输出导航信息，不会创建云资源。

## 示例

| 示例 | 说明 |
| --- | --- |
| [httpbin/simple](./httpbin/simple/README_zh.md) | 创建 Tool 和 Deployment，通过本地 proxy 与生产域名访问 httpbin，并清理资源。 |
| [httpbin/scaling](./httpbin/scaling/README_zh.md) | 从按需启动切换到常驻容量，理解三个伸缩参数及完整替换更新。 |
| [httpbin/lifecycle](./httpbin/lifecycle/README_zh.md) | 依次观察空闲实例的 `STOP` 与 `PAUSE` 行为。 |
| [httpbin/affinity](./httpbin/affinity/README_zh.md) | 比较共享的 `BEST_EFFORT` 与专属的 `EXCLUSIVE` 会话亲和。 |
| [mcp-server/simple](./mcp-server/simple/README_zh.md) | 部署官方 Everything MCP Server，使用原生 Python SDK，并观察 `0 → N → 0` 与缩容到零后的新会话。 |
| [deepseek-harness/all-in-one](./deepseek-harness/all-in-one/README_zh.md) | 部署 all-in-one DeepSeek Harness，通过 TokenHub 完成编码任务，并验证独占会话的暂停与恢复。 |
| [deepseek-harness/brain-hands](./deepseek-harness/brain-hands/README_zh.md) | 运行多副本无状态 DSH Brain，以 MySQL 保存状态，并访问持久的 E2B/envd Hands workspace。 |
| [session](./session/README_zh.md) | 将 DSH 与 Workspace Deployment 接入同一个 Agent Runtime 云端 Session，验证对话与工具调用 Events、Deployment 关联和基于 affinity 的 workspace 路由。 |

每个场景目录中的 `README.md` 是英文版，`README_zh.md` 是中文版。部署教程默认使用已发布镜像；需要查看镜像来源或自行构建时，可按教程链接进入对应说明。
