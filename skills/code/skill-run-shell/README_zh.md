# Skill: Run Shell（Bash 命令执行）

本示例展示在 AGS 沙箱内执行 **bash 命令**——这是 Agent 工作流中最常用的原子操作。封装了 e2b SDK 的 `sandbox.commands.run()`，以 JSON-serialisable dict 返回 `(exit_code, stdout, stderr)` 三元组。

## 它展示了什么

- **`run_shell`** — 执行单条命令，返回 `exit_code`、`stdout`、`stderr`
- **`run_shell_many`** — 在同一沙箱中顺序执行命令列表，首个非零 exit 即停止；适用于 Agent 驱动的多步脚本，每一步都需要前一步成功

凭据模式由 `ags_client.SandboxSession` 在运行时自动感知。

## 前置条件

- Python 3.13（由 `uv` 管理）
- 已安装 `uv`
- AGS API Key **或** 腾讯云 AKSK 凭据（二选一）

## 必要环境变量

二选一：

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

两套变量同时存在时，AKSK 优先。

## 安装与运行

```bash
make setup
make run
```

## 预期输出

```
=== Skill Result: run_shell ===
{
  "cmd": "echo hello && echo boom >&2 && exit 3",
  "exit_code": 3,
  "stdout": "hello\n",
  "stderr": "boom\n"
}

=== Skill Result: run_shell_many ===
{
  "results": [...],
  "failed_at": 2,
  "ok": false
}
```

非零 `exit_code` 不是此 Skill 的错误——它是正常结果，由 Agent 自行决定如何处理。命令超时时 SDK 会抛出 `TimeoutError`。

## 常见失败提示

| 现象 | 可能原因 |
|---|---|
| `KeyError: 'E2B_API_KEY'` | 环境变量未导出 |
| 沙箱创建超时 | `E2B_DOMAIN` 与账号所在地域不匹配 |
| `TencentCloudSDKException` | `TENCENTCLOUD_SECRET_ID` / `SECRET_KEY` 无效或缺失 |
| 命令卡住并最终 `TimeoutError` | 命令运行时间超过 `timeout` —— 调大或改为后台执行 |

## Skill 接口

```python
run_shell(cmd: str, cwd: str | None = None, envs: dict | None = None, timeout: int = 60) -> dict
run_shell_many(cmds: list[str], timeout: int = 60) -> dict
```
