#!/usr/bin/env python3
"""
Single Sandbox Connection Tool - Connect to an existing E2B sandbox for mobile automation

Unlike quickstart.py (creates a new sandbox and runs a complete demo) and batch.py (batch testing),
this tool connects to an existing single sandbox and executes mobile automation operations via CLI.

Supported actions:
1. App operations: upload_app, install_app, launch_app, check_app, grant_app_permissions, close_app, uninstall_app, get_app_state
2. Screen operations: tap_screen, screenshot, set_screen_resolution, reset_screen_resolution, get_window_size
3. UI operations: dump_ui, click_element, input_text
4. Location operations: set_location, get_location
5. Device info: device_info, get_device_model, get_current_activity, get_current_package
6. System operations: open_browser, disable_gms, enable_gms, get_device_logs, shell

Usage examples:
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

# Script directory
SCRIPT_DIR = Path(__file__).parent
OUTPUT_DIR = SCRIPT_DIR / "output" / "sandbox_connect_output"

# Chunked upload configuration
CHUNK_SIZE = 20 * 1024 * 1024  # 20MB per chunk

# App configuration dictionary
APP_CONFIGS = {
    'yyb': {
        'name': 'Tencent App Store',
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
    """Load .env file"""
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
    """E2B Sandbox Client"""
    
    def __init__(self, sandbox_id: str, e2b_domain: str = None, e2b_api_key: str = None):
        """
        Initialize sandbox client
        
        Args:
            sandbox_id: Sandbox ID
            e2b_domain: E2B domain
            e2b_api_key: E2B API Key
        """
        self.sandbox_id = sandbox_id
        self.e2b_domain = e2b_domain or os.getenv("E2B_DOMAIN", "ap-guangzhou.tencentags.com")
        self.e2b_api_key = e2b_api_key or os.getenv("E2B_API_KEY", "")
        self.sandbox = None
        self.driver = None
        
        # Set environment variables
        os.environ["E2B_DOMAIN"] = self.e2b_domain
        os.environ["E2B_API_KEY"] = self.e2b_api_key
    
    def connect(self):
        """Connect to sandbox and Appium"""
        print("=" * 70)
        print("E2B Sandbox Client")
        print("=" * 70)
        print(f"Sandbox ID: {self.sandbox_id}")
        print(f"E2B Domain: {self.e2b_domain}")
        print("=" * 70)
        print()
        
        # Connect to sandbox
        print("[Connect] Connecting to sandbox...")
        try:
            self.sandbox = Sandbox.connect(self.sandbox_id)
            print(f"✓ Sandbox connected successfully")
        except Exception as e:
            print(f"✗ Sandbox connection failed: {e}")
            raise
        
        # Display VNC URL
        vnc_url = self._get_vnc_url()
        print(f"\nVNC URL (open in browser for real-time screen viewing):")
        print(vnc_url)
        print()
        
        # Connect to Appium
        print("[Connect] Connecting to Appium...")
        try:
            self.driver = self._create_appium_driver()
            print(f"✓ Appium connected successfully (Session ID: {self.driver.session_id})")
        except Exception as e:
            print(f"✗ Appium connection failed: {e}")
            raise
        print()
    
    def disconnect(self):
        """Disconnect from sandbox"""
        if self.driver:
            print("[Cleanup] Closing Appium session...")
            try:
                self.driver.quit()
            except Exception as e:
                print(f"[Warning] Error closing session (can be ignored): {e}")
            finally:
                self.driver = None
                print("✓ Session closed")
                print()
    
    def _get_vnc_url(self) -> str:
        """Get VNC URL"""
        scrcpy_host = self.sandbox.get_host(8000)
        scrcpy_token = self.sandbox._envd_access_token
        scrcpy_udid = "emulator-5554"
        scrcpy_ws = f"wss://{scrcpy_host}/?action=proxy-adb&remote=tcp%3A8886&udid={scrcpy_udid}&access_token={scrcpy_token}"
        scrcpy_url = f"https://{scrcpy_host}/?access_token={scrcpy_token}#!action=stream&udid={scrcpy_udid}&player=webcodecs&ws={quote(scrcpy_ws, safe='')}"
        return scrcpy_url
    
    def _create_appium_driver(self) -> WebDriver:
        """Create Appium Driver"""
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
        """Get app configuration"""
        app_name = app_name.lower()
        if app_name not in APP_CONFIGS:
            raise ValueError(f"Unsupported app: {app_name}, supported apps: {', '.join(APP_CONFIGS.keys())}")
        return APP_CONFIGS[app_name]
    
    def _is_app_installed(self, package_name: str) -> bool:
        """Check if app is installed"""
        try:
            state = self.driver.query_app_state(package_name)
            return state != 0
        except Exception:
            result = self.driver.execute_script('mobile: shell', {
                'command': 'pm',
                'args': ['list', 'packages', package_name]
            })
            return package_name in str(result)
    
    # ==================== App Operations ====================
    
    def upload_app(self, app_name: str, apk_path: str = None) -> bool:
        """Upload APK to device (chunked upload)"""
        config = self._get_app_config(app_name)
        print(f"[Action: upload_app] Uploading {config['name']} APK to device...")
        
        if apk_path is None:
            apk_path = SCRIPT_DIR / "apk" / config['apk_name']
        else:
            apk_path = Path(apk_path)
        
        if not apk_path.exists():
            print(f"✗ APK file not found: {apk_path}")
            return False
        
        file_size = apk_path.stat().st_size
        total_chunks = (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE
        
        print(f"  - Local APK path: {apk_path}")
        print(f"  - File size: {file_size / 1024 / 1024:.2f} MB")
        print(f"  - Number of chunks: {total_chunks}")
        
        temp_dir = '/data/local/tmp/chunks'
        remote_path = config['remote_path']
        
        try:
            # Clean up and create temp directory
            self.driver.execute_script('mobile: shell', {'command': 'rm', 'args': ['-rf', temp_dir]})
            self.driver.execute_script('mobile: shell', {'command': 'mkdir', 'args': ['-p', temp_dir]})
            self.driver.execute_script('mobile: shell', {'command': 'rm', 'args': ['-f', remote_path]})
            
            start_time = time.time()
            
            # Upload chunks
            print(f"  [Phase 1] Uploading chunks...")
            with open(apk_path, 'rb') as f:
                for i in range(total_chunks):
                    chunk_data = f.read(CHUNK_SIZE)
                    chunk_b64 = base64.b64encode(chunk_data).decode('utf-8')
                    chunk_path = f"{temp_dir}/chunk_{i:04d}"
                    
                    print(f"    - Chunk {i + 1}/{total_chunks} ({len(chunk_data) / 1024 / 1024:.2f}MB)...", end=' ', flush=True)
                    chunk_start = time.time()
                    self.driver.push_file(chunk_path, chunk_b64)
                    print(f"Done ({time.time() - chunk_start:.1f}s)")
            
            # Merge chunks
            print(f"  [Phase 2] Merging chunks...")
            for i in range(total_chunks):
                chunk_path = f"{temp_dir}/chunk_{i:04d}"
                print(f"    - Merging chunk {i + 1}/{total_chunks}...", end=' ', flush=True)
                
                if i == 0:
                    self.driver.execute_script('mobile: shell', {'command': 'cp', 'args': [chunk_path, remote_path]})
                else:
                    # Subsequent chunks: append to target file
                    self.driver.execute_script('mobile: shell', {
                        'command': 'cat',
                        'args': [chunk_path, '>>', remote_path]
                    })
                
                self.driver.execute_script('mobile: shell', {'command': 'rm', 'args': ['-f', chunk_path]})
                print(f"Done")
            
            # Cleanup
            self.driver.execute_script('mobile: shell', {'command': 'rm', 'args': ['-rf', temp_dir]})
            
            # Verify
            result = self.driver.execute_script('mobile: shell', {'command': 'ls', 'args': ['-la', remote_path]})
            
            print(f"  - Total time: {time.time() - start_time:.1f}s")
            
            if result and 'No such file' not in str(result):
                print(f"✓ APK upload completed")
                print()
                return True
            else:
                print(f"✗ File verification failed")
                print()
                return False
                
        except Exception as e:
            print(f"✗ APK upload failed: {e}")
            print()
            return False
    
    def install_app(self, app_name: str) -> bool:
        """Install app"""
        config = self._get_app_config(app_name)
        print(f"[Action: install_app] Installing {config['name']}...")
        
        try:
            # Check if already installed
            if self._is_app_installed(config['package']):
                print(f"  ⚠ {config['name']} already installed, skipping")
                print(f"✓ {config['name']} is available")
                print()
                return True
            
            # Install
            print(f"  - Installing APK...")
            result = self.driver.execute_script('mobile: shell', {
                'command': 'pm',
                'args': ['install', '-r', '-g', config['remote_path']]
            })
            
            if result and ('Success' in str(result) or 'success' in str(result).lower()):
                print(f"✓ {config['name']} installed successfully")
                print()
                return True
            
            # Verify
            time.sleep(2)
            if self._is_app_installed(config['package']):
                print(f"✓ {config['name']} installed successfully (verified)")
                print()
                return True
            
            print(f"✗ {config['name']} installation failed")
            print()
            return False
            
        except Exception as e:
            print(f"✗ Installation failed: {e}")
            print()
            return False
    
    def launch_app(self, app_name: str) -> bool:
        """Launch app"""
        config = self._get_app_config(app_name)
        print(f"[Action: launch_app] Launching {config['name']}...")
        
        try:
            self.driver.activate_app(config['package'])
            print(f"✓ {config['name']} launched")
            time.sleep(3)
            
            app_state = self.driver.query_app_state(config['package'])
            if app_state == 4:
                print(f"✓ App is running in foreground")
            elif app_state == 3:
                print(f"⚠ App is running in background")
            
            print()
            return True
            
        except Exception as e:
            print(f"✗ Launch failed: {e}")
            print()
            return False
    
    def check_app_installed(self, app_name: str) -> bool:
        """Check if app is installed"""
        config = self._get_app_config(app_name)
        print(f"[Action: check_app] Checking if {config['name']} is installed...")
        
        is_installed = self._is_app_installed(config['package'])
        
        if is_installed:
            print(f"✓ {config['name']} is installed (package: {config['package']})")
        else:
            print(f"✗ {config['name']} is not installed")
        
        print()
        return is_installed
    
    def grant_app_permissions(self, app_name: str) -> bool:
        """Grant app permissions"""
        config = self._get_app_config(app_name)
        print(f"[Action: grant_app_permissions] Granting permissions to {config['name']}...")
        
        permissions = config.get('permissions', [])
        if not permissions:
            print(f"  - No permissions to grant")
            print()
            return True
        
        success_count = 0
        for permission in permissions:
            try:
                perm_name = permission.split('.')[-1]
                print(f"  - Granting permission: {perm_name}...", end=' ')
                
                self.driver.execute_script('mobile: shell', {
                    'command': 'pm',
                    'args': ['grant', config['package'], permission]
                })
                print(f"✓")
                success_count += 1
            except Exception:
                print(f"⚠ Skipped")
        
        print(f"\nPermissions granted: {success_count}/{len(permissions)}")
        print()
        return success_count > 0
    
    def close_app(self, app_name: str) -> bool:
        """Close app"""
        config = self._get_app_config(app_name)
        print(f"[Action: close_app] Closing {config['name']}...")
        
        try:
            self.driver.terminate_app(config['package'])
            print(f"✓ {config['name']} closed")
            print()
            return True
        except Exception as e:
            print(f"✗ Close failed: {e}")
            print()
            return False
    
    def uninstall_app(self, app_name: str) -> bool:
        """
        Uninstall app
        
        Args:
            app_name: App name (yyb)
            
        Returns:
            Whether uninstall was successful
        """
        config = self._get_app_config(app_name)
        print(f"[Action: uninstall_app] Uninstalling {config['name']}...")
        
        try:
            # First check if app is installed
            print(f"  - Checking if {config['name']} is installed...")
            if not self._is_app_installed(config['package']):
                print(f"✗ {config['name']} is not installed, no need to uninstall")
                print()
                return True
            
            print(f"✓ {config['name']} is installed")
            
            # Force stop app first (to ensure smooth uninstall)
            print(f"  - Stopping {config['name']}...")
            try:
                self.driver.terminate_app(config['package'])
            except Exception:
                pass
            time.sleep(1)
            print(f"✓ {config['name']} stopped")
            
            # Uninstall using Appium's remove_app
            print(f"  - Uninstalling {config['name']}...")
            self.driver.remove_app(config['package'])
            
            print(f"✓ {config['name']} uninstalled successfully")
            
            # Verify app is uninstalled
            print(f"  - Verifying uninstall...")
            time.sleep(2)
            
            if not self._is_app_installed(config['package']):
                print(f"✓ Uninstall verified: {config['name']} has been removed from device")
            else:
                print(f"⚠ Verification warning: {config['name']} still exists on device")
            
            print()
            return True
            
        except Exception as e:
            print(f"✗ {config['name']} uninstall failed: {e}")
            print(f"  - Possible reason: insufficient permissions or system app")
            print()
            return False
    
    # ==================== Screen Operations ====================
    
    def tap_screen(self, x: int, y: int) -> bool:
        """Tap screen at coordinates"""
        print(f"[Action: tap_screen] Tapping screen at ({x}, {y})...")
        
        try:
            self.driver.execute_script('mobile: shell', {
                'command': 'input',
                'args': ['tap', str(x), str(y)]
            })
            print(f"✓ Tap successful")
            print()
            return True
        except Exception as e:
            print(f"✗ Tap failed: {e}")
            print()
            return False
    
    def take_screenshot(self, filename: str = None) -> str:
        """Take screenshot"""
        print("[Action: screenshot] Taking screenshot...")
        
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        
        if filename is None:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{timestamp}.png"
        
        screenshot_path = OUTPUT_DIR / filename
        
        try:
            self.driver.save_screenshot(str(screenshot_path))
            print(f"✓ Screenshot saved")
            print(f"  - Filename: {filename}")
            print(f"  - Full path: {screenshot_path}")
            print(f"  - File size: {screenshot_path.stat().st_size / 1024:.2f} KB")
            print()
            return str(screenshot_path)
        except Exception as e:
            print(f"✗ Screenshot failed: {e}")
            print()
            return None
    
    def set_screen_resolution(self, width: int, height: int, dpi: int = None) -> bool:
        """
        Set screen resolution
        
        Uses ADB wm size command to modify Android device screen resolution.
        Note: This change is temporary and will be reset after device reboot.
        """
        print(f"[Action: set_screen_resolution] Setting screen resolution...")
        print(f"  - Target resolution: {width}x{height}")
        if dpi:
            print(f"  - Target DPI: {dpi}")
        
        try:
            # Step 1: Get current resolution
            print(f"  - Step 1: Getting current resolution...")
            current_size = self.driver.execute_script('mobile: shell', {
                'command': 'wm',
                'args': ['size']
            })
            print(f"    Current setting: {current_size.strip()}")
            
            # Step 2: Set new resolution
            print(f"  - Step 2: Setting new resolution {width}x{height}...")
            result = self.driver.execute_script('mobile: shell', {
                'command': 'wm',
                'args': ['size', f'{width}x{height}']
            })
            
            if result and 'error' in str(result).lower():
                print(f"    ✗ Setting failed: {result}")
                return False
            
            print(f"    ✓ Resolution set")
            
            # Step 3: Set DPI if specified
            if dpi:
                print(f"  - Step 3: Setting DPI to {dpi}...")
                dpi_result = self.driver.execute_script('mobile: shell', {
                    'command': 'wm',
                    'args': ['density', str(dpi)]
                })
                
                if dpi_result and 'error' in str(dpi_result).lower():
                    print(f"    ⚠ DPI setting failed: {dpi_result}")
                else:
                    print(f"    ✓ DPI set")
            
            # Step 4: Verify resolution is applied
            print(f"  - Step 4: Verifying resolution...")
            time.sleep(1)
            
            new_size = self.driver.execute_script('mobile: shell', {
                'command': 'wm',
                'args': ['size']
            })
            print(f"    New setting: {new_size.strip()}")
            
            # Parse and verify
            expected = f"{width}x{height}"
            if expected in str(new_size):
                print(f"\n✓ Screen resolution set successfully")
                print(f"  - Resolution: {width}x{height}")
                
                # Display current DPI
                current_dpi = self.driver.execute_script('mobile: shell', {
                    'command': 'wm',
                    'args': ['density']
                })
                if current_dpi:
                    print(f"  - DPI: {current_dpi.strip()}")
                
                print(f"\n  Note:")
                print(f"    - This change is temporary and will be reset after device reboot")
                print(f"    - Use reset_screen_resolution action to restore default resolution")
            else:
                print(f"\n⚠ Resolution verification mismatch, may need to restart app for full effect")
            
            print()
            return True
            
        except Exception as e:
            print(f"✗ Set screen resolution failed: {e}")
            print()
            return False
    
    def reset_screen_resolution(self) -> bool:
        """Reset screen resolution to default"""
        print(f"[Action: reset_screen_resolution] Resetting screen resolution...")
        
        try:
            # Get current resolution
            print(f"  - Current resolution:")
            current_size = self.driver.execute_script('mobile: shell', {
                'command': 'wm',
                'args': ['size']
            })
            print(f"    {current_size.strip()}")
            
            # Reset resolution
            print(f"  - Resetting resolution...")
            self.driver.execute_script('mobile: shell', {
                'command': 'wm',
                'args': ['size', 'reset']
            })
            
            # Reset DPI
            print(f"  - Resetting DPI...")
            self.driver.execute_script('mobile: shell', {
                'command': 'wm',
                'args': ['density', 'reset']
            })
            
            # Verify reset result
            time.sleep(1)
            new_size = self.driver.execute_script('mobile: shell', {
                'command': 'wm',
                'args': ['size']
            })
            new_dpi = self.driver.execute_script('mobile: shell', {
                'command': 'wm',
                'args': ['density']
            })
            
            print(f"\n✓ Screen resolution reset")
            print(f"  - Resolution: {new_size.strip()}")
            print(f"  - DPI: {new_dpi.strip()}")
            print()
            return True
            
        except Exception as e:
            print(f"✗ Reset screen resolution failed: {e}")
            print()
            return False
    
    # ==================== UI Operations ====================
    
    def dump_ui(self, save_path: str = None) -> str:
        """
        Get current screen UI hierarchy (XML format)
        
        Uses Appium's page_source to get the complete UI tree of current screen,
        useful for analyzing UI elements and locating controls.
        
        Args:
            save_path: Local path to save XML file (optional)
            
        Returns:
            UI XML string
        """
        print("[Action: dump_ui] Getting UI hierarchy...")
        
        try:
            # Get UI structure using Appium's page_source
            xml_content = self.driver.page_source
            
            if not xml_content:
                print(f"✗ Failed to get UI structure: empty response")
                print()
                return None
            
            # Save to output directory by default
            if save_path is None:
                OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
                save_path = OUTPUT_DIR / 'ui_dump.xml'
            
            with open(save_path, 'w', encoding='utf-8') as f:
                f.write(xml_content)
            
            print(f"✓ UI structure saved to: {save_path}")
            
            # Parse and print key element info
            self._print_ui_summary(xml_content)
            
            print()
            return xml_content
            
        except Exception as e:
            print(f"✗ Failed to get UI structure: {e}")
            print()
            return None
    
    def _print_ui_summary(self, xml_content: str):
        """Parse and print UI structure summary"""
        
        # Extract all clickable elements
        node_pattern = r'<[^>]*clickable="true"[^>]*>'
        clickable_nodes = re.findall(node_pattern, xml_content)
        
        if clickable_nodes:
            print(f"\n  Clickable elements ({len(clickable_nodes)} total):")
            count = 0
            for node in clickable_nodes:
                if count >= 15:  # Show at most 15
                    print(f"    ... {len(clickable_nodes) - 15} more elements")
                    break
                
                # Extract attributes
                text_match = re.search(r'text="([^"]*)"', node)
                res_id_match = re.search(r'resource-id="([^"]*)"', node)
                bounds_match = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', node)
                content_desc_match = re.search(r'content-desc="([^"]*)"', node)
                
                text = text_match.group(1) if text_match else ""
                res_id = res_id_match.group(1) if res_id_match else ""
                content_desc = content_desc_match.group(1) if content_desc_match else ""
                
                # Skip elements without any identifier
                if not text and not res_id and not content_desc:
                    continue
                
                display_text = text[:20] if text else (content_desc[:20] if content_desc else "(no text)")
                display_id = res_id.split('/')[-1] if res_id else "(no ID)"
                
                if bounds_match:
                    x1, y1, x2, y2 = bounds_match.groups()
                    center_x = (int(x1) + int(x2)) // 2
                    center_y = (int(y1) + int(y2)) // 2
                    print(f"    [{display_id}] {display_text} @ ({center_x}, {center_y})")
                else:
                    print(f"    [{display_id}] {display_text}")
                
                count += 1
        
        # Extract all input field elements
        input_pattern = r'<[^>]*class="[^"]*EditText[^"]*"[^>]*>'
        input_nodes = re.findall(input_pattern, xml_content)
        
        if input_nodes:
            print(f"\n  Input fields ({len(input_nodes)} total):")
            for i, node in enumerate(input_nodes[:5]):  # Show at most 5
                res_id_match = re.search(r'resource-id="([^"]*)"', node)
                hint_match = re.search(r'text="([^"]*)"', node)
                
                res_id = res_id_match.group(1) if res_id_match else ""
                hint = hint_match.group(1) if hint_match else ""
                
                display_id = res_id.split('/')[-1] if res_id else "(no ID)"
                display_hint = hint[:20] if hint else "(no hint text)"
                
                print(f"    [{display_id}] {display_hint}")
    
    def click_element(self, text: str = None, resource_id: str = None, partial: bool = False) -> bool:
        """Click element"""
        print(f"[Action: click_element] Finding and clicking element...")
        
        element = None
        
        try:
            if resource_id:
                print(f"  - Search method: resource-id")
                print(f"  - Target ID: {resource_id}")
                try:
                    element = self.driver.find_element(AppiumBy.ID, resource_id)
                except Exception:
                    if ':id/' in resource_id:
                        xpath = f'//*[@resource-id="{resource_id}"]'
                    else:
                        xpath = f'//*[contains(@resource-id, ":id/{resource_id}")]'
                    element = self.driver.find_element(AppiumBy.XPATH, xpath)
            elif text:
                print(f"  - Search method: text matching")
                print(f"  - Target text: {text}")
                if partial:
                    xpath = f'//*[contains(@text, "{text}")]'
                else:
                    xpath = f'//*[@text="{text}"]'
                element = self.driver.find_element(AppiumBy.XPATH, xpath)
            else:
                print(f"✗ Either text or resource_id parameter is required")
                print()
                return False
            
            if element:
                location = element.location
                size = element.size
                center_x = location['x'] + size['width'] // 2
                center_y = location['y'] + size['height'] // 2
                print(f"  - Element found, center coordinates: ({center_x}, {center_y})")
                
                element.click()
                print(f"✓ Click successful")
                print()
                return True
            
        except Exception as e:
            print(f"✗ Element not found or click failed: {e}")
            print()
            return False
    
    def input_text(self, text: str) -> bool:
        """Input text"""
        print(f"[Action: input_text] Inputting text: {text}")
        
        try:
            # Try to get focused element
            try:
                active_element = self.driver.switch_to.active_element
                if active_element:
                    active_element.send_keys(text)
                    print(f"✓ Text input successful (Appium)")
                    print()
                    return True
            except Exception:
                pass
            
            # Check if text contains Chinese characters
            has_chinese = any('\u4e00' <= char <= '\u9fff' for char in text)
            
            if has_chinese:
                self.driver.execute_script('mobile: shell', {
                    'command': 'am',
                    'args': ['broadcast', '-a', 'ADB_INPUT_TEXT', '--es', 'msg', text]
                })
                print(f"✓ Text input successful (ADB Broadcast)")
            else:
                escaped_text = text.replace(' ', '%s')
                self.driver.execute_script('mobile: shell', {
                    'command': 'input',
                    'args': ['text', escaped_text]
                })
                print(f"✓ Text input successful (adb input)")
            
            print()
            return True
            
        except Exception as e:
            print(f"✗ Text input failed: {e}")
            print()
            return False
    
    # ==================== Location Operations ====================
    
    def set_location(self, latitude: float, longitude: float, altitude: float = 0.0) -> bool:
        """Set GPS location"""
        print(f"[Action: set_location] Setting GPS location...")
        print(f"  - Latitude: {latitude}")
        print(f"  - Longitude: {longitude}")
        
        if not (-90 <= latitude <= 90):
            print(f"✗ Latitude out of range")
            return False
        
        if not (-180 <= longitude <= 180):
            print(f"✗ Longitude out of range")
            return False
        
        try:
            appium_settings_pkg = "io.appium.settings"
            
            # Grant permissions
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
            
            # Start LocationService
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
            print(f"✓ GPS location set: ({latitude}, {longitude})")
            print()
            return True
            
        except Exception as e:
            print(f"✗ GPS location setting failed: {e}")
            print()
            return False
    
    def get_location(self) -> Dict[str, Any]:
        """Get current GPS location"""
        print("[Action: get_location] Getting current GPS location...")
        
        try:
            # Try Appium API
            try:
                location = self.driver.location
                if location and location.get('latitude') and location.get('longitude'):
                    print(f"✓ GPS location: ({location['latitude']}, {location['longitude']})")
                    print()
                    return location
            except Exception:
                pass
            
            # Try dumpsys
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
                    print(f"✓ GPS location ({provider}): ({location['latitude']}, {location['longitude']})")
                    print()
                    return location
            
            print(f"✗ Unable to get GPS location")
            print()
            return None
            
        except Exception as e:
            print(f"✗ Failed to get GPS location: {e}")
            print()
            return None
    
    # ==================== Other Operations ====================
    
    def get_device_info(self) -> Dict[str, Any]:
        """Get device information"""
        print("[Action: device_info] Getting device information...")
        
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
        
        print(f"  - Device name: {info['deviceName']}")
        print(f"  - Platform version: Android {info['platformVersion']}")
        print(f"  - Screen resolution: {info['wmSize']}")
        print(f"  - Screen DPI: {info['wmDensity']}")
        print(f"  - Window size: {info['windowSize']}")
        print(f"✓ Device info retrieved")
        print()
        
        return info
    
    def open_browser(self, url: str) -> bool:
        """Open browser"""
        print(f"[Action: open_browser] Opening browser...")
        print(f"  - URL: {url}")
        
        try:
            self.driver.execute_script('mobile: shell', {
                'command': 'am',
                'args': ['start', '-a', 'android.intent.action.VIEW', '-d', url]
            })
            
            time.sleep(5)
            print(f"✓ Browser opened")
            print()
            return True
        except Exception as e:
            print(f"✗ Open failed: {e}")
            print()
            return False
    
    def disable_gms(self) -> bool:
        """Disable Google Play Services"""
        print("[Action: disable_gms] Disabling Google Play Services...")
        
        gms_package = "com.google.android.gms"
        
        try:
            if not self._is_app_installed(gms_package):
                print(f"⚠ GMS not installed, no need to disable")
                print()
                return True
            
            self.driver.execute_script('mobile: shell', {
                'command': 'pm',
                'args': ['disable-user', '--user', '0', gms_package]
            })
            
            print(f"✓ GMS disabled")
            print()
            return True
        except Exception as e:
            print(f"✗ Disable failed: {e}")
            print()
            return False
    
    def enable_gms(self) -> bool:
        """Enable Google Play Services"""
        print("[Action: enable_gms] Enabling Google Play Services...")
        
        gms_package = "com.google.android.gms"
        
        try:
            self.driver.execute_script('mobile: shell', {
                'command': 'pm',
                'args': ['enable', gms_package]
            })
            
            print(f"✓ GMS enabled")
            print()
            return True
        except Exception as e:
            print(f"✗ Enable failed: {e}")
            print()
            return False
    
    def get_window_size(self) -> Dict[str, int]:
        """Get screen window size"""
        print("[Action: get_window_size] Getting screen window size...")
        
        try:
            size = self.driver.get_window_size()
            print(f"✓ Window size: {size['width']}x{size['height']}")
            print()
            return size
        except Exception as e:
            print(f"✗ Failed to get: {e}")
            print()
            return None
    
    def get_device_model(self) -> str:
        """Get device model"""
        print("[Action: get_device_model] Getting device model...")
        
        try:
            result = self.execute_shell('getprop', ['ro.product.model'])
            model = result.strip() if result else 'N/A'
            print(f"✓ Device model: {model}")
            print()
            return model
        except Exception as e:
            print(f"✗ Failed to get: {e}")
            print()
            return 'N/A'
    
    def get_app_state(self, app_name: str) -> int:
        """
        Get app state
        
        State codes:
            0 = Not installed
            1 = Not running
            2 = Running in background (suspended)
            3 = Running in background
            4 = Running in foreground
        """
        config = self._get_app_config(app_name)
        print(f"[Action: get_app_state] Getting {config['name']} app state...")
        
        try:
            state = self.driver.query_app_state(config['package'])
            state_names = {
                0: 'Not installed',
                1: 'Not running',
                2: 'Background (suspended)',
                3: 'Background (running)',
                4: 'Foreground (running)'
            }
            state_name = state_names.get(state, 'Unknown')
            print(f"✓ App state: {state} ({state_name})")
            print()
            return state
        except Exception as e:
            print(f"✗ Failed to get: {e}")
            print()
            return -1
    
    def get_current_activity(self) -> str:
        """Get current Activity"""
        print("[Action: get_current_activity] Getting current Activity...")
        
        try:
            activity = self.driver.current_activity
            print(f"✓ Current Activity: {activity}")
            print()
            return activity
        except Exception as e:
            print(f"✗ Failed to get: {e}")
            print()
            return None
    
    def get_current_package(self) -> str:
        """Get current package name"""
        print("[Action: get_current_package] Getting current package name...")
        
        try:
            package = self.driver.current_package
            print(f"✓ Current package: {package}")
            print()
            return package
        except Exception as e:
            print(f"✗ Failed to get: {e}")
            print()
            return None
    
    def get_device_logs(self, save_to_file: bool = True) -> str:
        """
        Get device logs (logcat)
        
        Args:
            save_to_file: Whether to save to file
        """
        print("[Action: get_device_logs] Getting device logs...")
        
        try:
            logs = self.execute_shell('logcat', ['-d'])
            
            if logs and save_to_file:
                OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                log_path = OUTPUT_DIR / f'device_logs_{timestamp}.txt'
                log_path.write_text(logs, encoding='utf-8')
                print(f"✓ Logs saved to: {log_path}")
                print(f"  - Log size: {len(logs) / 1024:.2f} KB")
            else:
                print(f"✓ Logs retrieved successfully ({len(logs) if logs else 0} bytes)")
            
            print()
            return logs
        except Exception as e:
            print(f"✗ Failed to get: {e}")
            print()
            return None
    
    def execute_shell(self, command: str, args: List[str] = None) -> str:
        """
        Execute ADB shell command
        
        Args:
            command: Command
            args: Argument list
            
        Returns:
            Command output string
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
        Execute ADB shell command (public interface with print output)
        
        Args:
            command: Command
            args: Argument list
        """
        print(f"[Action: shell] Executing command: {command} {' '.join(args or [])}")
        
        try:
            result = self.execute_shell(command, args)
            if result:
                # Limit output length
                display_result = result[:500] + '...' if len(result) > 500 else result
                print(f"✓ Command output:\n{display_result}")
            else:
                print(f"✓ Command executed successfully (no output)")
            print()
            return result
        except Exception as e:
            print(f"✗ Execution failed: {e}")
            print()
            return None


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="E2B Sandbox Client - Connect to an existing sandbox for mobile automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Supported actions:

  App operations (requires --app-name yyb):
    upload_app              - Upload APK to device
    install_app             - Install uploaded APK
    launch_app              - Launch app
    check_app               - Check if app is installed
    grant_app_permissions   - Grant app permissions
    close_app               - Close app
    uninstall_app           - Uninstall app

  Screen operations:
    tap_screen              - Tap screen coordinates (requires --tap-x and --tap-y)
    screenshot              - Take screenshot
    set_screen_resolution   - Set screen resolution (requires --width and --height)
    reset_screen_resolution - Reset screen resolution

  UI operations:
    dump_ui                 - Get current UI hierarchy
    click_element           - Click element (requires --element-text or --element-id)
    input_text              - Input text (requires --text)

  Location operations:
    set_location            - Set GPS location (requires --latitude and --longitude)
    get_location            - Get current GPS location

  Other operations:
    device_info             - Get device information
    get_window_size         - Get screen window size
    get_device_model        - Get device model
    get_app_state           - Get app state (requires --app-name)
    get_current_activity    - Get current Activity
    get_current_package     - Get current package name
    get_device_logs         - Get device logs
    open_browser            - Open browser (requires --url)
    disable_gms             - Disable Google Play Services
    enable_gms              - Enable Google Play Services
    shell                   - Execute ADB shell command (requires --shell-cmd)

Usage examples:
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
    
    parser.add_argument('--sandbox-id', type=str, required=True, help='Sandbox ID')
    parser.add_argument('--action', type=str, required=True, help='Action to execute, multiple actions separated by comma')
    parser.add_argument('--app-name', type=str, default=None, help='App name (yyb)')
    parser.add_argument('--apk-path', type=str, default=None, help='APK file path')
    parser.add_argument('--tap-x', type=int, default=None, help='Tap X coordinate')
    parser.add_argument('--tap-y', type=int, default=None, help='Tap Y coordinate')
    parser.add_argument('--text', type=str, default=None, help='Input text')
    parser.add_argument('--element-text', type=str, default=None, help='Element text')
    parser.add_argument('--element-id', type=str, default=None, help='Element resource-id')
    parser.add_argument('--latitude', type=float, default=None, help='GPS latitude')
    parser.add_argument('--longitude', type=float, default=None, help='GPS longitude')
    parser.add_argument('--altitude', type=float, default=0.0, help='GPS altitude')
    parser.add_argument('--width', type=int, default=None, help='Screen width')
    parser.add_argument('--height', type=int, default=None, help='Screen height')
    parser.add_argument('--dpi', type=int, default=None, help='Screen DPI')
    parser.add_argument('--url', type=str, default=None, help='Browser URL')
    parser.add_argument('--shell-cmd', type=str, default=None, help='ADB shell command')
    parser.add_argument('--list-actions', action='store_true', help='List all available actions')
    
    return parser.parse_args()


def execute_actions(client: SandboxClient, actions: List[str], args):
    """Execute actions"""
    results = {}
    
    for i, action in enumerate(actions, 1):
        print(f"[{i}/{len(actions)}] Executing action: {action}")
        print("-" * 70)
        
        try:
            # App operations
            if action == 'upload_app':
                if args.app_name is None:
                    print(f"✗ upload_app requires --app-name parameter")
                    results[action] = False
                else:
                    results[action] = client.upload_app(args.app_name, args.apk_path)
            
            elif action == 'install_app':
                if args.app_name is None:
                    print(f"✗ install_app requires --app-name parameter")
                    results[action] = False
                else:
                    results[action] = client.install_app(args.app_name)
            
            elif action == 'launch_app':
                if args.app_name is None:
                    print(f"✗ launch_app requires --app-name parameter")
                    results[action] = False
                else:
                    results[action] = client.launch_app(args.app_name)
            
            elif action == 'check_app':
                if args.app_name is None:
                    print(f"✗ check_app requires --app-name parameter")
                    results[action] = False
                else:
                    results[action] = client.check_app_installed(args.app_name)
            
            elif action == 'grant_app_permissions':
                if args.app_name is None:
                    print(f"✗ grant_app_permissions requires --app-name parameter")
                    results[action] = False
                else:
                    results[action] = client.grant_app_permissions(args.app_name)
            
            elif action == 'close_app':
                if args.app_name is None:
                    print(f"✗ close_app requires --app-name parameter")
                    results[action] = False
                else:
                    results[action] = client.close_app(args.app_name)
            
            elif action == 'uninstall_app':
                if args.app_name is None:
                    print(f"✗ uninstall_app requires --app-name parameter")
                    results[action] = False
                else:
                    results[action] = client.uninstall_app(args.app_name)
            
            # Screen operations
            elif action == 'tap_screen':
                if args.tap_x is None or args.tap_y is None:
                    print(f"✗ tap_screen requires --tap-x and --tap-y parameters")
                    results[action] = False
                else:
                    results[action] = client.tap_screen(args.tap_x, args.tap_y)
            
            elif action == 'screenshot':
                results[action] = client.take_screenshot() is not None
            
            elif action == 'set_screen_resolution':
                if args.width is None or args.height is None:
                    print(f"✗ set_screen_resolution requires --width and --height parameters")
                    results[action] = False
                else:
                    results[action] = client.set_screen_resolution(args.width, args.height, args.dpi)
            
            elif action == 'reset_screen_resolution':
                results[action] = client.reset_screen_resolution()
            
            # UI operations
            elif action == 'dump_ui':
                results[action] = client.dump_ui() is not None
            
            elif action == 'click_element':
                if args.element_text is None and args.element_id is None:
                    print(f"✗ click_element requires --element-text or --element-id parameter")
                    results[action] = False
                else:
                    results[action] = client.click_element(
                        text=args.element_text,
                        resource_id=args.element_id
                    )
            
            elif action == 'input_text':
                if args.text is None:
                    print(f"✗ input_text requires --text parameter")
                    results[action] = False
                else:
                    results[action] = client.input_text(args.text)
            
            # Location operations
            elif action == 'set_location':
                if args.latitude is None or args.longitude is None:
                    print(f"✗ set_location requires --latitude and --longitude parameters")
                    results[action] = False
                else:
                    results[action] = client.set_location(args.latitude, args.longitude, args.altitude)
            
            elif action == 'get_location':
                results[action] = client.get_location() is not None
            
            # Other operations
            elif action == 'device_info':
                results[action] = client.get_device_info() is not None
            
            elif action == 'open_browser':
                if args.url is None:
                    print(f"✗ open_browser requires --url parameter")
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
                    print(f"✗ get_app_state requires --app-name parameter")
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
                    print(f"✗ shell requires --shell-cmd parameter")
                    results[action] = False
                else:
                    # Parse command and arguments
                    parts = args.shell_cmd.split()
                    cmd = parts[0] if parts else ''
                    cmd_args = parts[1:] if len(parts) > 1 else []
                    results[action] = client.shell(cmd, cmd_args) is not None
            
            else:
                print(f"✗ Unknown action: {action}")
                results[action] = False
        
        except Exception as e:
            print(f"✗ Action execution failed: {e}")
            results[action] = False
        
        print()
    
    # Print execution summary
    print("=" * 70)
    print("Execution Summary")
    print("=" * 70)
    
    success_count = sum(1 for v in results.values() if v)
    total_count = len(results)
    
    for action, result in results.items():
        status = "✓ Success" if result else "✗ Failed"
        print(f"{action:<25} : {status}")
    
    print("-" * 70)
    print(f"Total: {success_count}/{total_count} succeeded")
    print("=" * 70)


def main():
    """Main function"""
    # Load environment variables
    _load_env_file()
    
    args = parse_arguments()
    
    # Check API Key
    if not os.getenv("E2B_API_KEY"):
        print("Error: E2B_API_KEY is not set")
        print("Please set it in .env file or export as environment variable")
        sys.exit(1)
    
    # Parse action list
    actions = [a.strip() for a in args.action.split(',')]
    
    # Create client
    client = SandboxClient(sandbox_id=args.sandbox_id)
    
    try:
        # Connect
        client.connect()
        
        # Execute actions
        execute_actions(client, actions, args)
        
    except Exception as e:
        print(f"✗ Error occurred: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    finally:
        # Disconnect
        client.disconnect()
        
        print("=" * 70)
        print("Test completed!")
        print("=" * 70)


if __name__ == '__main__':
    main()
