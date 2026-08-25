# Deployment Cookbook

本目录通过可独立运行的示例介绍如何使用 `agr` 管理 Deployment。示例以 httpbin 为工作负载，先完成最短部署链路，再分别观察弹性伸缩、空闲生命周期和会话亲和。

## 前置条件

- 已安装 `agr`，并通过 `agr status` 确认凭证和 region 配置有效。
- 已安装 Jupyter Notebook，Notebook 使用 IPython 的 `%env` 和 `!` 直接执行命令。
- 可以访问 `ccr.ccs.tencentyun.com/ags.dev/go-httpbin:v2.25.0`。
- 已准备一个允许 AGR 拉取该 CCR 镜像的 CAM 角色 ARN；运行 Notebook 时将它填入 `AGR_ROLE_ARN`。
- 账号具有创建和删除 Sandbox Tool、Deployment 以及获取 Deployment Token 的权限。

每个 Notebook 都会创建独立资源。资源 ID 不会自动提取：请从命令输出中复制 ID，并在下一步按提示设置环境变量。完成或中止实验后，请执行清理章节，避免遗留资源。

## 示例

| 示例 | 说明 |
| --- | --- |
| [httpbin/simple](./httpbin/simple/httpbin-simple.ipynb) | 创建 Tool 和 Deployment，通过本地 proxy 与生产域名访问 httpbin，并清理资源。 |
| [httpbin/scaling](./httpbin/scaling/httpbin-scaling.ipynb) | 从按需启动切换到常驻容量，理解三个伸缩参数及完整替换更新。 |
| [httpbin/lifecycle](./httpbin/lifecycle/httpbin-lifecycle.ipynb) | 依次观察空闲实例的 `STOP` 与 `PAUSE` 行为。 |
| [httpbin/affinity](./httpbin/affinity/httpbin-affinity.ipynb) | 比较 `BEST_EFFORT`、`STRICT` 和 `EXCLUSIVE` 三种会话亲和模式。 |

英文版 Notebook 使用 `_en.ipynb` 后缀。httpbin 镜像的来源、构建和发布方式见 [httpbin/dockerfiles](./httpbin/dockerfiles/README_zh.md)。
