"""
Mobile Actions Unit Tests

针对 mobile_actions.py 的单元测试，使用 mock 模拟 Appium driver。

运行测试:
    cd examples/mobile-use
    python -m pytest test_mobile_actions.py -v

运行单个测试:
    python -m pytest test_mobile_actions.py::TestTapScreen -v

查看覆盖率:
    python -m pytest test_mobile_actions.py -v --cov=mobile_actions --cov-report=term-missing
"""

import json
import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, PropertyMock

import mobile_actions


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_driver():
    """创建模拟的 Appium driver"""
    driver = Mock()
    driver.get_window_size.return_value = {'width': 1080, 'height': 1920}
    driver.capabilities = {
        'deviceName': 'test_device',
        'platformVersion': '12',
        'automationName': 'UiAutomator2'
    }
    return driver


@pytest.fixture
def mock_element():
    """创建模拟的 WebElement"""
    element = Mock()
    element.location = {'x': 100, 'y': 200}
    element.size = {'width': 200, 'height': 100}
    element.click.return_value = None
    return element


@pytest.fixture
def temp_dir(tmp_path):
    """创建临时目录"""
    return tmp_path


# ============================================================================
# 屏幕操作测试
# ============================================================================

class TestTapScreen:
    """tap_screen 测试"""

    def test_tap_screen_success(self, mock_driver):
        """测试点击成功"""
        mock_driver.execute_script.return_value = None
        
        result = mobile_actions.tap_screen(mock_driver, 500, 800)
        
        assert result is True
        mock_driver.execute_script.assert_called_once_with(
            'mobile: shell',
            {'command': 'input', 'args': ['tap', '500', '800']}
        )

    def test_tap_screen_failure(self, mock_driver):
        """测试点击失败"""
        mock_driver.execute_script.side_effect = Exception("Tap failed")
        
        result = mobile_actions.tap_screen(mock_driver, 500, 800)
        
        assert result is False


class TestTakeScreenshot:
    """take_screenshot 测试"""

    def test_take_screenshot_success(self, mock_driver, temp_dir):
        """测试截图成功"""
        save_path = temp_dir / "screenshot.png"
        mock_driver.save_screenshot.return_value = True
        
        result = mobile_actions.take_screenshot(mock_driver, save_path)
        
        assert result is True
        mock_driver.save_screenshot.assert_called_once_with(str(save_path))

    def test_take_screenshot_creates_parent_dir(self, mock_driver, temp_dir):
        """测试截图时自动创建父目录"""
        save_path = temp_dir / "subdir" / "screenshot.png"
        mock_driver.save_screenshot.return_value = True
        
        result = mobile_actions.take_screenshot(mock_driver, save_path)
        
        assert result is True
        assert save_path.parent.exists()

    def test_take_screenshot_failure(self, mock_driver, temp_dir):
        """测试截图失败"""
        save_path = temp_dir / "screenshot.png"
        mock_driver.save_screenshot.side_effect = Exception("Screenshot failed")
        
        result = mobile_actions.take_screenshot(mock_driver, save_path)
        
        assert result is False


# ============================================================================
# 元素操作测试
# ============================================================================

class TestFindElementByText:
    """find_element_by_text 测试"""

    def test_find_element_exact_match(self, mock_driver, mock_element):
        """测试精确匹配文本"""
        mock_driver.find_element.return_value = mock_element
        
        result = mobile_actions.find_element_by_text(mock_driver, "登录")
        
        assert result is not None
        assert result['text'] == "登录"
        assert result['bounds'] == {'left': 100, 'top': 200, 'right': 300, 'bottom': 300}
        assert result['center'] == {'x': 200, 'y': 250}
        assert result['element'] == mock_element

    def test_find_element_partial_match(self, mock_driver, mock_element):
        """测试部分匹配文本"""
        mock_driver.find_element.return_value = mock_element
        
        result = mobile_actions.find_element_by_text(mock_driver, "登", partial=True)
        
        assert result is not None
        # 验证使用了 contains
        call_args = mock_driver.find_element.call_args
        assert 'contains(@text' in call_args[0][1]

    def test_find_element_not_found(self, mock_driver):
        """测试元素未找到"""
        mock_driver.find_element.side_effect = Exception("Element not found")
        
        result = mobile_actions.find_element_by_text(mock_driver, "不存在")
        
        assert result is None

    def test_find_element_with_quotes(self, mock_driver, mock_element):
        """测试包含引号的文本"""
        mock_driver.find_element.return_value = mock_element
        
        result = mobile_actions.find_element_by_text(mock_driver, '点击"确定"')
        
        assert result is not None
        # 验证引号被转义
        call_args = mock_driver.find_element.call_args
        assert '\\"' in call_args[0][1]


