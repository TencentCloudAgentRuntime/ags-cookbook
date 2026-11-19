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

上传、安装、授权并打开 QQ 浏览器：

```bash
python sandbox_connect.py --sandbox-id abc123 --action upload_app,install_app,grant_app_permissions,launch_app --app-name qqbrowser
```

获取当前界面 UI 层级（XML）：

```bash
python sandbox_connect.py --sandbox-id abc123 --action dump_ui
```

拉取全量 logcat 日志：

```bash
python sandbox_connect.py --sandbox-id abc123 --action get_device_logs
```

设置 GPS 位置（深圳）：

```bash
python sandbox_connect.py --sandbox-id abc123 --action set_location --latitude 22.5431 --longitude 113.9298
```

执行 ADB shell 命令：

```bash
python sandbox_connect.py --sandbox-id abc123 --action shell --shell-cmd "pm list packages"
```

卸载应用：

```bash
python sandbox_connect.py --sandbox-id abc123 --action uninstall_app --app-name yyb
```

获取应用状态：

```bash
python sandbox_connect.py --sandbox-id abc123 --action get_app_state --app-name yyb
```

## 模拟收到短信

手机沙箱是容器化 Android，没有模拟器 console，因此 `adb emu sms send` 不可用。沙箱镜像内置了等价的设备端工具 `/system/bin/smartrun-sms-inject`，会把一条收件短信（及其会话）写入系统短信库，写入后 `content://sms/inbox` 和短信 App 都能看到。

`sms_inject.py` 演示三种调用方式：

| 方式 | 适用场景 | 工具参数 |
|------|----------|----------|
| adb + stdin（默认） | 自己执行 adb，能往标准输入写内容 | `--from-stdin`（第 1 行号码，其余为正文） |
| adb + base64 | 调用方只能给 adb 传命令行参数 | `--b64 <b64 号码> <b64 正文>` |
| SDK（e2b + Appium） | 通过 Appium `mobile: shell` 操作沙箱（没有标准输入） | `--b64` |

三种方式都不经过 shell 引号解析，引号、`$`、反引号、换行、中文、emoji 都会逐字保存。

**adb 方式**：先用 AGS CLI 拿到 adb 地址，再注入：

```bash
agr instance mobile connect <sandbox_id>
# connected to 127.0.0.1:<端口>

uv run sms_inject.py adb --serial 127.0.0.1:<端口> +8613800000000 "你好"
uv run sms_inject.py adb --serial 127.0.0.1:<端口> --method b64 +8613800000000 "你好"
```

**SDK 方式**（需要 `E2B_API_KEY`、`E2B_DOMAIN`）：

```bash
uv run sms_inject.py sdk --sandbox-id <sandbox_id> +8613800000000 "你好"
```

**在自己的代码里调用**，直接导入函数：

```python
from sms_inject import inject_sms_via_adb, inject_sms_via_appium

inject_sms_via_adb("127.0.0.1:5555", "+8613800000000", "你好")
inject_sms_via_appium(driver, "+8613800000000", "你好")  # 已建立的 Appium driver
```

**不用 Python**：

```bash
# adb + stdin
printf '%s\n%s' "$NUM" "$MSG" | adb -s "$SERIAL" shell smartrun-sms-inject --from-stdin

# adb + base64（Linux 要加 -w0：GNU base64 默认每 76 字符换行）
adb -s "$SERIAL" shell smartrun-sms-inject --b64 \
    "$(printf '%s' "$NUM" | base64 -w0)" "$(printf '%s' "$MSG" | base64 -w0)"
```

注意事项：

- 需要镜像内置 `smartrun-sms-inject`（SmartRun redroid `android_world` 镜像 v33.3 及以上）。
- **不要**用 `smartrun-sms-inject '<号码>' '<内容>'` 这种参数形式：参数会被本机和设备各解析一次，内容含空格或引号时会被截断（例如 `"plain arg msg"` 只会存进 `plain`）。
- Linux 下不加 `-w0` 时，较长的 base64 会被换行，设备 shell 会把换行后的部分当命令执行，短信被静默截断，且退出码仍是 0。
- 已经打开的短信 App 不会实时刷新，重新打开后可见。

常见失败：

| 现象 | 原因 / 处理 |
|------|-------------|
| `failed (exit 127): ... smartrun-sms-inject: inaccessible or not found` | 沙箱镜像版本早于该工具，请使用基于 SmartRun redroid `android_world` v33.3 及以上的模板 |
| `failed (exit 2): usage: smartrun-sms-inject ...` | 号码或内容为空 |
| `adb: device offline` / `device not found` | `agr` 隧道已断开（例如执行了 `adb disconnect` 或 `adb kill-server`），重新执行 `agr instance mobile connect <sandbox_id>` 并使用新端口 |
| `E2B_API_KEY is required for sdk mode` | 设置 `E2B_API_KEY`、`E2B_DOMAIN`（环境变量或 `.env`） |

## 批量工具

批量工具统一通过 `sandboxes.yaml` 配置文件传入沙箱 ID。

先从模板复制一份本地配置：

```bash
cp sandboxes_example.yaml sandboxes.yaml
```

`sandboxes.yaml` 仅用于本地运行，已被 git 忽略。

然后在 `sandboxes.yaml` 中填写：

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

# 指定配置文件和并发数（并发必须 >= 1）
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

# 指定并发（必须 >= 1）和批次间隔（必须 >= 0）
python batch_sandbox_kill.py --concurrency 20 --sleep 2
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
- 模拟收到短信（替代 `adb emu sms send`）
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
| `sms_inject.py` | 模拟收到短信（替代 `adb emu sms send`），支持 adb 与 SDK |
