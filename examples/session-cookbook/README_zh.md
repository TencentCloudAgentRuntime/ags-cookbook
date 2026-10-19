# Session Cookbook

[English](./README.md)

把框架的会话历史从本地磁盘迁移到 Agent Runtime Session，使会话不再随进程一起消失。

每个示例均自包含，覆盖配置、构建、验证和清理，且都不需要独立的工作区服务。

| 框架 | 示例内容 |
| --- | --- |
| DeepSeek Harness | 将 DSH 的会话持久化对接到云端 Session，删除容器后在新容器中加载同一会话并继续对话 —— [deepseek-harness](./deepseek-harness/README_zh.md) |

`make run` 显示导航。

需要事先说明：Session 负责保存历史，但不负责决定由谁写入。多个实例写入同一会话，或进行中的回合需要由另一个实例接续时，需要额外的协调机制，详见[本适配器的限制](./deepseek-harness/README_zh.md#本适配器的限制)。

扩缩容、亲和性和工作区关联请看 [Deployment Cookbook](../deployment-cookbook/README_zh.md)。Session 与工作区组合的场景在 [session-workspace](../deployment-cookbook/session-workspace/README_zh.md)。
