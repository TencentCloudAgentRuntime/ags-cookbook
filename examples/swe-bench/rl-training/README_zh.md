# SWE-Bench RL 训练：使用 AGS 云端沙箱

使用 AGS（Agent Sandbox Server）沙箱作为 Agent RL 训练的执行后端，完成 SWE-Bench 代码修复任务的分布式 PPO 强化学习训练。

AGS 为每个 SWE-Bench 任务按需创建隔离的 Linux 容器环境，Agent 在沙箱中执行代码编辑和测试，测试结果作为 reward 信号驱动 PPO 训练。

## 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                      PPO Training Loop                      │
│                                                             │
│  ┌──────────┐    ┌──────────────┐    ┌──────────────────┐  │
│  │ SWE-Bench│───>│  vLLM Rollout│───>│    SWEAgent      │  │
│  │   Data   │    │ (生成代码编辑) │    │ (解析为工具调用)  │  │
│  └──────────┘    └──────────────┘    └────────┬─────────┘  │
│                                               │             │
│                                               ▼             │
│                                      ┌────────────────┐    │
│                                      │  AGS 沙箱       │    │
│                                      │  (执行编辑、     │    │
│                                      │   运行测试)      │    │
│                                      └────────┬───────┘    │
│                                               │             │
│                                               ▼             │
│  ┌──────────┐    ┌──────────────┐    ┌────────────────┐    │
│  │ PPO 更新  │<───│   Reward      │<───│ 测试通过/失败   │    │
│  │ (更新权重) │    │   Signal      │    │ = reward 0/1   │    │
│  └──────────┘    └──────────────┘    └────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

关键设置：`+rllm.env.env_args.backend=ags` 指定使用 AGS 云端沙箱，替代本地 Docker 或 Kubernetes。

## 前置条件

| 项目 | 要求 |
|------|------|
| **GPU** | H20 x 8（或根据模型大小调整配置） |
| **AGS 凭证** | `E2B_API_KEY`、`TENCENTCLOUD_SECRET_ID`、`TENCENTCLOUD_SECRET_KEY` |
| **AGS 沙箱工具** | 已为数据集中的 docker_image 创建好沙箱工具（参考 [ags_tool 文档](https://github.com/lirong-lirong/ags_tool)） |
| **模型权重** | 本 demo 使用 Qwen3-8B，需提前下载至本地路径 |
| **网络** | 可访问 HuggingFace（或 HF 镜像）下载数据集 |

## 快速开始

通过 Jupyter Notebook [`rllm_with_ags.ipynb`](rllm_with_ags.ipynb) 体验完整流程，分为 4 个步骤：

1. **安装依赖** — 克隆 rLLM、verl、R2E-Gym、ags_tool 源码并安装
2. **环境变量配置** — 设置 AGS 凭证、vLLM 运行时、MLflow 监控等
3. **数据集准备** — 从 HuggingFace 下载 SWE-Bench-Lite（验证集）和 R2E-Gym-Subset（训练集），按 `docker_image` 排序后截取
4. **配置并启动训练** — 通过 Hydra override 配置 PPO 参数，使用 `AgentTrainer.train()` 启动训练

## 配置参数

训练通过 Hydra override 配置，基于 `agent_ppo_trainer.yaml`。关键参数分组：

| 参数组 | 作用 | 关键设置 |
|--------|------|----------|
| `algorithm.*` | PPO/RLOO 算法参数 | `adv_estimator=rloo`, `kl_coef=0.001` |
| `data.*` | 批次大小、序列长度 | `train_batch_size=4`, `max_response_length=32768` |
| `actor_rollout_ref.*` | 模型、优化器、vLLM 推理 | `model.path=Qwen3-8B`, `rollout.n=4`, `gpu_memory_utilization=0.5` |
| `rllm.*` | Agent/Environment 设置 | **`env.env_args.backend=ags`**（启用 AGS） |
| `trainer.*` | 日志、检查点、GPU 拓扑 | `n_gpus_per_node=8`, `total_epochs=2` |

说明：

- `ppo_max_token_len_per_gpu` 必须大于 `max_prompt_length + max_response_length`
- `rollout.n=4` 表示每条数据采样 4 次（每个问题 4 个独立沙箱），训练会强化高分轨迹、降低低分轨迹的概率
- `train_batch_size x rollout.n` 必须能被 `n_gpus_per_node` 整除（本 demo: 4 x 4 = 16，16 / 8 = 2）
- 整个训练过程创建的沙箱数 = 数据条数 x epoch 数 x rollout.n

## 常见问题

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| AGS 连接 401/403 | 凭证错误或区域不匹配 | 检查 `E2B_API_KEY`、Secret ID/Key，确认 `AGS_REGION` 与沙箱工具区域一致 |
| `Numba needs NumPy 2.2 or less` | NumPy 版本过高 | `pip install 'numpy<2.3'` |
| `must be called with a dataclass type or instance` | datasets 版本过低 | `pip install 'datasets>=4.5.0'` |
| vLLM OOM | 显存不足 | 减小 `gpu_memory_utilization`、`max_response_length`，或使用更小模型 |
| Ray 初始化失败 | 残留 Ray 进程 | `ray stop --force` 后重试 |
| 数据集下载失败 | HF 不可达 | 设置 `HF_ENDPOINT` 为可用的镜像地址 |

## 技术栈

- [rLLM](https://github.com/rllm-org/rllm) — Agent RL 训练框架
- [verl](https://github.com/volcengine/verl) — 分布式 PPO 训练引擎
- [R2E-Gym](https://github.com/R2E-Gym/R2E-Gym) — SWE-Bench 环境与数据集
- [vLLM](https://github.com/vllm-project/vllm) — LLM 推理引擎
- AgentSandbox — 云端沙箱执行后端
