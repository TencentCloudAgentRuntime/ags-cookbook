# Mobile Automation: 基于云端沙箱的移动端自动化测试

本示例展示如何使用 AgentSandbox 云端沙箱运行 Android 设备，结合 Appium 实现移动端应用自动化任务。

## 架构

```
┌─────────────┐     Appium      ┌─────────────┐      ADB       ┌───────────────┐
│   Python    │ ───────────────▶│   Appium    │ ─────────────▶│  AgentSandbox │
│   脚本      │                 │   Driver    │               │   (Android)   │
└─────────────┘                 └─────────────┘               └───────────────┘
      ▲                                │                              │
      │                                │◀─────────────────────────────┘
      │                                │      设备状态 / 结果
      └────────────────────────────────┘
              响应
```

**核心特性**：
- Android 设备运行在云端沙箱，本地通过 Appium 远程控制
- 支持 ws-scrcpy 实时屏幕流查看
- 完整的移动端自动化能力：应用安装、GPS 模拟、浏览器控制、屏幕截图等

## 项目结构

```
mobile-use/
├── README.md                  # 英文文档
├── README_zh.md               # 中文文档
├── .env.example               # 环境配置示例
├── requirements.txt           # Python 依赖
├── quickstart.py              # 快速入门示例
├── batch.py                   # 批量操作脚本（多进程 + 异步）
├── sandbox_connect.py         # 单沙箱连接工具（CLI）
├── test_mobile_actions.py     # 单元测试
├── apk/                       # APK 文件目录
└── output/                    # 截图和日志输出目录
```

## 脚本说明

| 脚本 | 说明 |
|------|------|
| `quickstart.py` | 快速入门示例，演示基本的移动端自动化功能 |
| `batch.py` | 批量操作脚本，用于高并发沙箱测试（多进程 + 异步） |
| `sandbox_connect.py` | 单沙箱连接工具，用于连接已存在的沙箱执行指定操作 |
| `test_mobile_actions.py` | 单元测试 |

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 API Key

**方式1：.env 文件（推荐用于本地开发）**
```bash
# 复制示例文件
cp .env.example .env

# 编辑 .env 并填入配置
```

**方式2：环境变量（推荐用于 CI/CD）**
```bash
export E2B_API_KEY="your_api_key"
export E2B_DOMAIN="ap-guangzhou.tencentags.com"
export SANDBOX_TEMPLATE="mobile-v1"
```

### 3. 运行示例

**快速入门示例：**
```bash
python quickstart.py
```

**批量操作：**
```bash
python batch.py
```

## Sandbox Connect 工具

`sandbox_connect.py` 是一个命令行工具，用于连接到已存在的沙箱并按需执行移动端自动化操作。

### 与其他脚本的区别

| 脚本 | 用途 |
|------|------|
| `quickstart.py` | 创建新沙箱，运行完整演示流程 |
| `batch.py` | 批量测试多个场景 |
| `sandbox_connect.py` | 连接到已存在的单个沙箱，按需执行指定操作 |

### 基本用法

```bash
python sandbox_connect.py --sandbox-id <沙箱ID> --action <动作> [其他参数]
```

### 支持的动作

**应用操作**（需配合 `--app-name`）：

| 动作 | 说明 |
|------|------|
| `upload_app` | 上传 APK 到设备 |
| `install_app` | 安装已上传的 APK |
| `launch_app` | 启动应用 |
| `check_app` | 检查应用是否已安装 |
| `grant_app_permissions` | 授予应用权限 |
| `close_app` | 关闭应用 |
| `uninstall_app` | 卸载应用 |

**屏幕操作**：

| 动作 | 说明 | 必需参数 |
|------|------|----------|
| `tap_screen` | 点击屏幕坐标 | `--tap-x`, `--tap-y` |
| `screenshot` | 截取屏幕截图 | 无 |
| `set_screen_resolution` | 设置屏幕分辨率 | `--width`, `--height`, `--dpi`(可选) |
| `reset_screen_resolution` | 重置屏幕分辨率 | 无 |

**UI 操作**：

| 动作 | 说明 | 必需参数 |
|------|------|----------|
| `dump_ui` | 获取 UI 层次结构（XML） | 无 |
| `click_element` | 点击元素 | `--element-text` 或 `--element-id` |
| `input_text` | 输入文本 | `--text` |

**定位操作**：

| 动作 | 说明 | 必需参数 |
|------|------|----------|
| `set_location` | 设置 GPS 定位 | `--latitude`, `--longitude`, `--altitude`(可选) |
| `get_location` | 获取当前 GPS 定位 | 无 |

**设备信息操作**：

| 动作 | 说明 | 必需参数 |
|------|------|----------|
| `device_info` | 获取设备详细信息 | 无 |
| `get_window_size` | 获取屏幕窗口尺寸 | 无 |
| `get_device_model` | 获取设备型号 | 无 |
| `get_app_state` | 获取应用状态 | `--app-name` |
| `get_current_activity` | 获取当前 Activity | 无 |
| `get_current_package` | 获取当前包名 | 无 |

**系统操作**：

| 动作 | 说明 | 必需参数 |
|------|------|----------|
| `open_browser` | 打开浏览器 | `--url` |
| `disable_gms` | 禁用 Google Play Services | 无 |
| `enable_gms` | 启用 Google Play Services | 无 |
| `get_device_logs` | 获取设备日志 | 无 |
| `shell` | 执行 ADB shell 命令 | `--shell-cmd` |

