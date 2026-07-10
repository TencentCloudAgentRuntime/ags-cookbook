# LocalProxy

Local management tool for Hermes Agent sandboxes. Create, connect, pause, and resume sandboxes via a browser UI, with the in-sandbox Hermes Dashboard reverse-proxied to localhost.

---

## Architecture

```
pnpm dev / pnpm start
  +- tsx server.ts
       +- Express :3001
            +-- GET /_admin              Management UI (embedded HTML + CSS + JS, no build step)
            +-- GET /_admin/api/status   Current state snapshot
            +-- GET /_admin/api/events   SSE real-time push
            +-- POST /_admin/api/start   Create new sandbox
            +-- POST /_admin/api/stop    Stop and destroy sandbox
            +-- POST /_admin/api/pause   Pause sandbox
            +-- POST /_admin/api/resume  Resume sandbox
            +-- POST /_admin/api/connect Connect to existing sandbox
            +-- /* (catch-all)           Reverse proxy to Hermes Dashboard (when running)

http://localhost:3001/  ->  Hermes Dashboard (when sandbox is running)
http://localhost:3001/  ->  Redirects to /_admin (when sandbox is not running)
```

The entire project is a **single file** (`server.ts`) -- HTML, CSS, and client-side JS are all embedded. No build step needed; just run `tsx server.ts`.

---

## Quick Start

### Prerequisites

- Node.js >= 20
- pnpm
- Tencent Cloud API credentials (SecretId / SecretKey)

### Install

```bash
pnpm install
```

### Configure

Copy and edit `.env`:

```bash
cp .env.example .env
```

```env
# Tencent Cloud API credentials (required)
TENCENTCLOUD_SECRET_ID=your_secret_id_here
TENCENTCLOUD_SECRET_KEY=your_secret_key_here
TENCENTCLOUD_REGION=ap-guangzhou

# AGS configuration (required)
TOOL_NAME=my-hermes-agent

# CFS mount (optional, uses tool default mount if not set)
MOUNT_NAME=cfs
```

### Run

```bash
# Development mode (auto-restart on file changes)
pnpm dev

# Production mode
pnpm start
```

Then open **http://localhost:3001/_admin**.

---

## Usage

### Create a New Sandbox

1. Open http://localhost:3001/_admin
2. (Optional) Enter a CFS sub-path in the **Mount subpath** field
3. Click **Start Sandbox**
4. State transitions: `Idle -> Starting -> Connecting -> Running`
5. Once Running, click **Open Dashboard** to access Hermes Dashboard (at `http://localhost:3001/`)
6. Click **Stop Sandbox** to stop and destroy the sandbox

### Connect to an Existing Sandbox

1. Enter the Sandbox ID in the **Connect to existing sandbox** field
2. Click **Connect** (or press Enter)
3. Once connected, the state becomes Running
4. Stopping only closes the local proxy -- the remote sandbox is **not destroyed**

### Pause / Resume

- While Running, click **Pause** to pause the sandbox (frees compute resources, preserves state)
- While Paused, click **Resume** to resume the sandbox

---

## Ports

| Port | Purpose |
|------|---------|
| 3001 | Management UI (`/_admin`) + API (`/_admin/api`) + Hermes Dashboard proxy (all other paths) |

---

## State Machine

```
idle --start--> starting --> connecting --> running --pause--> pausing --> paused
 ^                                             |                            |
 +------------------ stop <--------------------+                            |
 ^                                                                          |
 +------------------ stop <-------------------------------------------------+

idle --connect--> connecting --> running

paused --resume--> resuming --> running
```

| State | Meaning |
|-------|---------|
| `idle` | No sandbox, waiting for action |
| `starting` | Creating sandbox |
| `connecting` | Sandbox created/specified, waiting for Hermes to be ready |
| `running` | Proxy started, service available |
| `pausing` | Pausing sandbox |
| `paused` | Sandbox paused |
| `resuming` | Resuming sandbox |
| `stopping` | Closing proxy and (depending on mode) destroying sandbox |

---

## Project Structure

```
localproxy/
+-- .env.example     # Environment variable template
+-- .gitignore
+-- README.md        # This file (English)
+-- README_zh.md     # Chinese version
+-- package.json
+-- pnpm-lock.yaml
+-- create-tool.ts   # Script to create sandbox tool via AGS SDK
+-- server.ts        # All logic: Express server, state machine, SSE, embedded UI
```

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `tencentcloud-sdk-nodejs-ags` | Tencent Cloud AGS SDK (create/stop/pause/resume sandbox) |
| `express` | HTTP server |
| `cors` | CORS headers |
| `dotenv` | Environment variable loading |
| `http-proxy` | Reverse proxy |
| `tsx` | Run TypeScript directly, no compilation needed |
