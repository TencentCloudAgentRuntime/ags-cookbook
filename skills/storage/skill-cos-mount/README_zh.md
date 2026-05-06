# Skill: COS-Mounted Sandbox（COS 挂载沙箱）

本示例展示**跨沙箱实例的持久化存储**：把 COS（对象存储）桶挂载进沙箱文件系统，`mount_path` 下写入的文件在实例销毁后仍保留，并在下一个挂载相同 bucket+path 的实例中可见——这是让短生命周期沙箱之间共享状态的标准做法。

流程对齐 `e2e/storage/cos_mount/*`。

> **仅 AKSK 模式。** COS 挂载配置是控制面专属能力。

## 它展示了什么

- **`start_cos_sandbox(cos_bucket, cos_path, mount_path, role_arn, …)`** — 建 Tool + 启实例
- **`write_then_read_across_instances(cos_bucket, cos_path, mount_path, content)`** — 完整演示：启 A → 写入 → 停 A → 启 B → 读取 → 停 B → 验证 `match == True`
- **`stop_cos_sandbox(instance_id, tool_id=None, delete_tool_after=False)`** — 清理

## 前置条件

- Python 3.13（由 `uv` 管理）
- 已安装 `uv`
- 有效的腾讯云凭据
- 自有 COS 桶和授权 AGS 读写对应路径的 `RoleArn`

## 必要环境变量

```bash
export TENCENTCLOUD_SECRET_ID="your_secret_id"
export TENCENTCLOUD_SECRET_KEY="your_secret_key"
export TENCENTCLOUD_REGION="ap-guangzhou"

export AGS_ROLE_ARN="qcs::cam::uin/<uin>:roleName/<role>"
export AGS_DEMO_COS_BUCKET="my-bucket-1300000000"
export AGS_DEMO_COS_PATH="skills-demo/"
export AGS_DEMO_COS_MOUNT="/mnt/cos"
```

## 安装与运行

```bash
make setup
make run
```

## 预期输出

```
=== Skill Result: write_then_read_across_instances ===
{
  "written_in": "sbi-AAAAAAAA",
  "read_from":  "sbi-BBBBBBBB",
  "match":      true,
  "round_trip_bytes": 32
}
```

`match == true` 证明 A 写入的文件已持久化到 COS 并在 B 实例中被正确挂载。

## 常见失败提示

| 现象 | 可能原因 |
|---|---|
| `KeyError: 'E2B_API_KEY'` | 不适用——本 Skill 仅 AKSK |
| 沙箱创建超时 | `E2B_DOMAIN` 错误（仅影响其它 Skill） |
| `TencentCloudSDKException` | `TENCENTCLOUD_SECRET_ID` / `SECRET_KEY` 无效或缺失 |
| `InvalidParameter` 在 CreateSandboxTool | 缺 `RoleArn`，或 bucket 不在 AGS 同地域 |
| `retrieved != expected` | COS 同步延迟；重试或在 write 与启 B 之间加 sleep |
| 沙箱内写入 `AccessDenied` | `RoleArn` 缺 `cos:PutObject` 权限 |

## Skill 接口

```python
start_cos_sandbox(cos_bucket, cos_path, mount_path, *, role_arn=None, tool_type="code-interpreter", tool_name=None, timeout="10m", read_only=False) -> dict
write_then_read_across_instances(cos_bucket, cos_path, mount_path, content="…", *, role_arn=None, timeout="10m") -> dict
stop_cos_sandbox(instance_id, tool_id=None, delete_tool_after=False) -> dict
```
