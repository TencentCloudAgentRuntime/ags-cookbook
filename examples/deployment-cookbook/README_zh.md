# Deployment Cookbook

本目录通过可独立运行的示例介绍如何使用 `agr` 管理 Deployment。httpbin 示例从最短部署链路讲解平台能力；DeepSeek Harness 示例进一步演示长驻 Agent 工作区。

## 前置条件

- 已安装 `agr`，并通过 `agr status` 确认凭证和 region 配置有效。
- 已准备允许 AGR 拉取示例 CCR 镜像的 CAM 角色 ARN。
- 账号具有创建和删除 Sandbox Tool、Deployment 以及获取 Deployment Token 的权限。

全部示例都使用标准 Markdown，并直接在终端执行命令。DeepSeek Harness 示例另需腾讯云 TokenHub API Key。

每个示例都会创建独立资源。资源 ID 不会自动提取：请从命令输出中复制 ID，并在下一步按提示设置环境变量。完成或中止实验后，请执行清理章节，避免遗留资源。

在本目录运行 `make run` 可列出可选场景，随后请按所选场景的 README 操作。该命令只输出导航信息，不会创建云资源。

## 示例

| 示例 | 说明 |
| --- | --- |
| [httpbin/simple](./httpbin/simple/README_zh.md) | 创建 Tool 和 Deployment，通过本地 proxy 与生产域名访问 httpbin，并清理资源。 |
| [httpbin/scaling](./httpbin/scaling/README_zh.md) | 从按需启动切换到常驻容量，理解三个伸缩参数及完整替换更新。 |
| [httpbin/lifecycle](./httpbin/lifecycle/README_zh.md) | 依次观察空闲实例的 `STOP` 与 `PAUSE` 行为。 |
| [httpbin/affinity](./httpbin/affinity/README_zh.md) | 比较 `BEST_EFFORT`、`STRICT` 和 `EXCLUSIVE` 三种会话亲和模式。 |
| [deepseek-harness/all-in-one](./deepseek-harness/all-in-one/README_zh.md) | 部署 all-in-one DeepSeek Harness，通过 TokenHub 完成编码任务，并验证独占会话的暂停与恢复。 |

每个场景目录中的 `README.md` 是英文版，`README_zh.md` 是中文版。httpbin 镜像的来源、构建和发布方式见 [httpbin/dockerfiles](./httpbin/dockerfiles/README_zh.md)。
