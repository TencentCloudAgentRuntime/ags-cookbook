# Hermes Agent 沙箱使用指南

基于官方 `nousresearch/hermes-agent` 镜像，在腾讯云 AGS 中运行 Hermes Agent。Hermes 首次启动时自动使用默认配置，无需预上传配置文件。

---

## 目录

1. [架构概述](#架构概述)
2. [前置准备](#前置准备)
3. [构建并推送镜像](#构建并推送镜像)
4. [创建沙箱工具](#创建沙箱工具)
5. [启动沙箱并访问 Dashboard](#启动沙箱并访问-dashboard)
6. [持久化存储](#持久化存储)
7. [日志与调试](#日志与调试)
8. [常见问题](#常见问题)

---

## 架构概述

```
浏览器
  |
  +- http://localhost:3001/_admin     <-- localproxy 管理界面（创建/连接/停止沙箱）
  |
  +- http://localhost:3001/           <-- 反向代理到 Hermes Dashboard（沙箱运行时）
       |  自动注入 X-Access-Token Header
       v
  AGS 鉴权网关（<region>.tencentags.com）
       |  验证 X-Access-Token
       v
  Hermes Dashboard:9119（--host 0.0.0.0, --insecure）
```

**容器内部结构：**

| 进程 | 端口 | 作用 |
|------|------|------|
| `envd` | 49983 | AGS 沙箱管理守护进程（健康探针、命令执行） |
| `hermes dashboard` | 9119 | Hermes Dashboard，`--host 0.0.0.0` 监听所有网络接口 |
| `hermes gateway` | 8642 | Hermes Gateway（Agent 执行、Hooks） |

---

## 前置准备

### 工具依赖

| 工具 | 用途 | 安装方式 |
|------|------|----------|
| `podman` 或 `docker` | 构建/推送镜像 | [podman.io](https://podman.io) / [docker.com](https://docker.com) |
| `Node.js >= 20` | 运行本地代理 | [nodejs.org](https://nodejs.org) |
| `pnpm` | 包管理器 | `npm install -g pnpm` |

### 凭据准备

localproxy 使用腾讯云 AGS SDK 管理沙箱，需要以下凭据：

| 凭据 | 说明 | 获取方式 |
|------|------|----------|
| `TENCENTCLOUD_SECRET_ID` | 腾讯云 API 密钥 ID | [API 密钥管理](https://console.cloud.tencent.com/cam/capi) |
| `TENCENTCLOUD_SECRET_KEY` | 腾讯云 API 密钥 Key | 同上 |

登录镜像仓库：

```bash
podman login ccr.ccs.tencentyun.com
```

---

## 构建并推送镜像

### 目录结构

```
hermes-cookbook/
+-- .env.example        # 环境变量模板（make setup 时自动复制到 localproxy/.env）
+-- .gitignore
+-- Dockerfile          # FROM 官方镜像，COPY --from AGS envd 镜像，自定义 entrypoint
+-- Makefile
+-- README.md           # 英文文档
+-- README_zh.md        # 中文文档（本文件）
+-- localproxy/         # 本地管理工具（创建/连接/停止沙箱 + 反向代理）
    +-- .env.example    # 环境变量模板
    +-- .gitignore
    +-- README.md       # LocalProxy 文档（英文）
    +-- README_zh.md    # LocalProxy 文档（中文）
    +-- package.json
    +-- pnpm-lock.yaml
    +-- create-tool.ts  # 通过 AGS SDK 创建沙箱工具的脚本
    +-- server.ts       # 主服务：Express + 状态机 + SSE + 内嵌 Web UI
```

### 构建与推送

> **重要**：AGS 运行环境为 `linux/amd64`，必须构建 amd64 镜像。Makefile 已默认指定 `--platform linux/amd64`，在 Apple Silicon Mac 上构建时会自动交叉编译。

> Makefile 默认使用 `podman`。Docker 用户可通过 `make push CONTAINER_ENGINE=docker` 覆盖。

```bash
cd hermes-cookbook

make setup   # 从模板创建 localproxy/.env

# 在 localproxy/.env 中设置 DOCKER_REGISTRY
# DOCKER_REGISTRY=ccr.ccs.tencentyun.com/your-namespace

# 构建并推送（同时推送 latest 和 hash 两个 tag）
make push
# 输出示例：
# Pushed: ccr.ccs.tencentyun.com/your-namespace/sandbox-hermes:latest
# Pushed: ccr.ccs.tencentyun.com/your-namespace/sandbox-hermes:73f17f45ddf3
```

---

## 创建沙箱工具

### 方式 A：通过命令行创建

无需手动在控制台填写，只需一条命令即可创建沙箱工具。首先在 `localproxy/.env` 中取消注释并填写 `Create sandbox tool` 部分：

| 变量 | 必填 | 格式 / 示例 | 说明 |
|------|------|-------------|------|
| `IMAGE_ADDRESS` | 是 | `ccr.ccs.tencentyun.com/<namespace>/<image>:<tag>` | 完整的容器镜像地址（含 tag） |
| `IMAGE_REGISTRY_TYPE` | 否 | `personal`（默认）或 `enterprise` | `personal` = CCR 个人版，`enterprise` = TCR 企业版 |
| `CFS_FILE_SYSTEM_ID` | 是 | `cfs-xxxxxxxx` | CFS 文件系统 ID（在 [CFS 控制台](https://console.cloud.tencent.com/cfs) 查看） |
| `CFS_PATH` | 否 | `/`（默认）或 `/<sub-path>` | CFS 内挂载的子路径，默认 `/` |
| `ROLE_ARN` | 是 | `qcs::cam::uin/<owner-uin>:roleName/<role-name>` | AGS 拉取镜像时扮演的 CAM 角色 ARN。该角色需有 CCR 拉取权限。[管理角色](https://console.cloud.tencent.com/cam/role) |

然后执行：

```bash
make create_sandbox_tool
```

该命令通过 AGS SDK 调用 `CreateSandboxTool`，自动填入下方文档中的所有参数（启动命令、探针、资源规格、CFS 挂载等）。

### 方式 B：通过 AGS 控制台创建

在 [AGS 控制台](https://console.cloud.tencent.com/ags) 创建沙箱工具时，填写以下配置：

### 基本配置

> **重要**：AGS 运行沙箱时会忽略镜像内的 `CMD`/`ENTRYPOINT`，必须在控制台手动填写启动命令和启动参数。

| 字段 | 值 |
|------|----|
| 工具名称 | `my-hermes-agent` |
| 工具类型 | 自定义镜像 |
| 镜像地址 | `ccr.ccs.tencentyun.com/your-namespace/sandbox-hermes:<hash>` |
| 镜像仓库类型 | 个人版 |
| 启动命令 | `/entrypoint.sh` |
| 启动参数 | （无） |
| CPU | 4 核 |
| 内存 | 8 GiB |
| 探针路径 | `/health` |
| 探针端口 | `49983` |
| 就绪超时 | `30000` ms |
| 探针周期 | `3000` ms |
| 失败阈值 | `100` |
| 网络策略 | 公网 |

### 端口开放配置

以下三个端口都必须在 AGS 控制台中配置（点击「新增」添加端口条目）：

| 端口名称 | 端口 | 协议 |
|----------|------|------|
| `dashboard` | `9119` | TCP |
| `gateway` | `8642` | TCP |
| `envd` | `49983` | TCP |

> **重要**：如果端口未显式开放，AGS 网关会对该端口的所有请求返回 500。Hermes Dashboard（9119）、Gateway（8642）和 envd 守护进程（49983，用于健康探针）这三个端口都必须开放。

### 环境变量配置

以下环境变量必须在 AGS 控制台中设置（点击「新增」添加条目）：

| 变量 | 值 | 说明 |
|------|-----|------|
| `PYTHONUNBUFFERED` | `1` | 禁用 Python 输出缓冲 |
| `HERMES_WEB_DIST` | `/opt/hermes/hermes_cli/web_dist` | Dashboard 静态资源路径 |
| `PLAYWRIGHT_BROWSERS_PATH` | `/opt/hermes/.playwright` | Playwright 浏览器二进制路径 |
| `TERM` | `xterm` | 终端类型 |
| `SHLVL` | `1` | Shell 层级 |
| `HERMES_HOME` | `/opt/data` | Hermes 数据目录（必须与 CFS 挂载路径一致） |
| `PATH` | `/opt/data/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin` | 系统 PATH，包含 Hermes 本地 bin 目录 |
| `GATEWAY_ALLOW_ALL_USERS` | `true` | 允许所有用户访问 Gateway（AGS 环境必须，否则所有请求都会被拒绝） |

> **重要**：`HERMES_HOME` 必须与 CFS 挂载路径（`/opt/data`）一致。缺少这些环境变量可能导致 Hermes 无法启动或 Dashboard 无法正常渲染。

### 存储挂载配置

| 挂载项 | CFS ID | 容器内挂载路径 |
|--------|--------|---------------|
| Hermes 数据 | `cfs-xxxxxxxx` | `/opt/data` |

> **注意**：CFS 挂载路径为 `/opt/data`，即默认的 `HERMES_HOME`。Hermes 会将所有运行时数据写入该目录。CFS 是 POSIX 兼容的网络文件系统，支持所有标准文件操作（包括 SQLite、文件锁、符号链接等）。首次启动时，entrypoint 脚本会自动从安装目录复制默认配置文件（`.env`、`config.yaml`、`SOUL.md`）。

> **注意**：更新工具镜像后约 3 分钟内新建沙箱可能返回 502，属正常现象，稍后重试即可。

---

## 启动沙箱并访问 Dashboard

### 配置本地代理

复制环境变量模板：

```bash
cp localproxy/.env.example localproxy/.env
```

编辑 `localproxy/.env`，填入以下环境变量：

```bash
# 腾讯云 API 凭据（必须）
TENCENTCLOUD_SECRET_ID=your_secret_id_here
TENCENTCLOUD_SECRET_KEY=your_secret_key_here
TENCENTCLOUD_REGION=ap-guangzhou          # AGS 所在地域

# AGS 配置（必须）
TOOL_NAME=my-hermes-agent               # AGS 控制台创建的沙箱工具名称

# CFS 挂载（可选，不填则使用工具配置的默认挂载）
MOUNT_NAME=cfs                           # 指定挂载项名称
```

安装依赖并启动：

```bash
# 在 hermes-cookbook 根目录下执行
make setup   # 安装 localproxy 依赖
make run     # 启动 localproxy 管理服务
```

### 使用流程

1. 打开管理界面 **http://localhost:3001/_admin**
2. 点击 **Start Sandbox** 创建新沙箱（或在输入框填入已有沙箱 ID 后点击 **Connect**）
3. 等待状态流转：`Idle -> Starting -> Connecting -> Running`
4. Running 后，点击 **Open Dashboard** 访问 Hermes Dashboard（地址为 `http://localhost:3001/`）

---

## 持久化存储

Hermes 通过 `HERMES_HOME` 环境变量决定配置和运行时数据的存储位置，默认为：

```
HERMES_HOME=/opt/data
```

只需将 CFS 文件系统挂载到容器的 `/opt/data` 路径即可实现持久化。CFS 是 POSIX 兼容的网络文件系统，使用方式与本地文件系统完全一致，支持所有标准文件操作（包括 SQLite、文件锁、符号链接等）。

Hermes 会读写 `/opt/data/`，包含：

| 路径 | 内容 |
|------|------|
| `/opt/data/.env` | 环境配置（首次启动自动创建） |
| `/opt/data/config.yaml` | CLI 配置（首次启动自动创建） |
| `/opt/data/SOUL.md` | Agent 人设定义（首次启动自动创建） |
| `/opt/data/sessions/` | 会话数据 |
| `/opt/data/skills/` | 技能数据 |
| `/opt/data/memories/` | 记忆数据 |
| `/opt/data/logs/` | 日志文件 |
| `/opt/data/cron/` | Cron 任务 |
| `/opt/data/hooks/` | Hooks |
| `/opt/data/workspace/` | 工作区文件 |

> **注意**：Hermes **不需要**预先上传配置文件。首次启动时，entrypoint 脚本会自动从安装目录复制默认配置到 `HERMES_HOME`。

如需按用户/会话隔离，可在创建沙箱工具时设置 `CFS_PATH` 为子路径（如 `/user-123`），或在 localproxy 管理界面的 **Mount subpath** 输入框中填写子路径：

```
CFS 挂载效果：
cfs-xxxxxxxx:/user-123/    -> /opt/data
```

---

## 日志与调试

使用 [ags-cli](https://github.com/TencentCloudAgentRuntime/ags-cli) 登录沙箱：

```bash
ags instance login <sandbox_id> --user root
```

常用调试命令：

```bash
# 查看进程状态
ps aux | grep -E 'hermes|envd' | grep -v grep

# Hermes Dashboard 日志
cat /logs/dashboard.log

# Hermes Gateway 日志
cat /logs/gateway.log

# 技能同步日志
cat /logs/skills_sync.log

# envd 守护进程日志
cat /logs/envd.log
```

---

## 常见问题

### Q1：Dashboard 打开后显示连接错误

**原因**：Hermes Dashboard 可能未正常启动，或缺少 `--host 0.0.0.0` 参数。

**解决**：登录沙箱检查 `/logs/dashboard.log` 中的错误信息。

### Q2：WebSocket 连接被拦截

**解决**：必须通过 `localproxy` 本地代理访问，不要直接访问 AGS 外部 URL。

### Q3：如何更新 Hermes 版本

更新 `Dockerfile` 中的基础镜像 tag：

```dockerfile
FROM nousresearch/hermes-agent:v2026.4.23
```

然后重新构建并推送：

```bash
cd hermes-cookbook
make push
```

然后在 AGS 控制台更新工具镜像为新的 hash tag。

