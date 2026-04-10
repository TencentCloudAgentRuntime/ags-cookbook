# Multi-OpenClaw — 多用户沙箱路由中心

将多个用户的浏览器请求路由到一个中心服务，中心服务通过 WebSocket 代理与各自独立的 OpenClaw 沙箱通信。

## 架构总览

```
┌──────────┐                                         ┌──────────────┐
│ 浏览器 A │──┐                                  ┌──▶│ OpenClaw     │
│ (alice)  │  │   ┌────────────────────────────┐ │   │ 沙箱 A       │
└──────────┘  │   │                            │ │   └──────────────┘
              ├──▶│   Multi-OpenClaw           │─┤
┌──────────┐  │   │   中心路由服务              │ │   ┌──────────────┐
│ 浏览器 B │──┤   │                            │ └──▶│ OpenClaw     │
│ (bob)    │  │   │  ┌────────────────────┐    │     │ 沙箱 B       │
└──────────┘  │   │  │ SandboxManager     │    │     └──────────────┘
              │   │  │                    │    │
┌──────────┐  │   │  │ userId → proxy Map │    │     ┌──────────────┐
│ 浏览器 C │──┘   │  │ alice → proxy-A    │    │────▶│ OpenClaw     │
│ (carol)  │      │  │ bob   → proxy-B    │    │     │ 沙箱 C       │
└──────────┘      │  │ carol → proxy-C    │    │     └──────────────┘
                  │  └────────────────────┘    │
                  └────────────────────────────┘
```

## 核心路由机制

### 1. HTTP 代理路由

```
浏览器请求: GET /sandbox/:userId/foo/bar
                         ▼
Express 路由: app.use('/sandbox/:userId', ...)
                         ▼
SandboxManager.proxyHttpRequest(userId, req, res)
                         ▼
从 Map<userId, UserSandbox> 取出对应 proxy
                         ▼
proxy.web(req, res)  ──▶  https://<sandbox-host>/foo/bar
                           (自动注入 X-Access-Token)
```

### 2. WebSocket 代理路由（关键）

WebSocket 的 upgrade 请求不经过 Express 路由中间件，必须在 HTTP server 级别手动处理：

```
浏览器: new WebSocket('ws://host/sandbox/alice/')
                         ▼
server.on('upgrade', (req, socket, head) => ...)
                         ▼
从 URL 解析: /sandbox/:userId/... → userId = 'alice'
                         ▼
SandboxManager.handleWsUpgrade(req, socket, head)
                         ▼
从 Map 取出 alice 的 proxy 实例
                         ▼
重写 URL: /sandbox/alice/ → /
                         ▼
proxy.ws(req, socket, head)  ──▶  wss://<sandbox-a-host>/
                                   (注入 X-Access-Token)
```

### 3. OpenClaw WebSocket 协议流程

```
浏览器                    中心服务                     OpenClaw 沙箱
  │                         │                            │
  │  ws://host/sandbox/     │                            │
  │  alice/                 │                            │
  │────── WS upgrade ──────▶│                            │
  │                         │── proxy.ws() ─────────────▶│
  │                         │   (+X-Access-Token)        │
  │                         │◀── WS established ────────│
  │◀── WS established ─────│                            │
  │                         │                            │
  │  { event:               │                            │
  │    "connect.challenge" }│                            │
  │◀────────────────────────│◀───────────────────────────│
  │                         │                            │
  │  { method: "connect",   │                            │
  │    auth: { token } }    │                            │
  │────────────────────────▶│───────────────────────────▶│
  │                         │                            │
  │  { ok: true }           │                            │
  │◀────────────────────────│◀───────────────────────────│
  │                         │                            │
  │  { method: "chat.send", │                            │
  │    message: "..." }     │                            │
  │────────────────────────▶│───────────────────────────▶│
  │                         │                            │
  │  { event: "agent",      │                            │
  │    stream: "assistant", │                            │
  │    delta: "..." }       │                            │
  │◀────────────────────────│◀───────────────────────────│
  │        ...              │          ...               │
```

## 数据流向

```
┌─────────────────────────────────────────────────────────┐
│                    中心服务 (server.ts)                   │
│                                                         │
│  ┌──────────────────┐    ┌──────────────────────────┐  │
│  │   管理员界面 (/)   │    │  SandboxManager          │  │
│  │                  │    │                          │  │
│  │  分配: userId    │───▶│  assignments.json        │  │
│  │      + sandboxId │    │  (持久化 userId→sandboxId) │  │
│  │                  │    │                          │  │
│  │  SSE 实时状态    │◀───│  Map<userId, UserSandbox> │  │
│  └──────────────────┘    │  ├─ proxy 实例            │  │
│                          │  ├─ accessToken           │  │
│  ┌──────────────────┐    │  └─ remoteHost            │  │
│  │ 用户聊天界面     │    │                          │  │
│  │ /chat?user=alice │    │  connectUser(userId)      │  │
│  │                  │───▶│  1. acquireToken()        │  │
│  │  WebSocket      │    │  2. waitForOpenClaw()     │  │
│  │  /sandbox/alice/ │    │  3. createProxyForUser()  │  │
│  │                  │    │     └─ new httpProxy()    │  │
│  │  SSE 状态通知   │◀───│                          │  │
│  └──────────────────┘    └──────────────────────────┘  │
│                                                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Express 路由层                                    │  │
│  │                                                    │  │
│  │  /sandbox/:userId/*  → proxyHttpRequest(userId)   │  │
│  │                                                    │  │
│  │  server.on('upgrade')                              │  │
│  │    → 解析 URL → handleWsUpgrade(userId)            │  │
│  │    → proxy.ws(req, socket, head)                   │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

## 快速开始

### 前置条件

- 已在 AGS 中创建好沙箱工具（参考 `../openclaw-cookbook/localproxy/create-tool.ts`）
- 已启动若干沙箱实例（通过 localproxy 或 AGS 控制台）
- 获取了各沙箱的 Instance ID

### 安装和运行

```bash
# 方式一：使用 Makefile（推荐）
make setup    # 安装依赖 + 创建 .env
make dev      # 开发模式（文件变更自动重启）
make start    # 生产模式

