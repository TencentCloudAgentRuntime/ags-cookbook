# Skills Hello World

本示例展示 AGS **最小可运行的 Skills 接入**：

1. 通过 `tencentcloud-sdk-python` 验证腾讯云凭据
2. 通过 `e2b-code-interpreter` 在 AGS 沙箱中执行代码
3. 返回可被 Agent 解析的结构化结果

## 它展示了什么

- AGS Skills 示例的标准工程结构（Python 3.13、`uv`、`pyproject.toml`）
- 如何在同一项目中同时使用 `tencentcloud-sdk-python` 和 `e2b-code-interpreter`
- 一个 Agent 可注册为工具的可调用 `run_code` Skill

## 前置条件

- Python 3.13（由 `uv` 管理）
- 已安装 `uv`
- AGS API Key（`E2B_API_KEY`）
- 腾讯云凭据（`TENCENTCLOUD_SECRET_ID`、`TENCENTCLOUD_SECRET_KEY`）——仅凭据健康检查时需要

## 必要环境变量

将 `.env.example` 复制为 `.env` 并填入实际值，然后导出：

```bash
cp .env.example .env
# 编辑 .env，然后：
export E2B_API_KEY="your_ags_api_key"
export E2B_DOMAIN="ap-guangzhou.tencentags.com"

# 可选——仅在需要凭据健康检查时填写
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
INFO Creating sandbox (domain=ap-guangzhou.tencentags.com)…
INFO Sandbox closed.

=== Skill Result ===
{
  "stdout": "372\n",
  "logs": {
    "stdout": ["372\n"],
    "stderr": []
  },
  "error": null
}
```

## 常见失败提示

| 现象 | 可能原因 |
|---|---|
| `KeyError: 'E2B_API_KEY'` | 环境变量未导出 |
| 沙箱创建超时 | `E2B_DOMAIN` 与账号所在地域不匹配 |
| 凭据检查抛出 `TencentCloudSDKException` | `TENCENTCLOUD_SECRET_ID` / `SECRET_KEY` 无效或缺失 |

## Skill 接口契约

Skill 是一个签名清晰的普通 Python 可调用对象：

```python
def skill_name(arg1: type, ...) -> dict:
    ...
```

- 参数来自 Agent 的 tool-call payload
- 返回值必须可 JSON 序列化，供 Agent 解析
- 密钥始终从环境变量读取——严禁硬编码
