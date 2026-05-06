# Skill: Browser Interact（浏览器交互）

本示例补充 `skill-browser-action` 只能做导航/截图/文本抽取的不足，提供 Agent 真正**驱动**页面所需的原语：click、fill、执行 JS、多 Tab、注入 cookie、构造 NoVNC URL（让人类实时观看会话）。

所有 Skill 通过 CDP + Playwright 连接 AGS 浏览器沙箱，凭据模式由 `ags_client.BrowserSandboxSession` 自动感知。

## 它展示了什么

- **`click(url, selector)`** — 点击首个匹配元素
- **`fill(url, selector, text)`** — 向表单输入框输入文本
- **`get_page_text(url, selector="body")`** — 完整 `inner_text()`（不截断到 2000 字符）
- **`evaluate_js(url, expression)`** — 执行 JS 并返回值
- **`multi_tab(urls)`** — 每个 URL 开独立 Tab，收集标题
- **`inject_cookies(url, cookies)`** — 预先注入 cookie，导航后读取服务端回种的 cookie
- **`get_vnc_url()`** — 构造 `https://9000-<id>.<region>.tencentags.com/novnc/` 和 token；沙箱保持运行直到显式停止

## 前置条件

- Python 3.13（由 `uv` 管理）
- 已安装 `uv`
- 有权访问 `browser-v1` 沙箱模板，认证方式为 AGS API Key **或** 腾讯云 AKSK

## 必要环境变量

```bash
# 方式 A
export E2B_API_KEY="your_ags_api_key"
export E2B_DOMAIN="ap-guangzhou.tencentags.com"
```

```bash
# 方式 B
export TENCENTCLOUD_SECRET_ID="your_secret_id"
export TENCENTCLOUD_SECRET_KEY="your_secret_key"
export TENCENTCLOUD_REGION="ap-guangzhou"
```

## 安装与运行

```bash
make setup     # 安装 Python 依赖 + Playwright Chromium
make run
```

## 预期输出

```
=== Skill Result: evaluate_js ===
{"value": {"title": "Example Domain", "links": 1}, ...}

=== Skill Result: multi_tab ===
{"count": 2, "tabs": [{"title": "Example Domain"}, ...]}
```

## 常见失败提示

| 现象 | 可能原因 |
|---|---|
| `KeyError: 'E2B_API_KEY'` | 环境变量未导出 |
| 沙箱创建超时 | `E2B_DOMAIN` 与账号所在地域不匹配 |
| `TencentCloudSDKException` | `TENCENTCLOUD_SECRET_ID` / `SECRET_KEY` 无效或缺失 |
| `playwright._impl._errors.TimeoutError` | 选择器未在 `timeout_ms` 内出现；放宽或调大 |
| NoVNC URL 401 | 浏览器未携带 `X-Access-Token`；若 nginx 支持可改用 `?token=` |

## Skill 接口

```python
click(url: str, selector: str, timeout_ms: int = 10000) -> dict
fill(url: str, selector: str, text: str, timeout_ms: int = 10000) -> dict
get_page_text(url: str, selector: str = "body") -> dict
evaluate_js(url: str, expression: str) -> dict
multi_tab(urls: list[str]) -> dict
inject_cookies(url: str, cookies: list[dict]) -> dict
get_vnc_url(tool_name: str = "browser-v1", timeout: str = "10m") -> dict
```