# 方式二：手动
pnpm install
cp .env.example .env
# 编辑 .env，填入 API 密钥和 OpenClaw Token
pnpm dev
```

### 使用流程

1. **管理员**打开 `http://localhost:3001`
2. 在管理界面输入用户 ID 和沙箱 Instance ID，点击「分配」
3. 点击「连接」，中心服务会为该用户建立到沙箱的代理通道
4. **用户**通过 `http://localhost:3001/chat?user=alice` 打开聊天
5. 聊天页面自动连接到分配给该用户的沙箱，开始对话

## API 参考

### 管理员 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 管理界面 |
| GET | `/api/admin/status` | 获取所有分配和状态 |
| GET | `/api/admin/events` | SSE 实时推送管理状态 |
| POST | `/api/admin/assign` | 分配用户到沙箱 `{userId, sandboxId}` |
| POST | `/api/admin/unassign` | 解绑用户 `{userId}` |

### 用户 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/chat?user=:userId` | 用户聊天页面 |
| GET | `/api/user/:userId/status` | 获取用户沙箱状态 |
| GET | `/api/user/:userId/chat-config` | 获取聊天配置（wsUrl + openclawToken） |
| GET | `/api/user/:userId/events` | SSE 推送该用户状态 |
| POST | `/api/user/:userId/connect` | 建立到用户沙箱的代理 |
| POST | `/api/user/:userId/disconnect` | 断开用户沙箱代理 |

### 代理路由

| 路径 | 说明 |
|------|------|
| `/sandbox/:userId/*` | HTTP 代理（自动路由到对应沙箱） |
| `ws://host/sandbox/:userId/` | WebSocket 代理（upgrade 路由） |

## 关键设计决策

### 为什么每个用户一个 http-proxy 实例？

每个 AGS 沙箱实例有独立的 `remoteHost` 和 `accessToken`。`http-proxy` 的 `target` 和 `proxyReq` 头注入在创建时绑定，所以需要为每个沙箱创建独立的 proxy 实例。

### WebSocket upgrade 为什么不经过 Express？

Node.js 的 HTTP server 收到 `Connection: Upgrade` 请求时，直接触发 `server.on('upgrade')` 事件，不会走 Express 的路由/中间件链。因此必须在 server 级别手动解析 URL、提取 userId、查找对应 proxy、调用 `proxy.ws()`。

### 数据持久化

用户-沙箱分配关系保存在 `data/assignments.json` 文件中，服务重启后自动加载。运行时的 proxy 实例和连接状态不持久化，需要重新建立。

### OpenClaw Token 安全获取

聊天页面不在 HTML 中硬编码 Token。页面加载后通过 `/api/user/:userId/chat-config` API 动态获取 OpenClaw Token 和 WebSocket 代理 URL，避免敏感凭证暴露在页面源码中。

## 目录结构

```
examples/multi-openclaw/
├── server.ts              # 核心服务（SandboxManager + 路由 + 内嵌 HTML 界面）
├── package.json           # 依赖配置
├── tsconfig.json          # TypeScript 配置
├── Makefile               # 构建和运行命令
├── .env.example           # 环境变量模板
├── README.md              # 本文档
└── data/
    └── assignments.json   # 用户-沙箱分配持久化（JSON 数组）
```

## 环境变量

| 变量 | 必填 | 说明 |
|------|------|------|
| `TENCENTCLOUD_SECRET_ID` | ✅ | 腾讯云 API 密钥 ID |
| `TENCENTCLOUD_SECRET_KEY` | ✅ | 腾讯云 API 密钥 Key |
| `TENCENTCLOUD_REGION` | | 区域，默认 `ap-shanghai` |
| `PORT` | | 服务端口，默认 `3001` |
| `DATA_DIR` | | 数据目录，默认 `./data` |

> **注意**: OpenClaw Gateway Token 由用户在聊天界面中手动输入，不再通过环境变量配置。Token 值应与沙箱中 `openclaw.json` 的 `gateway.auth.token` 一致。用户输入后可选择"记住 Token"，会保存到浏览器 localStorage 中。
