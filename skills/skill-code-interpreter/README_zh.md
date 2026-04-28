# Skill: Code Interpreter（代码解释器）

本示例展示**在沙箱内执行代码**的 AGS Skill，Agent 可将其作为工具调用。

## 它展示了什么

- **`run_code`** — 在全新的 AGS 沙箱中执行任意 Python 代码片段，以结构化 dict 的形式返回 `stdout` 和错误信息
- **`run_code_multi_context`** — 在**同一**沙箱中运行多个代码片段，每个片段位于独立的执行 context；验证 Python 变量在不同 context 之间互不可见，但 `/tmp` 文件系统仍共享

凭据模式由 `ags_client.SandboxSession` 在运行时自动感知——AKSK 控制面模式或 APIKey 直连模式——Skill 主体代码在两种模式下完全一致。

## 前置条件

- Python 3.13（由 `uv` 管理）
- 已安装 `uv`
- AGS API Key **或** 腾讯云 AKSK 凭据（二选一）

## 必要环境变量

二选一：

```bash
# 方式 A —— APIKey 模式（直连沙箱）
export E2B_API_KEY="your_ags_api_key"
export E2B_DOMAIN="ap-guangzhou.tencentags.com"
```

```bash
# 方式 B —— AKSK 模式（通过腾讯云 AGS 控制面）
export TENCENTCLOUD_SECRET_ID="your_secret_id"
export TENCENTCLOUD_SECRET_KEY="your_secret_key"
export TENCENTCLOUD_REGION="ap-guangzhou"
```

两套变量同时存在时，AKSK 模式优先（详见 `ags_client.credential_mode()`）。

## 安装与运行

```bash
make setup
make run
```

## 预期输出

```
INFO SandboxSession: mode=apikey tool=code-interpreter-v1 timeout=10m
INFO APIKey sandbox created (template=code-interpreter-v1, timeout=300s).
INFO APIKey sandbox killed.

=== Skill Result: run_code ===
{
  "stdout": ["2^10 = 1024\n", "Python 3.x.x …\n"],
  "text_results": [],
  "error": null
}

=== Skill Result: run_code_multi_context ===
{
  "contexts": [
    {"context_index": 0, "stdout": ["[ctx0] ctx A secret: context-A-only\n"], "error": null},
    {"context_index": 1, "stdout": ["[ctx1] ctx B: secret is NOT visible — isolation confirmed\n"], "error": null}
  ]
}
```

AKSK 模式下日志前缀为 `mode=aksk`，实例 ID 为真实的 AGS 沙箱 ID。

## 常见失败提示

| 现象 | 可能原因 |
|---|---|
| `KeyError: 'E2B_API_KEY'` | 环境变量未导出 |
| 沙箱创建超时 | `E2B_DOMAIN` 与账号所在地域不匹配 |
| `TencentCloudSDKException` | `TENCENTCLOUD_SECRET_ID` / `SECRET_KEY` 无效或缺失 |

## Skill 接口

```python
run_code(code: str) -> dict
run_code_multi_context(snippets: list[str]) -> dict
```

两者均返回 JSON-serialisable dict，可直接被 Agent 消费。
