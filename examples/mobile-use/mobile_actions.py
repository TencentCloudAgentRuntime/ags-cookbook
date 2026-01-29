"""
Mobile Actions Module

通用的手机操作方法集合，从 quickstart.py、batch.py 和 mobile_sandbox_client.py 中提取的已验证操作。

包含:
- 屏幕操作 (点击、截图、分辨率设置)
- 文本输入 (输入文本到焦点元素)
- 元素操作 (查找元素、点击元素)
- 界面分析 (获取页面 XML、设备信息)
- 应用管理 (启动、检查安装状态)
- 系统操作 (浏览器、日志、shell 命令)
- GPS 定位 (获取/设置位置)
"""

import re
import time
from pathlib import Path
from typing import Optional, Dict, Any, List, Union

from appium.webdriver.webdriver import WebDriver
from appium.webdriver.common.appiumby import AppiumBy


# ============================================================================
# 屏幕操作
# ============================================================================

def tap_screen(driver: WebDriver, x: int, y: int) -> bool:
    """
    点击屏幕指定坐标
    
    来源: quickstart.py tap_screen, batch.py _tap_random
    
    Args:
        driver: Appium driver
        x: X 坐标
        y: Y 坐标
        
    Returns:
        是否成功
    """
    try:
        driver.execute_script('mobile: shell', {
            'command': 'input',
            'args': ['tap', str(x), str(y)]
        })
        return True
    except Exception:
        return False


