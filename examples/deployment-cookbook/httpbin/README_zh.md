# httpbin Deployment 示例

本目录使用同一个已发布的 httpbin 镜像，把 Deployment 能力拆成四个互不依赖的 Markdown 教程：

1. [simple](./simple/README_zh.md)：最短完整链路与两种访问方式。
2. [scaling](./scaling/README_zh.md)：按需启动、常驻实例和单实例请求并发。
3. [lifecycle](./lifecycle/README_zh.md)：空闲后的停止与暂停。
4. [affinity](./affinity/README_zh.md)：共享与独占会话亲和。

每个教程都直接使用终端中的 `agr` 与 `curl` 命令，并创建、删除自己的 Sandbox Tool 和 Deployment。它们只共享镜像，不共享任何运行中的云资源。

已发布镜像为 `ccr.ccs.tencentyun.com/ags.dev/go-httpbin:v2.25.0`。构建与发布说明位于 [dockerfiles](./dockerfiles/README_zh.md)。

## 前置条件

- 完成 [Deployment Cookbook 公共前置条件](../README_zh.md#前置条件)。
- 安装 `curl`；教程使用本地 proxy 时，确保本地端口 `18080` 可用。
- 所有示例均在 `ap-shanghai` 运行；每条命令都会显式指定 region。
