# Hermes Agent Sandbox Guide

Run [Hermes Agent](https://github.com/NousResearch/hermes-agent) on Tencent Cloud AGS using the official `nousresearch/hermes-agent` image. Hermes uses default configuration on first boot — no config file upload needed.

---

## Table of Contents

1. [Architecture](#architecture)
2. [Prerequisites](#prerequisites)
3. [Build and Push Image](#build-and-push-image)
4. [Create Sandbox Tool](#create-sandbox-tool)
5. [Launch Sandbox and Access Dashboard](#launch-sandbox-and-access-dashboard)
6. [Persistent Storage](#persistent-storage)
7. [Logs and Debugging](#logs-and-debugging)
8. [FAQ](#faq)

---

## Architecture

```
Browser
  |
  +- http://localhost:3001/_admin     <-- localproxy management UI (create/connect/stop sandbox)
  |
  +- http://localhost:3001/           <-- reverse proxy to Hermes Dashboard (when sandbox is running)
       |  Automatically injects X-Access-Token header
       v
  AGS Auth Gateway (<region>.tencentags.com)
       |  Validates X-Access-Token
       v
  Hermes Dashboard:9119 (--host 0.0.0.0, --insecure)
```

**Container processes:**

| Process | Port | Purpose |
|---------|------|---------|
| `envd` | 49983 | AGS sandbox management daemon (health probe, command execution) |
| `hermes dashboard` | 9119 | Hermes Dashboard, `--host 0.0.0.0` listens on all network interfaces |
| `hermes gateway` | 8642 | Hermes Gateway (agent execution, hooks) |

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

## Build and Push Image

### Directory Structure

```
hermes-cookbook/
+-- .env.example        # Environment variable template (copied to localproxy/.env on make setup)
+-- .gitignore
+-- Dockerfile          # FROM official image, COPY --from AGS envd image, custom entrypoint
+-- Makefile
+-- README.md           # This file (English)
+-- README_zh.md        # Chinese version
+-- localproxy/         # Local management tool (create/connect/stop sandbox + reverse proxy)
    +-- .env.example    # Environment variable template
    +-- .gitignore
    +-- README.md       # LocalProxy documentation (English)
    +-- README_zh.md    # LocalProxy documentation (Chinese)
    +-- package.json
    +-- pnpm-lock.yaml
    +-- create-tool.ts  # Script to create sandbox tool via AGS SDK
    +-- server.ts       # Main service: Express + state machine + SSE + embedded Web UI
```

### Build and Push

> **Important**: The AGS runtime is `linux/amd64`. You must build an amd64 image. The Makefile defaults to `--platform linux/amd64`, which cross-compiles automatically on Apple Silicon Macs.

> The Makefile defaults to `podman`. Docker users can override via `make push CONTAINER_ENGINE=docker`.

```bash
cd hermes-cookbook

make setup   # Creates localproxy/.env from template

# Set DOCKER_REGISTRY in localproxy/.env
# DOCKER_REGISTRY=ccr.ccs.tencentyun.com/your-namespace

# Build and push (pushes both latest and hash tags)
make push
# Example output:
# Pushed: ccr.ccs.tencentyun.com/your-namespace/sandbox-hermes:latest
# Pushed: ccr.ccs.tencentyun.com/your-namespace/sandbox-hermes:73f17f45ddf3
```

---

## Create Sandbox Tool

### Option A: Create via CLI

Instead of filling in the console manually, you can create the sandbox tool with a single command. First, uncomment and fill in the `Create sandbox tool` section in `localproxy/.env`:

| Variable | Required | Format / Example | Description |
|----------|----------|------------------|-------------|
| `IMAGE_ADDRESS` | Yes | `ccr.ccs.tencentyun.com/<namespace>/<image>:<tag>` | Full container image address including tag |
| `IMAGE_REGISTRY_TYPE` | No | `personal` (default) or `enterprise` | `personal` = CCR, `enterprise` = TCR |
| `CFS_FILE_SYSTEM_ID` | Yes | `cfs-xxxxxxxx` | CFS file system ID (find in [CFS console](https://console.cloud.tencent.com/cfs)) |
| `CFS_PATH` | No | `/` (default) or `/<sub-path>` | Sub-path inside CFS to mount. Default `/` |
| `ROLE_ARN` | Yes | `qcs::cam::uin/<owner-uin>:roleName/<role-name>` | CAM role ARN that AGS assumes to pull the image. The role must have CCR pull permissions. [Manage roles](https://console.cloud.tencent.com/cam/role) |

Then run:

```bash
make create_sandbox_tool
```

This calls `CreateSandboxTool` via the AGS SDK with all the parameters documented below (startup command, probe, resources, CFS mount, etc.) pre-configured.

### Option B: Create via AGS Console

When creating a sandbox tool in the [AGS Console](https://console.cloud.tencent.com/ags), fill in the following:

### Basic Configuration

> **Important**: AGS ignores `CMD`/`ENTRYPOINT` in the image when running sandboxes. You must manually set the startup command and parameters in the console.

| Field | Value |
|-------|-------|
| Tool Name | `my-hermes-agent` |
| Tool Type | Custom Image |
| Image Address | `ccr.ccs.tencentyun.com/your-namespace/sandbox-hermes:<hash>` |
| Image Registry Type | Personal |
| Startup Command | `/entrypoint.sh` |
| Startup Parameters | (none) |
| CPU | 4 cores |
| Memory | 8 GiB |
| Probe Path | `/health` |
| Probe Port | `49983` |
| Ready Timeout | `30000` ms |
| Probe Interval | `3000` ms |
| Failure Threshold | `100` |
| Network Policy | Public |

### Exposed Ports

All three ports must be configured in the AGS console (click "Add" to create port entries):

| Port Name | Port | Protocol |
|-----------|------|----------|
| `dashboard` | `9119` | TCP |
| `gateway` | `8642` | TCP |
| `envd` | `49983` | TCP |

> **Important**: If ports are not explicitly exposed, the AGS gateway will return 500 for any request to those ports. The Hermes Dashboard (9119), Gateway (8642), and the envd daemon (49983, used for health probing) must all be exposed.

### Environment Variables

The following environment variables must be set in the AGS console (click "Add" to create entries):

| Variable | Value | Description |
|----------|-------|-------------|
| `PYTHONUNBUFFERED` | `1` | Disable Python output buffering |
| `HERMES_WEB_DIST` | `/opt/hermes/hermes_cli/web_dist` | Dashboard static assets path |
| `PLAYWRIGHT_BROWSERS_PATH` | `/opt/hermes/.playwright` | Playwright browser binaries path |
| `TERM` | `xterm` | Terminal type |
| `SHLVL` | `1` | Shell level |
| `HERMES_HOME` | `/opt/data` | Hermes data directory (must match CFS mount path) |
| `PATH` | `/opt/data/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin` | System PATH including Hermes local bin |
| `GATEWAY_ALLOW_ALL_USERS` | `true` | Allow all users to access the Gateway (required for AGS, otherwise all requests are denied) |

> **Important**: `HERMES_HOME` must match the CFS mount path (`/opt/data`). Without these environment variables, Hermes may fail to start or the Dashboard may not render correctly.

### Storage Mount Configuration

| Mount Item | CFS ID | Container Mount Path |
|------------|--------|---------------------|
| Hermes Data | `cfs-xxxxxxxx` | `/opt/data` |

> **Note**: CFS is mounted at `/opt/data`, which is the default `HERMES_HOME`. Hermes reads/writes all runtime data to this directory. CFS is a POSIX-compatible network filesystem — it supports all standard file operations including SQLite, file locking, symlinks, etc. On first boot, Hermes will automatically copy default config files (`.env`, `config.yaml`, `SOUL.md`) from the install directory.

> **Note**: After updating the tool image, new sandboxes may return 502 for about 3 minutes. This is normal -- just retry later.

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
TENCENTCLOUD_REGION=ap-guangzhou          # AGS region

# AGS Configuration (required)
TOOL_NAME=my-hermes-agent               # Sandbox tool name created in AGS console

# CFS Mount (optional, uses tool default mount if not set)
MOUNT_NAME=cfs                           # Mount item name
```

Install dependencies and start:

```bash
# Run from the hermes-cookbook root directory
make setup   # Install localproxy dependencies
make run     # Start localproxy management service
```

### Usage Flow

1. Open the management UI at **http://localhost:3001/_admin**
2. Click **Start Sandbox** to create a new sandbox (or enter an existing sandbox ID and click **Connect**)
3. Wait for state transitions: `Idle -> Starting -> Connecting -> Running`
4. Once Running, click **Open Dashboard** to access Hermes Dashboard (at `http://localhost:3001/`)

---

## Persistent Storage

Hermes uses the `HERMES_HOME` environment variable to determine where config and runtime data are stored. The default is:

```
HERMES_HOME=/opt/data
```

Simply mount the CFS file system to `/opt/data` in the container for persistence. CFS is a POSIX-compatible network filesystem — it behaves like a normal local filesystem and supports all standard operations (including SQLite, file locking, symlinks, etc.).

Hermes reads/writes `/opt/data/`, which contains:

| Path | Content |
|------|---------|
| `/opt/data/.env` | Environment config (auto-created on first boot) |
| `/opt/data/config.yaml` | CLI config (auto-created on first boot) |
| `/opt/data/SOUL.md` | Agent personality definition (auto-created on first boot) |
| `/opt/data/sessions/` | Session data |
| `/opt/data/skills/` | Skills data |
| `/opt/data/memories/` | Memory data |
| `/opt/data/logs/` | Log files |
| `/opt/data/cron/` | Cron tasks |
| `/opt/data/hooks/` | Hooks |
| `/opt/data/workspace/` | Workspace files |

> **Note**: Hermes does NOT require any pre-uploaded config files. On first boot, the entrypoint script automatically copies default configs from the install directory to `HERMES_HOME`.

To isolate by user/session, set `CFS_PATH` to a sub-path (e.g. `/user-123`) when creating the sandbox tool, or enter a sub-path in the **Mount subpath** input field of the localproxy management UI:

```
CFS mount effect:
cfs-xxxxxxxx:/user-123/    -> /opt/data
```

---

## Logs and Debugging

Log in to the sandbox using [ags-cli](https://github.com/TencentCloudAgentRuntime/ags-cli):

```bash
ags instance login <sandbox_id> --user root
```

Common debugging commands:

```bash
# Check process status
ps aux | grep -E 'hermes|envd' | grep -v grep

# Hermes Dashboard logs
cat /logs/dashboard.log

# Hermes Gateway logs
cat /logs/gateway.log

# Skills sync logs
cat /logs/skills_sync.log

# envd daemon logs
cat /logs/envd.log
```

---

## FAQ

### Q1: Dashboard shows connection error

**Cause**: Hermes Dashboard may not have started properly, or the `--host 0.0.0.0` flag is missing.

**Solution**: Log into the sandbox and check `/logs/dashboard.log` for errors.

### Q2: WebSocket connection intercepted

**Solution**: You must access via `localproxy` local proxy. Do not access the AGS external URL directly.

### Q3: How to update Hermes version

Update the base image tag in the `Dockerfile`:

```dockerfile
FROM nousresearch/hermes-agent:v2026.4.23
```

Then rebuild and push:

```bash
cd hermes-cookbook
make push
```

Then update the tool image in the AGS console with the new hash tag.