def take_screenshot(driver: WebDriver, save_path: Union[str, Path]) -> bool:
    """
    截图并保存到指定路径
    
    来源: quickstart.py take_screenshot, batch.py _take_screenshot, mobile_sandbox_client.py take_screenshot
    
    测试命令: python3 test/mobile_sandbox_client.py --action screenshot
    
    Args:
        driver: Appium driver
        save_path: 保存路径
        
    Returns:
        是否成功
    """
    try:
        save_path = Path(save_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        result = driver.save_screenshot(str(save_path))
        if result:
            return True
        # 兼容不同 Appium 客户端版本
        return save_path.exists() and save_path.stat().st_size > 0
    except Exception:
        return False


def set_screen_resolution(driver: WebDriver, width: int, height: int, dpi: Optional[int] = None) -> bool:
    """
    设置屏幕分辨率
    
    来源: mobile_sandbox_client.py set_screen_resolution
    
    测试命令: python3 test/mobile_sandbox_client.py --action set_screen_resolution --width 720 --height 1280
    
    通过 ADB 的 wm size 命令修改 Android 设备的屏幕分辨率。
    注意：此修改是临时的，设备重启后会恢复默认分辨率。
    
    Args:
        driver: Appium driver
        width: 屏幕宽度（像素）
        height: 屏幕高度（像素）
        dpi: 屏幕 DPI（可选，不指定则保持当前 DPI）
        
    Returns:
        是否成功
    """
    try:
        # 设置分辨率
        driver.execute_script('mobile: shell', {
            'command': 'wm',
            'args': ['size', f'{width}x{height}']
        })
        
        # 如果指定了 DPI，设置 DPI
        if dpi is not None:
            driver.execute_script('mobile: shell', {
                'command': 'wm',
                'args': ['density', str(dpi)]
            })
        
        # 等待设置生效
        time.sleep(1)
        
        # 验证分辨率是否生效
        result = driver.execute_script('mobile: shell', {
            'command': 'wm',
            'args': ['size']
        })
        
        expected = f"{width}x{height}"
        return expected in str(result)
        
    except Exception:
        return False


def reset_screen_resolution(driver: WebDriver) -> bool:
    """
    重置屏幕分辨率为默认值
    
    来源: mobile_sandbox_client.py reset_screen_resolution
    
    Args:
        driver: Appium driver
        
    Returns:
        是否成功
    """
    try:
        driver.execute_script('mobile: shell', {
            'command': 'wm',
            'args': ['size', 'reset']
        })
        
        driver.execute_script('mobile: shell', {
            'command': 'wm',
            'args': ['density', 'reset']
        })
        
        return True
    except Exception:
        return False


# ============================================================================
# 文本输入
# ============================================================================

def input_text(driver: WebDriver, text: str) -> bool:
    """
    输入文本到当前焦点输入框
    
    来源: mobile_sandbox_client.py input_text
    
    测试命令: python3 test/mobile_sandbox_client.py --action input_text --text "Hello World"
    
    支持中英文输入：
    - 英文/数字：使用 adb input text
    - 中文：使用 ADB Broadcast 方法
    
    Args:
        driver: Appium driver
        text: 要输入的文本内容
        
    Returns:
        是否成功
    """
    try:
        # 方法1: 尝试获取当前焦点元素并使用 send_keys
        try:
            active_element = driver.switch_to.active_element
            if active_element:
                active_element.send_keys(text)
                time.sleep(0.5)
                return True
        except Exception:
            pass
        
        # 方法2: 使用 adb input text (适用于纯英文/数字)
        # 检查是否包含中文
        has_chinese = any('\u4e00' <= char <= '\u9fff' for char in text)
        
        if has_chinese:
            # 中文使用 am broadcast 方法
            driver.execute_script('mobile: shell', {
                'command': 'am',
                'args': [
                    'broadcast',
                    '-a',
                    'ADB_INPUT_TEXT',
                    '--es',
                    'msg',
                    text
                ]
            })
        else:
            # 纯英文/数字，使用 input text
            # 替换空格为 %s
            escaped_text = text.replace(' ', '%s')
            driver.execute_script('mobile: shell', {
                'command': 'input',
                'args': ['text', escaped_text]
            })
        
        time.sleep(0.5)
        return True
        
    except Exception:
        return False


# ============================================================================
# 元素操作
# ============================================================================

def find_element_by_text(driver: WebDriver, text: str, partial: bool = False) -> Optional[Dict[str, Any]]:
    """
    通过文本查找元素
    
    来源: mobile_sandbox_client.py find_element_by_text
    
    Args:
        driver: Appium driver
        text: 要查找的文本
        partial: 是否部分匹配
        
    Returns:
        元素信息字典，包含 bounds, center, element 等，失败返回 None
    """
    try:
        # 转义文本中的引号，防止 XPATH 注入
        escaped_text = text.replace('"', '\\"')
        if partial:
            xpath = f'//*[contains(@text, "{escaped_text}")]'
        else:
            xpath = f'//*[@text="{escaped_text}"]'
        
        element = driver.find_element(AppiumBy.XPATH, xpath)
        
        # 获取元素位置和大小
        location = element.location
        size = element.size
        
        bounds = {
            'left': location['x'],
            'top': location['y'],
            'right': location['x'] + size['width'],
            'bottom': location['y'] + size['height']
        }
        
        center_x = location['x'] + size['width'] // 2
        center_y = location['y'] + size['height'] // 2
        
        return {
            'bounds': bounds,
            'center': {'x': center_x, 'y': center_y},
            'text': text,
            'element': element
        }
    except Exception:
        return None


def find_element_by_id(driver: WebDriver, resource_id: str) -> Optional[Dict[str, Any]]:
    """
    通过 resource-id 查找元素
    
    来源: mobile_sandbox_client.py find_element_by_id
    
    Args:
        driver: Appium driver
        resource_id: 元素的 resource-id (如 'com.example:id/button')
        
    Returns:
        元素信息字典，包含 bounds, center, element 等，失败返回 None
    """
    try:
        # 先尝试直接用 ID 定位
        try:
            element = driver.find_element(AppiumBy.ID, resource_id)
        except Exception:
            # 备用: 使用 XPATH
            xpath = f'//*[@resource-id="{resource_id}"]'
            element = driver.find_element(AppiumBy.XPATH, xpath)
        
        # 获取元素位置和大小
        location = element.location
        size = element.size
        
        bounds = {
            'left': location['x'],
            'top': location['y'],
            'right': location['x'] + size['width'],
            'bottom': location['y'] + size['height']
        }
        
        center_x = location['x'] + size['width'] // 2
        center_y = location['y'] + size['height'] // 2
        
        return {
            'bounds': bounds,
            'center': {'x': center_x, 'y': center_y},
            'resource_id': resource_id,
            'element': element
        }
    except Exception:
        return None


def click_element(driver: WebDriver, text: str = None, resource_id: str = None, partial: bool = False) -> bool:
    """
    点击元素 (通过文本或 resource-id)
    
    来源: mobile_sandbox_client.py click_element
    
    测试命令: python3 test/mobile_sandbox_client.py --action click_element --element-id "com.example.app:id/button_ok"
    
    Args:
        driver: Appium driver
        text: 元素文本 (与 resource_id 二选一)
        resource_id: 元素的 resource-id (与 text 二选一)
        partial: 文本是否部分匹配 (仅当使用 text 时有效)
        
    Returns:
        是否成功
    """
    element_info = None
    
    # 优先使用 resource_id
    if resource_id:
        element_info = find_element_by_id(driver, resource_id)
    elif text:
        element_info = find_element_by_text(driver, text, partial)
    
    if not element_info:
        return False
    
    try:
        # 使用 Appium 的 element.click()
        element_info['element'].click()
        return True
    except Exception:
        # 备用: 使用坐标点击
        try:
            center = element_info['center']
            return tap_screen(driver, center['x'], center['y'])
        except Exception:
            return False


# ============================================================================
# 界面分析
# ============================================================================

def get_page_source(driver: WebDriver) -> Optional[str]:
    """
    获取当前页面 XML 结构
    
    来源: batch.py _get_page_xml
    
    Args:
        driver: Appium driver
        
    Returns:
        XML 字符串，失败返回 None
    """
    try:
        return driver.page_source
    except Exception:
        return None


def get_page_source_to_file(driver: WebDriver, save_path: Union[str, Path]) -> Optional[str]:
    """
    获取当前页面 XML 结构并保存到文件
    
    来源: batch.py _get_page_xml
    
    Args:
        driver: Appium driver
        save_path: 保存路径
        
    Returns:
        XML 字符串，失败返回 None
    """
    try:
        page_source = driver.page_source
        if page_source:
            save_path = Path(save_path)
            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_text(page_source, encoding='utf-8')
        return page_source
    except Exception:
        return None


def get_window_size(driver: WebDriver) -> Dict[str, int]:
    """
    获取屏幕尺寸
    
    来源: quickstart.py get_device_info, batch.py AsyncSandboxTester
    
    Args:
        driver: Appium driver
        
    Returns:
        {'width': int, 'height': int}
    """
    return driver.get_window_size()


def get_device_info(driver: WebDriver) -> Dict[str, Any]:
    """
    获取设备详细信息
    
    来源: quickstart.py get_device_info
    
    Args:
        driver: Appium driver
        
    Returns:
        设备信息字典
    """
    capabilities = driver.capabilities
    window_size = driver.get_window_size()
    
    try:
        wm_size = driver.execute_script('mobile: shell', {'command': 'wm', 'args': ['size']})
        wm_density = driver.execute_script('mobile: shell', {'command': 'wm', 'args': ['density']})
    except Exception:
        wm_size = "N/A"
        wm_density = "N/A"
    
    info = {
        'deviceName': capabilities.get('deviceName', 'N/A'),
        'platformVersion': capabilities.get('platformVersion', 'N/A'),
        'automationName': capabilities.get('automationName', 'N/A'),
        'windowSize': window_size,
        'wmSize': wm_size.strip() if isinstance(wm_size, str) else wm_size,
        'wmDensity': wm_density.strip() if isinstance(wm_density, str) else wm_density,
    }
    return info


def get_device_model(driver: WebDriver) -> str:
    """
    获取设备型号
    
    来源: batch.py _get_device_info
    
    Args:
        driver: Appium driver
        
    Returns:
        设备型号字符串
    """
    try:
        result = execute_shell(driver, 'getprop', ['ro.product.model'])
        return result.strip() if result else 'N/A'
    except Exception:
        return 'N/A'


# ============================================================================
# 应用管理
# ============================================================================

def is_app_installed(driver: WebDriver, package: str) -> bool:
    """
    检查应用是否已安装
    
    来源: quickstart.py is_app_installed
    
    Args:
        driver: Appium driver
        package: 包名
        
    Returns:
        是否已安装
    """
    try:
        state = driver.query_app_state(package)
        return state != 0
    except Exception:
        try:
            result = driver.execute_script('mobile: shell', {
                'command': 'pm',
                'args': ['list', 'packages', package]
            })
            return package in str(result)
        except Exception:
            return False


def get_app_state(driver: WebDriver, package: str) -> int:
    """
    获取应用状态
    
    来源: quickstart.py launch_app
    
    Args:
        driver: Appium driver
        package: 包名
        
    Returns:
        状态码: 0=未安装, 1=未运行, 2=后台暂停, 3=后台运行, 4=前台运行
    """
    try:
        return driver.query_app_state(package)
    except Exception:
        return -1


def launch_app(driver: WebDriver, package: str, wait_seconds: float = 2) -> bool:
    """
    启动应用
    
    来源: quickstart.py launch_app, batch.py _launch_app
    
    Args:
        driver: Appium driver
        package: 包名
        wait_seconds: 启动后等待时间(秒)
        
    Returns:
        是否成功 (应用在前台运行)
    """
    try:
        driver.activate_app(package)
        time.sleep(wait_seconds)
        state = driver.query_app_state(package)
        return state == 4  # 4 = 前台运行
    except Exception:
        return False


def get_current_activity(driver: WebDriver) -> Optional[str]:
    """
    获取当前 Activity
    
    来源: quickstart.py main (heartbeat)
    
    Args:
        driver: Appium driver
        
    Returns:
        Activity 名称
    """
    try:
        return driver.current_activity
    except Exception:
        return None


def get_current_package(driver: WebDriver) -> Optional[str]:
    """
    获取当前包名
    
    Args:
        driver: Appium driver
        
    Returns:
        包名
    """
    try:
        return driver.current_package
    except Exception:
        return None


# ============================================================================
# 系统操作
# ============================================================================

def open_browser(driver: WebDriver, url: str, wait_seconds: float = 2) -> bool:
    """
    打开浏览器访问 URL
    
    来源: quickstart.py open_browser, batch.py _open_browser
    
    Args:
        driver: Appium driver
        url: 要访问的 URL
        wait_seconds: 等待页面加载时间(秒)
        
    Returns:
        是否成功
    """
    try:
        driver.execute_script('mobile: shell', {
            'command': 'am',
            'args': ['start', '-a', 'android.intent.action.VIEW', '-d', url]
        })
        time.sleep(wait_seconds)
        return True
    except Exception:
        return False


def get_device_logs(driver: WebDriver) -> Optional[str]:
    """
    获取设备日志 (logcat)
    
    来源: batch.py _get_device_logs
    
    Args:
        driver: Appium driver
        
    Returns:
        日志内容字符串
    """
    try:
        return execute_shell(driver, 'logcat', ['-d'])
    except Exception:
        return None


def get_device_logs_to_file(driver: WebDriver, save_path: Union[str, Path]) -> Optional[str]:
    """
    获取设备日志并保存到文件
    
    来源: batch.py _get_device_logs
    
    Args:
        driver: Appium driver
        save_path: 保存路径
        
    Returns:
        日志内容字符串
    """
    try:
        logs = execute_shell(driver, 'logcat', ['-d'])
        if logs:
            save_path = Path(save_path)
            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_text(logs, encoding='utf-8')
        return logs
    except Exception:
        return None


def execute_shell(driver: WebDriver, command: str, args: Optional[List[str]] = None) -> Optional[str]:
    """
    执行 ADB shell 命令
    
    来源: batch.py _execute_shell
    
    Args:
        driver: Appium driver
        command: 命令
        args: 参数列表
        
    Returns:
        命令输出字符串
    """
    try:
        result = driver.execute_script('mobile: shell', {
            'command': command,
            'args': args or []
        })
        return str(result) if result else None
    except Exception:
        return None


# ============================================================================
# GPS 定位
# ============================================================================

def get_location(driver: WebDriver) -> Optional[Dict[str, Any]]:
    """
    获取当前 GPS 位置
    
    来源: quickstart.py get_location
    
    注意: dumpsys 中 'last location=null' 是正常的，表示没有应用正在请求位置。
    当应用请求位置时，mock location 会被返回。
    
    Args:
        driver: Appium driver
        
    Returns:
        位置信息字典，包含 latitude, longitude, provider 等
        如果 LocationService 运行但无位置数据，返回 {'status': 'mock_ready'}
        失败返回 None
    """
    try:
        result = driver.execute_script('mobile: shell', {
            'command': 'dumpsys',
            'args': ['location']
        })
        
        # 检查 LocationService 是否运行
        services = driver.execute_script('mobile: shell', {
            'command': 'dumpsys',
            'args': ['activity', 'services', 'io.appium.settings']
        })
        location_service_running = 'LocationService' in services
        
        # 尝试从 dumpsys 提取位置
        patterns = [
            (r'last location=Location\[(\w+)\s+([\d.-]+),([\d.-]+)', 3),
            (r'Location\[(\w+)\s+([\d.-]+),([\d.-]+)', 3),
        ]
        
        for pattern, _ in patterns:
            match = re.search(pattern, result)
            if match:
                groups = match.groups()
                return {
                    'latitude': float(groups[1]),
                    'longitude': float(groups[2]),
                    'altitude': 0,
                    'provider': groups[0]
                }
        
        # 即使没有 last location，mock 可能仍然工作
        if location_service_running:
            return {
                'status': 'mock_ready',
                'note': 'LocationService running, location available on request'
            }
        
        return None
            
    except Exception:
        return None


def set_location(driver: WebDriver, latitude: float, longitude: float, altitude: float = 0.0) -> bool:
    """
    设置 GPS 位置 (mock location)
    
    来源: quickstart.py set_location
    
    使用 Appium Settings 的 LocationService 设置模拟位置。
    
    Args:
        driver: Appium driver
        latitude: 纬度 (-90 到 90)
        longitude: 经度 (-180 到 180)
        altitude: 海拔(米)，默认 0
        
    Returns:
        是否成功
    """
    # 验证坐标范围
    if not (-90 <= latitude <= 90):
        return False
    
    if not (-180 <= longitude <= 180):
        return False
    
    try:
        appium_settings_pkg = "io.appium.settings"
        
        # 授予位置权限
        for perm in ['ACCESS_FINE_LOCATION', 'ACCESS_COARSE_LOCATION']:
            try:
                driver.execute_script('mobile: shell', {
                    'command': 'pm',
                    'args': ['grant', appium_settings_pkg, f'android.permission.{perm}']
                })
            except Exception:
                pass

        # 授予模拟位置权限
        driver.execute_script('mobile: shell', {
            'command': 'appops',
            'args': ['set', appium_settings_pkg, 'android:mock_location', 'allow']
        })
        
        # 启动 LocationService
        driver.execute_script('mobile: shell', {
            'command': 'am',
            'args': [
                'start-foreground-service',
                '--user', '0',
                '-n', f'{appium_settings_pkg}/.LocationService',
                '--es', 'longitude', str(longitude),
                '--es', 'latitude', str(latitude),
                '--es', 'altitude', str(altitude)
            ]
        })
        
        time.sleep(3)
        
        # 验证服务是否运行
        services = driver.execute_script('mobile: shell', {
            'command': 'dumpsys',
            'args': ['activity', 'services', 'io.appium.settings']
        })
        
        return 'LocationService' in services
        
    except Exception:
        return False


# ============================================================================
# 权限管理
# ============================================================================

def grant_permission(driver: WebDriver, package: str, permission: str) -> bool:
    """
    授予应用权限
    
    来源: quickstart.py grant_app_permissions, batch.py _grant_permissions
    
    Args:
        driver: Appium driver
        package: 包名
        permission: 权限名 (完整格式如 'android.permission.CAMERA')
        
    Returns:
        是否成功
    """
    try:
        driver.execute_script('mobile: shell', {
            'command': 'pm',
            'args': ['grant', package, permission]
        })
        return True
    except Exception:
        return False


def grant_permissions(driver: WebDriver, package: str, permissions: List[str]) -> int:
    """
    批量授予应用权限
    
    来源: quickstart.py grant_app_permissions, batch.py _grant_permissions
    
    Args:
        driver: Appium driver
        package: 包名
        permissions: 权限列表
        
    Returns:
        成功授予的权限数量
    """
    success_count = 0
    for permission in permissions:
        if grant_permission(driver, package, permission):
            success_count += 1
    return success_count
