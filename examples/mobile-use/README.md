# Mobile Automation: Cloud Sandbox-Based Mobile App Testing

This example demonstrates how to use AgentSandbox cloud sandbox to run Android devices, combined with Appium for mobile app automation tasks.

## Architecture

```
┌─────────────┐     Appium      ┌─────────────┐      ADB       ┌───────────────┐
│   Python    │ ───────────────▶│   Appium    │ ─────────────▶│  AgentSandbox │
│   Script    │                 │   Driver    │               │   (Android)   │
└─────────────┘                 └─────────────┘               └───────────────┘
      ▲                                │                              │
      │                                │◀─────────────────────────────┘
      │                                │      Device State / Result
      └────────────────────────────────┘
              Response
```

**Core Features**:
- Android device runs in cloud sandbox, locally controlled via Appium
- Supports ws-scrcpy for real-time screen streaming
- Complete mobile automation capabilities: app installation, GPS mocking, browser control, screen capture, etc.

## Project Structure

```
mobile-use/
├── README.md                  # English documentation
├── README_zh.md               # Chinese documentation
├── .env.example               # Environment configuration example
├── requirements.txt           # Python dependencies
├── quickstart.py              # Quick start example
├── batch.py                   # Batch operations script (multi-process + async)
├── mobile_actions.py          # Reusable mobile action library
├── test_mobile_actions.py     # Unit tests for mobile_actions
├── apk/                       # APK files directory
└── output/                    # Screenshots and logs output
```

## Scripts

| Script | Description |
|--------|-------------|
| `quickstart.py` | Quick start example demonstrating basic mobile automation features |
| `batch.py` | Batch operations script for high-concurrency sandbox testing (multi-process + async) |
| `mobile_actions.py` | Reusable mobile action library with verified operations |
| `test_mobile_actions.py` | Unit tests for mobile_actions module |

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure API Keys

**Option 1: .env file (recommended for local development)**
```bash
# Copy the example file
cp .env.example .env

# Edit .env and fill in your configuration
```

**Option 2: Environment variables (recommended for CI/CD)**
```bash
export E2B_API_KEY="your_api_key"
export E2B_DOMAIN="ap-guangzhou.tencentags.com"
export SANDBOX_TEMPLATE="mobile-v1"
```

### 3. Run Examples

**Quick Start Example:**
```bash
python quickstart.py
```

**Batch Operations:**
```bash
python batch.py
```

**Run Unit Tests:**
```bash
python -m pytest test_mobile_actions.py -v
```

## Configuration

### Required Configuration

| Variable | Description |
|----------|-------------|
| `E2B_API_KEY` | Your AgentSandbox API Key |
| `E2B_DOMAIN` | Service domain (e.g., `ap-guangzhou.tencentags.com`) |
| `SANDBOX_TEMPLATE` | Sandbox template name (e.g., `mobile-v1`) |

### Optional Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `SANDBOX_TIMEOUT` | 3600 (quickstart) / 300 (batch) | Sandbox timeout in seconds |
| `LOG_LEVEL` | INFO | Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL |

### Batch Operations Configuration (batch.py only)

| Variable | Default | Description |
|----------|---------|-------------|
| `SANDBOX_COUNT` | 2 | Total number of sandboxes to create |
| `PROCESS_COUNT` | 2 | Number of processes for parallel execution |
| `THREAD_POOL_SIZE` | 5 | Thread pool size per process |
| `USE_MOUNTED_APK` | false | Use mounted APK instead of uploading from local |

## Mobile Actions Library

The `mobile_actions.py` module provides a collection of verified, reusable mobile operations extracted from `quickstart.py`, `batch.py`, and tested scripts.

### Available Functions

| Category | Function | Description |
|----------|----------|-------------|
| **Screen Operations** | `tap_screen(driver, x, y)` | Tap screen at specified coordinates |
| | `take_screenshot(driver, save_path)` | Take and save screenshot |
| | `set_screen_resolution(driver, width, height, dpi)` | Set screen resolution |
| | `reset_screen_resolution(driver)` | Reset screen resolution to default |
| **Text Input** | `input_text(driver, text)` | Input text to focused element (supports Chinese) |
| **Element Operations** | `find_element_by_text(driver, text, partial)` | Find element by text |
| | `find_element_by_id(driver, resource_id)` | Find element by resource-id |
| | `click_element(driver, text, resource_id, partial)` | Click element by text or resource-id |
| **Page Analysis** | `get_page_source(driver)` | Get current page XML |
| | `get_page_source_to_file(driver, save_path)` | Get page XML and save to file |
| | `get_window_size(driver)` | Get screen dimensions |
| | `get_device_info(driver)` | Get device detailed info |
| | `get_device_model(driver)` | Get device model |
| **App Management** | `is_app_installed(driver, package)` | Check if app is installed |
| | `get_app_state(driver, package)` | Get app state |
| | `launch_app(driver, package, wait_seconds)` | Launch app |
| | `get_current_activity(driver)` | Get current activity |
| | `get_current_package(driver)` | Get current package |
| **System Operations** | `open_browser(driver, url, wait_seconds)` | Open URL in browser |
| | `get_device_logs(driver)` | Get device logcat |
| | `get_device_logs_to_file(driver, save_path)` | Get logs and save to file |
| | `execute_shell(driver, command, args)` | Execute ADB shell command |
| **GPS Location** | `get_location(driver)` | Get current GPS location |
| | `set_location(driver, latitude, longitude, altitude)` | Set mock GPS location |
| **Permissions** | `grant_permission(driver, package, permission)` | Grant single permission |
| | `grant_permissions(driver, package, permissions)` | Grant multiple permissions |

