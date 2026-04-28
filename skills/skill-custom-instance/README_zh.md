# Skill: Custom Instance（自定义镜像实例）

本示例展示**使用用户自备容器镜像创建沙箱 Tool 并启动实例**。当内置的 `code-interpreter-v1` / `browser-v1` / `aio-v1` 不含所需运行时或二进制时使用本 Skill。

流程对齐 `e2e/basic/custom/custom_tool_test.go`：

1. `CreateSandboxTool(ToolType="custom", CustomConfiguration={Image, Command, Args, Ports, Resources, Probe, Env}, RoleArn=…)`
2. `StartSandboxInstance(ToolId=<新 Tool>)`
3. 通过暴露端口访问实例（URL：`https://<port>-<instanceId>.<region>.tencentags.com/…`，带 `X-Access-Token` 头）
4. `StopSandboxInstance`
5. 可选 `DeleteSandboxTool`

> **仅 AKSK 模式。** 自定义镜像需要 `RoleArn` 和控制面访问权限。

## 它展示了什么

- **`start_custom(image, command, ports, resources, probe, env, role_arn, …)`** — 一次调用完成建 Tool + 启实例；返回 `tool_id`、`instance_id` 和端口名 → 数据面 URL 映射
- **`stop_custom(instance_id, tool_id=None, delete_tool_after=False)`** — 清理

## 前置条件

- Python 3.13（由 `uv` 管理）
- 已安装 `uv`
- 有效的腾讯云凭据
- 已授权拉取目标镜像的 `RoleArn`
- （可选）已验证可用的镜像引用；demo 默认仅作示意，请替换为账号拥有的镜像

## 必要环境变量

```bash
export TENCENTCLOUD_SECRET_ID="your_secret_id"
export TENCENTCLOUD_SECRET_KEY="your_secret_key"
export TENCENTCLOUD_REGION="ap-guangzhou"

# 自定义镜像必须
export AGS_ROLE_ARN="qcs::cam::uin/<uin>:roleName/<role>"

# 可选 —— 覆盖 demo 镜像
export AGS_DEMO_CUSTOM_IMAGE="ags-sandbox-image-pub/python-general:latest"
export AGS_DEMO_CUSTOM_REGISTRY_TYPE="system"    # enterprise | personal | system
```

## 安装与运行

```bash
make setup
make run
```

## 预期输出

```
=== Skill Result: start_custom ===
{
  "tool_id":   "tool-xxxxxxxx",
  "instance_id": "sbi-xxxxxxxx",
  "ports":  [{"Name": "envd", "Port": 49983, "Protocol": "TCP"}],
  "data_plane_urls": {"envd": "https://49983-sbi-xxxxxxxx.ap-guangzhou.tencentags.com/"}
}
```

## 常见失败提示

| 现象 | 可能原因 |
|---|---|
| `KeyError: 'E2B_API_KEY'` | 不适用——本 Skill 仅 AKSK |
| 沙箱创建超时 | `E2B_DOMAIN` 错误（仅影响其它 Skill） |
| `TencentCloudSDKException: InvalidParameter` 在 CreateSandboxTool | 缺 `RoleArn`、`ImageRegistryType` 错误，或镜像不可访问 |
| 实例卡在 `STARTING` | 探针失败——检查 `Probe.HttpGet.{Path,Port,Scheme}` 是否匹配真实就绪端点 |
| 端口 URL 403/401 | nginx/proxy 可能要求 token；请求时带 `X-Access-Token` |

## Skill 接口

```python
start_custom(
    image: str,
    command: list[str],
    role_arn: str | None = None,
    args: list[str] | None = None,
    ports: list[dict] | None = None,
    resources: dict | None = None,
    probe: dict | None = None,
    env: list[dict] | None = None,
    image_registry_type: str = "enterprise",
    tool_name: str | None = None,
    timeout: str = "10m",
) -> dict

stop_custom(instance_id: str, tool_id: str | None = None, delete_tool_after: bool = False) -> dict
```
