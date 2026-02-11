# SWE-Bench 推理：使用 AGS 云端沙箱

使用 AGS（Agent Sandbox Server）云端沙箱配合 R2E-Gym Python API，完成 SWE-Bench 代码任务推理。

AGS 为每个 SWE-Bench 任务按需创建隔离的 Linux 容器环境。Agent 在沙箱中阅读代码、编辑文件、运行测试，测试结果作为 reward 信号（通过 = 1.0，失败 = 0.0）输出。

## 架构概览

```
┌──────────────────────────────────────────────────────────────┐
│                     SWE-Bench 推理流程                        │
│                                                              │
│  ┌──────────┐    ┌──────────────┐    ┌───────────────────┐  │
│  │ SWE-Bench│───>│   LLM API    │───>│   EditAgent       │  │
│  │   数据集  │    │ (生成代码编辑) │    │ (解析为工具调用)   │  │
│  └──────────┘    └──────────────┘    └─────────┬─────────┘  │
│                                                │             │
│                                                ▼             │
│                                       ┌────────────────┐    │
│                                       │   AGS 沙箱      │    │
│                                       │  - 执行编辑      │    │
│                                       │  - 运行测试      │    │
│                                       └────────┬───────┘    │
│                                                │             │
│                                                ▼             │
│  ┌──────────┐    ┌──────────────┐    ┌────────────────┐     │
│  │  保存     │<───│   Reward      │<───│ 测试通过/失败   │     │
│  │ Trajectory│    │   0 or 1      │    │ (沙箱内执行)    │     │
│  └──────────┘    └──────────────┘    └────────────────┘     │
└──────────────────────────────────────────────────────────────┘
```

核心流程：

1. 从 HuggingFace 加载 SWE-Bench 数据集（包含 GitHub issue 和对应的 Docker 镜像）
2. AGS 根据镜像创建云端沙箱（替代本地 Docker）
3. Agent 在沙箱中执行代码编辑（str_replace_editor、execute_bash 等工具）
4. 沙箱运行项目测试套件，计算 reward（全部通过 = 1.0，否则 = 0.0）
5. 保存 trajectory（包含完整的 Agent 动作序列和 reward）

## 前置条件

| 项目 | 要求 |
|------|------|
| **Python** | >= 3.10 |
| **AGS 凭证** | `E2B_API_KEY`、`TENCENTCLOUD_SECRET_ID`、`TENCENTCLOUD_SECRET_KEY` |
| **AGS 沙箱工具** | 已为数据集中的 docker_image 创建好沙箱工具（见下方说明） |
| **LLM API** | 兼容 OpenAI 接口的 LLM 服务（如 vLLM 部署的模型） |
| **网络** | 可访问 HuggingFace（或配置 HF 镜像）下载数据集 |

### 关于 AGS 沙箱工具

AGS 使用"沙箱工具"（SandboxTool）作为容器模板。使用前需要：

1. 将 SWE-Bench 数据集中的 Docker 镜像推送到 TCR（腾讯容器镜像仓库）
2. 基于推送后的 TCR 镜像创建对应的沙箱工具

为了简化演示流程，我们已经为 `R2E-Gym/SWE-Bench-Lite` 数据集的前 10 个镜像预先创建好了沙箱工具，ags_tool 会根据原始镜像名自动查找对应的沙箱工具。

如需创建更多沙箱工具，请参考 [ags_tool 文档](https://github.com/lirong-lirong/ags_tool) 中的 `example/swe_bench_ags_tool.ipynb`。

## 快速开始

通过 Jupyter Notebook [`swe-bench-ags-python.ipynb`](swe-bench-ags-python.ipynb) 体验完整流程，分为 5 个步骤：

1. **安装依赖** — 克隆并安装 R2E-Gym 和 ags_tool
2. **配置环境变量** — 设置 LLM API、AGS 凭证、HuggingFace 镜像
3. **加载数据集** — 从 HuggingFace 加载 SWE-Bench-Lite，选择任务范围
4. **运行 Agent** — 创建沙箱、运行 EditAgent、计算 reward、保存 trajectory
5. **查看结果** — 检查 trajectory 和日志文件

## 参数说明

### 数据集参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `START_IDX` | 0 | 从数据集的第几条开始 |
| `K` | 1 | 运行多少条数据 |

### Agent 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `max_steps` | 60 | Agent 最大交互步数 |
| `temperature` | 1.0 | LLM 采样温度 |
| `max_steps_absolute` | 100 | 绝对最大步数上限 |
| `max_token_limit` | 65536 | 上下文 token 限制 |
| `use_fn_calling` | False | 是否使用函数调用模式（本示例使用文本解析模式） |
| `scaffold` | "r2egym" | Agent 脚手架类型 |

### Reward 计算参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `timeout` | 300 | 测试执行超时时间（秒） |

reward 计算逻辑：在沙箱中执行项目测试套件，根据数据集类型自动选择评估方式：

- **SWE-Bench**：使用 swebench 官方 grading 模块判定 FAIL_TO_PASS 和 PASS_TO_PASS
- **R2E-Edit**：对比测试输出与 expected_output_json
- **SWE-Smith**：检查 FAIL_TO_PASS 测试是否通过且 PASS_TO_PASS 不退化

## 常见问题

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| AGS 连接 401/403 | 凭证错误或区域不匹配 | 检查 `E2B_API_KEY`、Secret ID/Key，确认 `AGS_REGION` 与沙箱工具区域一致 |
| `Sandbox tool not found for image ...` | 未提前创建沙箱工具 | 运行 `ags_tool_sync.py` 或手动创建沙箱工具（参考 ags_tool 文档） |
| `ags_tool is required for AGS runtime` | 未安装 ags_tool | `pip install -e './ags_tool[e2b]'` |
| 数据集下载失败 | HuggingFace 不可达 | 设置 `HF_ENDPOINT` 环境变量为可用的镜像地址 |
| Agent 运行时 LLM 报错 | LLM API 地址或 Key 配置错误 | 检查 `LLM_BASE_URL` 和 `OPENAI_API_KEY` 是否正确 |
| 测试超时 | 项目测试套件执行时间过长 | 增大 `timeout` 参数（默认 300 秒） |
| `Numba needs NumPy 2.2 or less` | NumPy 版本过高 | `pip install 'numpy<2.3'` |

## 技术栈

- [R2E-Gym](https://github.com/R2E-Gym/R2E-Gym) — SWE-Bench 环境封装与数据集
- [ags_tool](https://github.com/lirong-lirong/ags_tool) — AGS 沙箱 Python 封装
- [swebench](https://github.com/princeton-nlp/SWE-bench) — SWE-Bench 官方评估工具
- AgentSandbox — 云端沙箱执行后端
