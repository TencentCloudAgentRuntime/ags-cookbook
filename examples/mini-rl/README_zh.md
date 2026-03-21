# Mini-RL: 强化学习 + AgentSandbox 沙箱最小示例

本示例展示如何在强化学习场景中集成 AgentSandbox 沙箱，实现"模型输出 ToolCall → Runtime 解析 → 沙箱执行 → 结果回填"的完整流程。

## 核心概念

```
┌─────────────┐     ToolCall      ┌─────────────┐     Execute      ┌─────────────┐
│   Policy    │ ───────────────▶  │    VERL     │ ───────────────▶ │  AgentSandbox   │
│   (Model)   │                   │   Runtime   │                  │   Sandbox   │
└─────────────┘                   └─────────────┘                  └─────────────┘
                                        │                                │
                                        │◀───────────────────────────────┘
                                        │         Observation
                                        ▼
                                  ┌─────────────┐
                                  │   Reward    │
                                  │ Calculation │
                                  └─────────────┘
```

**关键点**：沙箱由 Runtime 启动，而不是模型直接调用。

## 快速开始

### 1. 配置 API Key

运行前设置环境变量：

```bash
export E2B_API_KEY="your_ags_api_key"  # 由腾讯云 Agent Sandbox 产品提供
export E2B_DOMAIN="ap-guangzhou.tencentags.com"  # 可选
```

### 2. 运行示例

```bash
uv run main.py
```

### 预期输出

```
=== Rollout Result ===
Question: 计算：23 × 17 − 19
Sandbox Result: 372
Reward: 1.0
```

## 代码结构

| 函数 | 说明 |
|------|------|
| `model_generate()` | 模拟模型输出 ToolCall（Policy 行为） |
| `parse_tool_call()` | 从模型输出中解析工具调用 |
| `verl_parse_and_execute()` | Runtime 解析并触发沙箱执行 |
| `stitch_context()` | 将沙箱结果回填到上下文 |
| `rollout_one_episode()` | 一次完整的 RL 轨迹 |

## 强化学习视角

| RL 概念 | 本示例对应 |
|---------|-----------|
| State | 问题 + 历史上下文 |
| Action | 模型输出的 ToolCall |
| Environment | AgentSandbox 沙箱 |
| Observation | 沙箱执行结果 |
| Reward | 答案正确性判断 |

## 依赖

- Python >= 3.12
- e2b-code-interpreter >= 2.4.1

## 快速开始

```bash
make run
```

