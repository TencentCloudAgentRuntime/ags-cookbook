#!/usr/bin/env python3
"""
单沙箱连接操作工具 - 连接到已存在的 E2B 沙箱执行移动端操作

与 quickstart.py（创建新沙箱并运行完整演示）和 batch.py（批量测试）不同，
本工具用于连接到单个已存在的沙箱，通过命令行参数执行移动端自动化操作。

支持的测试动作:
1. 应用操作: upload_app, install_app, launch_app, check_app, grant_app_permissions, close_app, uninstall_app, get_app_state
2. 屏幕操作: tap_screen, screenshot, set_screen_resolution, reset_screen_resolution, get_window_size
3. UI操作: dump_ui, click_element, input_text
4. 定位操作: set_location, get_location
5. 设备信息: device_info, get_device_model, get_current_activity, get_current_package
6. 系统操作: open_browser, disable_gms, enable_gms, get_device_logs, shell

使用示例:
    python sandbox_connect.py --sandbox-id <id> --action device_info
    python sandbox_connect.py --sandbox-id <id> --action screenshot
    python sandbox_connect.py --sandbox-id <id> --action tap_screen --tap-x 500 --tap-y 1000
    python sandbox_connect.py --sandbox-id <id> --action input_text --text "Hello World"
    python sandbox_connect.py --sandbox-id <id> --action click_element --element-id "com.example:id/button"
    python sandbox_connect.py --sandbox-id <id> --action launch_app --app-name yyb
    python sandbox_connect.py --sandbox-id <id> --action set_location --latitude 22.5431 --longitude 113.9298
    python sandbox_connect.py --sandbox-id <id> --action shell --shell-cmd "pm list packages"
"""

import os
import re
import sys
import time
import base64
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional
from urllib.parse import quote

from e2b import Sandbox
from appium import webdriver
from appium.options.android import UiAutomator2Options
from appium.webdriver.appium_connection import AppiumConnection
from appium.webdriver.client_config import AppiumClientConfig
from appium.webdriver.webdriver import WebDriver
from appium.webdriver.common.appiumby import AppiumBy

# 脚本目录
SCRIPT_DIR = Path(__file__).parent
OUTPUT_DIR = SCRIPT_DIR / "output" / "sandbox_connect_output"

# 切片上传配置
CHUNK_SIZE = 20 * 1024 * 1024  # 20MB 每块

# 应用配置字典
APP_CONFIGS = {
    'yyb': {
        'name': '应用宝',
        'package': 'com.tencent.android.qqdownloader',
        'activity': 'com.tencent.assistantv2.activity.MainActivity',
        'apk_name': '应用宝.apk',
        'remote_path': '/data/local/tmp/yyb.apk',
        'permissions': [
            'android.permission.ACCESS_FINE_LOCATION',
            'android.permission.ACCESS_COARSE_LOCATION',
            'android.permission.READ_EXTERNAL_STORAGE',
            'android.permission.WRITE_EXTERNAL_STORAGE',
        ]
    }
}


