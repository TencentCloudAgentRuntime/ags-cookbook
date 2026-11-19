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
├── sandboxes_example.yaml     # Sandbox IDs template (copy to sandboxes.yaml for local use)
├── quickstart.py              # Quick start example
├── batch.py                   # Batch operations script (multi-process + async)
├── sandbox_connect.py         # Single sandbox connection tool (CLI)
├── batch_dump_logcat.py       # Batch dump logcat logs from existing sandboxes
├── batch_sandbox_kill.py      # Batch kill sandboxes with confirmation
├── batch_sandbox_create.py    # Batch create sandboxes
├── sms_inject.py              # Simulate an incoming SMS (adb / SDK)
├── apk/                       # APK files directory
└── output/                    # Screenshots and logs output
```

## Scripts

| Script | Description |
|--------|-------------|
| `quickstart.py` | Quick start example demonstrating basic mobile automation features |
| `batch.py` | Batch operations script for high-concurrency sandbox testing (multi-process + async) |
| `sandbox_connect.py` | Single sandbox connection tool for connecting to existing sandboxes via CLI |
| `batch_dump_logcat.py` | Batch dump full logcat logs from existing sandboxes, organized by sandbox ID |
| `batch_sandbox_kill.py` | Batch kill sandboxes from YAML config with manual confirmation |
| `batch_sandbox_create.py` | Batch create sandboxes with concurrency control |
| `sms_inject.py` | Simulate an incoming SMS (replacement for `adb emu sms send`) over adb or the SDK |

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

Or using make:

```bash
make setup
```

### 2. Configure API keys

**Option 1: .env file (recommended for local development)**
```bash
# Copy the example file
cp .env.example .env

# Edit .env and fill in your configuration
```

**Option 2: Environment variables (recommended for CI/CD)**
```bash
export E2B_API_KEY="your_api_key"  # provided by Tencent Cloud Agent Sandbox product
export E2B_DOMAIN="ap-guangzhou.tencentags.com"
export SANDBOX_TEMPLATE="mobile-v1"
```

### 3. Run examples

**Quick Start Example:**
```bash
make run
```

**Batch Operations:**
```bash
uv run batch.py
```


### Useful runtime controls

The quickstart script now supports environment variables that make local validation easier:

```bash
export LONG_RUN_SECONDS=0
export LONG_RUN_RESERVE_SECONDS=0
```

Use them when you want a smoke-like local run instead of waiting through the full long-running demo phase.

## Batch Tools

The batch tools use a shared `sandboxes.yaml` config file for sandbox IDs.

First copy the template file locally:

```bash
cp sandboxes_example.yaml sandboxes.yaml
```

`sandboxes.yaml` is local-only and ignored by git.

Then fill `sandbox_ids` in `sandboxes.yaml`:

```yaml
sandbox_ids:
  - sandbox_id_1
  - sandbox_id_2
  - sandbox_id_3
```

### Batch Dump Logcat

Dump full logcat logs from existing sandboxes without killing them:

```bash
# Use default sandboxes.yaml
python batch_dump_logcat.py

# Specify config and concurrency (must be >= 1)
python batch_dump_logcat.py --config my_sandboxes.yaml --concurrency 10

# Custom output directory
python batch_dump_logcat.py --output-dir /tmp/logcat
```

Output structure:
```
output/batch_dump_logcat_output/
├── <sandbox_id_1>/
│   └── logcat_YYYYMMDD_HHMMSS.txt
├── <sandbox_id_2>/
│   └── logcat_YYYYMMDD_HHMMSS.txt
└── summary_YYYYMMDD_HHMMSS.json
```

### Batch Kill Sandboxes

Kill sandboxes with manual confirmation before execution:

```bash
# Use default sandboxes.yaml (requires y/yes confirmation)
python batch_sandbox_kill.py

# Skip confirmation
python batch_sandbox_kill.py --yes