class TestFindElementById:
    """find_element_by_id 测试"""

    def test_find_element_by_id_success(self, mock_driver, mock_element):
        """测试通过 ID 查找成功"""
        mock_driver.find_element.return_value = mock_element
        
        result = mobile_actions.find_element_by_id(mock_driver, "com.example:id/button")
        
        assert result is not None
        assert result['resource_id'] == "com.example:id/button"
        assert result['bounds'] == {'left': 100, 'top': 200, 'right': 300, 'bottom': 300}
        assert result['center'] == {'x': 200, 'y': 250}

    def test_find_element_by_id_fallback_to_xpath(self, mock_driver, mock_element):
        """测试 ID 查找失败后回退到 XPATH"""
        # 第一次调用（ID）失败，第二次调用（XPATH）成功
        mock_driver.find_element.side_effect = [Exception("ID not found"), mock_element]
        
        result = mobile_actions.find_element_by_id(mock_driver, "com.example:id/button")
        
        assert result is not None
        assert mock_driver.find_element.call_count == 2

    def test_find_element_by_id_not_found(self, mock_driver):
        """测试元素未找到"""
        mock_driver.find_element.side_effect = Exception("Element not found")
        
        result = mobile_actions.find_element_by_id(mock_driver, "com.example:id/not_exist")
        
        assert result is None


class TestClickElement:
    """click_element 测试"""

    def test_click_element_by_id(self, mock_driver, mock_element):
        """测试通过 ID 点击"""
        mock_driver.find_element.return_value = mock_element
        
        result = mobile_actions.click_element(mock_driver, resource_id="com.example:id/button")
        
        assert result is True
        mock_element.click.assert_called_once()

    def test_click_element_by_text(self, mock_driver, mock_element):
        """测试通过文本点击"""
        mock_driver.find_element.return_value = mock_element
        
        result = mobile_actions.click_element(mock_driver, text="登录")
        
        assert result is True
        mock_element.click.assert_called_once()

    def test_click_element_fallback_to_tap(self, mock_driver, mock_element):
        """测试 click() 失败后回退到坐标点击"""
        mock_driver.find_element.return_value = mock_element
        mock_element.click.side_effect = Exception("Click failed")
        mock_driver.execute_script.return_value = None  # tap_screen 成功
        
        result = mobile_actions.click_element(mock_driver, resource_id="com.example:id/button")
        
        assert result is True
        # 验证调用了 tap_screen (通过 execute_script)
        mock_driver.execute_script.assert_called()

    def test_click_element_not_found(self, mock_driver):
        """测试元素未找到"""
        mock_driver.find_element.side_effect = Exception("Element not found")
        
        result = mobile_actions.click_element(mock_driver, resource_id="com.example:id/not_exist")
        
        assert result is False

    def test_click_element_no_params(self, mock_driver):
        """测试无参数调用"""
        result = mobile_actions.click_element(mock_driver)
        
        assert result is False

    def test_click_element_id_priority(self, mock_driver, mock_element):
        """测试 resource_id 优先于 text"""
        mock_driver.find_element.return_value = mock_element
        
        result = mobile_actions.click_element(
            mock_driver, 
            text="登录", 
            resource_id="com.example:id/button"
        )
        
        assert result is True
        # 验证使用了 ID 而不是 text
        call_args = mock_driver.find_element.call_args
        assert call_args[0][1] == "com.example:id/button"


# ============================================================================
# 界面分析测试
# ============================================================================

class TestGetPageSource:
    """get_page_source 测试"""

    def test_get_page_source_success(self, mock_driver):
        """测试获取页面源码成功"""
        mock_driver.page_source = "<hierarchy>...</hierarchy>"
        
        result = mobile_actions.get_page_source(mock_driver)
        
        assert result == "<hierarchy>...</hierarchy>"

    def test_get_page_source_failure(self, mock_driver):
        """测试获取页面源码失败"""
        type(mock_driver).page_source = PropertyMock(side_effect=Exception("Failed"))
        
        result = mobile_actions.get_page_source(mock_driver)
        
        assert result is None


