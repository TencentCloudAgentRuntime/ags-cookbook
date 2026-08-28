# LocalProxy

OpenClaw 沙箱本地管理工具。通过浏览器 UI 一键创建/连接/暂停/恢复沙箱，并将沙箱内的 OpenClaw 服务代理到本地。

---

## 架构

```
pnpm dev / pnpm start
  └─ tsx server.ts
       └─ Express :3001
            ├── GET /              管理界面（内嵌 HTML + CSS + JS，无构建步骤）
            ├── GET /api/status    当前状态快照
            ├── GET /api/events    SSE 实时推送
            ├── POST /api/start    创建新沙箱
            ├── POST /api/stop     停止并销毁沙箱
            ├── POST /api/pause    暂停沙箱
            ├── POST /api/resume   恢复沙箱
            └── POST /api/connect  连接已有沙箱

http://localhost:3001/sandbox/  →  反向代理到沙箱内 OpenClaw（仅 running 时可用）
```

整个工程是**单文件**（`server.ts`）——HTML、CSS、客户端 JS 全部内嵌，无需构建步骤，`tsx server.ts` 直接运行。

---

## 快速开始

### 前置条件

- Node.js >= 20
- pnpm
- 腾讯云 API 密钥（SecretId / SecretKey）

### 安装

```bash
pnpm install
```

### 配置

复制并编辑 `.env`：

```bash
cp .env.example .env
```

```env
# 腾讯云 API 凭据（必须）
TENCENTCLOUD_SECRET_ID=your_secret_id_here
TENCENTCLOUD_SECRET_KEY=your_secret_key_here
TENCENTCLOUD_REGION=ap-shanghai

# AGS 配置（必须）
TOOL_NAME=my-openclaw-official

# COS 挂载（可选，不填则使用工具配置的默认挂载）
MOUNT_NAME=cos
```

### 运行

```bash
# 开发模式（文件变更自动重启）
pnpm dev

# 生产模式
pnpm start
```

启动后访问 **http://localhost:3001**。

---

## 使用流程

### 创建新沙箱

1. 打开 http://localhost:3001
2. （可选）在 **Mount subpath** 输入框填写 COS 子路径
3. 点击 **Start Sandbox**
4. 状态流转：`Idle → Starting → Connecting → Running`
5. Running 后，点击 **Open Dashboard** 访问 OpenClaw（地址为 `http://localhost:3001/sandbox/__openclaw__`）
6. 点击 **Stop Sandbox** 停止并销毁沙箱

### 连接已有沙箱

1. 在 **Connect to existing sandbox** 输入框中填入 Sandbox ID
2. 点击 **Connect**（或按 Enter）
3. 连接成功后进入 Running 状态
4. Stop 时仅关闭本地代理，**不销毁**远端沙箱

### 暂停 / 恢复

- Running 状态下点击 **Pause** 暂停沙箱（释放计算资源，保留状态）
- Paused 状态下点击 **Resume** 恢复沙箱

---

## 端口说明

| 端口 | 用途 |
|------|------|
| 3001 | 管理界面 + API + OpenClaw 反向代理（`/sandbox/` 路径） |

---

## 状态机

```
idle ──start──▶ starting ──▶ connecting ──▶ running ──pause──▶ pausing ──▶ paused
 ▲                                             │                            │
 └──────────────── stop ◀──────────────────────┘                            │
 ▲                                                                          │
 └──────────────── stop ◀──────────────────────────────────────────────────┘

idle ──connect──▶ connecting ──▶ running

paused ──resume──▶ resuming ──▶ running
```

| 状态 | 含义 |
|------|------|
| `idle` | 无沙箱，等待操作 |
| `starting` | 正在创建沙箱 |
| `connecting` | 沙箱已创建/指定，等待 OpenClaw 就绪 |
| `running` | 代理已启动，服务可用 |
| `pausing` | 正在暂停沙箱 |
| `paused` | 沙箱已暂停 |
| `resuming` | 正在恢复沙箱 |
| `stopping` | 正在关闭代理并（视模式）销毁沙箱 |

---

## 项目结构

```
localproxy/
├── .env.example     # 环境变量模板
├── .gitignore
├── README.md        # 英文文档
├── README_zh.md     # 中文文档（本文件）
├── package.json
├── pnpm-lock.yaml
└── server.ts        # 全部逻辑：Express 服务、状态机、SSE、内嵌 UI
```

---

## 依赖

| 包 | 用途 |
|----|------|
| `tencentcloud-sdk-nodejs-ags` | 腾讯云 AGS SDK（创建/停止/暂停/恢复沙箱） |
| `express` | HTTP 服务器 |
| `cors` | 跨域头 |
| `dotenv` | 环境变量加载 |
| `http-proxy` | 反向代理 |
| `tsx` | 直接运行 TypeScript，无需编译 |