# Custom concurrency (must be >= 1) and sleep interval (must be >= 0)
python batch_sandbox_kill.py --concurrency 20 --sleep 2
```

### Batch Create Sandboxes

Batch create sandboxes with concurrency control:

```bash
python batch_sandbox_create.py
```

Created sandbox IDs are saved to `output/batch_create_output/`.

## Sandbox Connect Tool

`sandbox_connect.py` is a CLI tool for connecting to an existing sandbox and executing mobile automation operations on demand.

### Difference from Other Scripts

| Script | Purpose |
|--------|---------|
| `quickstart.py` | Creates a new sandbox and runs a complete demo flow |
| `batch.py` | Batch testing of multiple scenarios |
| `sandbox_connect.py` | Connects to an existing single sandbox and executes specified operations |
| `batch_dump_logcat.py` | Batch dump logcat logs from multiple existing sandboxes |
| `batch_sandbox_kill.py` | Batch kill sandboxes with confirmation |
| `batch_sandbox_create.py` | Batch create sandboxes |

### Basic Usage

```bash
uv run sandbox_connect.py --sandbox-id <sandbox_id> --action <action> [other parameters]
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
| `get_app_state` | Get app state (0=not installed, 1=not running, 2=background paused, 3=background running, 4=foreground running) |

**Screen Operations**:

| Action | Description | Required Parameters |
|--------|-------------|---------------------|
| `tap_screen` | Tap screen coordinates | `--tap-x`, `--tap-y` |
| `screenshot` | Take screenshot | None |
| `set_screen_resolution` | Set screen resolution | `--width`, `--height`, `--dpi`(optional) |
| `reset_screen_resolution` | Reset screen resolution | None |
| `get_window_size` | Get screen window size | None |

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
| `get_device_model` | Get device model | None |
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

**Upload, install, grant permissions, and launch app (comma-separated batch operations):**
```bash
python sandbox_connect.py --sandbox-id abc123 --action upload_app,install_app,grant_app_permissions,launch_app --app-name yyb
```

**Upload, install, grant permissions, and launch QQ Browser:**
```bash
python sandbox_connect.py --sandbox-id abc123 --action upload_app,install_app,grant_app_permissions,launch_app --app-name qqbrowser
```

**Get device logs (full logcat):**
```bash
python sandbox_connect.py --sandbox-id abc123 --action get_device_logs
```

**Execute ADB shell command:**
```bash
python sandbox_connect.py --sandbox-id abc123 --action shell --shell-cmd "pm list packages"
```

**Uninstall app:**
```bash
python sandbox_connect.py --sandbox-id abc123 --action uninstall_app --app-name yyb
```

**Get app state:**
```bash
python sandbox_connect.py --sandbox-id abc123 --action get_app_state --app-name yyb
```

### Command Line Help

```bash
python sandbox_connect.py --help
```

## Simulate an Incoming SMS

The mobile sandbox runs containerized Android without an emulator console, so `adb emu sms send` does not work. The sandbox image ships an equivalent device-side tool, `/system/bin/smartrun-sms-inject`, which writes a received SMS (and its conversation thread) into the system SMS database. The message then appears in `content://sms/inbox` and in SMS apps.

`sms_inject.py` shows the three ways to call it:

| Method | When to use | Tool flag |
|--------|-------------|-----------|
| adb + stdin (default) | You run adb yourself and can write to its stdin | `--from-stdin` (line 1 = number, rest = body) |
| adb + base64 | Your caller can only pass command-line arguments to adb | `--b64 <b64 number> <b64 body>` |
| SDK (e2b + Appium) | You drive the sandbox through Appium `mobile: shell` (no stdin) | `--b64` |

None of them goes through shell quoting, so quotes, `$`, backticks, newlines, CJK and emoji are stored byte-for-byte.

**adb**: get the adb address with the AGS CLI, then inject:

```bash
agr instance mobile connect <sandbox_id>
# connected to 127.0.0.1:<port>

uv run sms_inject.py adb --serial 127.0.0.1:<port> +8613800000000 "Hello"
uv run sms_inject.py adb --serial 127.0.0.1:<port> --method b64 +8613800000000 "Hello"
```

**SDK** (requires `E2B_API_KEY` and `E2B_DOMAIN`):

```bash
uv run sms_inject.py sdk --sandbox-id <sandbox_id> +8613800000000 "Hello"
```

**From your own code**, import the functions instead of the CLI:

```python
from sms_inject import inject_sms_via_adb, inject_sms_via_appium

inject_sms_via_adb("127.0.0.1:5555", "+8613800000000", "Hello")
inject_sms_via_appium(driver, "+8613800000000", "Hello")  # an existing Appium driver
```

