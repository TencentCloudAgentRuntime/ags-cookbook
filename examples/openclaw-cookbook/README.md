# OpenClaw Sandbox Guide (Official Image)

Run OpenClaw on Tencent Cloud AGS using the official `ghcr.io/openclaw/openclaw:latest` image. No need to maintain nginx or startup scripts — OpenClaw always tracks the latest official release.

---

## Table of Contents

1. [Architecture](#architecture)
2. [Prerequisites](#prerequisites)
3. [Prepare openclaw.json](#prepare-openclawjson)
4. [Build and Push Image](#build-and-push-image)
5. [Create Sandbox Tool](#create-sandbox-tool)
6. [Launch Sandbox and Access Dashboard](#launch-sandbox-and-access-dashboard)
7. [Persistent Storage](#persistent-storage)
8. [Logs and Debugging](#logs-and-debugging)
9. [FAQ](#faq)

---

## Architecture

```
Browser
  │
  ├─ http://localhost:3001           ←── localproxy management UI (create/connect/stop sandbox)
  │
  └─ http://localhost:3001/sandbox/  ←── localproxy reverse proxy (available only when sandbox is running)
       │  Automatically injects X-Access-Token header
       ▼
  AGS Auth Gateway (<region>.tencentags.com)
       │  Validates X-Access-Token
       ▼
  OpenClaw Gateway:8080 (directly exposed, no nginx layer)
```

**Container processes:**

| Process | Port | Purpose |
|---------|------|---------|
| `envd` | 49983 | AGS sandbox management daemon (health probe, command execution) |
| `node openclaw.mjs gateway` | 8080 | OpenClaw Gateway, `--bind lan` listens on all network interfaces |

---

## Prerequisites

### Tool Dependencies

| Tool | Purpose | Installation |
|------|---------|-------------|
| `podman` or `docker` | Build/push images | [podman.io](https://podman.io) / [docker.com](https://docker.com) |
| `Node.js >= 20` | Run local proxy | [nodejs.org](https://nodejs.org) |
| `pnpm` | Package manager | `npm install -g pnpm` |

### Credentials

localproxy uses the Tencent Cloud AGS SDK to manage sandboxes. The following credentials are required:

| Credential | Description | How to Obtain |
|------------|-------------|---------------|
| `TENCENTCLOUD_SECRET_ID` | Tencent Cloud API Key ID | [API Key Management](https://console.cloud.tencent.com/cam/capi) |
| `TENCENTCLOUD_SECRET_KEY` | Tencent Cloud API Key Secret | Same as above |

Log in to the image registry:

```bash
podman login ccr.ccs.tencentyun.com
```

---

## Prepare openclaw.json

`openclaw.json` is the OpenClaw configuration file. It is **not baked into the image** but persisted via COS.

### Storage Path Mapping

The startup parameters set `OPENCLAW_HOME=/openclaw`. OpenClaw reads the config at startup:

```
$OPENCLAW_HOME/.openclaw/openclaw.json
= /openclaw/.openclaw/openclaw.json
```

COS mount configuration (set in AGS console or setup.py):

| Field | Example Value | Description |
|-------|---------------|-------------|
| COS Bucket | `your-bucket` | Bucket name |
| COS Sub-path | `openclaw-user1` | Directory prefix inside the bucket |
| Container Mount Path | `/openclaw` | i.e. `OPENCLAW_HOME`, fixed value |

After mounting, the path mapping inside the container:

```
/openclaw/                    ← OPENCLAW_HOME, COS bucket root (sub-path) mount point
└── .openclaw/
    ├── openclaw.json         ← Config file (must be uploaded in advance)
    ├── canvas/               ← Agent Canvas data (auto-created at runtime)
    └── cron/                 ← Cron task data (auto-created at runtime)
```

### Upload Config to COS

Before use, upload `openclaw.json` to the corresponding COS path:

```
cos://your-bucket/openclaw-user1/.openclaw/openclaw.json
                  ^^^^^^^^^^^^^^ ^^^^^^^^^^
                  COS sub-path    fixed as .openclaw/
```

```json
{
  "agents": {
    "defaults": {
      "compaction": { "mode": "safeguard" }
    }
  },
  "commands": {
    "native": "auto",
    "nativeSkills": "auto",
    "restart": true,
    "ownerDisplay": "raw"
  },
  "gateway": {
    "mode": "local",
    "controlUi": {
      "dangerouslyAllowHostHeaderOriginFallback": true,
      "dangerouslyDisableDeviceAuth": true,
      "allowedOrigins": ["*"]
    },
    "auth": {
      "mode": "token",
      "token": "openclaw-sandbox-token"
    },
    "bind": "lan"
  }
}
```

### Key Configuration Items

| Config Path | Value | Description |
|-------------|-------|-------------|
| `gateway.bind` | `"lan"` | **Required**. Makes OpenClaw listen on `0.0.0.0` instead of loopback, so it's accessible from outside the container |
| `gateway.auth.token` | `"openclaw-sandbox-token"` | OpenClaw's own Bearer Token |
| `gateway.controlUi.dangerouslyDisableDeviceAuth` | `true` | **Required**. Disables device pairing check |
| `gateway.controlUi.dangerouslyAllowHostHeaderOriginFallback` | `true` | **Required**. Adapts to AGS domain access |

---

## Build and Push Image

### Directory Structure

```
openclaw-cookbook/
├── Dockerfile          # FROM official image, COPY --from AGS envd image
├── Makefile
├── .gitignore
├── openclaw.json       # Config file template to upload to COS
└── localproxy/         # Local management tool (create/connect/stop sandbox + reverse proxy)
    ├── server.ts       # Main service: Express + state machine + SSE + embedded Web UI
    ├── package.json
    ├── .env.example    # Environment variable template
    └── .env            # Local config (not committed to Git)
```

### Build and Push

> ⚠️ **Important**: The AGS runtime is `linux/amd64`. You must build an amd64 image. The Makefile defaults to `--platform linux/amd64`, which cross-compiles automatically on Apple Silicon Macs.

> 💡 The Makefile defaults to `podman`. Docker users can override via `make push CONTAINER_ENGINE=docker`.

```bash
cd openclaw-cookbook

# Edit DOCKER_REGISTRY in Makefile
# DOCKER_REGISTRY ?= ccr.ccs.tencentyun.com/your-namespace

# Build and push (pushes both latest and hash tags)
make push
# Example output:
# Pushed: ccr.ccs.tencentyun.com/your-namespace/sandbox-openclaw:latest
# Pushed: ccr.ccs.tencentyun.com/your-namespace/sandbox-openclaw:73f17f45ddf3
```

---

## Create Sandbox Tool

When creating a sandbox tool in the [AGS Console](https://console.cloud.tencent.com/ags), fill in the following:

### Basic Configuration

> ⚠️ **Important**: AGS ignores `CMD`/`ENTRYPOINT` in the image when running sandboxes. You must manually set the startup command and parameters in the console.

| Field | Value |
|-------|-------|
| Tool Name | `my-openclaw-official` |
| Tool Type | Custom Image |
| Image Address | `ccr.ccs.tencentyun.com/your-namespace/sandbox-openclaw:<hash>` |
| Image Registry Type | Personal |
| Startup Command | `/bin/bash` |
| Startup Parameters | `-l` `-c` `/usr/bin/envd > /tmp/envd.log 2>&1 & while true; do su -s /bin/bash node -c 'OPENCLAW_HOME=/openclaw node /app/openclaw.mjs gateway --port 8080 --bind lan --allow-unconfigured'; echo '[restart] openclaw exited ($?), restarting in 1s...'; sleep 1; done` |
| CPU | 4 cores |
| Memory | 8 GiB |
| Probe Path | `/health` |
| Probe Port | `49983` |
| Ready Timeout | `30000` ms |
| Probe Interval | `3000` ms |
| Failure Threshold | `100` |
| Network Policy | Public |

### Storage Mount Configuration

| Mount Item | COS Path | Container Mount Path |
|------------|----------|---------------------|
| OpenClaw Data | `cos://your-bucket/user1/` | `/openclaw` |

> ⚠️ **Note**: COS mount path is `/openclaw`. The startup parameters set `OPENCLAW_HOME=/openclaw`. OpenClaw reads `/openclaw/.openclaw/openclaw.json` as its config and writes all runtime data to that directory. You must upload the config file to `user1/.openclaw/openclaw.json` in COS beforehand (refer to `openclaw.json`).

> ⚠️ **Note**: After updating the tool image, new sandboxes may return 502 for about 3 minutes. This is normal — just retry later.

---

## Launch Sandbox and Access Dashboard

### Configure Local Proxy

Copy the environment variable template:

```bash
cp localproxy/.env.example localproxy/.env
```

Edit `localproxy/.env` with the following:

```bash
# Tencent Cloud API Credentials (required)
TENCENTCLOUD_SECRET_ID=your_secret_id_here
TENCENTCLOUD_SECRET_KEY=your_secret_key_here
TENCENTCLOUD_REGION=ap-shanghai          # AGS region

# AGS Configuration (required)
TOOL_NAME=my-openclaw-official           # Sandbox tool name created in AGS console

# COS Mount (optional, uses tool default mount if not set)
MOUNT_NAME=cos                           # Mount item name, used to pass subpath etc.
```

Install dependencies and start:

```bash
# Run from the openclaw-cookbook root directory
make setup   # Install localproxy dependencies
make run     # Start localproxy management service
```

### Usage Flow

1. Open the management UI at **http://localhost:3001**
2. Click **Start Sandbox** to create a new sandbox (or enter an existing sandbox ID and click **Connect**)
3. Wait for state transitions: `Idle → Starting → Connecting → Running`
4. Once Running, click **Open Dashboard** to access OpenClaw Dashboard (at `http://localhost:3001/sandbox/__openclaw__`)

> ⚠️ On first visit to the Dashboard, you'll need to enter the OpenClaw Token. The default is `openclaw-sandbox-token` (as configured in `openclaw.json`).

---

## Persistent Storage

OpenClaw uses the `OPENCLAW_HOME` environment variable to determine where config and runtime data are stored. The startup parameters set:

```
OPENCLAW_HOME=/openclaw
```

OpenClaw reads `$OPENCLAW_HOME/.openclaw/openclaw.json` as its config and writes all runtime data to `$OPENCLAW_HOME/.openclaw/`. Simply mount the COS bucket to `/openclaw` in the container for persistence:

| COS Path | Container Mount Path | Content |
|----------|---------------------|---------|
| `cos://your-bucket/user1/` | `/openclaw` | OpenClaw config and all runtime data |

OpenClaw reads/writes `/openclaw/.openclaw/`, which contains:

| Path | Content |
|------|---------|
| `/openclaw/.openclaw/openclaw.json` | Config file (**must** be uploaded to COS beforehand) |
| `/openclaw/.openclaw/canvas/` | Canvas data |
| `/openclaw/.openclaw/cron/` | Cron tasks |

> ⚠️ **Note**: `/openclaw/.openclaw/openclaw.json` must be uploaded to COS beforehand. OpenClaw will fail to start if COS is not mounted or the file doesn't exist. No default fallback is provided so configuration issues can be caught quickly.

To isolate by user/session, enter a sub-path (e.g. `user-123`) in the **Mount subpath** input field of the localproxy management UI. The sub-path will be automatically passed to the AGS storage mount when creating the sandbox:

```
COS mount effect:
cos://your-bucket/user-123/         → /openclaw
cos://your-bucket/user-123/.openclaw/openclaw.json  → config file for this user
```

---

## Logs and Debugging

Log in to the sandbox using ags-cli:

```bash
ags instance login <sandbox_id> --user root
```

Common debugging commands:

```bash
# Check process status
ps aux | grep -E 'node|envd' | grep -v grep

# OpenClaw startup logs (stdout output, view via AGS console or ags-cli)

# OpenClaw detailed session logs
cat /tmp/openclaw/openclaw-$(date +%Y-%m-%d).log

# envd daemon logs
cat /tmp/envd.log
```

---

## FAQ

### Q1: Dashboard shows 401

**Cause**: `openclaw.json` was not read correctly. OpenClaw started in default loopback mode.

**Solution**: Verify that COS is mounted at `/openclaw` and that `/openclaw/.openclaw/openclaw.json` exists and contains `"bind": "lan"`.

### Q2: `ENOENT` or config read failure when creating sandbox

**Cause**: The COS-mounted directory is empty; `openclaw.json` was not uploaded.

**Solution**: Upload `openclaw.json` to the `openclaw-config/` directory in the COS bucket.

### Q3: favicon 404

**Cause**: The official OpenClaw image references `./favicon.svg` under the `/__openclaw__/` path, but the actual favicon is at `/favicon.svg`. Without nginx, there's no rewrite.

**Note**: This is a known issue that only affects the browser tab icon and does not impact Dashboard functionality. To display the icon correctly, remove the `/__openclaw__` path prefix.

### Q4: WebSocket connection intercepted

**Solution**: You must access via `localproxy` local proxy. Do not access the AGS external URL directly.

### Q5: How to update OpenClaw version

```bash
cd openclaw-cookbook
make push   # Re-pulls ghcr.io/openclaw/openclaw:latest and pushes
```

Then update the tool image in the AGS console with the new hash tag.

---

## TODO

- [ ] Monitoring solution
- [ ] Session and memory integrity verification after pause/resume
- [ ] Performance benchmarks for pause/resume duration
