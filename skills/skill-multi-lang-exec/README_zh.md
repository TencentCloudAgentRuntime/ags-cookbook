# Skill: Multi-Language Code Execution（多语言代码执行·AIO）

本示例展示 AIO 沙箱镜像在 49999 端口提供的 uvicorn `/execute` 接口的**多语言代码执行**能力。与 code-interpreter（仅 Python）不同，AIO 单次 HTTP 请求即可执行 `python` / `javascript` / `bash` / `r` / `java`，返回 NDJSON 流（`stdout` / `result` / `error` 事件）。

契约对齐 `e2e/aio/aio_dataplane_test.go` uvicorn 章节。

## 它展示了什么

- **`run_code(code, language)`** — 一次调用，返回 `{stdout, result, error}`
- **`run_many(snippets)`** — 同一个 AIO 沙箱连续执行多个片段（无状态——跨调用不保留语言级状态；若需持久 Python 状态请用 `skill-code-repl`）
- **`get_host_info()`** — 返回沙箱各端口/路径 URL，便于 Agent 自行扩展调用 `/execute`、`/contexts`、`/novnc/`、`/vscode/`

## 前置条件

- Python 3.13（由 `uv` 管理）
- 已安装 `uv`
- 有权访问 AIO 沙箱模板（默认 `aio-v1`），认证方式为 AGS API Key 或腾讯云 AKSK

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
=== Skill Result: run_code (python) ===
{"stdout": "hello from python\n5050\n", ...}

=== Skill Result: run_code (bash) ===
{"stdout": "hello from bash\n12\n", ...}
```

各语言输出风格就是该语言原生 `print` 的行为；R 的 `cat()` 不自动换行，Java 需要 `public class`。

## 常见失败提示

| 现象 | 可能原因 |
|---|---|
| `KeyError: 'E2B_API_KEY'` | 环境变量未导出 |
| 沙箱创建超时 | `E2B_DOMAIN` 与账号所在地域不匹配 |
| `TencentCloudSDKException` | `TENCENTCLOUD_SECRET_ID` / `SECRET_KEY` 无效或缺失 |
| `status_code == 404` | Tool 不是 AIO 镜像——改用 `aio-v1`（或账号对应模板） |
| `httpx.ReadTimeout` | 代码超过 120s 客户端超时；拆成更小片段 |
| `error.name == "SyntaxError"` | 服务端解释器拒绝代码；查看 `error.traceback` |

## Skill 接口

```python
run_code(code: str, language: str = "python", tool_name: str = "aio-v1", timeout: str = "10m") -> dict
run_many(snippets: list[dict], tool_name: str = "aio-v1", timeout: str = "10m") -> dict
get_host_info(tool_name: str = "aio-v1", timeout: str = "10m") -> dict
```
