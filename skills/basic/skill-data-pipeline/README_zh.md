# Skill: Data Pipeline（多 Context 数据流水线）

本示例是 `examples/data-analysis` 的 Skill 化版本：**多阶段流水线**，每个阶段运行在独立的 Python code context（变量不泄漏），所有阶段**共享沙箱文件系统**——阶段 N 写的文件对阶段 N+1 可见。

这是 AGS 多 Context 能力的典型用法，也是 Agent 协调 load → transform → chart 工作流的最佳方式，无需创建多个沙箱。

## 它展示了什么

- **`run_pipeline(stages, downloads=None)`** — 在一个沙箱中顺序执行 `{name, code, writes?}` 列表；结束后可选下载声明的产物；遇到失败阶段即停止，但仍会下载已生成的产物

变量隔离由每阶段一个 `sbx.create_code_context()` 保证；文件共享走 `/tmp/*`。

## 前置条件

- Python 3.13（由 `uv` 管理）
- 已安装 `uv`
- AGS API Key **或** 腾讯云 AKSK 凭据
- 阶段代码依赖的库需在沙箱模板中预装（`code-interpreter-v1` 已含 pandas + matplotlib）

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
make setup
make run
```

## 预期输出

```
=== Skill Result: run_pipeline ===
{
  "stages": [...],
  "downloads": [
    {"remote": "/tmp/summary.json", "saved_to": "summary.json", "size": 150},
    {"remote": "/tmp/chart.png",    "saved_to": "chart.png",    "size": 25431}
  ],
  "ok": true
}
```

`summary.json` 和 `chart.png` 保存在当前工作目录。

## 常见失败提示

| 现象 | 可能原因 |
|---|---|
| `KeyError: 'E2B_API_KEY'` | 环境变量未导出 |
| 沙箱创建超时 | `E2B_DOMAIN` 与账号所在地域不匹配 |
| `TencentCloudSDKException` | `TENCENTCLOUD_SECRET_ID` / `SECRET_KEY` 无效或缺失 |
| 后续阶段 `FileNotFoundError` | 前一阶段未真正写入 `writes` 路径；`writes` 仅是元数据，不做强制 |
| 后续阶段 `NameError` | 记住：**变量不跨阶段共享**，只共享文件 |

## Skill 接口

```python
run_pipeline(
    stages: list[dict],
    downloads: list[str] | None = None,
    tool_name: str = "code-interpreter-v1",
    timeout: str = "10m",
) -> dict
```
