"""
Mobile Sandbox Quickstart Example

This module demonstrates how to use AgentSandbox for Android mobile automation.
It provides a complete example of:
- Creating and managing mobile sandboxes
- Connecting to Android devices via Appium
- Installing and launching apps (with chunked APK upload)
- Screen interactions (tap, screenshot)
- GPS location mocking

Usage:
    1. Set E2B_API_KEY environment variable or create .env file
    2. Run: python quickstart.py

Requirements:
    - e2b SDK
    - Appium-Python-Client
    - requests

For more information, see the README.md file.
"""

import os
import sys
import time
import base64
import signal
import atexit
import requests
from pathlib import Path
from types import FrameType
from typing import Optional, Dict, Any, Union

from e2b import Sandbox
from appium import webdriver
from appium.options.android import UiAutomator2Options
from appium.webdriver.appium_connection import AppiumConnection
from appium.webdriver.client_config import AppiumClientConfig
from appium.webdriver.webdriver import WebDriver

# Script directory (captured at import time for use in cleanup/signal handlers)
SCRIPT_DIR = Path(__file__).parent
OUTPUT_DIR = SCRIPT_DIR / "output" / "quickstart_output"

# Global variables for cleanup
_driver = None
_sandbox = None
_cleaned_up = False


def _load_env_file() -> None:
    """
    Load environment variables from .env file.

    Prefers python-dotenv if available, otherwise parses manually.
    """
    # Try to load .env file if python-dotenv is available
    try:
        from dotenv import load_dotenv
        # Load .env from the same directory as this script
        script_dir = Path(__file__).parent.absolute()
        load_dotenv(script_dir / ".env")
    except ImportError:
        # Fallback: manually parse .env file if python-dotenv is not available
        try:
            script_dir = Path(__file__).parent.absolute()
            env_file = script_dir / ".env"
            if env_file.exists():
                with open(env_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, value = line.split('=', 1)
                            os.environ[key.strip()] = value.strip()
        except Exception:
            # Silently ignore errors in fallback
            pass


def _load_config() -> Dict[str, Any]:
    """
    Load configuration.

    Priority: environment variables > .env file > default values

    Returns:
        dict: Dictionary containing all configuration items
    """
    # Load .env file first
    _load_env_file()
    
    config = {
        'E2B_DOMAIN': os.getenv("E2B_DOMAIN", "ap-guangzhou.tencentags.com"),
        'E2B_API_KEY': os.getenv("E2B_API_KEY", ""),
        'SANDBOX_TEMPLATE': os.getenv("SANDBOX_TEMPLATE", "mobile-v1"),
        'SANDBOX_TIMEOUT': int(os.getenv("SANDBOX_TIMEOUT", "3600")),  # 1 hour default
    }
    
    return config


def cleanup() -> None:
    """Cleanup resources: close driver and sandbox"""
    global _driver, _sandbox, _cleaned_up
    
    if _cleaned_up:
        return
    _cleaned_up = True
    
    print("\nCleaning up resources...")
    
    # Take screenshot before exit
    try:
        if _driver is not None:
            print("  - Taking screenshot before exit...")
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            screenshot_path = OUTPUT_DIR / f"screenshot_before_exit_{timestamp}.png"
            _driver.save_screenshot(str(screenshot_path))
            print(f"  - Screenshot saved: {screenshot_path}")
    except Exception as e:
        print(f"  - Failed to take screenshot: {e}")
    
    try:
        if _driver is not None:
            print("  - Closing Appium driver...")
            _driver.quit()
            print("  - Appium driver closed")
    except Exception as e:
        print(f"  - Error closing driver: {e}")
    
    try:
        if _sandbox is not None:
            print("  - Terminating sandbox...")
            _sandbox.kill()
            print("  - Sandbox terminated")
    except Exception as e:
        print(f"  - Error terminating sandbox: {e}")
    
    print("Test completed, sandbox cleaned up")


def signal_handler(signum: int, frame: Optional[FrameType]) -> None:
    """Handle SIGINT (Ctrl+C) and SIGTERM signals"""
    sig_name = signal.Signals(signum).name
    print(f"\nReceived {sig_name} signal, exiting...")
    cleanup()
    exit(0)


# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Register atexit handler (called on normal exit)
atexit.register(cleanup)

# Chunked upload configuration
CHUNK_SIZE = 20 * 1024 * 1024  # 20MB per chunk

# APK download base URL
APK_DOWNLOAD_BASE_URL = "https://agentsandbox-1251707795.cos.ap-guangzhou.myqcloud.com/repo/apk"

# App configuration dictionary
APP_CONFIGS = {
    'wechat': {
        'name': 'WeChat',
        'package': 'com.tencent.mm',
        'activity': '.ui.LauncherUI',
        'apk_name': 'weixin8067android3000_0x28004333_arm64.apk',
        'remote_path': '/data/local/tmp/wechat.apk',
        'permissions': [
            'android.permission.ACCESS_FINE_LOCATION',
            'android.permission.ACCESS_COARSE_LOCATION',
            'android.permission.READ_EXTERNAL_STORAGE',
            'android.permission.CAMERA',
            'android.permission.RECORD_AUDIO',
            'android.permission.READ_CONTACTS',
        ]
    },
    'yyb': {
        'name': 'App Store',
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


def download_apk(apk_name: str, save_path: Path) -> bool:
    """
    Download APK file from remote server.
    
    Note: Since Tencent Cloud COS blocks .apk downloads via default domain,
    remote files use .ap suffix, saved as .apk after download.
    
    Args:
        apk_name: APK filename (e.g., "yingyongbao.apk")
        save_path: Path to save the file
        
    Returns:
        Whether download succeeded
    """
    from urllib.parse import quote
    
    # Change .apk suffix to .ap (actual filename on COS)
    remote_name = apk_name.replace('.apk', '.ap')
    
    # URL encode filename (handle Chinese and special characters)
    encoded_name = quote(remote_name)
    download_url = f"{APK_DOWNLOAD_BASE_URL}/{encoded_name}"
    
    print(f"  - APK file not found, starting download...")
    print(f"  - Download URL: {download_url}")
    
    try:
        # Ensure directory exists
        save_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Download file
        response = requests.get(download_url, stream=True, timeout=300)
        response.raise_for_status()
        
        # Get file size
        total_size = int(response.headers.get('content-length', 0))
        if total_size > 0:
            print(f"  - File size: {total_size / 1024 / 1024:.2f} MB")
        
        # Write file
        downloaded = 0
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        progress = downloaded / total_size * 100
                        print(f"\r  - Download progress: {progress:.1f}%", end='', flush=True)
        
        print()  # New line
        print(f"  - Download completed: {save_path}")
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"\n  - Download failed: {e}")
        # Clean up incomplete file
        if save_path.exists():
            save_path.unlink()
        return False


def is_app_installed(driver: WebDriver, package_name: str) -> bool:
    """Check if app is installed"""
    try:
        state = driver.query_app_state(package_name)
        return state != 0
    except Exception:
        result = driver.execute_script('mobile: shell', {
            'command': 'pm',
            'args': ['list', 'packages', package_name]
        })
        return package_name in str(result)


def upload_app(driver: WebDriver, app_name: str, apk_path: Optional[str] = None) -> bool:
    """Upload APK to device (using chunked upload)"""
    config = APP_CONFIGS.get(app_name.lower())
    if not config:
        print(f"Unsupported app: {app_name}")
        return False
    
    print(f"[Action: upload_app] Uploading {config['name']} APK to device...")
    
    if apk_path is None:
        # Default APK path: apk/ subdirectory under script directory
        apk_dir = SCRIPT_DIR / "apk"
        apk_path = apk_dir / config['apk_name']
    else:
        apk_path = Path(apk_path)
    
    # If APK doesn't exist, try to download
    if not apk_path.exists():
        if not download_apk(config['apk_name'], apk_path):
            print(f"[x] APK file not found and download failed: {apk_path}")
            return False
    
    file_size = apk_path.stat().st_size
    total_chunks = (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE
    
    print(f"  - Local APK path: {apk_path}")
    print(f"  - File size: {file_size / 1024 / 1024:.2f} MB")
    print(f"  - Chunk size: {CHUNK_SIZE / 1024 / 1024:.0f} MB")
    print(f"  - Total chunks: {total_chunks}")
    
    temp_dir = '/data/local/tmp/chunks'
    remote_path = config['remote_path']
    
    try:
        # Clean and create temp directory
        driver.execute_script('mobile: shell', {
            'command': 'rm',
            'args': ['-rf', temp_dir]
        })
        driver.execute_script('mobile: shell', {
            'command': 'mkdir',
            'args': ['-p', temp_dir]
        })
        
        # Clear target file
        driver.execute_script('mobile: shell', {
            'command': 'rm',
            'args': ['-f', remote_path]
        })
        
        start_time = time.time()
        
        # Phase 1: Upload all chunks
        print(f"  [Phase 1] Uploading chunks...")
        with open(apk_path, 'rb') as f:
            for i in range(total_chunks):
                chunk_data = f.read(CHUNK_SIZE)
                chunk_b64 = base64.b64encode(chunk_data).decode('utf-8')
                chunk_path = f"{temp_dir}/chunk_{i:04d}"
                
                print(f"    - Chunk {i + 1}/{total_chunks} ({len(chunk_data) / 1024 / 1024:.2f}MB)...", end=' ', flush=True)
                chunk_start = time.time()
                
                driver.push_file(chunk_path, chunk_b64)
                
                elapsed = time.time() - chunk_start
                print(f"done ({elapsed:.1f}s)")
        
        upload_time = time.time() - start_time
        print(f"  - Upload completed, time: {upload_time:.1f}s")
        
        # Phase 2: Merge chunks one by one
        print(f"  [Phase 2] Merging chunks...")
        merge_start = time.time()
        
        for i in range(total_chunks):
            chunk_path = f"{temp_dir}/chunk_{i:04d}"
            print(f"    - Merging chunk {i + 1}/{total_chunks}...", end=' ', flush=True)
            
            chunk_merge_start = time.time()
            
            if i == 0:
                # First chunk: copy directly
                driver.execute_script('mobile: shell', {
                    'command': 'cp',
                    'args': [chunk_path, remote_path]
                })
            else:
                # Subsequent chunks: append with cat
                driver.execute_script('mobile: shell', {
                    'command': 'cat',
                    'args': [chunk_path, '>>', remote_path]
                })
            
            # Delete merged chunk
            driver.execute_script('mobile: shell', {
                'command': 'rm',
                'args': ['-f', chunk_path]
            })
            
            chunk_merge_time = time.time() - chunk_merge_start
            print(f"done ({chunk_merge_time:.1f}s)")
        
        merge_time = time.time() - merge_start
        print(f"  - Merge completed, time: {merge_time:.1f}s")
        
        # Clean temp directory
        driver.execute_script('mobile: shell', {
            'command': 'rm',
            'args': ['-rf', temp_dir]
        })
        
        # Verify file
        result = driver.execute_script('mobile: shell', {
            'command': 'ls',
            'args': ['-la', remote_path]
        })
        
        total_time = time.time() - start_time
        print(f"  - Total time: {total_time:.1f}s")
        
        if result and 'No such file' not in str(result):
            print(f"  - Remote file: {result.strip()}")
            print(f"[ok] APK upload completed")
            print()
            return True
        else:
            print(f"[x] File not found")
            print()
            return False
            
    except Exception as e:
        print(f"[x] APK upload failed: {e}")
        # Clean temp files
        try:
            driver.execute_script('mobile: shell', {
                'command': 'rm',
                'args': ['-rf', temp_dir]
            })
            driver.execute_script('mobile: shell', {
                'command': 'rm',
                'args': ['-f', remote_path]
            })
        except Exception:
            pass
        print()
        return False


def install_app(driver: WebDriver, app_name: str) -> bool:
    """Install uploaded APK"""
    config = APP_CONFIGS.get(app_name.lower())
    if not config:
        print(f"Unsupported app: {app_name}")
        return False
    
    print(f"[Action: install_app] Installing {config['name']}...")
    
    try:
        # Check if already installed
        print(f"  - Checking if {config['name']} is installed...")
        if is_app_installed(driver, config['package']):
            print(f"  [!] {config['name']} already installed, skipping installation")
            print(f"[ok] {config['name']} available (already exists)")
            print()
            return True
        
        # Install using pm install
        print(f"  - Installing APK...")
        print(f"  - Estimated time: 60-120 seconds, please wait...")
        
        result = driver.execute_script('mobile: shell', {
            'command': 'pm',
            'args': ['install', '-r', '-g', config['remote_path']]
        })
        
        if result and ('Success' in str(result) or 'success' in str(result).lower()):
            print(f"[ok] {config['name']} installed successfully")
            print()
            return True
        else:
            print(f"  [!] pm install returned: {str(result)[:200]}")
            # Check if actually installed
            time.sleep(2)
            if is_app_installed(driver, config['package']):
                print(f"[ok] {config['name']} installed successfully (verified)")
                print()
                return True
            else:
                print(f"[x] {config['name']} installation failed")
                print()
                return False
        
    except Exception as e:
        # Check if actually installed
        try:
            time.sleep(2)
            if is_app_installed(driver, config['package']):
                print(f"  [!] Error occurred, but {config['name']} was installed successfully")
                print(f"[ok] {config['name']} available")
                print()
                return True
        except Exception:
            pass

        print(f"[x] {config['name']} installation failed: {str(e)[:200]}")
        print()
        return False


def grant_app_permissions(driver: WebDriver, app_name: str) -> bool:
    """Grant all necessary permissions to app"""
    config = APP_CONFIGS.get(app_name.lower())
    if not config:
        print(f"Unsupported app: {app_name}")
        return False
    
    print(f"[Action: grant_permissions] Granting permissions to {config['name']}...")
    
    success_count = 0
    for permission in config['permissions']:
        try:
            perm_name = permission.split('.')[-1]
            driver.execute_script('mobile: shell', {
                'command': 'pm',
                'args': ['grant', config['package'], permission]
            })
            print(f"  - Granted: {perm_name}")
            success_count += 1
        except Exception as e:
            print(f"  - Failed to grant: {perm_name} ({e})")
    
    print(f"  Permissions granted: {success_count}/{len(config['permissions'])}")
    return success_count > 0


def launch_app(driver: WebDriver, app_name: str) -> bool:
    """Launch app"""
    config = APP_CONFIGS.get(app_name.lower())
    if not config:
        print(f"Unsupported app: {app_name}")
        return False
    
    print(f"[Action: launch_app] Launching {config['name']}...")
    
    try:
        driver.activate_app(config['package'])
        print(f"  - Launch command sent, waiting for app to start...")
        time.sleep(5)
        
        # Verify app state
        app_state = driver.query_app_state(config['package'])
        if app_state == 4:
            print(f"  {config['name']} running in foreground")
            print(f"[ok] {config['name']} launched successfully")
            return True
        elif app_state == 3:
            print(f"  [!] {config['name']} running in background, trying to reactivate...")
            driver.activate_app(config['package'])
            time.sleep(3)
            app_state = driver.query_app_state(config['package'])
            if app_state == 4:
                print(f"[ok] {config['name']} launched successfully")
                return True
            else:
                print(f"[x] {config['name']} failed to switch to foreground, state: {app_state}")
                return False
        else:
            print(f"[x] {config['name']} launch failed, state: {app_state}")
            print(f"  State codes: 0=not installed, 1=not running, 2=background suspended, 3=background running, 4=foreground running")
            return False
        
    except Exception as e:
        print(f"  Launch failed: {e}")
        return False


def open_browser(driver: WebDriver, url: str) -> bool:
    """
    Open URL in browser.

    Args:
        driver: Appium driver
        url: URL to open
        
    Returns:
        Whether open succeeded
    """
    print(f"[Action: open_browser] Opening URL in browser...")
    print(f"  - Target URL: {url}")
    
    try:
        # Use Android Intent to launch browser
        driver.execute_script('mobile: shell', {
            'command': 'am',
            'args': ['start', '-a', 'android.intent.action.VIEW', '-d', url]
        })
        
        print(f"  Browser launched")
        
        # Wait for page load
        print(f"  - Waiting for page to load...")
        time.sleep(5)
        print(f"  Page loaded")
        print()
        return True
        
    except Exception as e:
        print(f"  Open failed: {e}")
        print()
        return False


def tap_screen(driver: WebDriver, x: int, y: int) -> bool:
    """
    Tap screen at specified coordinates.

    Args:
        driver: Appium driver
        x: X coordinate
        y: Y coordinate
        
    Returns:
        Whether tap succeeded
    """
    print(f"[Action: tap_screen] Tapping screen at ({x}, {y})...")
    
    try:
        # Use adb input tap
        driver.execute_script('mobile: shell', {
            'command': 'input',
            'args': ['tap', str(x), str(y)]
        })
        
        print(f"  Tapped at: ({x}, {y})")
        time.sleep(0.5)
        print()
        return True
        
    except Exception as e:
        print(f"  Tap failed: {e}")
        print()
        return False


def take_screenshot(driver: WebDriver, filename: Optional[str] = None) -> Optional[str]:
    """
    Take screenshot.

    Screenshots are saved to output/quickstart_output/ under the script directory.
    Directory is created automatically if it doesn't exist.
    
    Args:
        driver: Appium driver
        filename: Screenshot filename, auto-generated if not provided
        
    Returns:
        Screenshot file path, None if failed
    """
    print("[Action: screenshot] Taking screenshot...")
    
    # Save to output/quickstart_output/ under the script directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Generate filename
    if filename is None:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"mobile_screenshot_{timestamp}.png"
    
    screenshot_path = OUTPUT_DIR / filename
    
    try:
        driver.save_screenshot(str(screenshot_path))
        print(f"  Screenshot saved")
        print(f"  - Filename: {filename}")
        print(f"  - Full path: {screenshot_path}")
        print(f"  - File size: {screenshot_path.stat().st_size / 1024:.2f} KB")
        print()
        return str(screenshot_path)
        
    except Exception as e:
        print(f"  Screenshot failed: {e}")
        print()
        return None


def get_location(driver: WebDriver, debug: bool = False) -> Optional[Dict[str, Any]]:
    """
    Get current GPS location.

    Note: 'last location=null' in dumpsys location is normal when no app
    is requesting location. Mock location will be returned when apps request it.
    
    Args:
        driver: Appium driver
        debug: Whether to output debug info
        
    Returns:
        Dictionary containing location info, None if failed
    """
    import re
    
    print("[Action: get_location] Getting current GPS location...")
    
    try:
        result = driver.execute_script('mobile: shell', {
            'command': 'dumpsys',
            'args': ['location']
        })
        
        # Check if mock provider is registered
        has_mock = '[mock]' in result
        
        # Check if LocationService is running
        services = driver.execute_script('mobile: shell', {
            'command': 'dumpsys',
            'args': ['activity', 'services', 'io.appium.settings']
        })
        location_service_running = 'LocationService' in services
        
        print(f"  - Mock Provider status: {'registered' if has_mock else 'not registered'}")
        print(f"  - LocationService status: {'running' if location_service_running else 'not running'}")
        
        # Try to get location from dumpsys
        patterns = [
            (r'last location=Location\[(\w+)\s+([\d.-]+),([\d.-]+)', 3),
            (r'Location\[(\w+)\s+([\d.-]+),([\d.-]+)', 3),
        ]
        
        for pattern, group_count in patterns:
            match = re.search(pattern, result)
            if match:
                groups = match.groups()
                provider = groups[0]
                latitude = float(groups[1])
                longitude = float(groups[2])
                
                location = {
                    'latitude': latitude,
                    'longitude': longitude,
                    'altitude': 0,
                    'provider': provider
                }
                print(f"[ok] GPS location: ({latitude}, {longitude})")
                print()
                return location
        
        # Even without last location, mock may still work
        if location_service_running:
            print(f"  [!] dumpsys shows no location data (this is normal)")
            print(f"  - Mock location will be returned when apps request it")
            print()
            return {'status': 'mock_ready', 'note': 'LocationService running, location available on request'}
        
        print(f"  GPS location: not set")
        print()
        return None
            
    except Exception as e:
        print(f"[x] Failed to get GPS location: {e}")
        print()
        return None


def set_location(driver: WebDriver, latitude: float, longitude: float, altitude: float = 0.0) -> bool:
    """
    Set GPS location.

    Uses Appium Settings LocationService to set mock location.
    
    Args:
        driver: Appium driver
        latitude: Latitude (-90 to 90)
        longitude: Longitude (-180 to 180)
        altitude: Altitude in meters (default 0)
        
    Returns:
        Whether setting succeeded
    """
    print(f"[Action: set_location] Setting GPS location...")
    print(f"  - Target location: ({latitude}, {longitude})")
    
    # Validate coordinate range
    if not (-90 <= latitude <= 90):
        print(f"[x] Latitude out of range: {latitude} (valid range: -90 to 90)")
        print()
        return False
    
    if not (-180 <= longitude <= 180):
        print(f"[x] Longitude out of range: {longitude} (valid range: -180 to 180)")
        print()
        return False
    
    try:
        appium_settings_pkg = "io.appium.settings"
        
        # Grant location permissions
        print(f"  - Granting location permissions to io.appium.settings...")
        for perm in ['ACCESS_FINE_LOCATION', 'ACCESS_COARSE_LOCATION']:
            try:
                driver.execute_script('mobile: shell', {
                    'command': 'pm',
                    'args': ['grant', appium_settings_pkg, f'android.permission.{perm}']
                })
            except Exception:
                pass

        # Grant mock location permission
        driver.execute_script('mobile: shell', {
            'command': 'appops',
            'args': ['set', appium_settings_pkg, 'android:mock_location', 'allow']
        })
        print(f"  - mock_location permission set")
        
        # Start LocationService
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
        print(f"  - LocationService started")
        
        time.sleep(3)
        
        # Verify service is running
        services = driver.execute_script('mobile: shell', {
            'command': 'dumpsys',
            'args': ['activity', 'services', 'io.appium.settings']
        })
        
        if 'LocationService' in services:
            print(f"[ok] GPS location set: ({latitude}, {longitude})")
            print(f"  - This mock location will be returned when apps request location")
            print()
            return True
        else:
            print(f"[!] LocationService may not have started properly")
            print()
            return False
        
    except Exception as e:
        print(f"[x] Failed to set GPS location: {e}")
        print()
        return False


def install_and_launch_app(driver: WebDriver, app_name: str, max_retries: int = 1) -> bool:
    """
    Complete app installation and launch flow:
    upload_app -> install_app -> grant_app_permissions -> launch_app
    
    Args:
        driver: Appium driver
        app_name: App name
        max_retries: Max retry count for install/launch failures, default 1
    """
    print(f"\n===== Installing and launching {app_name} =====")
    
    # 1. Upload APK
    if not upload_app(driver, app_name):
        print(f"Failed to upload {app_name}")
        return False
    
    # 2. Install APK (with retry)
    install_success = False
    for attempt in range(max_retries + 1):
        if attempt > 0:
            print(f"  [!] Install retry {attempt}/{max_retries}...")
            time.sleep(5)  # Wait 5 seconds before retry
        if install_app(driver, app_name):
            install_success = True
            break
    
    if not install_success:
        print(f"Failed to install {app_name} (retried {max_retries} times)")
        return False
    
    # 3. Grant permissions
    if not grant_app_permissions(driver, app_name):
        print(f"Failed to grant permissions to {app_name} (non-fatal error)")
    
    # 4. Launch app (with retry)
    launch_success = False
    for attempt in range(max_retries + 1):
        if attempt > 0:
            print(f"  [!] Launch retry {attempt}/{max_retries}...")
            time.sleep(3)  # Wait 3 seconds before retry
        if launch_app(driver, app_name):
            launch_success = True
            break
    
    if not launch_success:
        print(f"Failed to launch {app_name} (retried {max_retries} times)")
        return False
    
    print(f"===== {app_name} installation and launch completed =====\n")
    return True


def AppiumDriver(sandbox: Sandbox, port: int = 4723, http_timeout: int = 300, **options_kwargs: Any) -> WebDriver:
    """
    Create Appium Driver connected to E2B sandbox.

    Args:
        sandbox: E2B Sandbox instance
        port: Appium service port
        http_timeout: HTTP request timeout in seconds, default 300s (5 minutes)
    """
    # Configure Appium options
    options = UiAutomator2Options()
    options.platform_name = options_kwargs.pop('platform_name', 'Android')
    options.automation_name = options_kwargs.pop('automation_name', 'UiAutomator2')
    # Set to 0 to disable timeout, prevents session termination during long sleep
    options.new_command_timeout = 0

    # Apply additional options
    for key, value in options_kwargs.items():
        setattr(options, key, value)

    # Set authentication header (AppiumConnection uses class variable)
    AppiumConnection.extra_headers['X-Access-Token'] = sandbox._envd_access_token

    # Use AppiumClientConfig to set HTTP timeout
    appium_url = f"https://{sandbox.get_host(port)}"
    client_config = AppiumClientConfig(
        remote_server_addr=appium_url,
        timeout=http_timeout
    )

    return webdriver.Remote(options=options, client_config=client_config)


def create_driver(sandbox: Sandbox, max_retries: int = 3, retry_interval: int = 5) -> WebDriver:
    """
    Create Appium Driver, connect to Android device in sandbox.

    First tries direct connection (usually works after sandbox starts),
    retries with health check if failed.
    
    Args:
        sandbox: E2B Sandbox instance
        max_retries: Max retry count, default 3
        retry_interval: Retry interval in seconds, default 5
        
    Returns:
        Appium driver instance
    """
    health_url = f"https://{sandbox.get_host(8080)}/healthz"
    headers = {'X-Access-Token': sandbox._envd_access_token}
    
    # First try direct connection without health check
    print(f"\nConnecting to Appium service...")
    try:
        print(f"  - Attempting connection...", end=' ', flush=True)
        driver = AppiumDriver(sandbox)
        print(f"connected!")
        return driver
    except Exception as e:
        error_msg = str(e)
        if 'Bad Gateway' in error_msg:
            print(f"service not ready (Bad Gateway)")
        elif 'Connection refused' in error_msg:
            print(f"service not ready (Connection refused)")
        else:
            print(f"connection failed: {error_msg[:50]}")
    
    # First connection failed, enter retry logic (with health check)
    print(f"  - Waiting for service to be ready, max wait {max_retries * retry_interval}s...")
    
    for attempt in range(1, max_retries + 1):
        print(f"  - Waiting {retry_interval}s...")
        time.sleep(retry_interval)
        
        try:
            # Check health endpoint
            print(f"  - Retry {attempt}/{max_retries}: checking service status...", end=' ', flush=True)
            resp = requests.get(health_url, headers=headers, timeout=10)
            
            if resp.status_code == 200:
                print(f"health check passed")
                print(f"  - Attempting connection...", end=' ', flush=True)
                driver = AppiumDriver(sandbox)
                print(f"connected!")
                return driver
            else:
                print(f"health check returned {resp.status_code}")
                
        except requests.exceptions.RequestException as e:
            print(f"health check failed: {type(e).__name__}")
        except Exception as e:
            error_msg = str(e)
            if 'Bad Gateway' in error_msg:
                print(f"service not ready (Bad Gateway)")
            elif 'Connection refused' in error_msg:
                print(f"service not ready (Connection refused)")
            else:
                print(f"connection failed: {error_msg[:50]}")
    
    raise Exception(f"Appium service not ready within {max_retries * retry_interval}s")


def get_device_info(driver: WebDriver) -> Dict[str, Any]:
    """Get device details"""
    capabilities = driver.capabilities
    window_size = driver.get_window_size()
    
    # Get screen resolution and DPI
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


def main(
    e2b_domain: str,
    e2b_api_key: str,
    sandbox_template: str,
    sandbox_timeout: int,
) -> None:
    """
    Main function - Execute mobile automation test.

    Args:
        e2b_domain: E2B service domain
        e2b_api_key: E2B API Key
        sandbox_template: Sandbox template name
        sandbox_timeout: Sandbox timeout in seconds
    """
    global _driver, _sandbox
    
    # Validate API Key
    if not e2b_api_key:
        print("=" * 70)
        print("Error: E2B_API_KEY not set!")
        print("=" * 70)
        print("\nPlease set API Key using one of the following methods:")
        print("\n   Method 1: Environment variable (recommended for CI/CD):")
        print("      export E2B_API_KEY='your_api_key'")
        print("\n   Method 2: Create .env file (recommended for local development):")
        print("      Create .env file in examples/mobile-use/ directory with content:")
        print("      E2B_API_KEY=your_api_key")
        print("\n   Method 3: Modify config in if __name__ == '__main__' directly")
        print("=" * 70)
        sys.exit(1)
    
    # Set environment variables for SDK
    os.environ["E2B_DOMAIN"] = e2b_domain
    os.environ["E2B_API_KEY"] = e2b_api_key
    
    # Print current config
    print("=" * 70)
    print("Current Configuration:")
    print(f"  E2B_DOMAIN:       {e2b_domain}")
    print(f"  SANDBOX_TEMPLATE: {sandbox_template}")
    print(f"  SANDBOX_TIMEOUT:  {sandbox_timeout}s ({sandbox_timeout / 3600:.1f} hours)")
    print("=" * 70)
    
    # Create sandbox
    print(f"\nCreating sandbox (template={sandbox_template}, timeout={sandbox_timeout})...")
    sandbox_start_time = time.perf_counter()
    sandbox = Sandbox.create(template=sandbox_template, timeout=sandbox_timeout)
    sandbox_end_time = time.perf_counter()
    sandbox_elapsed_ms = (sandbox_end_time - sandbox_start_time) * 1000
    print(f"Sandbox created, time: {sandbox_elapsed_ms:.2f}ms ({sandbox_elapsed_ms / 1000:.3f}s)")
    _sandbox = sandbox
    
    # Get ws-scrcpy screen stream URL (WebCodecs player direct connection)
    from urllib.parse import quote
    scrcpy_host = sandbox.get_host(8000)
    scrcpy_token = sandbox._envd_access_token
    scrcpy_udid = "emulator-5554"
    scrcpy_ws = f"wss://{scrcpy_host}/?action=proxy-adb&remote=tcp%3A8886&udid={scrcpy_udid}&access_token={scrcpy_token}"
    scrcpy_url = f"https://{scrcpy_host}/?access_token={scrcpy_token}#!action=stream&udid={scrcpy_udid}&player=webcodecs&ws={quote(scrcpy_ws, safe='')}"
    
    print(f"VNC URL: {scrcpy_url}")

    # Create Appium driver (with wait and retry)
    driver = create_driver(sandbox)
    _driver = driver
    
    # Get device info
    device_info = get_device_info(driver)
    print(f"\n===== Device Info =====")
    print(f"Device Name: {device_info['deviceName']}")
    print(f"Platform Version: Android {device_info['platformVersion']}")
    print(f"Window Size: {device_info['windowSize']}")
    print(f"Screen Resolution: {device_info['wmSize']}")
    print(f"Screen DPI: {device_info['wmDensity']}")
    print(f"=======================\n")

    # Install and launch App Store
    install_and_launch_app(driver, 'yyb')

    # Install and launch WeChat
    install_and_launch_app(driver, 'wechat')
    
    # Get GPS location before setting
    print("===== GPS Location Before Setting =====")
    get_location(driver)
    
    # Set GPS location (Shenzhen)
    set_location(driver, latitude=22.54347, longitude=113.92972)
    
    # Get GPS location after setting
    print("===== GPS Location After Setting =====")
    get_location(driver)
    
    # Long-running test: run for sandbox timeout minus 10 minutes (reserve time for cleanup)
    total_sleep = sandbox_timeout - 600  # Sandbox timeout - 10 minutes
    interval = 600  # Take screenshot every 600 seconds (10 minutes)
    heartbeat_interval = 300  # Send heartbeat every 300 seconds (5 minutes) to keep session active
    elapsed = 0
    
    print(f"Starting long-running test...")
    print(f"  - Total duration: {total_sleep}s ({total_sleep / 3600:.1f} hours)")
    print(f"  - Screenshot interval: {interval}s ({interval / 3600:.1f} hours)")
    print(f"  - Heartbeat interval: {heartbeat_interval}s ({heartbeat_interval / 60:.0f} minutes)")
    print(f"  - Expected screenshot count: {total_sleep // interval + 1}")
    
    # Take initial screenshot
    take_screenshot(driver, f"screenshot_elapsed_0s.png")
    
    while elapsed < total_sleep:
        # Use heartbeat to keep session active instead of sleeping entire interval
        time_until_next_screenshot = interval
        while time_until_next_screenshot > 0:
            sleep_time = min(heartbeat_interval, time_until_next_screenshot)
            time.sleep(sleep_time)
            time_until_next_screenshot -= sleep_time
            elapsed += sleep_time
            
            # Send heartbeat command to keep session active
            try:
                # Use lightweight command as heartbeat
                driver.current_activity
            except Exception as e:
                print(f"  [!] Heartbeat failed (elapsed={elapsed}s): {e}")
        
        hours = elapsed / 3600
        print(f"Running for {elapsed}s ({hours:.1f} hours)...")
        take_screenshot(driver, f"screenshot_elapsed_{elapsed}s.png")

if __name__ == "__main__":
    # ==========================================================================
    # Configuration Section - Modify configuration here
    # ==========================================================================
    # 
    # Configuration priority (high to low):
    #   1. Direct assignment below (uncomment and modify)
    #   2. Configuration in .env file
    #   3. Environment variables
    #   4. Default values
    #
    # ==========================================================================
    
    # Load configuration from .env file and environment variables
    config = _load_config()
    
    # --------------------------------------------------------------------------
    # To override configuration manually, uncomment and modify the following:
    # --------------------------------------------------------------------------
    # config['E2B_API_KEY'] = "your_api_key_here"
    # config['E2B_DOMAIN'] = "ap-guangzhou.tencentags.com"
    # config['SANDBOX_TEMPLATE'] = "mobile-v1"
    # config['SANDBOX_TIMEOUT'] = 3600  # 1 hour
    # --------------------------------------------------------------------------
    
    # Execute main program
    main(
        e2b_domain=config['E2B_DOMAIN'],
        e2b_api_key=config['E2B_API_KEY'],
        sandbox_template=config['SANDBOX_TEMPLATE'],
        sandbox_timeout=config['SANDBOX_TIMEOUT'],
    )
    
    # Cleanup is executed automatically via atexit
    # cleanup() is called on normal exit or when receiving SIGINT/SIGTERM signal
