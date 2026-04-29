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
- `E2B_API_KEY`
- `SANDBOX_TEMPLATE`
- 必填 `E2B_DOMAIN`（例如 `ap-guangzhou.tencentags.com`）

## 安装依赖

```bash
pip install -r requirements.txt
```

或使用 make：

```bash
make setup
```

## 本地命令

```bash
make run
```

额外脚本：

```bash
python batch.py
python sandbox_connect.py --help
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
python sandbox_connect.py --sandbox-id <sandbox_id> --action <action> [其他参数]
```

例如：

```bash
python sandbox_connect.py --sandbox-id abc123 --action device_info
python sandbox_connect.py --sandbox-id abc123 --action screenshot
python sandbox_connect.py --sandbox-id abc123 --action tap_screen --tap-x 500 --tap-y 1000
python sandbox_connect.py --sandbox-id abc123 --action click_element --element-text "登录"
```

上传、安装、授权并打开应用宝（逗号分隔批量操作）：

```bash
python sandbox_connect.py --sandbox-id abc123 --action upload_app,install_app,grant_app_permissions,launch_app --app-name yyb
```

## 批量工具

批量工具统一通过 `sandboxes.yaml` 配置文件传入沙箱 ID：

```yaml
sandbox_ids:
  - sandbox_id_1
  - sandbox_id_2
  - sandbox_id_3
```

### 批量获取 logcat 日志

从现有沙箱批量获取全量 logcat 日志，按沙箱 ID 分目录保存，不会删除沙箱：

```bash
# 使用默认 sandboxes.yaml
python batch_dump_logcat.py

# 指定配置文件和并发数
python batch_dump_logcat.py --config my_sandboxes.yaml --concurrency 10

# 自定义输出目录
python batch_dump_logcat.py --output-dir /tmp/logcat
```

### 批量销毁沙箱

销毁沙箱前会列出所有目标并要求手动确认（输入 y/yes 确认，n/no 取消）：

```bash
# 使用默认 sandboxes.yaml，需确认
python batch_sandbox_kill.py

# 跳过确认
python batch_sandbox_kill.py --yes
```

### 批量创建沙箱

```bash
python batch_sandbox_create.py
```

创建的沙箱 ID 会保存到 `output/batch_create_output/`。

## 常见失败提示

- 如果设备或 Appium 连接失败，检查 `E2B_API_KEY`、`E2B_DOMAIN`、`SANDBOX_TEMPLATE`
- 如果流程耗时过长，先使用 `LONG_RUN_SECONDS=0` 和 `LONG_RUN_RESERVE_SECONDS=0` 做一次快速验证
- 如果需要上传 APK，请确认 `apk/` 目录下已有对应文件，或你的下载配置可用

## 它展示了什么

- 在 AGS 中运行 Android 设备并通过 Appium 远程控制
- quickstart、batch 与 sandbox_connect 三种不同使用路径
- 批量工具：logcat 日志获取、沙箱创建与销毁
- 屏幕操作、元素点击、位置模拟与批量执行等移动端自动化能力

## 脚本一览

| 脚本 | 说明 |
|------|------|
| `quickstart.py` | 快速入门示例，演示基本移动端自动化功能 |
| `batch.py` | 批量操作脚本，支持高并发沙箱测试 |
| `sandbox_connect.py` | 单沙箱连接工具，通过 CLI 操作已有沙箱 |
| `batch_dump_logcat.py` | 批量获取 logcat 日志，按沙箱 ID 分目录输出 |
| `batch_sandbox_kill.py` | 批量销毁沙箱，执行前需手动确认 |
| `batch_sandbox_create.py` | 批量创建沙箱 |