def _load_env_file() -> None:
    """加载 .env 文件"""
    try:
        from dotenv import load_dotenv
        load_dotenv(SCRIPT_DIR / ".env")
    except ImportError:
        try:
            env_file = SCRIPT_DIR / ".env"
            if env_file.exists():
                with open(env_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, value = line.split('=', 1)
                            os.environ[key.strip()] = value.strip()
        except Exception:
            pass


class SandboxClient:
    """E2B 沙箱客户端"""
    
    def __init__(self, sandbox_id: str, e2b_domain: str = None, e2b_api_key: str = None):
        """
        初始化沙箱客户端
        
        Args:
            sandbox_id: 沙箱 ID
            e2b_domain: E2B 域名
            e2b_api_key: E2B API Key
        """
        self.sandbox_id = sandbox_id
        self.e2b_domain = e2b_domain or os.getenv("E2B_DOMAIN", "ap-guangzhou.tencentags.com")
        self.e2b_api_key = e2b_api_key or os.getenv("E2B_API_KEY", "")
        self.sandbox = None
        self.driver = None
        
        # 设置环境变量
        os.environ["E2B_DOMAIN"] = self.e2b_domain
        os.environ["E2B_API_KEY"] = self.e2b_api_key
    
    def connect(self):
        """连接到沙箱和 Appium"""
        print("=" * 70)
        print("E2B 沙箱客户端")
        print("=" * 70)
        print(f"沙箱 ID: {self.sandbox_id}")
        print(f"E2B Domain: {self.e2b_domain}")
        print("=" * 70)
        print()
        
        # 连接沙箱
        print("[连接] 正在连接到沙箱...")
        try:
            self.sandbox = Sandbox.connect(self.sandbox_id)
            print(f"✓ 沙箱连接成功")
        except Exception as e:
            print(f"✗ 沙箱连接失败: {e}")
            raise
        
        # 显示 VNC URL
        vnc_url = self._get_vnc_url()
        print(f"\nVNC URL (在浏览器中打开可实时查看屏幕):")
        print(vnc_url)
        print()
        
        # 连接 Appium
        print("[连接] 正在连接到 Appium...")
        try:
            self.driver = self._create_appium_driver()
            print(f"✓ Appium 连接成功 (会话ID: {self.driver.session_id})")
        except Exception as e:
            print(f"✗ Appium 连接失败: {e}")
            raise
        print()
    
    def disconnect(self):
        """断开连接"""
        if self.driver:
            print("[清理] 关闭 Appium 会话...")
            try:
                self.driver.quit()
            except Exception as e:
                print(f"[警告] 关闭会话时出错（可忽略）: {e}")
            finally:
                self.driver = None
                print("✓ 会话已关闭")
                print()
    
    def _get_vnc_url(self) -> str:
        """获取 VNC URL"""
        scrcpy_host = self.sandbox.get_host(8000)
        scrcpy_token = self.sandbox._envd_access_token
        scrcpy_udid = "emulator-5554"
        scrcpy_ws = f"wss://{scrcpy_host}/?action=proxy-adb&remote=tcp%3A8886&udid={scrcpy_udid}&access_token={scrcpy_token}"
        scrcpy_url = f"https://{scrcpy_host}/?access_token={scrcpy_token}#!action=stream&udid={scrcpy_udid}&player=webcodecs&ws={quote(scrcpy_ws, safe='')}"
        return scrcpy_url
    
    def _create_appium_driver(self) -> WebDriver:
        """创建 Appium Driver"""
        options = UiAutomator2Options()
        options.platform_name = 'Android'
        options.automation_name = 'UiAutomator2'
        options.new_command_timeout = 600
        options.set_capability('adbExecTimeout', 300000)
        options.set_capability('androidInstallTimeout', 300000)
        
        AppiumConnection.extra_headers['X-Access-Token'] = self.sandbox._envd_access_token
        
        appium_url = f"https://{self.sandbox.get_host(4723)}"
        client_config = AppiumClientConfig(
            remote_server_addr=appium_url,
            timeout=300
        )
        
        return webdriver.Remote(options=options, client_config=client_config)
    
    def _get_app_config(self, app_name: str) -> dict:
        """获取应用配置"""
        app_name = app_name.lower()
        if app_name not in APP_CONFIGS:
            raise ValueError(f"不支持的应用: {app_name}，支持的应用: {', '.join(APP_CONFIGS.keys())}")
        return APP_CONFIGS[app_name]
    
    def _is_app_installed(self, package_name: str) -> bool:
        """检查应用是否已安装"""
        try:
            state = self.driver.query_app_state(package_name)
            return state != 0
        except Exception:
            result = self.driver.execute_script('mobile: shell', {
                'command': 'pm',
                'args': ['list', 'packages', package_name]
            })
            return package_name in str(result)
    
    # ==================== 应用操作 ====================
    
    def upload_app(self, app_name: str, apk_path: str = None) -> bool:
        """上传 APK 到设备（切片上传）"""
        config = self._get_app_config(app_name)
        print(f"[Action: upload_app] 上传{config['name']}APK到设备...")
        
        if apk_path is None:
            apk_path = SCRIPT_DIR / "apk" / config['apk_name']
        else:
            apk_path = Path(apk_path)
        
        if not apk_path.exists():
            print(f"✗ APK文件不存在: {apk_path}")
            return False
        
        file_size = apk_path.stat().st_size
        total_chunks = (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE
        
        print(f"  - 本地APK路径: {apk_path}")
        print(f"  - 文件大小: {file_size / 1024 / 1024:.2f} MB")
        print(f"  - 分块数量: {total_chunks}")
        
        temp_dir = '/data/local/tmp/chunks'
        remote_path = config['remote_path']
        
        try:
            # 清理并创建临时目录
            self.driver.execute_script('mobile: shell', {'command': 'rm', 'args': ['-rf', temp_dir]})
            self.driver.execute_script('mobile: shell', {'command': 'mkdir', 'args': ['-p', temp_dir]})
            self.driver.execute_script('mobile: shell', {'command': 'rm', 'args': ['-f', remote_path]})
            
            start_time = time.time()
            
            # 上传分块
            print(f"  [阶段1] 上传分块...")
            with open(apk_path, 'rb') as f:
                for i in range(total_chunks):
                    chunk_data = f.read(CHUNK_SIZE)
                    chunk_b64 = base64.b64encode(chunk_data).decode('utf-8')
                    chunk_path = f"{temp_dir}/chunk_{i:04d}"
                    
                    print(f"    - 分块 {i + 1}/{total_chunks} ({len(chunk_data) / 1024 / 1024:.2f}MB)...", end=' ', flush=True)
                    chunk_start = time.time()
                    self.driver.push_file(chunk_path, chunk_b64)
                    print(f"完成 ({time.time() - chunk_start:.1f}s)")
            
            # 合并分块
            print(f"  [阶段2] 合并分块...")
            for i in range(total_chunks):
                chunk_path = f"{temp_dir}/chunk_{i:04d}"
                print(f"    - 合并分块 {i + 1}/{total_chunks}...", end=' ', flush=True)
                
                if i == 0:
                    self.driver.execute_script('mobile: shell', {'command': 'cp', 'args': [chunk_path, remote_path]})
                else:
                    # 后续分块：追加到目标文件
                    self.driver.execute_script('mobile: shell', {
                        'command': 'cat',
                        'args': [chunk_path, '>>', remote_path]
                    })
                
                self.driver.execute_script('mobile: shell', {'command': 'rm', 'args': ['-f', chunk_path]})
                print(f"完成")
            
            # 清理
            self.driver.execute_script('mobile: shell', {'command': 'rm', 'args': ['-rf', temp_dir]})
            
            # 验证
            result = self.driver.execute_script('mobile: shell', {'command': 'ls', 'args': ['-la', remote_path]})
            
            print(f"  - 总耗时: {time.time() - start_time:.1f}s")
            
            if result and 'No such file' not in str(result):
                print(f"✓ APK上传完成")
                print()
                return True
            else:
                print(f"✗ 文件验证失败")
                print()
                return False
                
        except Exception as e:
            print(f"✗ APK上传失败: {e}")
            print()
            return False
    
    def install_app(self, app_name: str) -> bool:
        """安装应用"""
        config = self._get_app_config(app_name)
        print(f"[Action: install_app] 安装{config['name']}应用...")
        
        try:
            # 检查是否已安装
            if self._is_app_installed(config['package']):
                print(f"  ⚠ {config['name']}已安装，跳过")
                print(f"✓ {config['name']}可用")
                print()
                return True
            
            # 安装
            print(f"  - 正在安装APK...")
            result = self.driver.execute_script('mobile: shell', {
                'command': 'pm',
                'args': ['install', '-r', '-g', config['remote_path']]
            })
            
            if result and ('Success' in str(result) or 'success' in str(result).lower()):
                print(f"✓ {config['name']}安装成功")
                print()
                return True
            
            # 验证
            time.sleep(2)
            if self._is_app_installed(config['package']):
                print(f"✓ {config['name']}安装成功 (验证)")
                print()
                return True
            
            print(f"✗ {config['name']}安装失败")
            print()
            return False
            
        except Exception as e:
            print(f"✗ 安装失败: {e}")
            print()
            return False
    
    def launch_app(self, app_name: str) -> bool:
        """启动应用"""
        config = self._get_app_config(app_name)
        print(f"[Action: launch_app] 启动{config['name']}应用...")
        
        try:
            self.driver.activate_app(config['package'])
            print(f"✓ {config['name']}已启动")
            time.sleep(3)
            
            app_state = self.driver.query_app_state(config['package'])
            if app_state == 4:
                print(f"✓ 应用在前台运行")
            elif app_state == 3:
                print(f"⚠ 应用在后台运行")
            
            print()
            return True
            
        except Exception as e:
            print(f"✗ 启动失败: {e}")
            print()
            return False
    
    def check_app_installed(self, app_name: str) -> bool:
        """检查应用是否已安装"""
        config = self._get_app_config(app_name)
        print(f"[Action: check_app] 检查{config['name']}是否已安装...")
        
        is_installed = self._is_app_installed(config['package'])
        
        if is_installed:
            print(f"✓ {config['name']}已安装 (包名: {config['package']})")
        else:
            print(f"✗ {config['name']}未安装")
        
        print()
        return is_installed
    
    def grant_app_permissions(self, app_name: str) -> bool:
        """授予应用权限"""
        config = self._get_app_config(app_name)
        print(f"[Action: grant_app_permissions] 授予{config['name']}应用权限...")
        
        permissions = config.get('permissions', [])
        if not permissions:
            print(f"  - 无需授予权限")
            print()
            return True
        
        success_count = 0
        for permission in permissions:
            try:
                perm_name = permission.split('.')[-1]
                print(f"  - 授予权限: {perm_name}...", end=' ')
                
                self.driver.execute_script('mobile: shell', {
                    'command': 'pm',
                    'args': ['grant', config['package'], permission]
                })
                print(f"✓")
                success_count += 1
            except Exception:
                print(f"⚠ 跳过")
        
        print(f"\n权限授予完成: {success_count}/{len(permissions)}")
        print()
        return success_count > 0
    
    def close_app(self, app_name: str) -> bool:
        """关闭应用"""
        config = self._get_app_config(app_name)
        print(f"[Action: close_app] 关闭{config['name']}应用...")
        
        try:
            self.driver.terminate_app(config['package'])
            print(f"✓ {config['name']}已关闭")
            print()
            return True
        except Exception as e:
            print(f"✗ 关闭失败: {e}")
            print()
            return False
    
    def uninstall_app(self, app_name: str) -> bool:
        """
        卸载应用
        
        Args:
            app_name: 应用名称 (yyb)
            
        Returns:
            是否卸载成功
        """
        config = self._get_app_config(app_name)
        print(f"[Action: uninstall_app] 卸载{config['name']}应用...")
        
        try:
            # 首先检查应用是否已安装
            print(f"  - 检查{config['name']}是否已安装...")
            if not self._is_app_installed(config['package']):
                print(f"✗ {config['name']}未安装，无需卸载")
                print()
                return True
            
            print(f"✓ 检测到{config['name']}已安装")
            
            # 先强制停止应用（确保卸载顺利）
            print(f"  - 正在停止{config['name']}应用...")
            try:
                self.driver.terminate_app(config['package'])
            except Exception:
                pass
            time.sleep(1)
            print(f"✓ {config['name']}已停止")
            
            # 使用 Appium 的 remove_app 卸载应用
            print(f"  - 正在卸载{config['name']}...")
            self.driver.remove_app(config['package'])
            
            print(f"✓ {config['name']}卸载成功")
            
            # 验证应用是否已卸载
            print(f"  - 验证卸载结果...")
            time.sleep(2)
            
            if not self._is_app_installed(config['package']):
                print(f"✓ 卸载验证通过：{config['name']}已从设备移除")
            else:
                print(f"⚠ 卸载验证异常：{config['name']}仍存在于设备中")
            
            print()
            return True
            
        except Exception as e:
            print(f"✗ {config['name']}卸载失败: {e}")
            print(f"  - 可能原因：权限不足或应用为系统应用")
            print()
            return False
    
    # ==================== 屏幕操作 ====================
    
    def tap_screen(self, x: int, y: int) -> bool:
        """点击屏幕坐标"""
        print(f"[Action: tap_screen] 点击屏幕坐标 ({x}, {y})...")
        
        try:
            self.driver.execute_script('mobile: shell', {
                'command': 'input',
                'args': ['tap', str(x), str(y)]
            })
            print(f"✓ 点击成功")
            print()
            return True
        except Exception as e:
            print(f"✗ 点击失败: {e}")
            print()
            return False
    
    def take_screenshot(self, filename: str = None) -> str:
        """截取屏幕截图"""
        print("[Action: screenshot] 截取屏幕截图...")
        
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        
        if filename is None:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{timestamp}.png"
        
        screenshot_path = OUTPUT_DIR / filename
        
        try:
            self.driver.save_screenshot(str(screenshot_path))
            print(f"✓ 截图已保存")
            print(f"  - 文件名: {filename}")
            print(f"  - 完整路径: {screenshot_path}")
            print(f"  - 文件大小: {screenshot_path.stat().st_size / 1024:.2f} KB")
            print()
            return str(screenshot_path)
        except Exception as e:
            print(f"✗ 截图失败: {e}")
            print()
            return None
    
    def set_screen_resolution(self, width: int, height: int, dpi: int = None) -> bool:
        """
        设置屏幕分辨率
        
        通过 ADB 的 wm size 命令修改 Android 设备的屏幕分辨率。
        注意：此修改是临时的，设备重启后会恢复默认分辨率。
        """
        print(f"[Action: set_screen_resolution] 设置屏幕分辨率...")
        print(f"  - 目标分辨率: {width}x{height}")
        if dpi:
            print(f"  - 目标DPI: {dpi}")
        
        try:
            # 步骤1: 获取当前分辨率
            print(f"  - 步骤1: 获取当前分辨率...")
            current_size = self.driver.execute_script('mobile: shell', {
                'command': 'wm',
                'args': ['size']
            })
            print(f"    当前设置: {current_size.strip()}")
            
            # 步骤2: 设置新分辨率
            print(f"  - 步骤2: 设置新分辨率 {width}x{height}...")
            result = self.driver.execute_script('mobile: shell', {
                'command': 'wm',
                'args': ['size', f'{width}x{height}']
            })
            
            if result and 'error' in str(result).lower():
                print(f"    ✗ 设置失败: {result}")
                return False
            
            print(f"    ✓ 分辨率已设置")
            
            # 步骤3: 如果指定了DPI，设置DPI
            if dpi:
                print(f"  - 步骤3: 设置DPI为 {dpi}...")
                dpi_result = self.driver.execute_script('mobile: shell', {
                    'command': 'wm',
                    'args': ['density', str(dpi)]
                })
                
                if dpi_result and 'error' in str(dpi_result).lower():
                    print(f"    ⚠ DPI设置失败: {dpi_result}")
                else:
                    print(f"    ✓ DPI已设置")
            
            # 步骤4: 验证分辨率是否生效
            print(f"  - 步骤4: 验证分辨率...")
            time.sleep(1)
            
            new_size = self.driver.execute_script('mobile: shell', {
                'command': 'wm',
                'args': ['size']
            })
            print(f"    新设置: {new_size.strip()}")
            
            # 解析验证
            expected = f"{width}x{height}"
            if expected in str(new_size):
                print(f"\n✓ 屏幕分辨率设置成功")
                print(f"  - 分辨率: {width}x{height}")
                
                # 显示当前DPI
                current_dpi = self.driver.execute_script('mobile: shell', {
                    'command': 'wm',
                    'args': ['density']
                })
                if current_dpi:
                    print(f"  - DPI: {current_dpi.strip()}")
                
                print(f"\n  提示：")
                print(f"    - 此修改是临时的，设备重启后会恢复默认分辨率")
                print(f"    - 使用 reset_screen_resolution 动作可恢复默认分辨率")
            else:
                print(f"\n⚠ 分辨率验证不一致，可能需要重启应用才能完全生效")
            
            print()
            return True
            
        except Exception as e:
            print(f"✗ 设置屏幕分辨率失败: {e}")
            print()
            return False
    
    def reset_screen_resolution(self) -> bool:
        """重置屏幕分辨率为默认值"""
        print(f"[Action: reset_screen_resolution] 重置屏幕分辨率...")
        
        try:
            # 获取当前分辨率
            print(f"  - 当前分辨率:")
            current_size = self.driver.execute_script('mobile: shell', {
                'command': 'wm',
                'args': ['size']
            })
            print(f"    {current_size.strip()}")
            
            # 重置分辨率
            print(f"  - 重置分辨率...")
            self.driver.execute_script('mobile: shell', {
                'command': 'wm',
                'args': ['size', 'reset']
            })
            
            # 重置DPI
            print(f"  - 重置DPI...")
            self.driver.execute_script('mobile: shell', {
                'command': 'wm',
                'args': ['density', 'reset']
            })
            
            # 验证重置结果
            time.sleep(1)
            new_size = self.driver.execute_script('mobile: shell', {
                'command': 'wm',
                'args': ['size']
            })
            new_dpi = self.driver.execute_script('mobile: shell', {
                'command': 'wm',
                'args': ['density']
            })
            
            print(f"\n✓ 屏幕分辨率已重置")
            print(f"  - 分辨率: {new_size.strip()}")
            print(f"  - DPI: {new_dpi.strip()}")
            print()
            return True
            
        except Exception as e:
            print(f"✗ 重置屏幕分辨率失败: {e}")
            print()
            return False
    
    # ==================== UI 操作 ====================
    
    def dump_ui(self, save_path: str = None) -> str:
        """
        获取当前界面的 UI 层次结构（XML格式）
        
        使用 Appium 的 page_source 获取当前界面的完整 UI 树，
        可用于分析界面元素、定位控件等。
        
        Args:
            save_path: 保存 XML 文件的本地路径（可选）
            
        Returns:
            UI XML 字符串
        """
        print("[Action: dump_ui] 获取界面 UI 结构...")
        
        try:
            # 使用 Appium 的 page_source 获取 UI 结构
            xml_content = self.driver.page_source
            
            if not xml_content:
                print(f"✗ 获取 UI 结构失败: 返回为空")
                print()
                return None
            
            # 默认保存到输出目录
            if save_path is None:
                OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
                save_path = OUTPUT_DIR / 'ui_dump.xml'
            
            with open(save_path, 'w', encoding='utf-8') as f:
                f.write(xml_content)
            
            print(f"✓ UI 结构已保存到: {save_path}")
            
            # 解析并打印关键元素信息
            self._print_ui_summary(xml_content)
            
            print()
            return xml_content
            
        except Exception as e:
            print(f"✗ 获取 UI 结构失败: {e}")
            print()
            return None
    
    def _print_ui_summary(self, xml_content: str):
        """解析并打印 UI 结构摘要"""
        
        # 提取所有可点击元素
        node_pattern = r'<[^>]*clickable="true"[^>]*>'
        clickable_nodes = re.findall(node_pattern, xml_content)
        
        if clickable_nodes:
            print(f"\n  可点击元素 ({len(clickable_nodes)} 个):")
            count = 0
            for node in clickable_nodes:
                if count >= 15:  # 最多显示15个
                    print(f"    ... 还有 {len(clickable_nodes) - 15} 个元素")
                    break
                
                # 提取属性
                text_match = re.search(r'text="([^"]*)"', node)
                res_id_match = re.search(r'resource-id="([^"]*)"', node)
                bounds_match = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', node)
                content_desc_match = re.search(r'content-desc="([^"]*)"', node)
                
                text = text_match.group(1) if text_match else ""
                res_id = res_id_match.group(1) if res_id_match else ""
                content_desc = content_desc_match.group(1) if content_desc_match else ""
                
                # 跳过没有任何标识的元素
                if not text and not res_id and not content_desc:
                    continue
                
                display_text = text[:20] if text else (content_desc[:20] if content_desc else "(无文本)")
                display_id = res_id.split('/')[-1] if res_id else "(无ID)"
                
                if bounds_match:
                    x1, y1, x2, y2 = bounds_match.groups()
                    center_x = (int(x1) + int(x2)) // 2
                    center_y = (int(y1) + int(y2)) // 2
                    print(f"    [{display_id}] {display_text} @ ({center_x}, {center_y})")
                else:
                    print(f"    [{display_id}] {display_text}")
                
                count += 1
        
        # 提取所有输入框元素
        input_pattern = r'<[^>]*class="[^"]*EditText[^"]*"[^>]*>'
        input_nodes = re.findall(input_pattern, xml_content)
        
        if input_nodes:
            print(f"\n  输入框元素 ({len(input_nodes)} 个):")
            for i, node in enumerate(input_nodes[:5]):  # 最多显示5个
                res_id_match = re.search(r'resource-id="([^"]*)"', node)
                hint_match = re.search(r'text="([^"]*)"', node)
                
                res_id = res_id_match.group(1) if res_id_match else ""
                hint = hint_match.group(1) if hint_match else ""
                
                display_id = res_id.split('/')[-1] if res_id else "(无ID)"
                display_hint = hint[:20] if hint else "(无提示文字)"
                
                print(f"    [{display_id}] {display_hint}")
    
    def click_element(self, text: str = None, resource_id: str = None, partial: bool = False) -> bool:
        """点击元素"""
        print(f"[Action: click_element] 查找并点击元素...")
        
        element = None
        
        try:
            if resource_id:
                print(f"  - 查找方式: resource-id")
                print(f"  - 目标ID: {resource_id}")
                try:
                    element = self.driver.find_element(AppiumBy.ID, resource_id)
                except Exception:
                    if ':id/' in resource_id:
                        xpath = f'//*[@resource-id="{resource_id}"]'
                    else:
                        xpath = f'//*[contains(@resource-id, ":id/{resource_id}")]'
                    element = self.driver.find_element(AppiumBy.XPATH, xpath)
            elif text:
                print(f"  - 查找方式: 文本匹配")
                print(f"  - 目标文本: {text}")
                if partial:
                    xpath = f'//*[contains(@text, "{text}")]'
                else:
                    xpath = f'//*[@text="{text}"]'
                element = self.driver.find_element(AppiumBy.XPATH, xpath)
            else:
                print(f"✗ 需要提供 text 或 resource_id 参数")
                print()
                return False
            
            if element:
                location = element.location
                size = element.size
                center_x = location['x'] + size['width'] // 2
                center_y = location['y'] + size['height'] // 2
                print(f"  - 找到元素，中心坐标: ({center_x}, {center_y})")
                
                element.click()
                print(f"✓ 点击成功")
                print()
                return True
            
        except Exception as e:
            print(f"✗ 未找到元素或点击失败: {e}")
            print()
            return False
    
    def input_text(self, text: str) -> bool:
        """输入文本"""
        print(f"[Action: input_text] 输入文本: {text}")
        
        try:
            # 尝试获取焦点元素
            try:
                active_element = self.driver.switch_to.active_element
                if active_element:
                    active_element.send_keys(text)
                    print(f"✓ 文本输入成功 (Appium)")
                    print()
                    return True
            except Exception:
                pass
            
            # 检查是否包含中文
            has_chinese = any('\u4e00' <= char <= '\u9fff' for char in text)
            
            if has_chinese:
                self.driver.execute_script('mobile: shell', {
                    'command': 'am',
                    'args': ['broadcast', '-a', 'ADB_INPUT_TEXT', '--es', 'msg', text]
                })
                print(f"✓ 文本输入成功 (ADB Broadcast)")
            else:
                escaped_text = text.replace(' ', '%s')
                self.driver.execute_script('mobile: shell', {
                    'command': 'input',
                    'args': ['text', escaped_text]
                })
                print(f"✓ 文本输入成功 (adb input)")
            
            print()
            return True
            
        except Exception as e:
            print(f"✗ 文本输入失败: {e}")
            print()
            return False
    
    # ==================== 定位操作 ====================
    
    def set_location(self, latitude: float, longitude: float, altitude: float = 0.0) -> bool:
        """设置 GPS 定位"""
        print(f"[Action: set_location] 设置GPS定位...")
        print(f"  - 纬度: {latitude}")
        print(f"  - 经度: {longitude}")
        
        if not (-90 <= latitude <= 90):
            print(f"✗ 纬度超出范围")
            return False
        
        if not (-180 <= longitude <= 180):
            print(f"✗ 经度超出范围")
            return False
        
        try:
            appium_settings_pkg = "io.appium.settings"
            
            # 授予权限
            for perm in ['ACCESS_FINE_LOCATION', 'ACCESS_COARSE_LOCATION']:
                try:
                    self.driver.execute_script('mobile: shell', {
                        'command': 'pm',
                        'args': ['grant', appium_settings_pkg, f'android.permission.{perm}']
                    })
                except Exception:
                    pass
            
            self.driver.execute_script('mobile: shell', {
                'command': 'appops',
                'args': ['set', appium_settings_pkg, 'android:mock_location', 'allow']
            })
            
            # 启动 LocationService
            self.driver.execute_script('mobile: shell', {
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
            print(f"✓ GPS定位设置完成: ({latitude}, {longitude})")
            print()
            return True
            
        except Exception as e:
            print(f"✗ GPS定位设置失败: {e}")
            print()
            return False
    
    def get_location(self) -> Dict[str, Any]:
        """获取当前 GPS 定位"""
        print("[Action: get_location] 获取当前GPS定位...")
        
        try:
            # 尝试 Appium API
            try:
                location = self.driver.location
                if location and location.get('latitude') and location.get('longitude'):
                    print(f"✓ GPS定位: ({location['latitude']}, {location['longitude']})")
                    print()
                    return location
            except Exception:
                pass
            
            # 尝试 dumpsys
            result = self.driver.execute_script('mobile: shell', {
                'command': 'dumpsys',
                'args': ['location']
            })
            
            for provider in ['gps', 'network', 'fused']:
                pattern = rf'{provider} provider.*?last location=Location\[{provider}\s+(-?[\d.]+),(-?[\d.]+).*?alt=(-?[\d.]+)'
                match = re.search(pattern, result, re.DOTALL)
                
                if match:
                    location = {
                        'latitude': float(match.group(1)),
                        'longitude': float(match.group(2)),
                        'altitude': float(match.group(3)),
                        'provider': provider
                    }
                    print(f"✓ GPS定位 ({provider}): ({location['latitude']}, {location['longitude']})")
                    print()
                    return location
            
            print(f"✗ 无法获取GPS定位")
            print()
            return None
            
        except Exception as e:
            print(f"✗ 获取GPS定位失败: {e}")
            print()
            return None
    
    # ==================== 其他操作 ====================
    
    def get_device_info(self) -> Dict[str, Any]:
        """获取设备信息"""
        print("[Action: device_info] 获取设备信息...")
        
        capabilities = self.driver.capabilities
        window_size = self.driver.get_window_size()
        
        try:
            wm_size = self.driver.execute_script('mobile: shell', {'command': 'wm', 'args': ['size']})
            wm_density = self.driver.execute_script('mobile: shell', {'command': 'wm', 'args': ['density']})
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
        
        print(f"  - 设备名称: {info['deviceName']}")
        print(f"  - 平台版本: Android {info['platformVersion']}")
        print(f"  - 屏幕分辨率: {info['wmSize']}")
        print(f"  - 屏幕DPI: {info['wmDensity']}")
        print(f"  - 窗口大小: {info['windowSize']}")
        print(f"✓ 设备信息获取完成")
        print()
        
        return info
    
    def open_browser(self, url: str) -> bool:
        """打开浏览器"""
        print(f"[Action: open_browser] 打开浏览器...")
        print(f"  - URL: {url}")
        
        try:
            self.driver.execute_script('mobile: shell', {
                'command': 'am',
                'args': ['start', '-a', 'android.intent.action.VIEW', '-d', url]
            })
            
            time.sleep(5)
            print(f"✓ 浏览器已打开")
            print()
            return True
        except Exception as e:
            print(f"✗ 打开失败: {e}")
            print()
            return False
    
    def disable_gms(self) -> bool:
        """禁用 Google Play Services"""
        print("[Action: disable_gms] 禁用 Google Play Services...")
        
        gms_package = "com.google.android.gms"
        
        try:
            if not self._is_app_installed(gms_package):
                print(f"⚠ GMS 未安装，无需禁用")
                print()
                return True
            
            self.driver.execute_script('mobile: shell', {
                'command': 'pm',
                'args': ['disable-user', '--user', '0', gms_package]
            })
            
            print(f"✓ GMS 已禁用")
            print()
            return True
        except Exception as e:
            print(f"✗ 禁用失败: {e}")
            print()
            return False
    
    def enable_gms(self) -> bool:
        """启用 Google Play Services"""
        print("[Action: enable_gms] 启用 Google Play Services...")
        
        gms_package = "com.google.android.gms"
        
        try:
            self.driver.execute_script('mobile: shell', {
                'command': 'pm',
                'args': ['enable', gms_package]
            })
            
            print(f"✓ GMS 已启用")
            print()
            return True
        except Exception as e:
            print(f"✗ 启用失败: {e}")
            print()
            return False
    
    def get_window_size(self) -> Dict[str, int]:
        """获取屏幕窗口尺寸"""
        print("[Action: get_window_size] 获取屏幕窗口尺寸...")
        
        try:
            size = self.driver.get_window_size()
            print(f"✓ 窗口尺寸: {size['width']}x{size['height']}")
            print()
            return size
        except Exception as e:
            print(f"✗ 获取失败: {e}")
            print()
            return None
    
    def get_device_model(self) -> str:
        """获取设备型号"""
        print("[Action: get_device_model] 获取设备型号...")
        
        try:
            result = self.execute_shell('getprop', ['ro.product.model'])
            model = result.strip() if result else 'N/A'
            print(f"✓ 设备型号: {model}")
            print()
            return model
        except Exception as e:
            print(f"✗ 获取失败: {e}")
            print()
            return 'N/A'
    
    def get_app_state(self, app_name: str) -> int:
        """
        获取应用状态
        
        状态码:
            0 = 未安装
            1 = 未运行
            2 = 后台暂停
            3 = 后台运行
            4 = 前台运行
        """
        config = self._get_app_config(app_name)
        print(f"[Action: get_app_state] 获取{config['name']}应用状态...")
        
        try:
            state = self.driver.query_app_state(config['package'])
            state_names = {
                0: '未安装',
                1: '未运行',
                2: '后台暂停',
                3: '后台运行',
                4: '前台运行'
            }
            state_name = state_names.get(state, '未知')
            print(f"✓ 应用状态: {state} ({state_name})")
            print()
            return state
        except Exception as e:
            print(f"✗ 获取失败: {e}")
            print()
            return -1
    
    def get_current_activity(self) -> str:
        """获取当前 Activity"""
        print("[Action: get_current_activity] 获取当前 Activity...")
        
        try:
            activity = self.driver.current_activity
            print(f"✓ 当前 Activity: {activity}")
            print()
            return activity
        except Exception as e:
            print(f"✗ 获取失败: {e}")
            print()
            return None
    
    def get_current_package(self) -> str:
        """获取当前包名"""
        print("[Action: get_current_package] 获取当前包名...")
        
        try:
            package = self.driver.current_package
            print(f"✓ 当前包名: {package}")
            print()
            return package
        except Exception as e:
            print(f"✗ 获取失败: {e}")
            print()
            return None
    
    def get_device_logs(self, save_to_file: bool = True) -> str:
        """
        获取设备日志 (logcat)
        
        Args:
            save_to_file: 是否保存到文件
        """
        print("[Action: get_device_logs] 获取设备日志...")
        
        try:
            logs = self.execute_shell('logcat', ['-d'])
            
            if logs and save_to_file:
                OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                log_path = OUTPUT_DIR / f'device_logs_{timestamp}.txt'
                log_path.write_text(logs, encoding='utf-8')
                print(f"✓ 日志已保存到: {log_path}")
                print(f"  - 日志大小: {len(logs) / 1024:.2f} KB")
            else:
                print(f"✓ 日志获取成功 ({len(logs) if logs else 0} 字节)")
            
            print()
            return logs
        except Exception as e:
            print(f"✗ 获取失败: {e}")
            print()
            return None
    
    def execute_shell(self, command: str, args: List[str] = None) -> str:
        """
        执行 ADB shell 命令
        
        Args:
            command: 命令
            args: 参数列表
            
        Returns:
            命令输出字符串
        """
        try:
            result = self.driver.execute_script('mobile: shell', {
                'command': command,
                'args': args or []
            })
            return str(result) if result else None
        except Exception:
            return None
    
    def shell(self, command: str, args: List[str] = None) -> str:
        """
        执行 ADB shell 命令（对外接口，带打印输出）
        
        Args:
            command: 命令
            args: 参数列表
        """
        print(f"[Action: shell] 执行命令: {command} {' '.join(args or [])}")
        
        try:
            result = self.execute_shell(command, args)
            if result:
                # 限制输出长度
                display_result = result[:500] + '...' if len(result) > 500 else result
                print(f"✓ 命令输出:\n{display_result}")
            else:
                print(f"✓ 命令执行成功（无输出）")
            print()
            return result
        except Exception as e:
            print(f"✗ 执行失败: {e}")
            print()
            return None


def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="E2B 沙箱客户端 - 连接到已存在的沙箱执行移动端操作",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
支持的测试动作:

  应用操作 (需配合 --app-name yyb):
    upload_app              - 上传应用APK到设备
    install_app             - 安装已上传的应用APK
    launch_app              - 启动应用
    check_app               - 检查应用是否已安装
    grant_app_permissions   - 授予应用权限
    close_app               - 关闭应用
    uninstall_app           - 卸载应用

  屏幕操作:
    tap_screen              - 点击屏幕坐标（需 --tap-x 和 --tap-y）
    screenshot              - 截取屏幕截图
    set_screen_resolution   - 设置屏幕分辨率（需 --width 和 --height）
    reset_screen_resolution - 重置屏幕分辨率

  UI 操作:
    dump_ui                 - 获取当前界面 UI 结构
    click_element           - 点击元素（需 --element-text 或 --element-id）
    input_text              - 输入文本（需 --text）

  定位操作:
    set_location            - 设置GPS定位（需 --latitude 和 --longitude）
    get_location            - 获取当前GPS定位

  其他操作:
    device_info             - 获取设备信息
    get_window_size         - 获取屏幕窗口尺寸
    get_device_model        - 获取设备型号
    get_app_state           - 获取应用状态（需 --app-name）
    get_current_activity    - 获取当前 Activity
    get_current_package     - 获取当前包名
    get_device_logs         - 获取设备日志
    open_browser            - 打开浏览器（需 --url）
    disable_gms             - 禁用 Google Play Services
    enable_gms              - 启用 Google Play Services
    shell                   - 执行 ADB shell 命令（需 --shell-cmd）

使用示例:
    %(prog)s --sandbox-id <id> --action device_info
    %(prog)s --sandbox-id <id> --action screenshot
    %(prog)s --sandbox-id <id> --action tap_screen --tap-x 500 --tap-y 1000
    %(prog)s --sandbox-id <id> --action input_text --text "Hello World"
    %(prog)s --sandbox-id <id> --action click_element --element-id "com.example:id/button"
    %(prog)s --sandbox-id <id> --action launch_app --app-name yyb
    %(prog)s --sandbox-id <id> --action set_location --latitude 22.5431 --longitude 113.9298
    %(prog)s --sandbox-id <id> --action upload_app,install_app,launch_app --app-name yyb
    %(prog)s --sandbox-id <id> --action shell --shell-cmd "pm list packages"
        """
    )
    
    parser.add_argument('--sandbox-id', type=str, required=True, help='沙箱 ID')
    parser.add_argument('--action', type=str, required=True, help='要执行的动作，多个动作用逗号分隔')
    parser.add_argument('--app-name', type=str, default=None, help='应用名称 (yyb)')
    parser.add_argument('--apk-path', type=str, default=None, help='APK 文件路径')
    parser.add_argument('--tap-x', type=int, default=None, help='点击 X 坐标')
    parser.add_argument('--tap-y', type=int, default=None, help='点击 Y 坐标')
    parser.add_argument('--text', type=str, default=None, help='输入文本')
    parser.add_argument('--element-text', type=str, default=None, help='元素文本')
    parser.add_argument('--element-id', type=str, default=None, help='元素 resource-id')
    parser.add_argument('--latitude', type=float, default=None, help='GPS 纬度')
    parser.add_argument('--longitude', type=float, default=None, help='GPS 经度')
    parser.add_argument('--altitude', type=float, default=0.0, help='GPS 海拔')
    parser.add_argument('--width', type=int, default=None, help='屏幕宽度')
    parser.add_argument('--height', type=int, default=None, help='屏幕高度')
    parser.add_argument('--dpi', type=int, default=None, help='屏幕 DPI')
    parser.add_argument('--url', type=str, default=None, help='浏览器 URL')
    parser.add_argument('--shell-cmd', type=str, default=None, help='ADB shell 命令')
    parser.add_argument('--list-actions', action='store_true', help='列出所有可用动作')
    
    return parser.parse_args()


def execute_actions(client: SandboxClient, actions: List[str], args):
    """执行测试动作"""
    results = {}
    
    for i, action in enumerate(actions, 1):
        print(f"[{i}/{len(actions)}] 执行动作: {action}")
        print("-" * 70)
        
        try:
            # 应用操作
            if action == 'upload_app':
                if args.app_name is None:
                    print(f"✗ upload_app 需要 --app-name 参数")
                    results[action] = False
                else:
                    results[action] = client.upload_app(args.app_name, args.apk_path)
            
            elif action == 'install_app':
                if args.app_name is None:
                    print(f"✗ install_app 需要 --app-name 参数")
                    results[action] = False
                else:
                    results[action] = client.install_app(args.app_name)
            
            elif action == 'launch_app':
                if args.app_name is None:
                    print(f"✗ launch_app 需要 --app-name 参数")
                    results[action] = False
                else:
                    results[action] = client.launch_app(args.app_name)
            
            elif action == 'check_app':
                if args.app_name is None:
                    print(f"✗ check_app 需要 --app-name 参数")
                    results[action] = False
                else:
                    results[action] = client.check_app_installed(args.app_name)
            
            elif action == 'grant_app_permissions':
                if args.app_name is None:
                    print(f"✗ grant_app_permissions 需要 --app-name 参数")
                    results[action] = False
                else:
                    results[action] = client.grant_app_permissions(args.app_name)
            
            elif action == 'close_app':
                if args.app_name is None:
                    print(f"✗ close_app 需要 --app-name 参数")
                    results[action] = False
                else:
                    results[action] = client.close_app(args.app_name)
            
            elif action == 'uninstall_app':
                if args.app_name is None:
                    print(f"✗ uninstall_app 需要 --app-name 参数")
                    results[action] = False
                else:
                    results[action] = client.uninstall_app(args.app_name)
            
            # 屏幕操作
            elif action == 'tap_screen':
                if args.tap_x is None or args.tap_y is None:
                    print(f"✗ tap_screen 需要 --tap-x 和 --tap-y 参数")
                    results[action] = False
                else:
                    results[action] = client.tap_screen(args.tap_x, args.tap_y)
            
            elif action == 'screenshot':
                results[action] = client.take_screenshot() is not None
            
            elif action == 'set_screen_resolution':
                if args.width is None or args.height is None:
                    print(f"✗ set_screen_resolution 需要 --width 和 --height 参数")
                    results[action] = False
                else:
                    results[action] = client.set_screen_resolution(args.width, args.height, args.dpi)
            
            elif action == 'reset_screen_resolution':
                results[action] = client.reset_screen_resolution()
            
            # UI 操作
            elif action == 'dump_ui':
                results[action] = client.dump_ui() is not None
            
            elif action == 'click_element':
                if args.element_text is None and args.element_id is None:
                    print(f"✗ click_element 需要 --element-text 或 --element-id 参数")
                    results[action] = False
                else:
                    results[action] = client.click_element(
                        text=args.element_text,
                        resource_id=args.element_id
                    )
            
            elif action == 'input_text':
                if args.text is None:
                    print(f"✗ input_text 需要 --text 参数")
                    results[action] = False
                else:
                    results[action] = client.input_text(args.text)
            
            # 定位操作
            elif action == 'set_location':
                if args.latitude is None or args.longitude is None:
                    print(f"✗ set_location 需要 --latitude 和 --longitude 参数")
                    results[action] = False
                else:
                    results[action] = client.set_location(args.latitude, args.longitude, args.altitude)
            
            elif action == 'get_location':
                results[action] = client.get_location() is not None
            
            # 其他操作
            elif action == 'device_info':
                results[action] = client.get_device_info() is not None
            
            elif action == 'open_browser':
                if args.url is None:
                    print(f"✗ open_browser 需要 --url 参数")
                    results[action] = False
                else:
                    results[action] = client.open_browser(args.url)
            
            elif action == 'disable_gms':
                results[action] = client.disable_gms()
            
            elif action == 'enable_gms':
                results[action] = client.enable_gms()
            
            elif action == 'get_window_size':
                results[action] = client.get_window_size() is not None
            
            elif action == 'get_device_model':
                results[action] = client.get_device_model() is not None
            
            elif action == 'get_app_state':
                if args.app_name is None:
                    print(f"✗ get_app_state 需要 --app-name 参数")
                    results[action] = False
                else:
                    results[action] = client.get_app_state(args.app_name) >= 0
            
            elif action == 'get_current_activity':
                results[action] = client.get_current_activity() is not None
            
            elif action == 'get_current_package':
                results[action] = client.get_current_package() is not None
            
            elif action == 'get_device_logs':
                results[action] = client.get_device_logs() is not None
            
            elif action == 'shell':
                if args.shell_cmd is None:
                    print(f"✗ shell 需要 --shell-cmd 参数")
                    results[action] = False
                else:
                    # 解析命令和参数
                    parts = args.shell_cmd.split()
                    cmd = parts[0] if parts else ''
                    cmd_args = parts[1:] if len(parts) > 1 else []
                    results[action] = client.shell(cmd, cmd_args) is not None
            
            else:
                print(f"✗ 未知的动作: {action}")
                results[action] = False
        
        except Exception as e:
            print(f"✗ 动作执行失败: {e}")
            results[action] = False
        
        print()
    
    # 打印执行摘要
    print("=" * 70)
    print("执行摘要")
    print("=" * 70)
    
    success_count = sum(1 for v in results.values() if v)
    total_count = len(results)
    
    for action, result in results.items():
        status = "✓ 成功" if result else "✗ 失败"
        print(f"{action:<25} : {status}")
    
    print("-" * 70)
    print(f"总计: {success_count}/{total_count} 成功")
    print("=" * 70)


def main():
    """主函数"""
    # 加载环境变量
    _load_env_file()
    
    args = parse_arguments()
    
    # 检查 API Key
    if not os.getenv("E2B_API_KEY"):
        print("错误: E2B_API_KEY 未设置")
        print("请在 .env 文件中设置或导出环境变量")
        sys.exit(1)
    
    # 解析动作列表
    actions = [a.strip() for a in args.action.split(',')]
    
    # 创建客户端
    client = SandboxClient(sandbox_id=args.sandbox_id)
    
    try:
        # 连接
        client.connect()
        
        # 执行动作
        execute_actions(client, actions, args)
        
    except Exception as e:
        print(f"✗ 发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    finally:
        # 断开连接
        client.disconnect()
        
        print("=" * 70)
        print("测试完成！")
        print("=" * 70)


if __name__ == '__main__':
    main()
