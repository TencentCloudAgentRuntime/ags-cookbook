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
├── mobile_actions.py          # 可复用的移动端操作库
├── test_mobile_actions.py     # mobile_actions 单元测试
├── apk/                       # APK 文件目录
└── output/                    # 截图和日志输出目录
```

## 脚本说明

| 脚本 | 说明 |
|------|------|
| `quickstart.py` | 快速入门示例，演示基本的移动端自动化功能 |
| `batch.py` | 批量操作脚本，用于高并发沙箱测试（多进程 + 异步） |
| `mobile_actions.py` | 可复用的移动端操作库，包含已验证的操作方法 |
| `test_mobile_actions.py` | mobile_actions 模块的单元测试 |

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

**运行单元测试：**
```bash
python -m pytest test_mobile_actions.py -v
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

## Mobile Actions 操作库

`mobile_actions.py` 模块提供了一系列可复用的移动端操作方法，这些方法都是从 `quickstart.py`、`batch.py` 和经过测试的脚本中提取的已验证操作。

### 可用方法

| 分类 | 方法 | 说明 |
|------|------|------|
| **屏幕操作** | `tap_screen(driver, x, y)` | 点击屏幕指定坐标 |
| | `take_screenshot(driver, save_path)` | 截图并保存 |
| **元素操作** | `find_element_by_text(driver, text, partial)` | 通过文本查找元素 |
| | `find_element_by_id(driver, resource_id)` | 通过 resource-id 查找元素 |
| | `click_element(driver, text, resource_id, partial)` | 通过文本或 resource-id 点击元素 |
| **界面分析** | `get_page_source(driver)` | 获取当前页面 XML |
| | `get_page_source_to_file(driver, save_path)` | 获取页面 XML 并保存到文件 |
| | `get_window_size(driver)` | 获取屏幕尺寸 |
| | `get_device_info(driver)` | 获取设备详细信息 |
| | `get_device_model(driver)` | 获取设备型号 |
| **应用管理** | `is_app_installed(driver, package)` | 检查应用是否已安装 |
| | `get_app_state(driver, package)` | 获取应用状态 |
| | `launch_app(driver, package, wait_seconds)` | 启动应用 |
| | `get_current_activity(driver)` | 获取当前 Activity |
| | `get_current_package(driver)` | 获取当前包名 |
| **系统操作** | `open_browser(driver, url, wait_seconds)` | 打开浏览器访问 URL |
| | `get_device_logs(driver)` | 获取设备日志 |
| | `get_device_logs_to_file(driver, save_path)` | 获取日志并保存到文件 |
| | `execute_shell(driver, command, args)` | 执行 ADB shell 命令 |
| **GPS 定位** | `get_location(driver)` | 获取当前 GPS 位置 |
| | `set_location(driver, latitude, longitude, altitude)` | 设置模拟 GPS 位置 |
| **权限管理** | `grant_permission(driver, package, permission)` | 授予单个权限 |
| | `grant_permissions(driver, package, permissions)` | 批量授予权限 |

### 使用示例

```python
from mobile_actions import (
    click_element, 
    tap_screen, 
    take_screenshot,
    get_page_source,
    launch_app
)

# 通过 resource-id 点击元素
click_element(driver, resource_id="com.example:id/login_button")

# 通过文本点击元素
click_element(driver, text="登录")

# 通过部分文本匹配点击
click_element(driver, text="登", partial=True)

# 点击屏幕坐标
tap_screen(driver, 500, 800)

# 截图
take_screenshot(driver, "output/screenshot.png")

# 获取页面 XML
page_source = get_page_source(driver)

# 启动应用
launch_app(driver, "com.example.app")
```

## 单元测试

`test_mobile_actions.py` 文件包含了 `mobile_actions.py` 中所有方法的单元测试。

### 运行测试

```bash
# 运行所有测试
python -m pytest test_mobile_actions.py -v

# 运行特定测试类
python -m pytest test_mobile_actions.py::TestClickElement -v

# 运行特定测试
python -m pytest test_mobile_actions.py::TestClickElement::test_click_element_by_id -v

# 查看测试覆盖率
pip install pytest-cov
python -m pytest test_mobile_actions.py -v --cov=mobile_actions --cov-report=term-missing
```

### 测试覆盖

| 分类 | 测试数量 | 状态 |
|------|---------|------|
| 屏幕操作 | 5 | ✅ |
| 元素操作 | 10 | ✅ |
| 界面分析 | 10 | ✅ |
| 应用管理 | 11 | ✅ |
| 系统操作 | 8 | ✅ |
| GPS 定位 | 7 | ✅ |
| 权限管理 | 7 | ✅ |
| **总计** | **58** | **✅** |

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
- **问小白** (`wenxiaobai`)：ChatXbai 应用

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
