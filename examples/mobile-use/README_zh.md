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

## 脚本说明

| 脚本 | 说明 |
|------|------|
| `quickstart.py` | 快速入门示例，演示基本的移动端自动化功能 |
| `batch.py` | 批量操作脚本，用于高并发沙箱测试（多进程 + 异步） |

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

## 可用功能

| 功能 | 说明 |
|------|------|
| `upload_app` | 使用分片上传将 APK 上传到设备（支持大文件） |
| `install_app` | 在设备上安装已上传的 APK |
| `grant_app_permissions` | 授予应用所有必要权限 |
| `launch_app` | 启动已安装的应用 |
| `open_browser` | 在设备浏览器中打开 URL |
| `tap_screen` | 点击屏幕指定坐标 |
| `take_screenshot` | 截取设备屏幕截图 |
| `get_location` | 获取当前 GPS 定位 |
| `set_location` | 设置 GPS 定位（模拟位置） |
| `install_and_launch_app` | 完整流程：上传 → 安装 → 授权 → 启动 |

## 输出目录

截图和日志保存在 `output/` 目录下：

```
output/
├── quickstart_output/     # quickstart.py 输出
│   ├── mobile_screenshot_*.png
│   └── screenshot_before_exit_*.png
└── batch_output/          # batch.py 输出
    └── {数量}_{时间戳}/
        ├── console.log
        ├── summary.json
        ├── details.json
        └── sandbox_*/
            ├── screenshot_1.png
            ├── screenshot_2.png
            └── ...
```

## 支持的应用

示例包含常见 Android 应用的配置。你可以自定义 `APP_CONFIGS` 字典来添加自己的应用。

**quickstart.py：**
- **微信** (`wechat`)：中文即时通讯应用
- **应用宝** (`yyb`)：中文应用商店

**batch.py：**
- **美团** (`meituan`)：中文生活服务应用

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

## 注意事项

- **APK 文件**：将 APK 文件放在 `apk/` 目录中。如果 APK 不存在，将自动下载（如果配置了下载 URL）。
- 屏幕流地址使用 ws-scrcpy 协议进行实时查看
- Appium 连接使用沙箱的认证令牌
- GPS 模拟在容器化 Android 环境中通过 LocationService 工作
- 使用 Ctrl+C 可以优雅地停止脚本 - 资源将被自动清理