### Usage Example

```python
from mobile_actions import (
    click_element, 
    tap_screen, 
    take_screenshot,
    get_page_source,
    launch_app
)

# Click element by resource-id
click_element(driver, resource_id="com.example:id/login_button")

# Click element by text
click_element(driver, text="Login")

# Click element by partial text match
click_element(driver, text="Log", partial=True)

# Tap screen coordinates
tap_screen(driver, 500, 800)

# Take screenshot
take_screenshot(driver, "output/screenshot.png")

# Get page XML
page_source = get_page_source(driver)

# Launch app
launch_app(driver, "com.example.app")
```

## Unit Tests

The `test_mobile_actions.py` file contains comprehensive unit tests for all functions in `mobile_actions.py`.

### Running Tests

```bash
# Run all tests
python -m pytest test_mobile_actions.py -v

# Run specific test class
python -m pytest test_mobile_actions.py::TestClickElement -v

# Run specific test
python -m pytest test_mobile_actions.py::TestClickElement::test_click_element_by_id -v

# Run with coverage report
pip install pytest-cov
python -m pytest test_mobile_actions.py -v --cov=mobile_actions --cov-report=term-missing
```

### Test Coverage

| Category | Tests | Status |
|----------|-------|--------|
| Screen Operations | 5 | ✅ |
| Screen Resolution | 6 | ✅ |
| Text Input | 5 | ✅ |
| Element Operations | 10 | ✅ |
| Page Analysis | 10 | ✅ |
| App Management | 11 | ✅ |
| System Operations | 8 | ✅ |
| GPS Location | 7 | ✅ |
| Permissions | 7 | ✅ |
| **Total** | **69** | **✅** |

## Output Directory

Screenshots and logs are saved to the `output/` directory:

```
output/
├── quickstart_output/     # quickstart.py output
│   ├── mobile_screenshot_*.png
│   └── screenshot_before_exit_*.png
└── batch_output/          # batch.py output
    └── {count}_{timestamp}/
        ├── console.log
        ├── summary.json
        ├── details.json
        └── sandbox_*/
            ├── screenshot_1.png
            ├── screenshot_2.png
            └── ...
```

## Supported Apps

The example includes configurations for common Android apps. You can customize `APP_CONFIGS` dictionary to add your own apps.

**quickstart.py:**
- **WeChat** (`wechat`): Chinese messaging app
- **应用宝** (`yyb`): Chinese app store

**batch.py:**
- **Meituan** (`meituan`): Chinese lifestyle service app

## Example Usage

### Basic Browser Test

```python
# Open browser and navigate
open_browser(driver, "https://example.com")
time.sleep(5)

# Tap screen
tap_screen(driver, 360, 905)

# Take screenshot
take_screenshot(driver)
```

### App Installation and Launch

```python
# Complete app installation flow
install_and_launch_app(driver, 'yyb')
```

### GPS Location Mocking

```python
# Get current location
get_location(driver)

# Set mock location (Shenzhen, China)
set_location(driver, latitude=22.54347, longitude=113.92972)

# Verify location
get_location(driver)
```

### Element Click Operations

```python
from mobile_actions import click_element

# Click by resource-id (most reliable)
click_element(driver, resource_id="com.example:id/button")

# Click by exact text
click_element(driver, text="Submit")

# Click by partial text
click_element(driver, text="Sub", partial=True)
```

## Chunked Upload

For large APK files, the example uses chunked upload strategy:

1. **Phase 1**: Upload all chunks to temporary directory
2. **Phase 2**: Merge chunks into final APK file

This approach handles large files efficiently and provides progress feedback.

## GPS Location Mocking

The example uses Appium Settings LocationService for GPS mocking, which is suitable for containerized Android environments. The mock location will be returned when apps request location services.

## Dependencies

- Python >= 3.8
- e2b >= 2.9.0
- Appium-Python-Client >= 3.1.0
- requests >= 2.28.0
- python-dotenv >= 1.0.0 (optional)
- pytest >= 7.0.0 (for testing)

## Notes

- **APK files**: Place APK files in the `apk/` directory. If APK is not found, it will be automatically downloaded (if download URL is configured).
- Screen stream URL uses ws-scrcpy protocol for real-time viewing
- Appium connection uses authentication token from sandbox
- GPS mocking works with LocationService in containerized Android environments
- Use Ctrl+C to gracefully stop the script - resources will be automatically cleaned up
