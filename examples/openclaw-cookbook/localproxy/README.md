# LocalProxy

Local management tool for OpenClaw sandboxes. Create, connect, pause, and resume sandboxes via a browser UI, with the in-sandbox OpenClaw service reverse-proxied to localhost.

---

## Architecture

```
pnpm dev / pnpm start
  └─ tsx server.ts
       └─ Express :3001
            ├── GET /              Management UI (embedded HTML + CSS + JS, no build step)
            ├── GET /api/status    Current state snapshot
            ├── GET /api/events    SSE real-time push
            ├── POST /api/start    Create new sandbox
            ├── POST /api/stop     Stop and destroy sandbox
            ├── POST /api/pause    Pause sandbox
            ├── POST /api/resume   Resume sandbox
            └── POST /api/connect  Connect to existing sandbox

http://localhost:3001/sandbox/  →  Reverse proxy to in-sandbox OpenClaw (available only when running)
```

The entire project is a **single file** (`server.ts`) — HTML, CSS, and client-side JS are all embedded. No build step needed; just run `tsx server.ts`.

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
TENCENTCLOUD_REGION=ap-shanghai

# AGS configuration (required)
TOOL_NAME=my-openclaw-official

# COS mount (optional, uses tool default mount if not set)
MOUNT_NAME=cos
```

### Run

```bash
# Development mode (auto-restart on file changes)
pnpm dev

# Production mode
pnpm start
```

Then open **http://localhost:3001**.

---

## Usage

### Create a New Sandbox

1. Open http://localhost:3001
2. (Optional) Enter a COS sub-path in the **Mount subpath** field
3. Click **Start Sandbox**
4. State transitions: `Idle → Starting → Connecting → Running`
5. Once Running, click **Open Dashboard** to access OpenClaw (at `http://localhost:3001/sandbox/__openclaw__`)
6. Click **Stop Sandbox** to stop and destroy the sandbox

### Connect to an Existing Sandbox

1. Enter the Sandbox ID in the **Connect to existing sandbox** field
2. Click **Connect** (or press Enter)
3. Once connected, the state becomes Running
4. Stopping only closes the local proxy — the remote sandbox is **not destroyed**

### Pause / Resume

- While Running, click **Pause** to pause the sandbox (frees compute resources, preserves state)
- While Paused, click **Resume** to resume the sandbox

---

## Ports

| Port | Purpose |
|------|---------|
| 3001 | Management UI + API + OpenClaw reverse proxy (`/sandbox/` path) |

---

## State Machine

```
idle ──start──▶ starting ──▶ connecting ──▶ running ──pause──▶ pausing ──▶ paused
 ▲                                             │                            │
 └──────────────── stop ◀──────────────────────┘                            │
 ▲                                                                          │
 └──────────────── stop ◀──────────────────────────────────────────────────┘

idle ──connect──▶ connecting ──▶ running

paused ──resume──▶ resuming ──▶ running
```

| State | Meaning |
|-------|---------|
| `idle` | No sandbox, waiting for action |
| `starting` | Creating sandbox |
| `connecting` | Sandbox created/specified, waiting for OpenClaw to be ready |
| `running` | Proxy started, service available |
| `pausing` | Pausing sandbox |
| `paused` | Sandbox paused |
| `resuming` | Resuming sandbox |
| `stopping` | Closing proxy and (depending on mode) destroying sandbox |

---

## Project Structure

```
localproxy/
├── .env.example     # Environment variable template
├── .gitignore
├── README.md        # This file (English)
├── README_zh.md     # Chinese version
├── package.json
├── pnpm-lock.yaml
└── server.ts        # All logic: Express server, state machine, SSE, embedded UI
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
