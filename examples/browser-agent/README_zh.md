# Browser Agent：浏览器自动化示例

本示例展示如何在 AGS 浏览器沙箱中运行远程浏览器，并借助 OpenAI-compatible LLM 让 Agent 完成网页自动化任务。

## 前置条件

- Python >= 3.12
- `uv`
- `E2B_API_KEY`
- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `OPENAI_MODEL`
- 必填 `E2B_DOMAIN`

## 必要环境变量

```bash
export E2B_API_KEY="your_ags_api_key"
export OPENAI_API_KEY="your_llm_api_key"
export OPENAI_BASE_URL="https://your-openai-compatible-api/v1"
export OPENAI_MODEL="your-model-name"  # 必填模型名
export E2B_DOMAIN="ap-guangzhou.tencentags.com"
```

## 本地命令

```bash
make setup
make run
```

运行成功后，控制台会输出可用于观察浏览器过程的远程调试 / VNC 信息。

## 它展示了什么

- 远程浏览器通过 CDP 与本地 Agent 协作
- LLM 通过函数调用驱动浏览器操作
- 浏览器状态、工具结果与任务推进的循环闭环

## 常见失败提示

- 如果 LLM 请求失败，检查 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL`
- 如果浏览器沙箱启动失败，检查 `E2B_API_KEY` 和 `E2B_DOMAIN`
