# Session Cookbook

[English](./README.md)

本目录演示如何将 Agent 应用的会话持久化接入 Agent Runtime Session，使应用在运行实例替换后能够加载已保存的对话历史。

每个示例均自包含，覆盖配置、构建、验证和清理，且都不需要独立的工作区服务。

| 接入对象 | 示例内容 |
| --- | --- |
| DeepSeek Harness（DSH） | 将 DSH 的会话持久化对接到云端 Session，删除容器后在新容器中加载同一会话并继续对话 —— [deepseek-harness](./deepseek-harness/README_zh.md) |

`make run` 显示导航。

需要事先说明：Session 负责保存历史，但不负责决定由谁写入。多个实例写入同一会话，或进行中的回合需要由另一个实例接续时，需要额外的协调机制，详见[本适配器的限制](./deepseek-harness/README_zh.md#本适配器的限制)。

扩缩容、亲和性和工作区关联请看 [Deployment Cookbook](../deployment-cookbook/README_zh.md)。Brain/Hands 分离、由云端 Session 保存对话和 Hands 工作区路由的组合示例在 [brain-hands-session](../deployment-cookbook/brain-hands-session/README_zh.md)。
