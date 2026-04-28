# Skill: Data Analysis（数据分析）

本示例展示**沙箱数据分析与图表生成** AGS Skill：将 CSV 上传到沙箱、在沙箱内运行 pandas 聚合和 matplotlib 图表生成、在本地保存 PNG 文件，并返回汇总统计数据。

## 它展示了什么

- **`analyse_csv`** — 将 CSV 字符串上传到沙箱，对数值列按指定字段计算分组 `sum / mean / count`，通过 matplotlib 生成柱状图，下载 PNG 到本地，以记录列表形式返回摘要

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
INFO analyse_csv: group_by=category value_col=revenue
INFO Uploaded 256 bytes to /tmp/input.csv
INFO Chart saved to revenue_by_category.png (42351 bytes)
INFO analyse_csv: done, error=None

=== Skill Result: analyse_csv ===
{
  "summary": [
    {"category": "Electronics", "sum": 24800.0, "mean": 12400.0, "count": 2},
    {"category": "Home",        "sum": 15900.0, "mean":  7950.0, "count": 2},
    …
  ],
  "chart_path": "revenue_by_category.png",
  "stdout": ["…", "chart saved"],
  "error": null
}
```

`revenue_by_category.png` 保存在当前工作目录。

## 常见失败提示

| 现象 | 可能原因 |
|---|---|
| `KeyError: 'E2B_API_KEY'` | 环境变量未导出 |
| 沙箱创建超时 | `E2B_DOMAIN` 与账号所在地域不匹配 |
| `TencentCloudSDKException` | `TENCENTCLOUD_SECRET_ID` / `SECRET_KEY` 无效或缺失 |
| 沙箱内 `KeyError: <column>` | `group_by` 或 `value_col` 不存在于 CSV 表头 |

## Skill 接口

```python
analyse_csv(
    csv_text: str,
    group_by: str,
    value_col: str,
    chart_path: str = "chart.png",
) -> dict
```

返回 `summary`（记录列表）、`chart_path`（本地 PNG 路径）、`stdout` 和 `error`。
