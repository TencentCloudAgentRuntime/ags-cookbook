# SWE-Bench with AgentSandbox

展示如何使用 AgentSandbox（AGS）云端沙箱完成 SWE-Bench 代码任务，涵盖推理测试和强化学习训练两个场景。

AGS 为每个 SWE-Bench 任务按需创建隔离的 Linux 容器环境，Agent 在沙箱中执行代码编辑和测试，测试通过/失败作为 reward 信号。

## 目录结构

```
swe-bench-rl/
├── README.md
├── README_zh.md
├── patches/                          # 上游仓库的 patch 文件
│   └── r2e-gym-ags-clean.patch     # R2E-Gym AGS 运行时 patch（基于 0d94c4e）
├── ags_tool/                         # AGS 沙箱工具（直接包含）
│   ├── pyproject.toml
│   ├── README.md
│   ├── src/ags_tool/
│   ├── example/
│   └── tcr_image_tool/
├── inference/                        # LLM 推理完成 SWE-Bench 任务
│   ├── README.md
│   ├── README_zh.md
│   └── swe-bench-ags-python.ipynb
└── rl-training/                      # 分布式 PPO 训练
    ├── README.md
    ├── README_zh.md
    ├── train.py
    └── rllm_with_ags.ipynb
```

## 子示例

| 目录                      | 说明                                | 核心依赖                   |
| ------------------------- | ----------------------------------- | -------------------------- |
| [inference/](inference/)     | 使用 LLM API + R2E-Gym 的单任务推理 | R2E-Gym, ags_tool, LLM API |
| [rl-training/](rl-training/) | 基于 rLLM + verl 的分布式 PPO 训练  | rLLM, verl, R2E-Gym, vLLM  |

## 依赖管理

本示例使用 **官方上游仓库 + patch 文件** 替代第三方 fork，以提高可复现性：

- **R2E-Gym**：从 [R2E-Gym/R2E-Gym](https://github.com/R2E-Gym/R2E-Gym) 克隆，在 commit `0d94c4e` 上应用 `patches/r2e-gym-ags-clean.patch` 以添加 AGS 运行时支持。
- **rllm**：从 [rllm-org/rllm](https://github.com/rllm-org/rllm) 克隆（仅 rl-training 使用）。
- **ags_tool**：直接包含在 `ags_tool/` 目录中 — AGS 沙箱 Python 封装（无上游依赖）。
- **verl**：直接克隆使用（无需 patch）。

## 前置条件

| 项目                   | 要求                                                                               |
| ---------------------- | ---------------------------------------------------------------------------------- |
| **AGS 凭证**     | `E2B_API_KEY`、`TENCENTCLOUD_SECRET_ID`、`TENCENTCLOUD_SECRET_KEY`           |
| **AGS 沙箱工具** | 已为数据集中的 docker_image 创建好沙箱工具（参考[ags_tool 文档](ags_tool/README.md)） |
| **网络**         | 可访问 HuggingFace（或 HF 镜像）下载数据集                                         |

各子示例的额外前置条件请参见对应 README。

## 技术栈

- [R2E-Gym](https://github.com/R2E-Gym/R2E-Gym) — SWE-Bench 环境与数据集
- [ags_tool](ags_tool/) — AGS 沙箱 Python 封装（包含在本仓库中）
- [rLLM](https://github.com/rllm-org/rllm) — Agent RL 训练框架（rl-training）
- [verl](https://github.com/volcengine/verl) — 分布式 PPO 训练引擎（rl-training）
- AgentSandbox — 云端沙箱执行后端