**Without Python**:

```bash
# adb + stdin
printf '%s\n%s' "$NUM" "$MSG" | adb -s "$SERIAL" shell smartrun-sms-inject --from-stdin

# adb + base64 (pass -w0 on Linux: GNU base64 wraps at 76 columns)
adb -s "$SERIAL" shell smartrun-sms-inject --b64 \
    "$(printf '%s' "$NUM" | base64 -w0)" "$(printf '%s' "$MSG" | base64 -w0)"
```

Notes:

- Requires a sandbox image that ships `smartrun-sms-inject` (SmartRun redroid `android_world` image v33.3 or later).
- Do **not** call the tool as `smartrun-sms-inject '<number>' '<message>'`: the arguments are parsed by both the local and the device shell, and a message with spaces or quotes is truncated (for example `"plain arg msg"` is stored as `plain`).
- Without `-w0` on Linux, a long base64 value is wrapped, the device shell runs the wrapped lines as commands, and the message is silently truncated while the exit status is still 0.
- An SMS app that is already open does not refresh until it is reopened.

Common failures:

| Symptom | Cause / fix |
|---------|-------------|
| `failed (exit 127): ... smartrun-sms-inject: inaccessible or not found` | The sandbox image predates the tool. Use a template on SmartRun redroid `android_world` v33.3 or later |
| `failed (exit 2): usage: smartrun-sms-inject ...` | Empty number or message reached the tool |
| `adb: device offline` / `device not found` | The `agr` tunnel was dropped (for example by `adb disconnect` or `adb kill-server`). Run `agr instance mobile connect <sandbox_id>` again and use the new port |
| `E2B_API_KEY is required for sdk mode` | Set `E2B_API_KEY` and `E2B_DOMAIN` (environment or `.env`) |

## Configuration

### Required Configuration

| Variable | Description |
|----------|-------------|
| `E2B_API_KEY` | Your AgentSandbox API Key (provided by Tencent Cloud Agent Sandbox product) |
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
├── quickstart_output/              # quickstart.py output
│   ├── mobile_screenshot_*.png
│   └── screenshot_before_exit_*.png
├── batch_output/                   # batch.py output
│   └── {count}_{timestamp}/
│       ├── console.log
│       ├── summary.json
│       ├── details.json
│       └── sandbox_*/
│           ├── screenshot_1.png
│           ├── screenshot_2.png
│           └── ...
├── sandbox_connect_output/         # sandbox_connect.py output
│   ├── screenshot_*.png
│   ├── ui_dump.xml
│   └── device_logs_*.txt
├── batch_dump_logcat_output/       # batch_dump_logcat.py output
│   ├── <sandbox_id>/
│   │   └── logcat_*.txt
│   └── summary_*.json
└── batch_create_output/            # batch_sandbox_create.py output
    ├── sandbox_ids_*.txt
    └── details_*.json
```

## Supported Apps

The example includes configurations for common Android apps. You can customize `APP_CONFIGS` dictionary to add your own apps.

**quickstart.py:**
- **应用宝** (`yyb`): Tencent App Store

**batch.py:**
- **Meituan** (`meituan`): Chinese lifestyle service app

**sandbox_connect.py:**
- **应用宝** (`yyb`): Tencent App Store
- **QQ Browser** (`qqbrowser`): Tencent QQ Browser

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

All dependencies are listed in `requirements.txt`:

```bash
pip install -r requirements.txt
```

- **e2b** - Sandbox creation/connection/management
- **Appium-Python-Client** - Android device automation via Appium
- **requests** - HTTP requests (health checks, chunked upload, etc.)
- **PyYAML** - YAML config parsing (for batch tools)
- **python-dotenv** - Optional, auto-load `.env` files (manual fallback built-in)

## Notes

- **APK files**: Place APK files in the `apk/` directory. If APK is not found, it will be automatically downloaded (if download URL is configured).
- Screen stream URL uses ws-scrcpy protocol for real-time viewing
- Appium connection uses authentication token from sandbox
- GPS mocking works with LocationService in containerized Android environments
- Use Ctrl+C to gracefully stop the script - resources will be automatically cleaned up

## Quick Start

```bash
make run
```
