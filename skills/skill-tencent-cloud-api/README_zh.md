# Skill: Tencent Cloud API（腾讯云 API）

本示例展示使用 `tencentcloud-sdk-python` 进行**腾讯云控制面调用**的 AGS Skill。

## 它展示了什么

- **`get_caller_identity`** — 通过 STS `GetCallerIdentity` 验证腾讯云凭据，返回调用方的 `AccountId`、`ARN` 和 `UserId`
- **`list_sandbox_images`** — 通过 AGS API 列出指定地域可用的沙箱镜像模板；当 API 端点暂不可访问时，优雅降级为具有代表性的静态列表

> **说明** —— 与本目录下其它 skill 不同，`skill-tencent-cloud-api` **仅支持 AKSK 模式**：它演示的控制面调用本身就归属于腾讯云账号。因此它不使用 `ags_client.SandboxSession`（不创建沙箱），APIKey 模式也不适用。

## 前置条件

- Python 3.13（由 `uv` 管理）
- 已安装 `uv`
- 有效的腾讯云凭据（`TENCENTCLOUD_SECRET_ID` / `SECRET_KEY`）

## 必要环境变量

```bash
export TENCENTCLOUD_SECRET_ID="your_secret_id"
export TENCENTCLOUD_SECRET_KEY="your_secret_key"
export TENCENTCLOUD_REGION="ap-guangzhou"

# 可选——仅在 AGS API 可访问时由 list_sandbox_images 使用
export E2B_API_KEY="your_ags_api_key"
export E2B_DOMAIN="ap-guangzhou.tencentags.com"
```

## 安装与运行

```bash
make setup
make run
```

## 预期输出

```
INFO get_caller_identity: verifying credentials (region=ap-guangzhou)…
INFO Credential OK — AccountId=100xxxxxxxxx

=== Skill Result: get_caller_identity ===
{
  "account_id": "100xxxxxxxxx",
  "arn": "qcs::cam::uin/100xxxxxxxxx:root",
  "user_id": "100xxxxxxxxx",
  "error": null
}

=== Skill Result: list_sandbox_images ===
{
  "region": "ap-guangzhou",
  "images": [
    {"image_id": "code-interpreter-v1", "name": "Code Interpreter v1", "type": "builtin"},
    …
  ],
  "source": "api",
  "error": null
}
```

当 AGS API 模块暂不可用时，`source` 为 `"static_fallback"`，`error` 包含导入或 SDK 错误信息。

## 常见失败提示

| 现象 | 可能原因 |
|---|---|
| `KeyError: 'E2B_API_KEY'` | 环境变量未导出 |
| 沙箱创建超时 | `E2B_DOMAIN` 与账号所在地域不匹配 |
| `TencentCloudSDKException` | `TENCENTCLOUD_SECRET_ID` / `SECRET_KEY` 无效或缺失 |

## Skill 接口

```python
get_caller_identity() -> dict
list_sandbox_images(region: str | None = None) -> dict
```
