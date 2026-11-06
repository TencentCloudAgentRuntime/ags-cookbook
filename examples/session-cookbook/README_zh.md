# Session Cookbook

[English](./README.md)

本目录演示如何将 Agent 应用的会话持久化接入 Agent Runtime Session，使应用在运行实例替换后能够加载已保存的对话历史。

每个示例均自包含，覆盖配置、构建、验证和清理，且都不需要独立的工作区服务。

| 接入对象 | 示例内容 |
| --- | --- |
| DeepSeek Harness（DSH） | 将 DSH 的会话持久化对接到云端 Session，删除容器后在新容器中加载同一会话并继续对话 —— [deepseek-harness](./deepseek-harness/README_zh.md) |
| pi | 用 pi 扩展把会话的每个条目复制到云端 Session，删除容器后在新容器中用官方 `pi` 可执行文件重新打开同一会话，`/fork` 和 `switch_session` 也可用；另有一个最小的内存方案 —— [pi](./pi/README_zh.md) |

`make run` 显示导航。


需要事先说明：Session 负责保存历史，但不负责决定由谁写入。如果多个实例可能轮流处理同一个会话，请从下面表格里选择切换参考实现；基础示例假定每个会话只有一个写入者。

扩缩容、亲和性和工作区关联请看 [Deployment Cookbook](../deployment-cookbook/README_zh.md)。Brain/Hands 分离、由云端 Session 保存对话和 Hands 工作区路由的组合示例在 [brain-hands-session](../deployment-cookbook/brain-hands-session/README_zh.md)。

## 按框架版本与实现方式选择

| 实现 | 适用场景 | 框架改动 | 文档 |
| --- | --- | --- | --- |
| DSH 0.2.1-rc.2 基础持久化 | 单 writer，新进程恢复云端历史 | 无框架源码补丁 | [接入与运行](./deepseek-harness/dsh-0.2.1-rc.2/README_zh.md) |
| DSH 0.2.1-rc.2 切换参考实现 | 常驻实例在完整轮次之间 A → B → A；检查并重建过期内存 generation | 独立目录、源码补丁与镜像 | [生命周期、改动与版本实现对比](./deepseek-harness/reference/dsh-0.2.1-rc.2-stateless-handoff/README_zh.md) |
| pi 1.4.0 文件/RPC | 官方 pi RPC、本地 JSONL、新进程恢复；单 writer | 无框架源码修改 | [接入与运行](./pi/README_zh.md) |
| pi 1.4.0 SDK/HTTP 参考实现 | 每请求重建内存会话；常驻实例在完整轮次之间切换 | 独立目录和镜像；SDK 外层 HTTP host，无框架源码修改 | [生命周期、改动与版本实现对比](./pi/reference/pi-1.4.0-stateless-handoff/README_zh.md) |

两个参考实现都不会让另一个实例接着执行到一半的轮次，不重放工具，也不复制工作区文件。实例崩溃留下的未结束轮次，在静默超过超时时间（默认 10 分钟）后会被自动收尾；Session 服务保持不改。选择参考实现需要构建对应目录的镜像，不会替换基础示例的入口。
