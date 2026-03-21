# Mobile Automation：基于云端沙箱的移动端自动化

本示例展示如何在 AGS 中运行 Android 设备，并使用 Appium 执行移动端自动化任务。

## 架构

```text
┌─────────────┐     Appium      ┌─────────────┐      ADB       ┌───────────────┐
│   Python    │ ───────────────▶│   Appium    │ ─────────────▶│      AGS      │
│   Script    │                 │   Driver    │               │   (Android)   │
└─────────────┘                 └─────────────┘               └───────────────┘
      ▲                                │                              │
      │                                │◀─────────────────────────────┘
      │                                │         Device State / Result
      └────────────────────────────────┘
                      Response
```

## 前置条件

- Python >= 3.12
- `uv`
- `E2B_API_KEY`
- `SANDBOX_TEMPLATE`
- 必填 `E2B_DOMAIN`（例如 `ap-guangzhou.tencentags.com`）

## 本地命令

```bash
make setup
make run
```

额外脚本：

```bash
uv run batch.py
uv run sandbox_connect.py --help
```

## 必要环境变量

```bash
export E2B_API_KEY="your_ags_api_key"
export E2B_DOMAIN="ap-guangzhou.tencentags.com"
export SANDBOX_TEMPLATE="mobile-v1"
```

## 便于本地验证的运行控制

如果你只是做一次本地 smoke，可以缩短 quickstart 的长时间运行阶段：

```bash
export LONG_RUN_SECONDS=0
export LONG_RUN_RESERVE_SECONDS=0
```

## `sandbox_connect.py`

`sandbox_connect.py` 用于连接一个已存在的沙箱并执行指定动作。

常见用法：

```bash
uv run sandbox_connect.py --sandbox-id <sandbox_id> --action <action> [其他参数]
```

例如：

```bash
uv run sandbox_connect.py --sandbox-id abc123 --action device_info
uv run sandbox_connect.py --sandbox-id abc123 --action screenshot
uv run sandbox_connect.py --sandbox-id abc123 --action tap_screen --tap-x 500 --tap-y 1000
uv run sandbox_connect.py --sandbox-id abc123 --action click_element --element-text "登录"
```

## 常见失败提示

- 如果设备或 Appium 连接失败，检查 `E2B_API_KEY`、`E2B_DOMAIN`、`SANDBOX_TEMPLATE`
- 如果流程耗时过长，先使用 `LONG_RUN_SECONDS=0` 和 `LONG_RUN_RESERVE_SECONDS=0` 做一次快速验证
- 如果需要上传 APK，请确认 `apk/` 目录下已有对应文件，或你的下载配置可用

## 它展示了什么

- 在 AGS 中运行 Android 设备并通过 Appium 远程控制
- quickstart、batch 与 sandbox_connect 三种不同使用路径
- 屏幕操作、元素点击、位置模拟与批量执行等移动端自动化能力
