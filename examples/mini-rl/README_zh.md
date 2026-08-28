# Mini-RL：强化学习 + Agent Sandbox 最小示例

本示例展示如何在强化学习场景中接入 AGS 沙箱，完成“模型输出 ToolCall → Runtime 解析 → 沙箱执行 → 结果回填”的最小闭环。

## 前置条件

- Python >= 3.12
- `uv`
- `E2B_API_KEY`
- 必填 `E2B_DOMAIN`

## 必要环境变量

```bash
export E2B_API_KEY="your_ags_api_key"
export E2B_DOMAIN="ap-guangzhou.tencentags.com"
```

## 本地命令

```bash
make setup
make run
```

## 预期输出

运行成功后，你应看到类似下面的结果：

```text
=== Rollout Result ===
Question: 计算：23 × 17 − 19
Sandbox Result: 372
Reward: 1.0
```

## 它展示了什么

- Runtime 而不是模型本身负责启动与调用沙箱
- ToolCall 解析与回填是 RL 集成中的关键粘合层
- 一个最小但完整的 rollout 闭环
