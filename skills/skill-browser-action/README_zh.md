# Skill: Browser Action（浏览器自动化）

本示例展示**浏览器自动化** AGS Skill：启动 AGS 浏览器沙箱，通过 CDP + Playwright 连接，执行页面导航、元素提取和截图。

## 它展示了什么

- **`navigate_and_extract`** — 在远程浏览器沙箱中打开 URL，等待 CSS 选择器，返回页面标题和匹配元素的文本
- **`screenshot_page`** — 在远程浏览器沙箱中打开 URL，在本地保存全页面 PNG 截图

凭据模式由 `ags_client.BrowserSandboxSession` 在运行时自动感知——AKSK 控制面模式或 APIKey 直连模式——Skill 主体代码在两种模式下完全一致。AKSK 模式下 CDP URL 由控制面返回的 `(instance_id, token, region)` 三元组构造；APIKey 模式下由 e2b 创建的沙箱构造。

## 前置条件

- Python 3.13（由 `uv` 管理）
- 已安装 `uv`
- 有权访问 `browser-v1` 沙箱模板，认证方式为 AGS API Key **或** 腾讯云 AKSK 凭据（二选一）

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
make setup   # 安装 Python 依赖 + Playwright Chromium
make run
```

## 预期输出

```
INFO Creating browser sandbox (domain=ap-guangzhou.tencentags.com)…
INFO Sandbox id=<sandbox-id>
INFO Navigating to https://example.com…
INFO Killing sandbox…

=== Skill Result: navigate_and_extract ===
{
  "url": "https://example.com",
  "title": "Example Domain",
  "text": "Example Domain",
  "error": null
}

=== Skill Result: screenshot_page ===
{
  "url": "https://example.com",
  "saved_to": "example_screenshot.png",
  "size_bytes": 34521,
  "error": null
}
```

`example_screenshot.png` 保存在当前工作目录。

## 常见失败提示

| 现象 | 可能原因 |
|---|---|
| `KeyError: 'E2B_API_KEY'` | 环境变量未导出 |
| 沙箱创建超时 | `E2B_DOMAIN` 与账号所在地域不匹配 |
| `TencentCloudSDKException` | `TENCENTCLOUD_SECRET_ID` / `SECRET_KEY` 无效或缺失 |
| CDP 连接被拒绝 | 账号中 `browser-v1` 模板不可用 |

## Skill 接口

```python
navigate_and_extract(url: str, selector: str = "body") -> dict
screenshot_page(url: str, local_path: str = "screenshot.png") -> dict
```