class TestGetPageSourceToFile:
    """get_page_source_to_file 测试"""

    def test_save_page_source_success(self, mock_driver, temp_dir):
        """测试保存页面源码成功"""
        mock_driver.page_source = "<hierarchy>test</hierarchy>"
        save_path = temp_dir / "page.xml"
        
        result = mobile_actions.get_page_source_to_file(mock_driver, save_path)
        
        assert result == "<hierarchy>test</hierarchy>"
        assert save_path.exists()
        assert save_path.read_text() == "<hierarchy>test</hierarchy>"

    def test_save_page_source_creates_parent_dir(self, mock_driver, temp_dir):
        """测试自动创建父目录"""
        mock_driver.page_source = "<hierarchy>test</hierarchy>"
        save_path = temp_dir / "subdir" / "page.xml"
        
        result = mobile_actions.get_page_source_to_file(mock_driver, save_path)
        
        assert result is not None
        assert save_path.parent.exists()


class TestGetWindowSize:
    """get_window_size 测试"""

    def test_get_window_size(self, mock_driver):
        """测试获取窗口尺寸"""
        result = mobile_actions.get_window_size(mock_driver)
        
        assert result == {'width': 1080, 'height': 1920}


class TestGetDeviceInfo:
    """get_device_info 测试"""

    def test_get_device_info_success(self, mock_driver):
        """测试获取设备信息成功"""
        mock_driver.execute_script.side_effect = [
            "Physical size: 1080x1920",  # wm size
            "Physical density: 480"       # wm density
        ]
        
        result = mobile_actions.get_device_info(mock_driver)
        
        assert result['deviceName'] == 'test_device'
        assert result['platformVersion'] == '12'
        assert result['automationName'] == 'UiAutomator2'
        assert result['windowSize'] == {'width': 1080, 'height': 1920}

    def test_get_device_info_shell_failure(self, mock_driver):
        """测试 shell 命令失败时的处理"""
        mock_driver.execute_script.side_effect = Exception("Shell failed")
        
        result = mobile_actions.get_device_info(mock_driver)
        
        assert result['wmSize'] == 'N/A'
        assert result['wmDensity'] == 'N/A'


class TestGetDeviceModel:
    """get_device_model 测试"""

    def test_get_device_model_success(self, mock_driver):
        """测试获取设备型号成功"""
        mock_driver.execute_script.return_value = "Pixel 6\n"
        
        result = mobile_actions.get_device_model(mock_driver)
        
        assert result == "Pixel 6"

    def test_get_device_model_failure(self, mock_driver):
        """测试获取设备型号失败"""
        mock_driver.execute_script.side_effect = Exception("Failed")
        
        result = mobile_actions.get_device_model(mock_driver)
        
        assert result == 'N/A'


# ============================================================================
# 应用管理测试
# ============================================================================

class TestIsAppInstalled:
    """is_app_installed 测试"""

    def test_app_installed(self, mock_driver):
        """测试应用已安装"""
        mock_driver.query_app_state.return_value = 1  # 已安装但未运行
        
        result = mobile_actions.is_app_installed(mock_driver, "com.example.app")
        
        assert result is True

    def test_app_not_installed(self, mock_driver):
        """测试应用未安装"""
        mock_driver.query_app_state.return_value = 0
        
        result = mobile_actions.is_app_installed(mock_driver, "com.example.app")
        
        assert result is False

    def test_app_installed_fallback(self, mock_driver):
        """测试回退到 pm list 检查"""
        mock_driver.query_app_state.side_effect = Exception("Not supported")
        mock_driver.execute_script.return_value = "package:com.example.app"
        
        result = mobile_actions.is_app_installed(mock_driver, "com.example.app")
        
        assert result is True


class TestGetAppState:
    """get_app_state 测试"""

    def test_get_app_state_running(self, mock_driver):
        """测试获取运行中的应用状态"""
        mock_driver.query_app_state.return_value = 4  # 前台运行
        
        result = mobile_actions.get_app_state(mock_driver, "com.example.app")
        
        assert result == 4

    def test_get_app_state_failure(self, mock_driver):
        """测试获取状态失败"""
        mock_driver.query_app_state.side_effect = Exception("Failed")
        
        result = mobile_actions.get_app_state(mock_driver, "com.example.app")
        
        assert result == -1


class TestLaunchApp:
    """launch_app 测试"""

    def test_launch_app_success(self, mock_driver):
        """测试启动应用成功"""
        mock_driver.activate_app.return_value = None
        mock_driver.query_app_state.return_value = 4  # 前台运行
        
        with patch('mobile_actions.time.sleep'):
            result = mobile_actions.launch_app(mock_driver, "com.example.app")
        
        assert result is True

    def test_launch_app_failure(self, mock_driver):
        """测试启动应用失败"""
        mock_driver.activate_app.return_value = None
        mock_driver.query_app_state.return_value = 1  # 未运行
        
        with patch('mobile_actions.time.sleep'):
            result = mobile_actions.launch_app(mock_driver, "com.example.app")
        
        assert result is False


