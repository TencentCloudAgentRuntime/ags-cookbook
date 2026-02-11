# SWE-Bench with AgentSandbox

展示如何使用 AgentSandbox（AGS）云端沙箱完成 SWE-Bench 代码修复任务，涵盖推理和强化学习训练两个场景。

AGS 为每个 SWE-Bench 任务按需创建隔离的 Linux 容器环境，Agent 在沙箱中执行代码编辑和测试，测试通过/失败作为 reward 信号。

## 子示例

| 目录 | 说明 | 核心依赖 |
|------|------|----------|
| [inference/](inference/) | 使用 LLM API + R2E-Gym 的单任务推理 | R2E-Gym, ags_tool, LLM API |
| [rl-training/](rl-training/) | 基于 rLLM + verl 的分布式 PPO 训练 | rLLM, verl, R2E-Gym, vLLM |

## 前置条件

| 项目 | 要求 |
|------|------|
| **AGS 凭证** | `E2B_API_KEY`、`TENCENTCLOUD_SECRET_ID`、`TENCENTCLOUD_SECRET_KEY` |
| **AGS 沙箱工具** | 已为数据集中的 docker_image 创建好沙箱工具（参考 [ags_tool 文档](https://github.com/lirong-lirong/ags_tool)） |
| **网络** | 可访问 HuggingFace（或 HF 镜像）下载数据集 |

各子示例的额外前置条件请参见对应 README。

## 技术栈

- [R2E-Gym](https://github.com/R2E-Gym/R2E-Gym) — SWE-Bench 环境与数据集
- [ags_tool](https://github.com/lirong-lirong/ags_tool) — AGS 沙箱 Python 封装
- [rLLM](https://github.com/rllm-org/rllm) — Agent RL 训练框架（rl-training）
- [verl](https://github.com/volcengine/verl) — 分布式 PPO 训练引擎（rl-training）
- AgentSandbox — 云端沙箱执行后端
