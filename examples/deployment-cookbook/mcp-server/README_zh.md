# MCP Server Deployment Cookbook

本目录收录在 AGR Deployment 上运行 Model Context Protocol（MCP）Server 的示例。

[simple](./simple/README_zh.md) 示例部署官方 Everything MCP Server，并使用官方 Python MCP SDK 连接。

文档包含三部分：

1. 通过生产 Deployment endpoint 调用 MCP Server；
2. 观察活跃实例从 `0` 变为 `N`，再在空闲 `STOP` 后回到 `0`；
3. 实例停止后保留 AGS `BEST_EFFORT` affinity，同时创建新的 MCP 会话。

示例直接使用已发布的示例镜像。如需将镜像构建并推送到自己的仓库，请参考 [simple/dockerfiles](./simple/dockerfiles/README_zh.md)。
