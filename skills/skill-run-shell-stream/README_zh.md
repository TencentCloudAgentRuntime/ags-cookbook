# Skill: Run Shell Stream（流式 Bash 命令执行）

本示例展示**实时流式命令执行**：长任务的 `stdout` / `stderr` 以 chunk 形式逐段推给调用方回调，而不是等命令结束才一次返回。流程与 AGS e2e 框架中的 `ExecCommandStream`（`e2e/basic/sandbox_operations_test.go` → "Streaming Output"）一致。

## 它展示了什么

- **`run_shell_stream`** — 每个 `stdout` / `stderr` chunk 到达时立刻调用 `on_chunk`；回调参数形如 `{"type", "data", "t"}`
- **`run_shell_collect_chunks`** — 缓冲版本，返回 chunks 列表、总 chunk 数和横跨的不同秒数（验证"确实在流式"的代理指标）

凭据模式由 `ags_client.SandboxSession` 在运行时自动感知。

## 前置条件

- Python 3.13（由 `uv` 管理）
- 已安装 `uv`
- AGS API Key **或** 腾讯云 AKSK 凭据（二选一）

## 必要环境变量

```bash
# 方式 A —— APIKey 模式
export E2B_API_KEY="your_ags_api_key"
export E2B_DOMAIN="ap-guangzhou.tencentags.com"
```

```bash
# 方式 B —— AKSK 模式
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
[stdout@0.0s] tick 1
[stdout@1.0s] tick 2
…

=== Skill Result: run_shell_stream ===
{"cmd": "...", "exit_code": 0, "duration_s": 5.123}
```

`distinct_seconds ≥ 2` 说明输出确实是流式传回的，而不是在命令结束后一次性返回。

## 常见失败提示

| 现象 | 可能原因 |
|---|---|
| `KeyError: 'E2B_API_KEY'` | 环境变量未导出 |
| 沙箱创建超时 | `E2B_DOMAIN` 与账号所在地域不匹配 |
| `TencentCloudSDKException` | `TENCENTCLOUD_SECRET_ID` / `SECRET_KEY` 无效或缺失 |
| chunk 在命令结束时才一次到达 | 进程未刷新缓冲（如 `python` 未加 `-u`）；可用 `stdbuf -o0 …` |

## Skill 接口

```python
run_shell_stream(cmd: str, on_chunk: Callable[[dict], None], cwd=None, envs=None, timeout=300) -> dict
run_shell_collect_chunks(cmd: str, cwd=None, envs=None, timeout=300) -> dict
```
