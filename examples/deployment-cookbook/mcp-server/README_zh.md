# MCP Server Deployment Cookbook

本目录演示如何在 AGR Deployment 上运行现有 Model Context Protocol（MCP）Server，同时保持原生的客户端使用方式。

当前的 [simple](./simple/README_zh.md) 场景通过 Streamable HTTP 部署官方 Everything MCP Server。`initialize`、`tools/list` 和 `tools/call` 全部由官方 Python SDK 完成；客户端中仅通过受支持的 HTTP request/response hooks 处理 AGS 特有逻辑。

该场景分别验证三个可观察结果：

1. 一个原生 MCP 会话可以通过生产 Deployment 数据面完成调用；
2. MCP 流量会激活实测数量为 `N` 的实例，并在空闲 `STOP` 后回到零；
3. 原实例停止后，可以保留 AGS `BEST_EFFORT` affinity 值，并用重新初始化的 MCP 会话继续访问。

本场景不承诺客户端数量等于实例数量，也不承诺 MCP 协议会话可以跨实例替换存活。

固定版本镜像的源码和发布说明位于 [simple/dockerfiles](./simple/dockerfiles/README_zh.md)。
