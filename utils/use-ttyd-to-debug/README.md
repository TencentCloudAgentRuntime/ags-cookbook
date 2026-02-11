# Debug Sandbox via ttyd Web Terminal

Deploy [ttyd](https://github.com/tsl0922/ttyd) inside an Agent Sandbox to get a browser-accessible Web terminal for real-time debugging and interactive operations.

## How It Works

```
Local Script                Agent Sandbox
┌──────────┐               ┌───────────────────┐
│          │  Upload ttyd  │                   │
│  main.py │──────────────>│  /root/ttyd       │
│          │               │     │              │
│          │  Start svc    │     ▼              │
│          │──────────────>│  ttyd -p 8080 bash│
│          │               │     │              │
│          │  Get URL      │     ▼              │
│          │<──────────────│  Web Terminal:8080 │
└──────────┘               └───────────────────┘
      │
      ▼
  Open URL in browser → Enter sandbox bash terminal
```

## Core Features

- **Web Terminal Access**: Access the sandbox bash terminal directly from your browser
- **Real-time Debugging**: Execute any command, inspect files, processes, and network in the sandbox
- **Auto Download**: Automatically downloads the ttyd binary from GitHub on first run — no manual preparation needed
- **Smart Detection**: Automatically detects ttyd file, process, and port status in the sandbox to avoid redundant operations
- **Secure Access**: Authentication via access_token

## Use Cases

- Debug program execution issues inside the sandbox
- Inspect the sandbox file system and environment configuration
- Monitor processes and resource usage in real time
- Interactively run commands and test inside the sandbox

## Quick Start

### 1. Install Dependencies

```bash
uv sync
```

### 2. Configure Environment

> The ttyd binary will be automatically downloaded from [GitHub Releases](https://github.com/tsl0922/ttyd/releases/tag/1.7.7) on first run — no manual preparation needed.

```bash
cp .env.example .env
```

Edit the `.env` file with your actual values:

```dotenv
E2B_DOMAIN=ap-chongqing.tencentags.com
E2B_API_KEY=your_api_key_here
SANDBOX_ID=your_sandbox_id
```

### 3. Run

```bash
uv run main.py
```

After running, a Web terminal access URL will be printed. Open it in your browser to enter the sandbox bash terminal.

## Example Output

First run (auto-downloads ttyd, uploads and starts):

```
ttyd binary not found: /path/to/ttyd.i686
Downloading ttyd from GitHub ...
URL: https://github.com/tsl0922/ttyd/releases/download/1.7.7/ttyd.i686
  [████████████████████████████████████████] 100.0% (800KB/800KB)
Download complete: /path/to/ttyd.i686
Connecting to sandbox: xxxxx
Sandbox connected: xxxxx
Uploading ttyd to sandbox...
ttyd upload complete
Starting ttyd service (port: 8080)...
ttyd service started in background

============================================================
ttyd Web Terminal is ready!
============================================================

Access URL:
https://xxxxx.ap-chongqing.tencentags.com/?access_token=xxxxx

Open the URL above in your browser to access the sandbox terminal.
============================================================
```

Subsequent run (detects existing state, skips upload and start):

```
ttyd binary found: /path/to/ttyd.i686
Connecting to sandbox: xxxxx
Sandbox connected: xxxxx
ttyd already exists in sandbox, skipping upload
ttyd process already running, skipping start

============================================================
ttyd Web Terminal is ready!
============================================================

Access URL:
https://xxxxx.ap-chongqing.tencentags.com/?access_token=xxxxx

Open the URL above in your browser to access the sandbox terminal.
============================================================
```

## Dependencies

- `e2b-code-interpreter` >= 2.0.0
- `python-dotenv` >= 1.0.0

## Notes

- ttyd runs as root — exercise caution with commands
- ttyd stops automatically when the sandbox is shut down
- The access URL contains an access_token — do not share it with others
- Default port is 8080; change `TTYD_PORT` in `main.py` if needed
- If port 8080 is already occupied by another process, the script will exit with an error
- Re-running the script will skip completed steps (upload, start) and directly output the access URL