class TestGetCurrentActivity:
    """get_current_activity 测试"""

    def test_get_current_activity_success(self, mock_driver):
        """测试获取当前 Activity 成功"""
        mock_driver.current_activity = ".MainActivity"
        
        result = mobile_actions.get_current_activity(mock_driver)
        
        assert result == ".MainActivity"

    def test_get_current_activity_failure(self, mock_driver):
        """测试获取当前 Activity 失败"""
        type(mock_driver).current_activity = PropertyMock(side_effect=Exception("Failed"))
        
        result = mobile_actions.get_current_activity(mock_driver)
        
        assert result is None


class TestGetCurrentPackage:
    """get_current_package 测试"""

    def test_get_current_package_success(self, mock_driver):
        """测试获取当前包名成功"""
        mock_driver.current_package = "com.example.app"
        
        result = mobile_actions.get_current_package(mock_driver)
        
        assert result == "com.example.app"

    def test_get_current_package_failure(self, mock_driver):
        """测试获取当前包名失败"""
        type(mock_driver).current_package = PropertyMock(side_effect=Exception("Failed"))
        
        result = mobile_actions.get_current_package(mock_driver)
        
        assert result is None


# ============================================================================
# 系统操作测试
# ============================================================================

class TestOpenBrowser:
    """open_browser 测试"""

    def test_open_browser_success(self, mock_driver):
        """测试打开浏览器成功"""
        mock_driver.execute_script.return_value = None
        
        with patch('mobile_actions.time.sleep'):
            result = mobile_actions.open_browser(mock_driver, "https://example.com")
        
        assert result is True
        mock_driver.execute_script.assert_called_once()

    def test_open_browser_failure(self, mock_driver):
        """测试打开浏览器失败"""
        mock_driver.execute_script.side_effect = Exception("Failed")
        
        with patch('mobile_actions.time.sleep'):
            result = mobile_actions.open_browser(mock_driver, "https://example.com")
        
        assert result is False


class TestGetDeviceLogs:
    """get_device_logs 测试"""

    def test_get_device_logs_success(self, mock_driver):
        """测试获取日志成功"""
        mock_driver.execute_script.return_value = "log line 1\nlog line 2"
        
        result = mobile_actions.get_device_logs(mock_driver)
        
        assert result == "log line 1\nlog line 2"

    def test_get_device_logs_failure(self, mock_driver):
        """测试获取日志失败"""
        mock_driver.execute_script.side_effect = Exception("Failed")
        
        result = mobile_actions.get_device_logs(mock_driver)
        
        assert result is None


class TestGetDeviceLogsToFile:
    """get_device_logs_to_file 测试"""

    def test_save_logs_success(self, mock_driver, temp_dir):
        """测试保存日志成功"""
        mock_driver.execute_script.return_value = "log content"
        save_path = temp_dir / "logcat.txt"
        
        result = mobile_actions.get_device_logs_to_file(mock_driver, save_path)
        
        assert result == "log content"
        assert save_path.exists()
        assert save_path.read_text() == "log content"


class TestExecuteShell:
    """execute_shell 测试"""

    def test_execute_shell_success(self, mock_driver):
        """测试执行 shell 命令成功"""
        mock_driver.execute_script.return_value = "output"
        
        result = mobile_actions.execute_shell(mock_driver, "echo", ["hello"])
        
        assert result == "output"
        mock_driver.execute_script.assert_called_once_with(
            'mobile: shell',
            {'command': 'echo', 'args': ['hello']}
        )

    def test_execute_shell_no_args(self, mock_driver):
        """测试无参数的 shell 命令"""
        mock_driver.execute_script.return_value = "output"
        
        result = mobile_actions.execute_shell(mock_driver, "pwd")
        
        assert result == "output"
        mock_driver.execute_script.assert_called_once_with(
            'mobile: shell',
            {'command': 'pwd', 'args': []}
        )

    def test_execute_shell_failure(self, mock_driver):
        """测试执行 shell 命令失败"""
        mock_driver.execute_script.side_effect = Exception("Failed")
        
        result = mobile_actions.execute_shell(mock_driver, "invalid")
        
        assert result is None


