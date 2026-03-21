# HTML 协作处理示例

本示例展示一个双沙箱 AGS 工作流：一个沙箱编辑 HTML，另一个沙箱在浏览器中渲染并截图。

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

成功运行后，`html_collaboration_output/` 中应包含：

- `demo.html`
- `demo_edited.html`
- `screenshot_before.png`
- `screenshot_after.png`

## 常见失败提示

- 如果浏览器或代码沙箱启动失败，检查 `E2B_API_KEY` 和 `E2B_DOMAIN`
- 如果产物缺失，先清理输出目录再重试，并观察沙箱日志

## 它展示了什么

- 浏览器沙箱与代码沙箱的协作
- 本地与远程沙箱之间的文件传输
- 通过前后截图完成可视化验证
