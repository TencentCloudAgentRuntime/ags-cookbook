# Skill: NoAuth Sandbox（无 Token 沙箱）

本示例展示**以 `AuthMode=NONE` 启动沙箱**——禁用所有数据面请求的 `X-Access-Token` 校验。仅适用于数据面 URL 仅在可信内网中可达的场景（参考 `e2e/basic/noauth_test.go`）。

与默认 `TOKEN` 模式对比：

| 模式 | 行为 |
|---|---|
| `DEFAULT` / `TOKEN` | 每次数据面请求必须带 `X-Access-Token: <token>`。缺失/无效 → 401/403。 |
| `NONE` | 数据面不做鉴权，所有请求直达后端。 |

> **仅 AKSK 模式。** `AuthMode` 是控制面参数。

## 它展示了什么

- **`start_noauth(tool_name, timeout)`** — `StartSandboxInstance` 带 `AuthMode=NONE`；返回 `instance_id` 和预构造的数据面 URL
- **`probe_noauth(instance_id, path)`** — 对数据面 GET 两次（带 token / 不带 token），通过状态码对比证明 NoAuth 生效
- **`stop_noauth(instance_id)`** — 清理

## 前置条件

- Python 3.13（由 `uv` 管理）
- 已安装 `uv`
- 有效的腾讯云凭据
- Tool 镜像在 9000 端口暴露 `/health`（`code-interpreter-v1` / `browser-v1` / `aio-v1` 均满足）

## 必要环境变量

```bash
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
=== Skill Result: probe_noauth ===
{
  "with_token":    {"status": 200, "body_head": "ok"},
  "without_token": {"status": 200, "body_head": "ok"},
  "same_status": true,
  "token_required_for_access": false
}
```

`"same_status": true` + `"token_required_for_access": false` 即 NoAuth 生效的证据：不带 token 的请求也成功。

将实例改用默认 `TOKEN` 模式启动（通过 `skill-sandbox-lifecycle.start_and_get_status` → `probe_noauth`），`without_token.status` 会变为 401，`token_required_for_access` 变为 `true`。

## 常见失败提示

| 现象 | 可能原因 |
|---|---|
| `KeyError: 'E2B_API_KEY'` | 不适用——本 Skill 仅 AKSK |
| 沙箱创建超时 | `E2B_DOMAIN` 错误（仅影响其它 Skill） |
| `TencentCloudSDKException` 在 `StartSandboxInstance` | 凭据错误，或 Tool 不支持 `AuthMode=NONE` |
| `AuthMode=NONE` 但 `without_token` 仍 401/403 | 反向代理缓存；稍等后重试，或实例仍在 `STARTING` |
| `httpx.ConnectError` | 数据面 URL 尚不可达——`start_instance` 返回早于 `/health` 就绪；加短暂 sleep |

## Skill 接口

```python
start_noauth(tool_name: str = "code-interpreter-v1", timeout: str = "10m") -> dict
probe_noauth(instance_id: str, path: str = "/health", port: int = 9000) -> dict
stop_noauth(instance_id: str) -> dict
```
