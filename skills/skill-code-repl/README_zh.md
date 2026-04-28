# Skill: Code REPL（持久 Python REPL）

本示例展示**跨 Agent 工具调用持久化的 Python REPL 上下文**。`skill-code-interpreter` 每次调用都会新建沙箱（变量不保留），本 Skill 通过 `repl_id` 缓存沙箱+code context，Agent 在多轮之间传递该 id 即可复用。

## 它展示了什么

- **`create_repl`** — 启动沙箱+code context，返回 `repl_id`
- **`run_in_repl(repl_id, code)`** — 在缓存的 context 中执行代码，可选 `on_stdout` 回调；第 N 轮定义的变量第 N+1 轮可见
- **`close_repl(repl_id)`** — 释放沙箱
- **`list_repls()`** — 列举所有活跃 REPL

缓存是**进程本地**的（普通 dict）。多进程部署时请自行接入共享存储（Redis、数据库等）。

凭据模式由 `ags_client.SandboxSession` 自动感知。

## 前置条件

- Python 3.13（由 `uv` 管理）
- 已安装 `uv`
- AGS API Key **或** 腾讯云 AKSK 凭据

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

```
=== Skill Result: run_in_repl (turn 2) ===
{"repl_id": "...", "turn": 2, "stdout": ["7! = 5040\n"], ...}
```

第 2、3 轮成功读取第 1 轮定义的 `x` 和 `math`，这是"持久 REPL"成立的标志。

## 常见失败提示

| 现象 | 可能原因 |
|---|---|
| `KeyError: 'E2B_API_KEY'` | 环境变量未导出 |
| 沙箱创建超时 | `E2B_DOMAIN` 与账号所在地域不匹配 |
| `TencentCloudSDKException` | `TENCENTCLOUD_SECRET_ID` / `SECRET_KEY` 无效或缺失 |
| `"error": "unknown repl_id"` | id 来自其它进程；REPL 缓存是进程本地的 |
| 沙箱中途被回收 | 超过 `timeout` 空闲时长——调大 `create_repl` 的 `timeout` 参数 |

## Skill 接口

```python
create_repl(timeout: str = "30m") -> dict
run_in_repl(repl_id: str, code: str, on_stdout=None) -> dict
close_repl(repl_id: str) -> dict
list_repls() -> dict
```
