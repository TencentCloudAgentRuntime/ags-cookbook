# Skill: Sandbox Lifecycle（沙箱生命周期管理）

本示例展示 AGS 沙箱实例的**完整控制面生命周期管理**：Start、Pause（Full / Disk 两种模式）、Resume、Describe、List、Stop。这些是让生产级 Agent 在多次工具调用间复用同一个热沙箱、通过暂停空闲实例节省成本的 API。

流程参考 `e2e/basic/auto_pause_resume_test.go` 和 `e2e/framework/pause_resume.go`。

> **仅 AKSK 模式。** 本 Skill 直接调用腾讯云 AGS 控制面，不打开数据面会话。若仅设置了 `E2B_API_KEY`，所有函数都会抛出 `RuntimeError` 并给出明确提示。

## 它展示了什么

- **`start_and_get_status`** — 一次调用完成 `StartSandboxInstance`（可选 `AutoPause` / `AutoResume`）+ `DescribeSandboxInstanceList`
- **`pause_and_resume`** — `PauseSandboxInstance`（`Full` / `Disk` 模式）→ 轮询直到 `PAUSED` → `ResumeSandboxInstance` → 轮询直到 `RUNNING`；返回观测到的状态转换
- **`list_instances`** — `DescribeSandboxInstanceList`，可按 `ToolName` / `ToolId` 过滤
- **`get_instance_status`** — 单实例状态查询
- **`stop`** — `StopSandboxInstance`

## 前置条件

- Python 3.13（由 `uv` 管理）
- 已安装 `uv`
- 有效的腾讯云凭据

## 必要环境变量

```bash
export TENCENTCLOUD_SECRET_ID="your_secret_id"
export TENCENTCLOUD_SECRET_KEY="your_secret_key"
export TENCENTCLOUD_REGION="ap-guangzhou"
```

APIKey 相关变量（`E2B_API_KEY` / `E2B_DOMAIN`）在本 Skill 中被忽略。

## 安装与运行

```bash
make setup
make run
```

## 预期输出

```
=== Skill Result: start_and_get_status ===
{"instance_id": "sbi-xxxxxxxx", "status": "RUNNING", "auto_pause": true, "auto_resume": true}

=== Skill Result: pause_and_resume ===
{
  "instance_id": "sbi-xxxxxxxx",
  "ok": true,
  "pause_mode": "Full",
  "last_status": "RUNNING",
  "transitions": [...]
}
```

状态字符串遵循 AGS 约定：`STARTING` / `RUNNING` / `PAUSING` / `PAUSED` / `RESUMING` / `STOPPED` / `FAILED`。

## 常见失败提示

| 现象 | 可能原因 |
|---|---|
| `KeyError: 'E2B_API_KEY'` | 不适用——本 Skill 仅 AKSK |
| 沙箱创建超时 | `E2B_DOMAIN` 与账号所在地域不匹配（仅影响其它 Skill） |
| `TencentCloudSDKException` | `TENCENTCLOUD_SECRET_ID` / `SECRET_KEY` 无效或缺失 |
| `RuntimeError: pause_instance requires AKSK mode` | 未设置 AKSK 环境变量 |
| `pause_and_resume.ok == false, step: "pause"` | Pause 未在 `wait_s` 内到达 `PAUSED`——实例卡住或镜像不支持暂停 |

## Skill 接口

```python
start_and_get_status(tool_name="code-interpreter-v1", timeout="10m", auto_pause=False, auto_resume=False) -> dict
pause_and_resume(instance_id: str, mode: str = "Full", wait_s: int = 60) -> dict
list_instances(tool_name: str | None = None, tool_id: str | None = None) -> dict
get_instance_status(instance_id: str) -> dict
stop(instance_id: str) -> dict
```
