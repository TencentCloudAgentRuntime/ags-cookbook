# Skill: File Sandbox（沙箱文件 I/O）

本示例展示**沙箱文件系统读写** AGS Skill：将数据上传到沙箱、在沙箱内执行代码变换、下载结果——全部在一次 Skill 调用中完成。

## 它展示了什么

- **`upload_and_run`** — 将文本内容写入沙箱路径，执行读写沙箱文件的 Python 变换脚本，然后下载并返回结果文件内容
- **`list_sandbox_dir`** — 返回全新沙箱中指定路径的目录列表

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
INFO upload_and_run: creating sandbox…
INFO uploaded 52 bytes → /tmp/scores.csv
INFO downloaded 128 bytes ← /tmp/ranked.json
INFO upload_and_run: sandbox closed.

=== Skill Result: upload_and_run ===
{
  "uploaded": "/tmp/scores.csv",
  "stdout": ["sorted 3 rows"],
  "result_content": "[\n  {\"name\": \"Charlie\", \"score\": \"95\"},\n  …\n]",
  "error": null
}
```

## 常见失败提示

| 现象 | 可能原因 |
|---|---|
| `KeyError: 'E2B_API_KEY'` | 环境变量未导出 |
| 沙箱创建超时 | `E2B_DOMAIN` 与账号所在地域不匹配 |
| `TencentCloudSDKException` | `TENCENTCLOUD_SECRET_ID` / `SECRET_KEY` 无效或缺失 |

## Skill 接口

```python
upload_and_run(local_text: str, remote_path: str, transform_code: str, result_path: str) -> dict
list_sandbox_dir(path: str = "/tmp") -> dict
```
