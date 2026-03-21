# Examples

本目录包含可运行的 AGS 示例。每个示例都保留自己的 README 和 Makefile，方便你进入单个目录后沿着一条本地路径完成安装与运行。

## 如何选择示例

### 入门

- `mini-rl` —— 最小代码沙箱 tool-calling 流程
- `hybrid-cookbook` —— 最小 Go 控制面 + 数据面流程
- `html-processing` —— 双沙箱协作，输出结果直观

### 进阶

- `browser-agent` —— 基于 OpenAI-compatible LLM 的浏览器自动化 Agent
- `data-analysis` —— 多 Context 数据工作流，生成多个产物
- `mobile-use` —— 在 AGS 中运行 Android / Appium 自动化
- `shop-assistant` —— 浏览器购物流程自动化，支持无 Cookie 的 guest 模式
- `custom-image-go-sdk` —— Go 中的自定义镜像启动与数据面执行

### 重型 / 外部依赖

- `osworld-ags` —— 上游 OSWorld 的 overlay；需要额外 checkout、Python 3.10，以及可用的 OSWorld-compatible AGS 工具

## 共享本地约定

在条件允许时，每个示例都尽量提供：

- `make setup`：依赖准备
- `make run`：主要本地执行路径
- `README.md`：写明前置条件、环境变量、运行步骤和预期结果

某些依赖较重或基于外部 overlay 的示例会是例外，但也应该在 README 中提供一条明确的主路径。

## 示例列表

| 示例 | 分类 | 主要技术栈 | 主命令 | 说明 |
|---|---|---|---|---|
| `browser-agent` | 进阶 | Python + 浏览器沙箱 + LLM | `make run` | 需要 OpenAI-compatible LLM backend 环境变量 |
| `custom-image-go-sdk` | 进阶 | Go | `make run` | 依赖 AGS 账号中的自定义工具 / 镜像配置 |
| `data-analysis` | 进阶 | Python + 代码沙箱 | `make run` | 会生成多种图表与报告文件 |
| `html-processing` | 入门 | Python + 浏览器/代码双沙箱 | `make run` | 适合作为双沙箱协作的直观起点 |
| `hybrid-cookbook` | 入门 | Go | `make run` | 最小 Go 集成路径 |
| `mini-rl` | 入门 | Python + 代码沙箱 | `make run` | 最小 Python 示例 |
| `mobile-use` | 进阶 | Python + 移动端沙箱 + Appium | `make run` | 运行时依赖较重，且流程较长 |
| `osworld-ags` | 重型 | Python 3.10 + OSWorld overlay | `make setup` 后 `make run` | 需要外部 checkout 与模板 / 工具准备 |
| `shop-assistant` | 进阶 | Python + 浏览器沙箱 | `make run` | 已支持无 Cookie 的 guest 模式 |

如需在仓库根目录调度单个示例，可执行：

```bash
make examples-list
make example-setup EXAMPLE=<name>
make example-run EXAMPLE=<name>
```