# ============================================================================
# GPS 定位测试
# ============================================================================

class TestGetLocation:
    """get_location 测试"""

    def test_get_location_success(self, mock_driver):
        """测试获取位置成功"""
        mock_driver.execute_script.side_effect = [
            "last location=Location[gps 31.230416,121.473701]",  # dumpsys location
            "LocationService running"  # dumpsys activity services
        ]
        
        result = mobile_actions.get_location(mock_driver)
        
        assert result is not None
        assert result['latitude'] == 31.230416
        assert result['longitude'] == 121.473701
        assert result['provider'] == 'gps'

    def test_get_location_mock_ready(self, mock_driver):
        """测试 mock location 就绪但无位置数据"""
        mock_driver.execute_script.side_effect = [
            "last location=null",  # 无位置数据
            "LocationService running"  # 服务运行中
        ]
        
        result = mobile_actions.get_location(mock_driver)
        
        assert result is not None
        assert result['status'] == 'mock_ready'

    def test_get_location_failure(self, mock_driver):
        """测试获取位置失败"""
        mock_driver.execute_script.side_effect = Exception("Failed")
        
        result = mobile_actions.get_location(mock_driver)
        
        assert result is None


class TestSetLocation:
    """set_location 测试"""

    def test_set_location_success(self, mock_driver):
        """测试设置位置成功"""
        mock_driver.execute_script.return_value = "LocationService"
        
        with patch('mobile_actions.time.sleep'):
            result = mobile_actions.set_location(mock_driver, 31.230416, 121.473701)
        
        assert result is True

    def test_set_location_invalid_latitude(self, mock_driver):
        """测试无效纬度"""
        result = mobile_actions.set_location(mock_driver, 91, 121)
        
        assert result is False

    def test_set_location_invalid_longitude(self, mock_driver):
        """测试无效经度"""
        result = mobile_actions.set_location(mock_driver, 31, 181)
        
        assert result is False

    def test_set_location_failure(self, mock_driver):
        """测试设置位置失败"""
        mock_driver.execute_script.return_value = "No service"
        
        with patch('mobile_actions.time.sleep'):
            result = mobile_actions.set_location(mock_driver, 31.230416, 121.473701)
        
        assert result is False


# ============================================================================
# 权限管理测试
# ============================================================================

class TestGrantPermission:
    """grant_permission 测试"""

    def test_grant_permission_success(self, mock_driver):
        """测试授予权限成功"""
        mock_driver.execute_script.return_value = None
        
        result = mobile_actions.grant_permission(
            mock_driver, 
            "com.example.app", 
            "android.permission.CAMERA"
        )
        
        assert result is True
        mock_driver.execute_script.assert_called_once_with(
            'mobile: shell',
            {'command': 'pm', 'args': ['grant', 'com.example.app', 'android.permission.CAMERA']}
        )

    def test_grant_permission_failure(self, mock_driver):
        """测试授予权限失败"""
        mock_driver.execute_script.side_effect = Exception("Failed")
        
        result = mobile_actions.grant_permission(
            mock_driver, 
            "com.example.app", 
            "android.permission.CAMERA"
        )
        
        assert result is False


class TestGrantPermissions:
    """grant_permissions 测试"""

    def test_grant_permissions_all_success(self, mock_driver):
        """测试批量授予权限全部成功"""
        mock_driver.execute_script.return_value = None
        
        permissions = [
            "android.permission.CAMERA",
            "android.permission.RECORD_AUDIO",
            "android.permission.READ_CONTACTS"
        ]
        
        result = mobile_actions.grant_permissions(mock_driver, "com.example.app", permissions)
        
        assert result == 3
        assert mock_driver.execute_script.call_count == 3

    def test_grant_permissions_partial_success(self, mock_driver):
        """测试批量授予权限部分成功"""
        mock_driver.execute_script.side_effect = [
            None,  # 第一个成功
            Exception("Failed"),  # 第二个失败
            None   # 第三个成功
        ]
        
        permissions = [
            "android.permission.CAMERA",
            "android.permission.RECORD_AUDIO",
            "android.permission.READ_CONTACTS"
        ]
        
        result = mobile_actions.grant_permissions(mock_driver, "com.example.app", permissions)
        
        assert result == 2

    def test_grant_permissions_empty_list(self, mock_driver):
        """测试空权限列表"""
        result = mobile_actions.grant_permissions(mock_driver, "com.example.app", [])
        
        assert result == 0
        mock_driver.execute_script.assert_not_called()


# ============================================================================
# 运行测试
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
