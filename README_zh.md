# Agent Sandbox Cookbook

用于腾讯云 Agent Sandbox / AGS 的教程、示例与调试工具集合。

## 仓库内容

- **skills/**：AGS 的参考 Agent Skill 示例；详见 [`skills/README.md`](./skills/README.md)
- **tutorials/**：SDK / Notebook 教程
- **examples/**：可运行的浏览器、代码、移动端、Go、OSWorld 示例
- **benchmarks/**：k6 压测脚本
- **utils/**：调试辅助工具及经过验证的 envd 等运行时源码组件

## 环境要求

### 本地工具

- `uv`
- `python3`
- `go`（Go 示例需要）
- `git`
- Docker 对部分流程有帮助，但不是每个示例都必需

### Python 版本

- `examples/` 下多数 Python 示例要求 **Python >= 3.12**
- `examples/osworld-ags` 当前要求 **Python 3.10**
- 建议统一使用 `uv` 管理解释器。

### agr CLI

`ags` 参考 Skill 示例使用 `agr` CLI：

```bash
# 一键安装（macOS / Linux）
curl -fsSL https://github.com/TencentCloudAgentRuntime/ags-cli/releases/latest/download/install.sh | sh

# 或通过 go install
go install github.com/TencentCloudAgentRuntime/ags-cli/cmd/agr@latest

agr version -o json
```

## 常用环境变量

### AGS / E2B 兼容运行时

```bash
export E2B_API_KEY="your_ags_api_key"
export E2B_DOMAIN="ap-guangzhou.tencentags.com"
```

### 腾讯云控制面示例

```bash
export TENCENTCLOUD_SECRET_ID="your_secret_id"
export TENCENTCLOUD_SECRET_KEY="your_secret_key"
export TENCENTCLOUD_REGION="ap-guangzhou"
```

## 快速开始

### 1. 查看所有示例

```bash
make examples-list
```

### 2. 运行单个示例

大多数示例目录都提供本地 `make run`：

```bash
make example-setup EXAMPLE=mini-rl
make example-run EXAMPLE=mini-rl
```

你也可以直接进入某个 example 目录，执行它自己的 `make setup` / `make run`。

## 示例概览

| 示例 | 技术栈 | 说明 |
|---|---|---|
| `browser-agent` | Python + 浏览器沙箱 + LLM | 浏览器自动化 Agent |
| `custom-image-go-sdk` | Go | 自定义镜像 / 自定义工具启动 |
| `data-analysis` | Python + 代码沙箱 | 多 Context 数据分析 |
| `deployment-cookbook` | agr CLI + Markdown | Deployment、伸缩、生命周期、亲和性与长驻 Agent 工作区场景 |
| `envd-oci-env` | Bash + Docker + agr | envd 作为 PID 1 时保留 OCI 镜像环境变量 |
| `harness-nix-volume` | Nix + 自定义镜像 + 镜像卷 | 自包含 Harness 依赖挂载 |
| `html-processing` | Python + Browser/Code 双沙箱 | HTML 协作处理 |
| `hybrid-cookbook` | Go | 最小控制面 + 数据面流程 |
| `mini-rl` | Python + 代码沙箱 | 最小 RL Tool Calling 示例 |
| `mini-swe-agent` | Python + SWE 沙箱 + LLM | 使用 AGS SWE 沙箱运行 SWE-bench 评测 |
| `mobile-use` | Python + 移动端沙箱 + Appium | Android 自动化 |
| `multi-openclaw` | Node.js + 自定义镜像 + AGS | 多用户沙箱路由中心，统一管理多个 OpenClaw 沙箱 |
| `openclaw-cookbook` | Node.js + 自定义镜像 + COS | 基于官方镜像在 AGS 中运行 OpenClaw |
| `osworld-ags` | Python 3.10 + OSWorld overlay | 依赖重，且需要可用的 OSWorld 工具 |
| `shop-assistant` | Python + 浏览器沙箱 | 搜索 / 加购演示 |
| `waa-ags` | Python + Windows 沙箱 + LLM | 通过 overlay 在 AGS 上运行 Windows Agent Arena |

详见 `examples/README_zh.md`，其中包含各示例的使用说明与推荐阅读顺序。

## Skills 概览

**`ags`** 是 AGS 的参考 Agent Skill 示例，展示基于 `agr` 的 CLI-first AGS 工作流。

| Skill | 路径 | 覆盖范围 |
|---|---|---|
| `ags` | [`skills/ags/SKILL.md`](./skills/ags/SKILL.md) | CLI-first AGS 工作流：工具、实例、代码/Shell 执行、文件传输、浏览器/移动端、存储挂载、API Key、调试实例、工具复制、原始 API 透传 |

通过 `skills` CLI 从 GitHub 添加：

```bash
npx skills add TencentCloudAgentRuntime/ags-cookbook --skill ags
```

索引与渐进式披露结构见 [`skills/README.md`](./skills/README.md)。

## 重要 DX 说明

- Python 示例优先使用 `uv sync` + `uv run ...`
- 不要假设根 README 中的默认值适用于所有示例；请始终以具体 example 的 README 和 `.env.example` 为准
- AGS 域名具有地域属性；请显式设置 `E2B_DOMAIN` 为你要使用的地域域名
- 某些示例依赖你账号中已预先创建的 AGS 工具 / 模板

## 贡献

见 [CONTRIBUTING.md](./CONTRIBUTING.md)。

## 许可证

本项目采用 Apache 2.0，详见 [LICENSE-Agent Sandbox Cookbook.txt](./LICENSE-Agent%20Sandbox%20Cookbook.txt)。
