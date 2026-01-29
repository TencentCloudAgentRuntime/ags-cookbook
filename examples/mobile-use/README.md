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
├── sandbox_connect.py         # Single sandbox connection tool (CLI)
├── test_mobile_actions.py     # Unit tests
├── apk/                       # APK files directory
└── output/                    # Screenshots and logs output
```

## Scripts

| Script | Description |
|--------|-------------|
| `quickstart.py` | Quick start example demonstrating basic mobile automation features |
| `batch.py` | Batch operations script for high-concurrency sandbox testing (multi-process + async) |
| `sandbox_connect.py` | Single sandbox connection tool for connecting to existing sandboxes via CLI |
| `test_mobile_actions.py` | Unit tests |

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

## Sandbox Connect Tool

`sandbox_connect.py` is a CLI tool for connecting to an existing sandbox and executing mobile automation operations on demand.

### Difference from Other Scripts

| Script | Purpose |
|--------|---------|
| `quickstart.py` | Creates a new sandbox and runs a complete demo flow |
| `batch.py` | Batch testing of multiple scenarios |
| `sandbox_connect.py` | Connects to an existing single sandbox and executes specified operations |

### Basic Usage

```bash
python sandbox_connect.py --sandbox-id <sandbox_id> --action <action> [other parameters]
```

### Supported Actions

**App Operations** (requires `--app-name`):

| Action | Description |
|--------|-------------|
| `upload_app` | Upload APK to device |
| `install_app` | Install uploaded APK |
| `launch_app` | Launch app |
| `check_app` | Check if app is installed |
| `grant_app_permissions` | Grant app permissions |
| `close_app` | Close app |
| `uninstall_app` | Uninstall app |

**Screen Operations**:

| Action | Description | Required Parameters |
|--------|-------------|---------------------|
| `tap_screen` | Tap screen coordinates | `--tap-x`, `--tap-y` |
| `screenshot` | Take screenshot | None |
| `set_screen_resolution` | Set screen resolution | `--width`, `--height`, `--dpi`(optional) |
| `reset_screen_resolution` | Reset screen resolution | None |

**UI Operations**:

| Action | Description | Required Parameters |
|--------|-------------|---------------------|
| `dump_ui` | Get UI hierarchy (XML) | None |
| `click_element` | Click element | `--element-text` or `--element-id` |
| `input_text` | Input text | `--text` |

**Location Operations**:

| Action | Description | Required Parameters |
|--------|-------------|---------------------|
| `set_location` | Set GPS location | `--latitude`, `--longitude`, `--altitude`(optional) |
| `get_location` | Get current GPS location | None |

**Device Info Operations**:

| Action | Description | Required Parameters |
|--------|-------------|---------------------|
| `device_info` | Get device details | None |
| `get_window_size` | Get screen window size | None |
| `get_device_model` | Get device model | None |
| `get_app_state` | Get app state | `--app-name` |
| `get_current_activity` | Get current Activity | None |
| `get_current_package` | Get current package | None |

**System Operations**:

| Action | Description | Required Parameters |
|--------|-------------|---------------------|
| `open_browser` | Open browser | `--url` |
| `disable_gms` | Disable Google Play Services | None |
| `enable_gms` | Enable Google Play Services | None |
| `get_device_logs` | Get device logs | None |
| `shell` | Execute ADB shell command | `--shell-cmd` |

### Usage Examples

**Get device info:**
```bash
python sandbox_connect.py --sandbox-id abc123 --action device_info
```

**Take screenshot:**
```bash
python sandbox_connect.py --sandbox-id abc123 --action screenshot
```

**Tap screen:**
```bash
python sandbox_connect.py --sandbox-id abc123 --action tap_screen --tap-x 500 --tap-y 1000
```

**Click element:**
```bash
# By resource-id
python sandbox_connect.py --sandbox-id abc123 --action click_element --element-id "com.example:id/button"

# By text
python sandbox_connect.py --sandbox-id abc123 --action click_element --element-text "Login"
```

**Set GPS location (Shenzhen):**
```bash
python sandbox_connect.py --sandbox-id abc123 --action set_location --latitude 22.5431 --longitude 113.9298
```

**Get UI hierarchy:**
```bash
python sandbox_connect.py --sandbox-id abc123 --action dump_ui
```

**Batch operations (comma-separated):**
```bash
python sandbox_connect.py --sandbox-id abc123 \
    --action upload_app,install_app,grant_app_permissions,launch_app \
    --app-name yyb
```

**Execute ADB shell command:**
```bash
python sandbox_connect.py --sandbox-id abc123 --action shell --shell-cmd "pm list packages"
```

### Command Line Help

```bash
python sandbox_connect.py --help
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

## Output Directory

Screenshots and logs are saved to the `output/` directory:

```
output/
├── quickstart_output/          # quickstart.py output
│   ├── mobile_screenshot_*.png
│   └── screenshot_before_exit_*.png
├── batch_output/               # batch.py output
│   └── {count}_{timestamp}/
│       ├── console.log
│       ├── summary.json
│       ├── details.json
│       └── sandbox_*/
│           ├── screenshot_1.png
│           ├── screenshot_2.png
│           └── ...
└── sandbox_connect_output/     # sandbox_connect.py output
    ├── screenshot_*.png
    ├── ui_dump.xml
    └── device_logs_*.txt
```

## Supported Apps

The example includes configurations for common Android apps. You can customize `APP_CONFIGS` dictionary to add your own apps.

**quickstart.py:**
- **应用宝** (`yyb`): Tencent App Store

**batch.py:**
- **Meituan** (`meituan`): Chinese lifestyle service app

**sandbox_connect.py:**
- **应用宝** (`yyb`): Tencent App Store

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
