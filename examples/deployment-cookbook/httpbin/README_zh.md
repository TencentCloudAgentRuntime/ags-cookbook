# httpbin Deployment 示例

本目录使用同一个固定版本的 httpbin 镜像，把 Deployment 能力拆成四个互不依赖的 Markdown 教程：

1. [simple](./simple/README_zh.md)：最短完整链路与两种访问方式。
2. [scaling](./scaling/README_zh.md)：按需启动、常驻实例和并发租约上限。
3. [lifecycle](./lifecycle/README_zh.md)：空闲后的停止与暂停。
4. [affinity](./affinity/README_zh.md)：三种会话亲和策略。

每个教程都直接使用终端中的 `agr` 与 `curl` 命令，并创建、删除自己的 Sandbox Tool 和 Deployment。它们只共享镜像，不共享任何运行中的云资源。

镜像固定为 `ccr.ccs.tencentyun.com/ags.dev/go-httpbin:v2.25.0`。构建材料与发布说明位于 [dockerfiles](./dockerfiles/README_zh.md)。
