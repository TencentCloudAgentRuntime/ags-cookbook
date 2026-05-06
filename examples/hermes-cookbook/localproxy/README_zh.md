# LocalProxy

Hermes Agent 沙箱本地管理工具。通过浏览器界面创建、连接、暂停和恢复沙箱，并将沙箱内的 Hermes Dashboard 反向代理到本地。

---

## 架构

```
pnpm dev / pnpm start
  +- tsx server.ts
       +- Express :3001
            +-- GET /_admin              管理界面（内嵌 HTML + CSS + JS，无需构建）
            +-- GET /_admin/api/status   当前状态快照
            +-- GET /_admin/api/events   SSE 实时推送
            +-- POST /_admin/api/start   创建新沙箱
            +-- POST /_admin/api/stop    停止并销毁沙箱
            +-- POST /_admin/api/pause   暂停沙箱
            +-- POST /_admin/api/resume  恢复沙箱
            +-- POST /_admin/api/connect 连接已有沙箱
            +-- /* (兜底)                反向代理到 Hermes Dashboard（运行时）

http://localhost:3001/  ->  Hermes Dashboard（沙箱运行时）
http://localhost:3001/  ->  重定向到 /_admin（沙箱未运行时）
```

整个项目是一个**单文件**（`server.ts`）—— HTML、CSS 和客户端 JS 都内嵌其中。无需构建步骤，直接运行 `tsx server.ts` 即可。

---

## 快速开始

### 前置条件

- Node.js >= 20
- pnpm
- 腾讯云 API 凭据（SecretId / SecretKey）

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
TENCENTCLOUD_REGION=ap-guangzhou

# AGS 配置（必须）
TOOL_NAME=my-hermes-agent

# CFS 挂载（可选，不填则使用工具配置的默认挂载）
MOUNT_NAME=cfs
```

### 运行

```bash
# 开发模式（文件修改后自动重启）
pnpm dev

# 生产模式
pnpm start
```

然后打开 **http://localhost:3001/_admin**。

---

## 使用方式

### 创建新沙箱

1. 打开 http://localhost:3001/_admin
2. （可选）在 **Mount subpath** 输入框中填写 CFS 子路径
3. 点击 **Start Sandbox**
4. 状态流转：`Idle -> Starting -> Connecting -> Running`
5. Running 后，点击 **Open Dashboard** 访问 Hermes Dashboard（地址为 `http://localhost:3001/`）
6. 点击 **Stop Sandbox** 停止并销毁沙箱

### 连接已有沙箱

1. 在 **Connect to existing sandbox** 输入框中填写沙箱 ID
2. 点击 **Connect**（或按回车）
3. 连接成功后状态变为 Running
4. 停止时仅关闭本地代理——远程沙箱**不会被销毁**

### 暂停 / 恢复

- Running 状态下点击 **Pause** 暂停沙箱（释放计算资源，保留状态）
- Paused 状态下点击 **Resume** 恢复沙箱

---

## 端口

| 端口 | 用途 |
|------|------|
| 3001 | 管理界面（`/_admin`）+ API（`/_admin/api`）+ Hermes Dashboard 代理（所有其他路径） |

---

## 状态机

```
idle --start--> starting --> connecting --> running --pause--> pausing --> paused
 ^                                             |                            |
 +------------------ stop <--------------------+                            |
 ^                                                                          |
 +------------------ stop <-------------------------------------------------+

idle --connect--> connecting --> running

paused --resume--> resuming --> running
```

| 状态 | 含义 |
|------|------|
| `idle` | 无沙箱，等待操作 |
| `starting` | 创建沙箱中 |
| `connecting` | 沙箱已创建/指定，等待 Hermes 就绪 |
| `running` | 代理已启动，服务可用 |
| `pausing` | 暂停沙箱中 |
| `paused` | 沙箱已暂停 |
| `resuming` | 恢复沙箱中 |
| `stopping` | 关闭代理并（根据模式）销毁沙箱 |

---

## 项目结构

```
localproxy/
+-- .env.example     # 环境变量模板
+-- .gitignore
+-- README.md        # 英文文档
+-- README_zh.md     # 中文文档（本文件）
+-- package.json
+-- pnpm-lock.yaml
+-- create-tool.ts   # 通过 AGS SDK 创建沙箱工具的脚本
+-- server.ts        # 所有逻辑：Express 服务器、状态机、SSE、内嵌 UI
```

---

## 依赖

| 包 | 用途 |
|----|------|
| `tencentcloud-sdk-nodejs-ags` | 腾讯云 AGS SDK（创建/停止/暂停/恢复沙箱） |
| `express` | HTTP 服务器 |
| `cors` | CORS 头 |
| `dotenv` | 环境变量加载 |
| `http-proxy` | 反向代理 |
| `tsx` | 直接运行 TypeScript，无需编译 |
