# 使用 Agent Runtime Session 持久化 DeepSeek Harness 会话

[English](./README.md)

DeepSeek Harness（下文简称 DSH）默认将会话保存在本地磁盘的 JSONL 文件中，容器删除后会话历史随之丢失。本示例通过持久化插件将 DSH 的会话写入云端 Agent Runtime Session：删除容器再启动全新的容器后，仍可加载原会话并继续对话。

本示例只涉及会话持久化。如需同时保留工作区文件，并将后续请求路由回原工作区，请参考 [Session 与工作区关联示例](../../deployment-cookbook/brain-hands-session/README_zh.md)。

## 选择 DSH 版本

DSH 在不同版本之间调整过会话持久化接口，部分版本之间存在不兼容变更，插件因此按 DSH 版本分别提供。每个版本目录都是一份完整的接入示例，包含文档、插件、镜像文件和验证脚本，进入对应目录按其文档操作即可。

| DSH 版本 | 说明 | 预集成镜像 | 文档 |
| --- | --- | --- | --- |
| **0.2.1-rc.2**（推荐） | 基于官方 DSH，未打任何补丁；可在本地或容器中运行，部署到 AGS 需要先做适配 | `ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:v0.2.1-rc.2-session-persistence.2` | [dsh-0.2.1-rc.2](./dsh-0.2.1-rc.2/README_zh.md) |
| 0.1.1-rc.2 | 基于官方 DSH 并加入 AGS 适配补丁；可直接部署到 AGS | `ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:v0.1.1-rc.2-ags.4-session-persistence.4` | [dsh-0.1.1-rc.2](./dsh-0.1.1-rc.2/README_zh.md) |

0.2.1-rc.2 使用官方 DSH，没有打任何补丁，启动行为与官方发布一致，因此官方限制（例如不接受 `--host 0.0.0.0`）都保留，不能直接部署到 AGS。需要在 AGS 上运行时，可以按其文档中的[部署到 AGS](./dsh-0.2.1-rc.2/README_zh.md#部署到-ags)自行适配，或改用带适配补丁的 0.1.1-rc.2。

按以下顺序选择：

1. **已经在使用 DSH**：选择与自有 DSH 版本相同的目录。在 DSH 所在的环境中执行 `npm ls -g @deepseek-ai/dsh` 查看版本。版本不在上表中时，插件无法直接使用。
2. **需要在 AGS 沙箱或 Deployment 中运行**：目前只有 0.1.1-rc.2 提供可直接使用的部署方式。0.2.1-rc.2 部署到 AGS 需要额外适配，见其文档中的[部署到 AGS](./dsh-0.2.1-rc.2/README_zh.md#部署到-ags)。
3. **其他情况**：选择 0.2.1-rc.2。

## 版本差异

| 方面 | 0.2.1-rc.2 | 0.1.1-rc.2 |
| --- | --- | --- |
| DSH 来源 | 从 npm 安装官方 `@deepseek-ai/dsh@0.2.1-rc.2` | 从源码构建，并加入 AGS 适配补丁 |
| 部署到 AGS | 需要额外适配 | 支持 |
| Web UI 登录 | 需使用启动日志中带 token 的地址 | 无需登录 |
| 模型配置 | 写在 Cordis 补丁中 | 启动时生成 `settings.yaml` |

两个版本写入云端的会话互不可见：0.2.1-rc.2 不显示 0.1.1-rc.2 写入的会话，也不会迁移这些会话。

## 版本约定

插件依赖 DSH 的内部模块，DSH 及这些模块的版本必须与插件适配的版本完全一致。请按所选版本文档中的「版本与依赖约定」固定全部版本，不要安装"最新版本"：

- `npm install -g @deepseek-ai/dsh` 不写版本号时，会安装 npm 上当前的最新版本，可能与插件适配的版本不同。
- 版本不一致时，DSH 在启动阶段即报错，例如 `does not provide an export named 'PersistenceCoordinator'`。
