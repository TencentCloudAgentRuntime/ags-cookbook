# Skill: Browser Agent（LLM 驱动浏览器任务）

本示例是 `examples/browser-agent` 的 Skill 化版本：在 AGS 浏览器沙箱中实现**通用的 LLM 驱动多步 tool loop**。Skill 负责 Playwright/CDP 管道；*你*注入任意 LLM，由它给出结构化的 action dict。

## 架构

```
browser_task(task, llm_fn, max_steps=10)
  │
  └── 启动一次浏览器沙箱，循环执行：
      1. 构造 observation（url、title、文本片段）
      2. llm_fn(observation, history, task) → 下一步 action
      3. 通过 Playwright 执行 action
      4. 记录步骤；llm_fn 发出 {"tool": "done"} 或达到 max_steps 即结束
```

## 支持的 action

```python
{"tool": "goto",       "url": "..."}
{"tool": "click",      "selector": "..."}
{"tool": "fill",       "selector": "...", "text": "..."}
{"tool": "evaluate",   "expression": "document.title"}
{"tool": "screenshot", "path": "step-N.png"}
{"tool": "done",       "answer": "..."}
```

刻意保持最小集合；若需扩展（多 Tab、cookie 等），在 `main.py` 的 `_execute_action` 中添加，或参考 `skill-browser-interact`。

## 它展示了什么

- **`browser_task(task, llm_fn, max_steps)`** — 完整 tool loop，返回 `{completed, steps, final_answer, history}`
- **`make_echo_llm(script)`** — 脚本化 LLM 桩，回放预设 action 列表；让本 Skill **无需任何 LLM 凭据即可端到端运行**

## 前置条件

- Python 3.13（由 `uv` 管理）
- 已安装 `uv`
- 有权访问 `browser-v1` 沙箱模板
- （真实 LLM 场景）你的 LLM 客户端——用一个函数包一层，使其返回 action dict

## 必要环境变量

```bash
# 方式 A
export E2B_API_KEY="your_ags_api_key"
export E2B_DOMAIN="ap-guangzhou.tencentags.com"
```

```bash
# 方式 B
export TENCENTCLOUD_SECRET_ID="your_secret_id"
export TENCENTCLOUD_SECRET_KEY="your_secret_key"
export TENCENTCLOUD_REGION="ap-guangzhou"
```

## 安装与运行

```bash
make setup
make run
```

## 预期输出

内置 demo 使用 `make_echo_llm` 对 `https://example.com` 执行固定 4 步脚本：

```
=== Skill Result: browser_task ===
{
  "task": "...",
  "completed": true,
  "steps": 4,
  "final_answer": "captured title + h1 + screenshot",
  "history": [...]
}
```

`browser-agent-demo.png` 保存在当前工作目录。

## 接入真实 LLM

```python
def my_llm(observation, history, task):
    prompt = f"Task: {task}\nObservation: {observation}\nHistory: {history[-3:]}"
    reply = my_llm_client.generate(prompt)
    return json.loads(reply)

browser_task("在 example-shop.com 找到最便宜的 N95 口罩价格",
             llm_fn=my_llm, max_steps=15)
```

Skill 不关心你用哪家 LLM，只要回调返回合法 action dict。若 LLM 给出未知 `tool`，该步骤记录 `{"ok": false, "detail": "unknown tool: ..."}` 但循环继续。

## 常见失败提示

| 现象 | 可能原因 |
|---|---|
| `KeyError: 'E2B_API_KEY'` | 环境变量未导出 |
| 沙箱创建超时 | `E2B_DOMAIN` 与账号所在地域不匹配 |
| `TencentCloudSDKException` | `TENCENTCLOUD_SECRET_ID` / `SECRET_KEY` 无效或缺失 |
| `completed: false` | LLM 从未发出 `done`，或 `max_steps` 太小 |
| 每步都 `"ok": false, "detail": "unknown tool"` | `llm_fn` 返回 action dict 格式错误——检查 JSON 结构 |
| `playwright TimeoutError` | 目标选择器一直不出现；给 LLM 更丰富的 observation，或调大 `_execute_action` 中的超时 |

## Skill 接口

```python
browser_task(
    task: str,
    llm_fn: Callable[[dict, list[dict], str], dict],
    max_steps: int = 10,
    tool_name: str = "browser-v1",
    timeout: str = "10m",
) -> dict

make_echo_llm(script: list[dict]) -> Callable[[dict, list[dict], str], dict]
```