### 使用示例

**获取设备信息：**
```bash
python sandbox_connect.py --sandbox-id abc123 --action device_info
```

**截取屏幕截图：**
```bash
python sandbox_connect.py --sandbox-id abc123 --action screenshot
```

**点击屏幕：**
```bash
python sandbox_connect.py --sandbox-id abc123 --action tap_screen --tap-x 500 --tap-y 1000
```

**点击元素：**
```bash
# 通过 resource-id
python sandbox_connect.py --sandbox-id abc123 --action click_element --element-id "com.example:id/button"

# 通过文本
python sandbox_connect.py --sandbox-id abc123 --action click_element --element-text "登录"
```

**设置 GPS 定位（深圳）：**
```bash
python sandbox_connect.py --sandbox-id abc123 --action set_location --latitude 22.5431 --longitude 113.9298
```

**批量操作（逗号分隔）：**
```bash
python sandbox_connect.py --sandbox-id abc123 \
    --action upload_app,install_app,grant_app_permissions,launch_app \
    --app-name yyb
```

**执行 ADB shell 命令：**
```bash
python sandbox_connect.py --sandbox-id abc123 --action shell --shell-cmd "pm list packages"
```

### 命令行帮助

```bash
python sandbox_connect.py --help
```

## 配置说明

### 必需配置

| 变量 | 说明 |
|------|------|
| `E2B_API_KEY` | 你的 AgentSandbox API Key |
| `E2B_DOMAIN` | 服务域名（如：`ap-guangzhou.tencentags.com`） |
| `SANDBOX_TEMPLATE` | 沙箱模板名称（如：`mobile-v1`） |

### 可选配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `SANDBOX_TIMEOUT` | 3600（quickstart）/ 300（batch） | 沙箱超时时间（秒） |
| `LOG_LEVEL` | INFO | 日志级别：DEBUG, INFO, WARNING, ERROR, CRITICAL |

### 批量操作配置（仅 batch.py）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `SANDBOX_COUNT` | 2 | 要创建的沙箱总数 |
| `PROCESS_COUNT` | 2 | 并行执行的进程数 |
| `THREAD_POOL_SIZE` | 5 | 每个进程的线程池大小 |
| `USE_MOUNTED_APK` | false | 使用挂载的 APK 而不是从本地上传 |

## 输出目录

截图和日志保存在 `output/` 目录下：

```
output/
├── quickstart_output/          # quickstart.py 输出
│   ├── mobile_screenshot_*.png
│   └── screenshot_before_exit_*.png
├── batch_output/               # batch.py 输出
│   └── {数量}_{时间戳}/
│       ├── console.log
│       ├── summary.json
│       ├── details.json
│       └── sandbox_*/
│           ├── screenshot_1.png
│           ├── screenshot_2.png
│           └── ...
└── sandbox_connect_output/     # sandbox_connect.py 输出
    ├── screenshot_*.png
    ├── ui_dump.xml
    └── device_logs_*.txt
```

## 支持的应用

示例包含常见 Android 应用的配置。你可以自定义 `APP_CONFIGS` 字典来添加自己的应用。

**quickstart.py：**
- **应用宝** (`yyb`)：腾讯应用商店

**batch.py：**
- **美团** (`meituan`)：中文生活服务应用

**sandbox_connect.py：**
- **应用宝** (`yyb`)：腾讯应用商店

## 使用示例

### 基础浏览器测试

```python
# 打开浏览器并导航
open_browser(driver, "https://example.com")
time.sleep(5)

# 点击屏幕
tap_screen(driver, 360, 905)

# 截图
take_screenshot(driver)
```

### 应用安装和启动

```python
# 完整的应用安装流程
install_and_launch_app(driver, 'yyb')
```

### GPS 定位模拟

```python
# 获取当前位置
get_location(driver)

# 设置模拟位置（深圳）
set_location(driver, latitude=22.54347, longitude=113.92972)

# 验证位置
get_location(driver)
```

### 元素点击操作

```python
from mobile_actions import click_element

# 通过 resource-id 点击（最可靠）
click_element(driver, resource_id="com.example:id/button")

# 通过精确文本点击
click_element(driver, text="提交")

# 通过部分文本点击
click_element(driver, text="提", partial=True)
```

## 分片上传

对于大型 APK 文件，示例使用分片上传策略：

1. **阶段1**：将所有分片上传到临时目录
2. **阶段2**：将分片合并为最终的 APK 文件

这种方式可以高效处理大文件，并提供进度反馈。

## GPS 定位模拟

示例使用 Appium Settings LocationService 进行 GPS 模拟，适用于容器化 Android 环境。当应用请求位置服务时，将返回模拟位置。

## 依赖

- Python >= 3.8
- e2b >= 2.9.0
- Appium-Python-Client >= 3.1.0
- requests >= 2.28.0
- python-dotenv >= 1.0.0（可选）
- pytest >= 7.0.0（用于测试）

## 注意事项

- **APK 文件**：将 APK 文件放在 `apk/` 目录中。如果 APK 不存在，将自动下载（如果配置了下载 URL）。
- 屏幕流地址使用 ws-scrcpy 协议进行实时查看
- Appium 连接使用沙箱的认证令牌
- GPS 模拟在容器化 Android 环境中通过 LocationService 工作
- 使用 Ctrl+C 可以优雅地停止脚本 - 资源将被自动清理
