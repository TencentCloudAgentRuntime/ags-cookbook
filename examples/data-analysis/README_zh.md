# Data Analysis 示例

本示例展示一个多 Context 的 AGS 数据工作流：数据清洗、分析与可视化在隔离的 Context 中完成，并通过沙箱文件系统交换产物。

## 前置条件

- Python >= 3.12
- `uv`
- `E2B_API_KEY`
- 必填 `E2B_DOMAIN`

## 必要环境变量

```bash
export E2B_API_KEY="your_ags_api_key"
export E2B_DOMAIN="ap-guangzhou.tencentags.com"
```

## 本地命令

```bash
make setup
make run
```

## 预期输出

成功运行后，`enhanced_demo_output/` 中应包含图表和报告文件，例如：

- `data_cleaning_comparison.png`
- `advanced_dashboard.png`
- `correlation_heatmap.png`
- `analysis_report.json`

## 常见失败提示

- 如果沙箱创建失败，检查 `E2B_API_KEY` 和 `E2B_DOMAIN`
- 如果你的账号是地域隔离的，建议显式设置区域域名，而不是依赖历史默认值

## 它展示了什么

- 多个 AGS 执行 Context 之间的真实隔离
- 通过文件系统完成产物交接
- 比单脚本演示更接近真实业务的数据处理流水线
