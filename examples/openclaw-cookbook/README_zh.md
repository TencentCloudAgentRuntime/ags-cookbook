# OpenClaw 沙箱使用指南（官方镜像方案）

基于官方 `ghcr.io/openclaw/openclaw:latest` 镜像，在腾讯云 AGS 中运行 OpenClaw。无需维护 nginx 和启动脚本，OpenClaw 始终跟随官方最新版本。

---

## 目录

1. [架构概述](#架构概述)
2. [前置准备](#前置准备)
3. [准备 openclaw.json](#准备-openclawjson)
4. [构建并推送镜像](#构建并推送镜像)
5. [创建沙箱工具](#创建沙箱工具)
6. [启动沙箱并访问 Dashboard](#启动沙箱并访问-dashboard)
7. [持久化存储](#持久化存储)
8. [日志与调试](#日志与调试)
9. [常见问题](#常见问题)

---

## 架构概述

```
浏览器
  │
  ├─ http://localhost:3001           ←── localproxy 管理界面（创建/连接/停止沙箱）
  │
  └─ http://localhost:3001/sandbox/  ←── localproxy 反向代理（仅沙箱 running 时可用）
       │  自动注入 X-Access-Token Header
       ▼
  AGS 鉴权网关（<region>.tencentags.com）
       │  验证 X-Access-Token
       ▼
  OpenClaw Gateway:8080（直接对外，无 nginx 层）
```

**容器内部结构：**

| 进程 | 端口 | 作用 |
|------|------|------|
| `envd` | 49983 | AGS 沙箱管理守护进程（健康探针、命令执行） |
| `node openclaw.mjs gateway` | 8080 | OpenClaw Gateway，`--bind lan` 直接监听所有网络接口 |

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

## 准备 openclaw.json

`openclaw.json` 是 OpenClaw 的配置文件，**不打包进镜像**，通过 COS 持久化存储。

### 存储路径关系

启动参数中设置了 `OPENCLAW_HOME=/openclaw`，OpenClaw 会在启动时读取：

```
$OPENCLAW_HOME/.openclaw/openclaw.json
= /openclaw/.openclaw/openclaw.json
```

COS 挂载配置（在 AGS 控制台或 setup.py 中填写）：

| 字段 | 示例值 | 说明 |
|------|--------|------|
| COS 桶 | `your-bucket` | 存储桶名称 |
| COS 子路径 | `openclaw-user1` | 桶内的目录前缀 |
| 容器挂载路径 | `/openclaw` | 即 `OPENCLAW_HOME`，固定值 |

挂载后，容器内的路径映射为：

```
/openclaw/                    ← OPENCLAW_HOME，COS 桶根（子路径）挂载点
└── .openclaw/
    ├── openclaw.json         ← 配置文件（需预先上传）
    ├── canvas/               ← Agent Canvas 数据（运行时自动创建）
    └── cron/                 ← Cron 任务数据（运行时自动创建）
```

### 上传配置文件到 COS

在使用前，需将 `openclaw.json` 上传到 COS 对应位置：

```
cos://your-bucket/openclaw-user1/.openclaw/openclaw.json
                  ^^^^^^^^^^^^^^ ^^^^^^^^^^
                  COS 子路径      固定为 .openclaw/
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
      "token": "REPLACE_WITH_YOUR_SECURE_TOKEN"
    },
    "bind": "lan"
  }
}
```

> ⚠️ **安全警告**：部署前**必须**将 `REPLACE_WITH_YOUR_SECURE_TOKEN` 替换为一个强且唯一的 Token。`dangerously*` 选项关闭了安全检查以适配 AGS 代理访问——**不要**在没有 AGS 鉴权网关保护的公网实例上使用这些配置。

### 关键配置项

| 配置路径 | 值 | 说明 |
|----------|-----|------|
| `gateway.bind` | `"lan"` | **必须**。让 OpenClaw 监听 `0.0.0.0` 而非 loopback，容器外部才能访问 |
| `gateway.auth.token` | `"REPLACE_WITH_YOUR_SECURE_TOKEN"` | **必须替换**。OpenClaw 自身的 Bearer Token，请使用强且唯一的值 |
| `gateway.controlUi.dangerouslyDisableDeviceAuth` | `true` | **AGS 环境必须**。禁用设备配对检查（AGS 代理无法完成设备配对） |
| `gateway.controlUi.dangerouslyAllowHostHeaderOriginFallback` | `true` | **AGS 环境必须**。适配 AGS 域名访问方式（Host 头与 Origin 不一致） |
| `gateway.controlUi.allowedOrigins` | `["*"]` | 允许任意来源跨域访问——在 AGS 鉴权网关后可接受 |

---

## 构建并推送镜像

### 目录结构

```
openclaw-cookbook/
├── Dockerfile          # FROM 官方镜像，COPY --from AGS envd 镜像
├── Makefile
├── .gitignore
├── openclaw.json       # 上传到 COS 的配置文件模板
└── localproxy/         # 本地管理工具（创建/连接/停止沙箱 + 反向代理）
    ├── server.ts       # 主服务：Express + 状态机 + SSE + 内嵌 Web UI
    ├── package.json
    ├── .env.example    # 环境变量模板
    └── .env            # 本地配置（不提交 Git）
```

### 构建与推送

> ⚠️ **重要**：AGS 运行环境为 `linux/amd64`，必须构建 amd64 镜像。Makefile 已默认指定 `--platform linux/amd64`，在 Apple Silicon Mac 上构建时会自动交叉编译。

> 💡 Makefile 默认使用 `podman`。Docker 用户可通过 `make push CONTAINER_ENGINE=docker` 覆盖。

```bash
cd openclaw-cookbook

# 修改 Makefile 中的 DOCKER_REGISTRY
# DOCKER_REGISTRY ?= ccr.ccs.tencentyun.com/your-namespace

# 构建并推送（同时推送 latest 和 hash 两个 tag）
make push
# 输出示例：
# Pushed: ccr.ccs.tencentyun.com/your-namespace/sandbox-openclaw:latest
# Pushed: ccr.ccs.tencentyun.com/your-namespace/sandbox-openclaw:73f17f45ddf3
```

---

## 创建沙箱工具

在 [AGS 控制台](https://console.cloud.tencent.com/ags) 创建沙箱工具时，填写以下配置：

### 基本配置

> ⚠️ **重要**：AGS 运行沙箱时会忽略镜像内的 `CMD`/`ENTRYPOINT`，必须在控制台手动填写启动命令和启动参数。

| 字段 | 值 |
|------|----|
| 工具名称 | `my-openclaw-official` |
| 工具类型 | 自定义镜像 |
| 镜像地址 | `ccr.ccs.tencentyun.com/your-namespace/sandbox-openclaw:<hash>` |
| 镜像仓库类型 | 个人版 |
| 启动命令 | `/bin/bash` |
| 启动参数 | `-l` `-c` `/usr/bin/envd > /tmp/envd.log 2>&1 & while true; do su -s /bin/bash node -c 'OPENCLAW_HOME=/openclaw node /app/openclaw.mjs gateway --port 8080 --bind lan --allow-unconfigured'; echo '[restart] openclaw exited ($?), restarting in 1s...'; sleep 1; done` |
| CPU | 4 核 |
| 内存 | 8 GiB |
| 探针路径 | `/health` |
| 探针端口 | `49983` |
| 就绪超时 | `30000` ms |
| 探针周期 | `3000` ms |
| 失败阈值 | `100` |
| 网络策略 | 公网 |

### 存储挂载配置

| 挂载项 | COS 路径 | 容器内挂载路径 |
|--------|----------|---------------|
| OpenClaw 数据 | `cos://your-bucket/user1/` | `/openclaw` |

> ⚠️ **注意**：COS 挂载路径为 `/openclaw`，启动参数中已设置 `OPENCLAW_HOME=/openclaw`，openclaw 会读取 `/openclaw/.openclaw/openclaw.json` 作为配置文件并将所有运行时数据写入该目录。需预先在 COS 的 `user1/.openclaw/openclaw.json` 上传配置文件（可参考 `openclaw.json`）。

> ⚠️ **注意**：更新工具镜像后约 3 分钟内新建沙箱可能返回 502，属正常现象，稍后重试即可。

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
TENCENTCLOUD_REGION=ap-shanghai          # AGS 所在地域

# AGS 配置（必须）
TOOL_NAME=my-openclaw-official           # AGS 控制台创建的沙箱工具名称

# COS 挂载（可选，不填则使用工具配置的默认挂载）
MOUNT_NAME=cos                           # 指定挂载项名称，用于传递 subpath 等参数
```

安装依赖并启动：

```bash
# 在 openclaw-cookbook 根目录下执行
make setup   # 安装 localproxy 依赖
make run     # 启动 localproxy 管理服务
```

### 使用流程

1. 打开管理界面 **http://localhost:3001**
2. 点击 **Start Sandbox** 创建新沙箱（或在输入框填入已有沙箱 ID 后点击 **Connect**）
3. 等待状态流转：`Idle → Starting → Connecting → Running`
4. Running 后，点击 **Open Dashboard** 访问 OpenClaw Dashboard（地址为 `http://localhost:3001/sandbox/__openclaw__`）

> ⚠️ 首次访问 Dashboard 需要填写 OpenClaw Token，请使用你在 `openclaw.json` 中为 `gateway.auth.token` 设置的值。

---

## 持久化存储

OpenClaw 通过 `OPENCLAW_HOME` 环境变量决定配置和运行时数据的存储位置。启动参数中已设置：

```
OPENCLAW_HOME=/openclaw
```

openclaw 会读取 `$OPENCLAW_HOME/.openclaw/openclaw.json` 作为配置文件，并将所有运行时数据写入 `$OPENCLAW_HOME/.openclaw/`。因此只需将 COS 桶挂载到容器的 `/openclaw` 路径即可实现持久化：

| COS 路径 | 容器内挂载路径 | 内容 |
|----------|---------------|------|
| `cos://your-bucket/user1/` | `/openclaw` | openclaw 的配置和所有运行时数据 |

openclaw 会读写 `/openclaw/.openclaw/`，包含：

| 路径 | 内容 |
|------|------|
| `/openclaw/.openclaw/openclaw.json` | 配置文件（**必须**预先上传到 COS） |
| `/openclaw/.openclaw/canvas/` | Canvas 数据 |
| `/openclaw/.openclaw/cron/` | Cron 任务 |

> ⚠️ **注意**：`/openclaw/.openclaw/openclaw.json` 必须预先上传到 COS，COS 未挂载或文件不存在时 openclaw 将无法正常启动。不提供默认 fallback，以便快速发现配置问题。

如需按用户/会话隔离，可在 localproxy 管理界面的 **Mount subpath** 输入框中填写子路径（如 `user-123`），创建沙箱时会自动将该子路径传递给 AGS 存储挂载：

```
COS 挂载效果：
cos://your-bucket/user-123/         → /openclaw
cos://your-bucket/user-123/.openclaw/openclaw.json  → 该用户的配置文件
```

---

## 日志与调试

使用 ags-cli 登录沙箱：

```bash
ags instance login <sandbox_id> --user root
```

常用调试命令：

```bash
# 查看进程状态
ps aux | grep -E 'node|envd' | grep -v grep

# OpenClaw 启动日志（stdout 直接输出，通过 AGS 控制台或 ags-cli 查看）

# OpenClaw 详细会话日志
cat /tmp/openclaw/openclaw-$(date +%Y-%m-%d).log

# envd 守护进程日志
cat /tmp/envd.log
```

---

## 常见问题

### Q1：Dashboard 打开后显示 401

**原因**：`openclaw.json` 未正确读取。由于启动参数包含 `--allow-unconfigured`，OpenClaw 不会崩溃，而是静默回退到默认 loopback 模式（仅监听 `127.0.0.1`），导致从容器外部无法访问网关。

**解决**：确认 COS 已挂载到 `/openclaw`，且 `/openclaw/.openclaw/openclaw.json` 存在并包含 `"bind": "lan"`。

### Q2：沙箱创建时报 `ENOENT` 或配置读取失败

**原因**：COS 挂载的目录为空，`openclaw.json` 未上传。

**解决**：将 `openclaw.json` 上传到正确的 COS 路径，例如 `cos://your-bucket/openclaw-user1/.openclaw/openclaw.json`（参见[准备 openclaw.json](#准备-openclawjson)）。

### Q3：favicon 404

**原因**：官方镜像的 OpenClaw 在 `/__openclaw__/` 路径下引用 `./favicon.svg`，但实际 favicon 在根路径 `/favicon.svg`，无 nginx 时无法 rewrite。

**说明**：这是已知问题，仅影响浏览器 tab 图标，不影响 Dashboard 功能，如需正常显示图标，移除路径前缀/__openclaw__即可。

### Q4：WebSocket 连接被拦截

**解决**：必须通过 `localproxy` 本地代理访问，不要直接访问 AGS 外部 URL。

### Q5：如何更新 OpenClaw 版本

```bash
cd openclaw-cookbook
make push   # 重新拉取 ghcr.io/openclaw/openclaw:latest 并推送
```

然后在 AGS 控制台更新工具镜像为新的 hash tag。

---

## 待办事项

- [ ] 监控方案
- [ ] 暂停/恢复后的会话和记忆完整性验证
- [ ] 暂停/恢复耗时的性能基准测试
