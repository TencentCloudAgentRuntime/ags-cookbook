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

## Scripts

| Script | Description |
|--------|-------------|
| `quickstart.py` | Quick start example demonstrating basic mobile automation features |
| `batch.py` | Batch operations script for high-concurrency sandbox testing (multi-process + async) |

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

## Available Features

| Feature | Description |
|---------|-------------|
| `upload_app` | Upload APK to device using chunked upload (supports large files) |
| `install_app` | Install uploaded APK on device |
| `grant_app_permissions` | Grant all necessary permissions to app |
| `launch_app` | Launch installed app |
| `open_browser` | Open URL in device browser |
| `tap_screen` | Tap screen at specified coordinates |
| `take_screenshot` | Take device screenshot |
| `get_location` | Get current GPS location |
| `set_location` | Set GPS location (mock location) |
| `install_and_launch_app` | Complete flow: upload → install → grant permissions → launch |

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

## Notes

- **APK files**: Place APK files in the `apk/` directory. If APK is not found, it will be automatically downloaded (if download URL is configured).
- Screen stream URL uses ws-scrcpy protocol for real-time viewing
- Appium connection uses authentication token from sandbox
- GPS mocking works with LocationService in containerized Android environments
- Use Ctrl+C to gracefully stop the script - resources will be automatically cleaned up
