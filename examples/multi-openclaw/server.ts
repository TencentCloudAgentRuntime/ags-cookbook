import 'dotenv/config';
import { config } from 'dotenv';
config({ override: true });
import express from 'express';
import cors from 'cors';
import http from 'http';
import fs from 'fs';
import path from 'path';
import { ags } from 'tencentcloud-sdk-nodejs-ags';
import httpProxy from 'http-proxy';

const AgsClient = ags.v20250920.Client;

// ---------------------------------------------------------------------------
// 常量
// ---------------------------------------------------------------------------

const PORT = parseInt(process.env.PORT || '3001', 10);
const OPENCLAW_PORT = 8080;
const LOG_RING_BUFFER_SIZE = 200;
const DATA_DIR = path.resolve(process.env.DATA_DIR || './data');
const ASSIGNMENTS_FILE = path.join(DATA_DIR, 'assignments.json');

// ---------------------------------------------------------------------------
// 类型定义
// ---------------------------------------------------------------------------

type SandboxStatus = 'idle' | 'connecting' | 'running' | 'error';

/** 单个用户绑定的沙箱上下文 */
interface UserSandbox {
  userId: string;
  sandboxId: string;
  status: SandboxStatus;
  remoteHost: string;
  accessToken: string;
  proxy: ReturnType<typeof httpProxy.createProxyServer> | null;
  startedAt?: number;
  error?: string;
  logs: string[];
}

/** 持久化的用户-沙箱分配记录 */
interface Assignment {
  userId: string;
  sandboxId: string;
  createdAt: string;
}

// ---------------------------------------------------------------------------
// SandboxManager — 多沙箱路由核心
// ---------------------------------------------------------------------------
//
// 整体架构:
//
//   浏览器A ─┐                ┌── http-proxy A ──▶ sandbox-A (OpenClaw)
//   浏览器B ─┤── Express ─────┤── http-proxy B ──▶ sandbox-B (OpenClaw)
//   浏览器C ─┘  (中心服务)    └── http-proxy C ──▶ sandbox-C (OpenClaw)
//
// 每个用户一个独立的 http-proxy 实例，持有各自沙箱的 accessToken。
// WebSocket upgrade 时根据 URL 中的 userId 路由到对应的 proxy.ws()。
//

class SandboxManager {
  /** userId → UserSandbox 运行时映射 */
  private sandboxes = new Map<string, UserSandbox>();

  /** userId → sandboxId 持久化分配 */
  private assignments = new Map<string, string>();

  /** 管理 SSE 连接 — 广播给所有管理员 */
  private adminSseClients = new Set<express.Response>();

  /** 每个用户的 SSE 连接 */
  private userSseClients = new Map<string, Set<express.Response>>();

  constructor() {
    this.loadAssignments();
  }

  // ─── 持久化 ──────────────────────────────────────

  private loadAssignments(): void {
    try {
      if (fs.existsSync(ASSIGNMENTS_FILE)) {
        const data: Assignment[] = JSON.parse(fs.readFileSync(ASSIGNMENTS_FILE, 'utf-8'));
        for (const a of data) {
          this.assignments.set(a.userId, a.sandboxId);
        }
        console.log(`📂 已加载 ${this.assignments.size} 条用户-沙箱分配`);
      }
    } catch (err) {
      console.error('⚠️  加载分配文件失败:', err);
    }
  }

  private saveAssignments(): void {
    fs.mkdirSync(DATA_DIR, { recursive: true });
    const data: Assignment[] = [];
    for (const [userId, sandboxId] of this.assignments) {
      data.push({ userId, sandboxId, createdAt: new Date().toISOString() });
    }
    fs.writeFileSync(ASSIGNMENTS_FILE, JSON.stringify(data, null, 2));
  }

  // ─── 分配管理 ──────────────────────────────────────

  /** 管理员为用户分配沙箱 */
  assign(userId: string, sandboxId: string): void {
    // 如果该用户之前有正在运行的代理，先停掉
    const existing = this.sandboxes.get(userId);
    if (existing?.proxy) {
      existing.proxy.close();
    }
    this.sandboxes.delete(userId);

    this.assignments.set(userId, sandboxId);
    this.saveAssignments();
    this.broadcastAdmin();
    console.log(`✅ 已分配: ${userId} → ${sandboxId}`);
  }

  /** 管理员解绑用户 */
  unassign(userId: string): void {
    const sb = this.sandboxes.get(userId);
    if (sb?.proxy) {
      sb.proxy.close();
    }
    this.sandboxes.delete(userId);
    this.assignments.delete(userId);
    this.saveAssignments();
    this.broadcastAdmin();
    console.log(`✅ 已解绑: ${userId}`);
  }

  /** 获取所有分配列表（含运行时状态） */
  getAllAssignments(): Array<{
    userId: string;
    sandboxId: string;
    status: SandboxStatus;
    startedAt?: number;
    error?: string;
  }> {
    const result = [];
    for (const [userId, sandboxId] of this.assignments) {
      const sb = this.sandboxes.get(userId);
      result.push({
        userId,
        sandboxId,
        status: sb?.status || 'idle',
        startedAt: sb?.startedAt,
        error: sb?.error,
      });
    }
    return result;
  }

  // ─── 沙箱连接 ──────────────────────────────────────
  //
  // 当用户访问 /chat?user=xxx 时，前端会请求 /api/user/:userId/connect
  // 触发中心服务为该用户建立到其沙箱的代理通道。
  //

  /** 为指定用户建立到其沙箱的代理连接 */
  async connectUser(userId: string): Promise<UserSandbox> {
    const sandboxId = this.assignments.get(userId);
    if (!sandboxId) {
      throw new Error(`用户 ${userId} 未分配沙箱`);
    }

    // 已有活跃连接，直接返回
    const existing = this.sandboxes.get(userId);
    if (existing && existing.status === 'running' && existing.proxy) {
      return existing;
    }

    // 创建用户沙箱上下文
    const sb: UserSandbox = {
      userId,
      sandboxId,
      status: 'connecting',
      remoteHost: '',
      accessToken: '',
      proxy: null,
      logs: [],
    };
    this.sandboxes.set(userId, sb);
    this.appendLog(userId, `🔌 正在连接沙箱 ${sandboxId}...`);
    this.broadcastAdmin();

    try {
      // 1. 获取 access token
      const accessToken = await this.acquireToken(sandboxId);
      sb.accessToken = accessToken;
      this.appendLog(userId, `✅ 已获取 Token`);

      // 2. 构造远端地址
      const remoteHost = this.getRemoteHost(sandboxId, OPENCLAW_PORT);
      sb.remoteHost = remoteHost;

      // 3. 等待 OpenClaw 就绪
      await this.waitForOpenClaw(userId, remoteHost, accessToken);

      // 4. 创建独立的 http-proxy 实例
      //    ┌─────────────────────────────────────────────────┐
      //    │  这是多用户路由的关键：每个用户一个 proxy 实例，   │
      //    │  各自持有不同沙箱的 target 和 accessToken。       │
      //    │  中心服务根据 URL 中的 userId 选择对应 proxy。    │
      //    └─────────────────────────────────────────────────┘
      sb.proxy = this.createProxyForUser(userId, remoteHost, accessToken);

      sb.status = 'running';
      sb.startedAt = Date.now();
      this.appendLog(userId, `🎉 沙箱代理已就绪`);
      this.broadcastAdmin();
      this.broadcastUser(userId);

      return sb;
    } catch (err: any) {
      sb.status = 'error';
      sb.error = err.message;
      this.appendLog(userId, `❌ 连接失败: ${err.message}`);
      this.broadcastAdmin();
      this.broadcastUser(userId);
      throw err;
    }
  }

  /** 断开用户的沙箱代理 */
  disconnectUser(userId: string): void {
    const sb = this.sandboxes.get(userId);
    if (sb?.proxy) {
      sb.proxy.close();
    }
    this.sandboxes.delete(userId);
    this.broadcastAdmin();
    this.broadcastUser(userId);
    console.log(`🔌 已断开用户 ${userId} 的沙箱代理`);
  }

  // ─── HTTP 代理路由 ──────────────────────────────────
  //
  //   客户端请求: GET /sandbox/:userId/foo/bar
  //   中心服务:   从 URL 提取 userId → 找到对应 proxy → 转发
  //
  //   ┌──────────┐     /sandbox/alice/...     ┌──────────┐     https://...     ┌──────────┐
  //   │ 浏览器A  │ ──────────────────────────▶│ 中心服务 │ ─────────────────▶│ 沙箱 A   │
  //   └──────────┘                            │          │                    └──────────┘
  //   ┌──────────┐     /sandbox/bob/...       │          │     https://...     ┌──────────┐
  //   │ 浏览器B  │ ──────────────────────────▶│ (路由)   │ ─────────────────▶│ 沙箱 B   │
  //   └──────────┘                            └──────────┘                    └──────────┘
  //

  /** HTTP 请求代理 — 根据 userId 路由 */
  proxyHttpRequest(userId: string, req: express.Request, res: express.Response): void {
    const sb = this.sandboxes.get(userId);
    if (!sb || !sb.proxy || sb.status !== 'running') {
      res.status(503).json({ error: `用户 ${userId} 的沙箱未连接` });
      return;
    }
    sb.proxy.web(req, res);
  }

  // ─── WebSocket 代理路由 ─────────────────────────────
  //
  //   这是最关键的部分：HTTP upgrade (WebSocket握手) 必须路由到正确的沙箱。
  //
  //   浏览器发送: ws://host/sandbox/:userId/
  //   Node.js 的 'upgrade' 事件在 HTTP server 级别触发（不经过 Express 中间件），
  //   所以需要在 server.on('upgrade', ...) 中手动解析 URL、提取 userId、
  //   找到对应的 proxy 实例，调用 proxy.ws() 完成 WebSocket 升级。
  //
  //   ┌──────────┐    ws://host/sandbox/alice/    ┌──────────┐    wss://sandbox-a.xxx.com/
  //   │ 浏览器A  │ ─────── WS upgrade ──────────▶│ 中心服务 │ ──── proxy.ws() ──────────▶ 沙箱 A
  //   └──────────┘                                │          │
  //   ┌──────────┐    ws://host/sandbox/bob/      │          │    wss://sandbox-b.xxx.com/
  //   │ 浏览器B  │ ─────── WS upgrade ──────────▶│ (解析URL │ ──── proxy.ws() ──────────▶ 沙箱 B
  //   └──────────┘                                │  取userId)│
  //                                               └──────────┘
  //

  /** WebSocket upgrade — 根据 userId 路由到对应沙箱 */
  handleWsUpgrade(req: http.IncomingMessage, socket: any, head: Buffer): void {
    const url = req.url || '';

    // 解析 /sandbox/:userId/... 格式
    const match = url.match(/^\/sandbox\/([^/]+)(\/.*)?$/);
    if (!match) {
      socket.destroy();
      return;
    }

    const userId = decodeURIComponent(match[1]);
    const remainingPath = match[2] || '/';

    const sb = this.sandboxes.get(userId);
    if (!sb || !sb.proxy || sb.status !== 'running') {
      // 沙箱未就绪，关闭连接
      socket.write('HTTP/1.1 503 Service Unavailable\r\n\r\n');
      socket.destroy();
      return;
    }

    // 重写 URL：去掉 /sandbox/:userId 前缀，只保留后续路径
    // 这样 proxy.ws() 会把 /sandbox/alice/ → / 转发到沙箱
    req.url = remainingPath;

    socket.on('error', (err: Error) => {
      this.appendLog(userId, `WebSocket error: ${err.message}`);
    });

    // 关键调用：将 WebSocket 升级请求转发到该用户对应的沙箱 proxy
    sb.proxy.ws(req, socket, head);
  }

  // ─── 内部工具方法 ──────────────────────────────────

  /**
   * 为单个用户创建独立的 http-proxy 实例。
   *
   * 每个 proxy 实例：
   * - target 指向该用户的沙箱远端地址
   * - 在 proxyReq 中注入该沙箱的 X-Access-Token
   * - 支持 HTTP 和 WebSocket 两种协议
   */
  private createProxyForUser(
    userId: string,
    remoteHost: string,
    accessToken: string,
  ): ReturnType<typeof httpProxy.createProxyServer> {
    const proxy = httpProxy.createProxyServer({
      target: `https://${remoteHost}`,
      changeOrigin: true,
      secure: true,
      ws: true,
    });

    // HTTP 请求：注入 access token
    proxy.on('proxyReq', (proxyReq, req) => {
      proxyReq.setHeader('X-Access-Token', accessToken);
    });

    // WebSocket 请求：注入 access token
    proxy.on('proxyReqWs', (proxyReq) => {
      proxyReq.setHeader('X-Access-Token', accessToken);
    });

    // 响应头清理：移除阻止 iframe 嵌入的头
    proxy.on('proxyRes', (proxyRes) => {
      delete proxyRes.headers['x-frame-options'];
      delete proxyRes.headers['X-Frame-Options'];
      delete proxyRes.headers['content-security-policy'];
      delete proxyRes.headers['Content-Security-Policy'];
    });

    proxy.on('error', (err, _req, res) => {
      this.appendLog(userId, `Proxy error: ${err.message}`);
      if (res && 'writeHead' in res) {
        (res as http.ServerResponse).writeHead(502);
        (res as http.ServerResponse).end('Bad Gateway: ' + err.message);
      }
    });

    return proxy;
  }

  private createAgsClient() {
    return new AgsClient({
      credential: {
        secretId: process.env.TENCENTCLOUD_SECRET_ID!,
        secretKey: process.env.TENCENTCLOUD_SECRET_KEY!,
      },
      region: process.env.TENCENTCLOUD_REGION || 'ap-shanghai',
    });
  }

  private getRemoteHost(instanceId: string, port: number): string {
    const region = process.env.TENCENTCLOUD_REGION || 'ap-shanghai';
    return `${port}-${instanceId}.${region}.tencentags.com`;
  }

  private async acquireToken(instanceId: string): Promise<string> {
    const client = this.createAgsClient();
    const resp = await client.AcquireSandboxInstanceToken({ InstanceId: instanceId });
    if (!resp.Token) throw new Error('AcquireSandboxInstanceToken 未返回 Token');
    return resp.Token;
  }

  private async waitForOpenClaw(
    userId: string,
    remoteHost: string,
    accessToken: string,
    timeoutMs = 60000,
  ): Promise<void> {
    const url = `https://${remoteHost}/`;
    this.appendLog(userId, `⏳ 等待 OpenClaw 就绪（最多 ${timeoutMs / 1000}s）...`);
    const deadline = Date.now() + timeoutMs;
    let attempt = 0;

    while (Date.now() < deadline) {
      attempt++;
      try {
        const res = await fetch(url, {
          headers: { 'X-Access-Token': accessToken },
          signal: AbortSignal.timeout(3000),
        });
        if (res.status !== 404 && !(res.status >= 500 && res.status <= 599)) {
          this.appendLog(userId, `✅ OpenClaw 已就绪（HTTP ${res.status}），共等待 ${attempt} 次探针`);
          return;
        }
      } catch {
        // 网络未通，继续重试
      }
      await new Promise((resolve) => setTimeout(resolve, 2000));
    }
    this.appendLog(userId, '⚠️  OpenClaw 启动超时，但仍继续');
  }

  // ─── 日志与广播 ──────────────────────────────────

  private appendLog(userId: string, msg: string): void {
    const sb = this.sandboxes.get(userId);
    const line = `[${new Date().toISOString()}] [${userId}] ${msg}`;
    if (sb) {
      sb.logs.push(line);
      if (sb.logs.length > LOG_RING_BUFFER_SIZE) {
        sb.logs = sb.logs.slice(-LOG_RING_BUFFER_SIZE);
      }
    }
    console.log(line);
    this.broadcastUser(userId);
  }

  /** 获取指定用户的状态（供聊天页面使用） */
  getUserStatus(userId: string): {
    userId: string;
    sandboxId?: string;
    status: SandboxStatus;
    error?: string;
  } {
    const sandboxId = this.assignments.get(userId);
    const sb = this.sandboxes.get(userId);
    return {
      userId,
      sandboxId,
      status: sb?.status || 'idle',
      error: sb?.error,
    };
  }

  // ─── SSE 广播 ──────────────────────────────────

  addAdminSseClient(res: express.Response): void {
    this.adminSseClients.add(res);
  }

  removeAdminSseClient(res: express.Response): void {
    this.adminSseClients.delete(res);
  }

  addUserSseClient(userId: string, res: express.Response): void {
    if (!this.userSseClients.has(userId)) {
      this.userSseClients.set(userId, new Set());
    }
    this.userSseClients.get(userId)!.add(res);
  }

  removeUserSseClient(userId: string, res: express.Response): void {
    this.userSseClients.get(userId)?.delete(res);
  }

  private broadcastAdmin(): void {
    const data = JSON.stringify({ assignments: this.getAllAssignments() });
    for (const res of this.adminSseClients) {
      res.write(`data: ${data}\n\n`);
    }
  }

  private broadcastUser(userId: string): void {
    const clients = this.userSseClients.get(userId);
    if (!clients || clients.size === 0) return;
    const data = JSON.stringify(this.getUserStatus(userId));
    for (const res of clients) {
      res.write(`data: ${data}\n\n`);
    }
  }
}

// ---------------------------------------------------------------------------
// 管理界面 HTML
// ---------------------------------------------------------------------------

function getAdminHtml(): string {
  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Multi-OpenClaw Admin</title>
  <style>${ADMIN_CSS}</style>
</head>
<body>
  ${ADMIN_HTML_BODY}
  <script>${ADMIN_JS}</script>
</body>
</html>`;
}

const ADMIN_CSS = `* { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --bg: #0f1117; --surface: #1a1d27; --surface2: #22263a; --border: #2e3250;
  --text: #e2e8f0; --text-muted: #94a3b8; --accent: #6366f1; --accent-hover: #818cf8;
  --danger: #ef4444; --success: #22c55e; --warning: #f59e0b; --radius: 8px;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}
body { background: var(--bg); color: var(--text); min-height: 100vh; }
.app { max-width: 1200px; margin: 0 auto; padding: 20px; }
.header { display: flex; align-items: center; gap: 12px; padding-bottom: 16px; border-bottom: 1px solid var(--border); margin-bottom: 20px; }
.header h1 { font-size: 1.25rem; }
.header .subtitle { font-size: 0.8rem; color: var(--text-muted); }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px; margin-bottom: 16px; }
.card-title { font-size: 0.75rem; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: var(--text-muted); margin-bottom: 12px; }
.assign-form { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.assign-form input { background: var(--surface2); border: 1px solid var(--border); border-radius: var(--radius); color: var(--text); font-size: 0.85rem; padding: 8px 12px; outline: none; flex: 1; min-width: 150px; }
.assign-form input:focus { border-color: var(--accent); }
.assign-form input::placeholder { color: var(--text-muted); }
.btn { display: inline-flex; align-items: center; justify-content: center; gap: 6px; padding: 8px 16px; border-radius: var(--radius); font-size: 0.85rem; font-weight: 600; cursor: pointer; border: none; transition: background 0.15s; }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-primary { background: var(--accent); color: #fff; }
.btn-primary:hover:not(:disabled) { background: var(--accent-hover); }
.btn-danger { background: var(--danger); color: #fff; }
.btn-danger:hover:not(:disabled) { background: #f87171; }
.btn-sm { padding: 4px 10px; font-size: 0.75rem; }
table { width: 100%; border-collapse: collapse; }
th, td { text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--border); font-size: 0.82rem; }
th { color: var(--text-muted); font-weight: 600; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.06em; }
.badge { display: inline-flex; align-items: center; gap: 5px; padding: 2px 8px; border-radius: 999px; font-size: 0.7rem; font-weight: 600; }
.badge-idle { background: rgba(148,163,184,.15); color: var(--text-muted); }
.badge-connecting { background: rgba(245,158,11,.12); color: #fcd34d; }
.badge-running { background: rgba(34,197,94,.12); color: #86efac; }
.badge-error { background: rgba(239,68,68,.12); color: #fca5a5; }
.badge-dot { width: 6px; height: 6px; border-radius: 50%; }
.badge-idle .badge-dot { background: var(--text-muted); }
.badge-connecting .badge-dot { background: var(--warning); animation: pulse 1s infinite; }
.badge-running .badge-dot { background: var(--success); }
.badge-error .badge-dot { background: var(--danger); }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }
.actions { display: flex; gap: 6px; }
.chat-link { color: var(--accent); text-decoration: none; font-weight: 600; font-size: 0.8rem; }
.chat-link:hover { text-decoration: underline; }
.empty-row { text-align: center; color: var(--text-muted); font-style: italic; padding: 30px; }
.mono { font-family: 'SF Mono','Fira Code',monospace; font-size: 0.75rem; }
.btn.loading { position: relative; color: transparent; pointer-events: none; }
.btn.loading::after { content: ''; position: absolute; width: 14px; height: 14px; border: 2px solid rgba(255,255,255,.3); border-top-color: #fff; border-radius: 50%; animation: spin 0.6s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.toast-container { position: fixed; top: 16px; right: 16px; z-index: 9999; display: flex; flex-direction: column; gap: 8px; }
.toast { padding: 10px 16px; border-radius: var(--radius); font-size: 0.8rem; font-weight: 500; animation: toastIn 0.3s ease-out, toastOut 0.3s ease-in 2.7s forwards; box-shadow: 0 4px 12px rgba(0,0,0,.4); backdrop-filter: blur(8px); }
.toast-success { background: rgba(34,197,94,.15); border: 1px solid rgba(34,197,94,.3); color: #86efac; }
.toast-error { background: rgba(239,68,68,.15); border: 1px solid rgba(239,68,68,.3); color: #fca5a5; }
@keyframes toastIn { from{opacity:0;transform:translateX(20px)} to{opacity:1;transform:translateX(0)} }
@keyframes toastOut { to{opacity:0;transform:translateY(-10px)} }
.empty-state { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 40px 20px; color: var(--text-muted); }
.empty-state .empty-icon { font-size: 2rem; opacity: 0.5; }
.empty-state .empty-text { font-size: 0.82rem; }
.empty-state .empty-hint { font-size: 0.72rem; opacity: 0.6; }
::-webkit-scrollbar { width: 6px; } ::-webkit-scrollbar-track { background: transparent; } ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }`;

const ADMIN_HTML_BODY = `<div class="app">
  <div class="toast-container" id="toast-container"></div>
  <header class="header">
    <div><h1>🛸 Multi-OpenClaw</h1><div class="subtitle">多用户沙箱管理中心</div></div>
  </header>
  <div class="card">
    <div class="card-title">分配沙箱</div>
    <div class="assign-form">
      <input id="inp-user" placeholder="用户 ID（如 alice）" />
      <input id="inp-sandbox" placeholder="沙箱实例 ID" />
      <button id="btn-assign" class="btn btn-primary">✅ 分配</button>
    </div>
  </div>
  <div class="card">
    <div class="card-title">用户-沙箱列表</div>
    <table>
      <thead><tr><th>用户</th><th>沙箱 ID</th><th>状态</th><th>聊天入口</th><th>操作</th></tr></thead>
      <tbody id="tbl-body"><tr><td colspan="5"><div class="empty-state"><span class="empty-icon">📭</span><span class="empty-text">暂无用户-沙箱分配</span><span class="empty-hint">在上方输入用户 ID 和沙箱实例 ID 开始分配</span></div></td></tr></tbody>
    </table>
  </div>
</div>`;

const ADMIN_JS = `
const tblBody = document.getElementById('tbl-body');
const inpUser = document.getElementById('inp-user');
const inpSandbox = document.getElementById('inp-sandbox');
const btnAssign = document.getElementById('btn-assign');
const toastContainer = document.getElementById('toast-container');

// Toast 提示
function showToast(msg, type) {
  const el = document.createElement('div');
  el.className = 'toast toast-' + (type || 'success');
  el.textContent = msg;
  toastContainer.appendChild(el);
  setTimeout(() => el.remove(), 3000);
}

// 按钮 loading 状态
function setLoading(btn, loading) {
  if (loading) { btn.classList.add('loading'); btn.disabled = true; }
  else { btn.classList.remove('loading'); btn.disabled = false; }
}

// SSE 实时更新
const es = new EventSource('/api/admin/events');
es.onmessage = e => render(JSON.parse(e.data));
fetch('/api/admin/status').then(r => r.json()).then(render);

function render(data) {
  const list = data.assignments || [];
  if (!list.length) {
    tblBody.innerHTML = '<tr><td colspan="5"><div class="empty-state"><span class="empty-icon">📭</span><span class="empty-text">暂无用户-沙箱分配</span><span class="empty-hint">在上方输入用户 ID 和沙箱实例 ID 开始分配</span></div></td></tr>';
    return;
  }
  tblBody.innerHTML = list.map(a => {
    const bc = 'badge-' + a.status;
    const isRunning = a.status === 'running';
    const isConnecting = a.status === 'connecting';
    return '<tr>' +
      '<td class="mono">' + esc(a.userId) + '</td>' +
      '<td class="mono" title="' + esc(a.sandboxId) + '">' + esc(a.sandboxId.length > 20 ? a.sandboxId.slice(0,20) + '...' : a.sandboxId) + '</td>' +
      '<td><span class="badge ' + bc + '"><span class="badge-dot"></span>' + esc(a.status) + '</span></td>' +
      '<td><a class="chat-link" href="/chat?user=' + encodeURIComponent(a.userId) + '" target="_blank">💬 打开聊天</a></td>' +
      '<td class="actions">' +
        (isRunning
          ? '<button class="btn btn-danger btn-sm" id="btn-dc-' + esc(a.userId) + '" onclick="doDisconnect(\\'' + esc(a.userId) + '\\')">⏹ 断开</button>'
          : '<button class="btn btn-primary btn-sm' + (isConnecting ? ' loading' : '') + '" id="btn-cn-' + esc(a.userId) + '" onclick="doConnect(\\'' + esc(a.userId) + '\\')"' + (isConnecting ? ' disabled' : '') + '>🔌 连接</button>') +
        '<button class="btn btn-danger btn-sm" onclick="doUnassign(\\'' + esc(a.userId) + '\\')">🗑 解绑</button>' +
      '</td>' +
    '</tr>';
  }).join('');
}

btnAssign.addEventListener('click', async () => {
  const userId = inpUser.value.trim();
  const sandboxId = inpSandbox.value.trim();
  if (!userId || !sandboxId) { showToast('请填写用户 ID 和沙箱 ID', 'error'); return; }
  setLoading(btnAssign, true);
  try {
    const res = await fetch('/api/admin/assign', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ userId, sandboxId })
    });
    const data = await res.json();
    if (data.error) { showToast('分配失败: ' + data.error, 'error'); }
    else { showToast('已分配 ' + userId + ' → ' + sandboxId, 'success'); inpUser.value = ''; inpSandbox.value = ''; }
  } catch (err) { showToast('网络错误: ' + err.message, 'error'); }
  finally { setLoading(btnAssign, false); }
});

async function doConnect(userId) {
  const btn = document.getElementById('btn-cn-' + userId);
  if (btn) setLoading(btn, true);
  try {
    const res = await fetch('/api/user/' + encodeURIComponent(userId) + '/connect', { method: 'POST' });
    const data = await res.json();
    if (data.error) showToast(userId + ' 连接失败: ' + data.error, 'error');
    else showToast(userId + ' 已连接', 'success');
  } catch (err) { showToast('网络错误: ' + err.message, 'error'); }
}
async function doDisconnect(userId) {
  const btn = document.getElementById('btn-dc-' + userId);
  if (btn) setLoading(btn, true);
  try {
    const res = await fetch('/api/user/' + encodeURIComponent(userId) + '/disconnect', { method: 'POST' });
    const data = await res.json();
    if (data.error) showToast(userId + ' 断开失败: ' + data.error, 'error');
    else showToast(userId + ' 已断开', 'success');
  } catch (err) { showToast('网络错误: ' + err.message, 'error'); }
}
function doUnassign(userId) {
  if (!confirm('确定解绑用户 ' + userId + '？')) return;
  fetch('/api/admin/unassign', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ userId })
  }).then(r => r.json()).then(data => {
    if (data.error) showToast('解绑失败: ' + data.error, 'error');
    else showToast(userId + ' 已解绑', 'success');
  }).catch(err => showToast('网络错误: ' + err.message, 'error'));
}
function esc(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }
`;

// ---------------------------------------------------------------------------
// 聊天界面 HTML
// ---------------------------------------------------------------------------

function getChatHtml(userId: string): string {
  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Chat — ${userId}</title>
  <style>${CHAT_CSS}</style>
</head>
<body>
  ${CHAT_HTML_BODY}
  <script>const CURRENT_USER = ${JSON.stringify(userId)};</script>
  <script>${CHAT_JS}</script>
</body>
</html>`;
}

const CHAT_CSS = `* { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --bg: #0f1117; --surface: #1a1d27; --surface2: #22263a; --border: #2e3250;
  --text: #e2e8f0; --text-muted: #94a3b8; --accent: #6366f1; --accent-hover: #818cf8;
  --danger: #ef4444; --success: #22c55e; --warning: #f59e0b; --radius: 8px;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}
body { background: var(--bg); color: var(--text); height: 100vh; overflow: hidden; }
.chat-app { display: flex; flex-direction: column; height: 100vh; max-width: 900px; margin: 0 auto; padding: 12px 16px; }
.chat-header { display: flex; align-items: center; gap: 10px; padding-bottom: 10px; border-bottom: 1px solid var(--border); flex-shrink: 0; }
.chat-header h2 { font-size: 1rem; font-weight: 700; }
.chat-header .user-tag { font-size: 0.75rem; color: var(--accent); background: rgba(99,102,241,.12); padding: 2px 8px; border-radius: 999px; font-weight: 600; }
.status-bar { display: flex; align-items: center; gap: 6px; padding: 8px 0; font-size: 0.78rem; color: var(--text-muted); flex-shrink: 0; }
.status-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--text-muted); transition: background 0.3s; }
.status-dot.connected { background: var(--success); box-shadow: 0 0 6px rgba(34,197,94,.5); }
.status-dot.connecting { background: var(--warning); animation: pulse 1s infinite; }
.status-dot.error { background: var(--danger); }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }
.chat-messages { flex: 1; overflow-y: auto; padding: 12px 0; display: flex; flex-direction: column; gap: 10px; min-height: 0; }
.chat-empty { display: flex; align-items: center; justify-content: center; height: 100%; color: var(--text-muted); font-size: 0.85rem; text-align: center; line-height: 1.6; }
.chat-msg { display: flex; flex-direction: column; max-width: 80%; animation: msgIn 0.2s ease-out; }
@keyframes msgIn { from{opacity:0;transform:translateY(6px)} to{opacity:1;transform:translateY(0)} }
.chat-msg.user { align-self: flex-end; }
.chat-msg.assistant { align-self: flex-start; }
.msg-role { font-size: 0.65rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-muted); margin-bottom: 3px; padding: 0 4px; }
.chat-msg.user .msg-role { text-align: right; }
.msg-bubble { padding: 10px 14px; border-radius: 12px; font-size: 0.82rem; line-height: 1.6; word-break: break-word; white-space: pre-wrap; }
.chat-msg.user .msg-bubble { background: rgba(99,102,241,.2); border: 1px solid rgba(99,102,241,.3); border-bottom-right-radius: 4px; }
.chat-msg.assistant .msg-bubble { background: var(--surface2); border: 1px solid var(--border); border-bottom-left-radius: 4px; }
.chat-msg.assistant.streaming .msg-bubble::after { content: '▌'; color: var(--accent); animation: blink 0.8s step-end infinite; margin-left: 1px; }
@keyframes blink { 50%{opacity:0} }
.tool-card { margin: 6px 0; border-left: 3px solid var(--accent); background: rgba(99,102,241,.06); border-radius: 0 var(--radius) var(--radius) 0; overflow: hidden; font-size: 0.78rem; }
.tool-header { display: flex; align-items: center; gap: 6px; padding: 6px 10px; cursor: pointer; user-select: none; }
.tool-header:hover { background: rgba(99,102,241,.1); }
.tool-icon { font-size: 0.7rem; transition: transform 0.2s; }
.tool-card.expanded .tool-icon { transform: rotate(90deg); }
.tool-name { font-weight: 600; color: var(--accent); font-family: 'SF Mono','Fira Code',monospace; font-size: 0.75rem; }
.tool-status { margin-left: auto; font-size: 0.65rem; color: var(--text-muted); }
.tool-status.running { color: var(--warning); }
.tool-status.done { color: var(--success); }
.tool-body { display: none; padding: 0 10px 8px; }
.tool-card.expanded .tool-body { display: block; }
.tool-section-label { font-size: 0.65rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-muted); margin: 6px 0 3px; }
.tool-json { background: var(--bg); border: 1px solid var(--border); border-radius: 4px; padding: 6px 8px; font-family: 'SF Mono','Fira Code',monospace; font-size: 0.7rem; color: var(--text-muted); overflow-x: auto; max-height: 120px; overflow-y: auto; white-space: pre-wrap; word-break: break-all; }
.chat-usage { display: inline-flex; gap: 10px; padding: 4px 8px; margin-top: 4px; font-size: 0.65rem; color: var(--text-muted); background: rgba(148,163,184,.08); border-radius: 4px; font-family: 'SF Mono','Fira Code',monospace; }
.chat-input-area { display: flex; gap: 8px; align-items: flex-end; padding-top: 10px; border-top: 1px solid var(--border); flex-shrink: 0; }
.chat-input { flex: 1; background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius); color: var(--text); font-size: 0.82rem; padding: 8px 12px; outline: none; resize: vertical; min-height: 38px; max-height: 120px; line-height: 1.5; font-family: inherit; transition: border-color 0.15s; }
.chat-input:focus { border-color: var(--accent); }
.chat-input::placeholder { color: var(--text-muted); }
.chat-input:disabled { opacity: 0.4; }
.btn-send { padding: 8px 16px; font-size: 0.82rem; font-weight: 600; border: none; border-radius: var(--radius); cursor: pointer; transition: background 0.15s; white-space: nowrap; flex-shrink: 0; min-height: 38px; }
.btn-send.send { background: var(--accent); color: #fff; }
.btn-send.send:hover { background: var(--accent-hover); }
.btn-send.stop { background: var(--danger); color: #fff; }
.btn-send.stop:hover { background: #f87171; }
.btn-send:disabled { opacity: 0.4; cursor: not-allowed; }
.error-page { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; gap: 12px; text-align: center; }
.error-page .error-icon { font-size: 3rem; opacity: 0.6; }
.error-page .error-title { font-size: 1.1rem; font-weight: 700; color: var(--text); }
.error-page .error-desc { font-size: 0.82rem; color: var(--text-muted); max-width: 400px; line-height: 1.6; }
.error-page .btn-retry { margin-top: 8px; padding: 8px 20px; background: var(--accent); color: #fff; border: none; border-radius: var(--radius); font-size: 0.82rem; font-weight: 600; cursor: pointer; transition: background 0.15s; }
.error-page .btn-retry:hover { background: var(--accent-hover); }
.reconnect-bar { display: none; align-items: center; gap: 6px; padding: 6px 12px; background: rgba(245,158,11,.1); border: 1px solid rgba(245,158,11,.2); border-radius: var(--radius); font-size: 0.75rem; color: #fcd34d; margin-top: 4px; }
.reconnect-bar.visible { display: flex; }
.reconnect-bar .reconnect-spinner { width: 12px; height: 12px; border: 2px solid rgba(245,158,11,.3); border-top-color: #fcd34d; border-radius: 50%; animation: spin 0.6s linear infinite; }
@keyframes spin { to{transform:rotate(360deg)} }
::-webkit-scrollbar { width: 6px; } ::-webkit-scrollbar-track { background: transparent; } ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
.token-panel { display: none; flex-direction: column; align-items: center; justify-content: center; flex: 1; min-height: 0; padding: 20px; }
.token-panel.visible { display: flex; }
.token-panel-inner { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 32px; max-width: 420px; width: 100%; text-align: center; }
.token-icon { font-size: 2.5rem; margin-bottom: 12px; }
.token-title { font-size: 1rem; font-weight: 700; margin-bottom: 8px; }
.token-desc { font-size: 0.78rem; color: var(--text-muted); line-height: 1.5; margin-bottom: 18px; }
.token-input { width: 100%; background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius); color: var(--text); font-size: 0.85rem; padding: 10px 14px; outline: none; font-family: 'SF Mono','Fira Code',monospace; transition: border-color 0.15s; }
.token-input:focus { border-color: var(--accent); }
.token-input::placeholder { color: var(--text-muted); }
.token-actions { display: flex; align-items: center; justify-content: space-between; margin-top: 14px; gap: 12px; }
.token-remember { font-size: 0.75rem; color: var(--text-muted); display: flex; align-items: center; gap: 5px; cursor: pointer; user-select: none; }
.token-remember input { accent-color: var(--accent); }
.btn-connect { background: var(--accent); color: #fff; border: none; border-radius: var(--radius); padding: 8px 24px; font-size: 0.82rem; font-weight: 600; cursor: pointer; transition: background 0.15s; }
.btn-connect:hover { background: var(--accent-hover); }
.btn-connect:disabled { opacity: 0.5; cursor: not-allowed; }
.token-error { margin-top: 12px; font-size: 0.75rem; color: var(--danger); min-height: 1.2em; }
.token-panel.visible ~ .chat-messages { display: none; }
.token-panel.visible ~ .chat-input-area { display: none; }`;

const CHAT_HTML_BODY = `<div class="chat-app">
  <div class="chat-header">
    <h2>🦞 OpenClaw Chat</h2>
    <span id="user-tag" class="user-tag"></span>
  </div>
  <div class="status-bar">
    <span id="status-dot" class="status-dot"></span>
    <span id="status-text">正在连接...</span>
  </div>
  <div id="reconnect-bar" class="reconnect-bar">
    <span class="reconnect-spinner"></span>
    <span id="reconnect-text">正在重新连接...</span>
  </div>
  <div id="token-panel" class="token-panel">
    <div class="token-panel-inner">
      <div class="token-icon">🔑</div>
      <h3 class="token-title">输入 Gateway Token</h3>
      <p class="token-desc">请输入 OpenClaw Gateway 的认证 Token（对应 openclaw.json 中 gateway.auth.token 的值）</p>
      <input id="token-input" class="token-input" type="password" placeholder="粘贴你的 Token..." autocomplete="off" />
      <div class="token-actions">
        <label class="token-remember"><input id="token-remember" type="checkbox" checked /> 记住 Token</label>
        <button id="btn-connect" class="btn-connect">连接</button>
      </div>
      <p id="token-error" class="token-error"></p>
    </div>
  </div>
  <div id="chat-messages" class="chat-messages">
    <div class="chat-empty">正在连接到你的沙箱...</div>
  </div>
  <div class="chat-input-area">
    <textarea id="chat-input" class="chat-input" rows="1"
              placeholder="输入消息... (Enter 发送, Shift+Enter 换行)"
              disabled></textarea>
    <button id="btn-send" class="btn-send send" disabled>发送</button>
  </div>
</div>`;

const CHAT_JS = `
// CURRENT_USER 在 HTML 中通过 <script> 注入

const statusDot = document.getElementById('status-dot');
const statusTextEl = document.getElementById('status-text');
const userTag = document.getElementById('user-tag');
const chatMessages = document.getElementById('chat-messages');
const chatInput = document.getElementById('chat-input');
const btnSend = document.getElementById('btn-send');
const reconnectBar = document.getElementById('reconnect-bar');
const reconnectText = document.getElementById('reconnect-text');
const tokenPanel = document.getElementById('token-panel');
const tokenInput = document.getElementById('token-input');
const tokenRemember = document.getElementById('token-remember');
const btnConnect = document.getElementById('btn-connect');
const tokenError = document.getElementById('token-error');

const MAX_MESSAGES = 100;
let reconnectAttempt = 0;

userTag.textContent = CURRENT_USER;

// ─── 聊天状态 ───

const chatState = {
  ws: null,
  connected: false,
  authenticated: false,
  connectReqId: null,
  sessionKey: 'agent:default:main',
  currentRunId: null,
  isStreaming: false,
  sandboxStatus: 'idle',
  pendingReqCallbacks: {},
  openclawToken: '',
};

let msgIdCounter = 0;
function nextMsgId() { return 'msg-' + (++msgIdCounter) + '-' + Date.now(); }

// ─── Token 本地存储 ───

const TOKEN_STORAGE_KEY = 'openclaw_token_' + CURRENT_USER;

function getSavedToken() {
  try { return localStorage.getItem(TOKEN_STORAGE_KEY) || ''; } catch { return ''; }
}
function saveToken(t) {
  try { localStorage.setItem(TOKEN_STORAGE_KEY, t); } catch {}
}
function clearSavedToken() {
  try { localStorage.removeItem(TOKEN_STORAGE_KEY); } catch {}
}

// 从 localStorage 恢复上次的 token
const savedToken = getSavedToken();
if (savedToken) tokenInput.value = savedToken;

// 显示 token 输入面板
function showTokenPanel(errorMsg) {
  tokenPanel.classList.add('visible');
  tokenError.textContent = errorMsg || '';
  tokenInput.focus();
  btnConnect.disabled = false;
  btnConnect.textContent = '连接';
}

// 隐藏 token 输入面板
function hideTokenPanel() {
  tokenPanel.classList.remove('visible');
  tokenError.textContent = '';
}

// 连接按钮点击
btnConnect.addEventListener('click', () => {
  const t = tokenInput.value.trim();
  if (!t) { tokenError.textContent = '请输入 Token'; tokenInput.focus(); return; }
  tokenError.textContent = '';
  btnConnect.disabled = true;
  btnConnect.textContent = '连接中...';
  chatState.openclawToken = t;
  if (tokenRemember.checked) saveToken(t);
  else clearSavedToken();
  hideTokenPanel();
  startWsConnection();
});

// 输入框回车也可触发连接
tokenInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') { e.preventDefault(); btnConnect.click(); }
});

// ─── 通过 SSE 监听沙箱状态 ───

const es = new EventSource('/api/user/' + encodeURIComponent(CURRENT_USER) + '/events');
es.onmessage = e => {
  const data = JSON.parse(e.data);
  chatState.sandboxStatus = data.status;
  updateStatusBar(data.status, data.error);
  updateUI();

  // 沙箱变为 running 时，如果已有 token 则自动连接，否则显示 token 面板
  if (data.status === 'running' && !chatState.ws) {
    if (chatState.openclawToken) {
      startWsConnection();
    } else if (getSavedToken()) {
      chatState.openclawToken = getSavedToken();
      startWsConnection();
    } else {
      showTokenPanel();
    }
  }
  // 沙箱停止时断开 WebSocket
  if (data.status !== 'running' && chatState.ws) {
    chatState.ws.close();
  }
};

// 初始拉取状态
fetch('/api/user/' + encodeURIComponent(CURRENT_USER) + '/status')
  .then(r => r.json())
  .then(data => {
    // 用户未分配沙箱时显示友好错误页面
    if (!data.sandboxId) {
      showErrorPage('🦞', '未分配沙箱', '管理员还没有为你分配 OpenClaw 沙箱。\\n请联系管理员在管理面板中完成分配。');
      return;
    }

    chatState.sandboxStatus = data.status;
    updateStatusBar(data.status, data.error);

    if (data.status === 'idle') {
      // 尝试自动连接
      updateStatusBar('connecting');
      fetch('/api/user/' + encodeURIComponent(CURRENT_USER) + '/connect', { method: 'POST' })
        .then(r => r.json())
        .then(resp => {
          if (resp.error) updateStatusBar('error', resp.error);
        })
        .catch(err => updateStatusBar('error', err.message));
    } else if (data.status === 'running') {
      if (chatState.openclawToken) {
        startWsConnection();
      } else if (getSavedToken()) {
        chatState.openclawToken = getSavedToken();
        startWsConnection();
      } else {
        showTokenPanel();
      }
    }
  })
  .catch(err => {
    showErrorPage('⚠️', '连接失败', '无法连接到服务器: ' + err.message);
  });

function showErrorPage(icon, title, desc) {
  chatMessages.innerHTML = '<div class="error-page"><span class="error-icon">' + icon + '</span><span class="error-title">' + esc(title) + '</span><span class="error-desc">' + esc(desc) + '</span><button class="btn-retry" onclick="location.reload()">🔄 重试</button></div>';
}

function updateStatusBar(status, error) {
  statusDot.className = 'status-dot';
  if (status === 'running' && chatState.authenticated) {
    statusDot.classList.add('connected');
    statusTextEl.textContent = '已连接';
  } else if (status === 'running' && chatState.openclawToken) {
    statusDot.classList.add('connecting');
    statusTextEl.textContent = '沙箱就绪，正在握手...';
  } else if (status === 'running') {
    statusDot.classList.add('connecting');
    statusTextEl.textContent = '沙箱就绪，请输入 Token 连接';
  } else if (status === 'connecting') {
    statusDot.classList.add('connecting');
    statusTextEl.textContent = error || '正在连接沙箱...';
  } else if (status === 'error') {
    statusDot.classList.add('error');
    statusTextEl.textContent = '连接失败: ' + (error || '未知错误');
  } else {
    statusTextEl.textContent = '等待沙箱就绪...';
  }
}

// ════════════════════════════════════════════════════════════
// WebSocket 连接 — 浏览器通过中心服务代理到用户自己的沙箱
// ════════════════════════════════════════════════════════════
//
//   浏览器                  中心服务                    沙箱
//   ──────                  ────────                    ────
//     │                        │                         │
//     │ ws://host/sandbox/alice/ │                         │
//     │──── WS upgrade ────────▶│                         │
//     │                        │── proxy.ws() ──────────▶│
//     │                        │   (注入 X-Access-Token)  │
//     │                        │◀───── WS established ───│
//     │◀──── WS established ───│                         │
//     │                        │                         │
//     │ { connect.challenge }  │                         │
//     │◀───────────────────────│◀────────────────────────│
//     │                        │                         │
//     │ { connect req+token }  │                         │
//     │───────────────────────▶│────────────────────────▶│
//     │                        │                         │
//     │ { connect res ok }     │                         │
//     │◀───────────────────────│◀────────────────────────│
//     │                        │                         │
//     │ { chat.send }          │                         │
//     │───────────────────────▶│────────────────────────▶│
//     │                        │                         │
//     │ { agent stream delta } │                         │
//     │◀───────────────────────│◀────────────────────────│
//

async function startWsConnection() {
  const token = chatState.openclawToken;
  if (!token) {
    showTokenPanel('请先输入 Token');
    return;
  }

  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  // 关键路由：/sandbox/:userId/ — 中心服务根据 userId 选择对应的 proxy
  const wsUrl = proto + '//' + location.host + '/sandbox/' + encodeURIComponent(CURRENT_USER) + '/';

  chatState.ws = new WebSocket(wsUrl);
  chatState.connected = false;
  chatState.authenticated = false;

  chatState.ws.onopen = () => {
    chatState.connected = true;
    reconnectAttempt = 0;
    reconnectBar.classList.remove('visible');
    updateStatusBar('connecting', '已连接，等待握手...');
  };

  chatState.ws.onmessage = (evt) => {
    let data;
    try { data = JSON.parse(evt.data); } catch { return; }
    handleWsMessage(data, token);
  };

  chatState.ws.onclose = () => {
    const wasAuthenticated = chatState.authenticated;
    chatState.ws = null;
    chatState.connected = false;
    chatState.authenticated = false;
    chatState.isStreaming = false;
    chatState.currentRunId = null;
    updateUI();
    // 如果沙箱还在运行且有有效 token，尝试重连（带递增延时）
    if (chatState.sandboxStatus === 'running' && chatState.openclawToken && wasAuthenticated) {
      reconnectAttempt++;
      const delay = Math.min(3000 * reconnectAttempt, 30000);
      reconnectBar.classList.add('visible');
      reconnectText.textContent = '正在重新连接... (第 ' + reconnectAttempt + ' 次, ' + (delay/1000) + 's 后)';
      setTimeout(startWsConnection, delay);
    }
  };

  chatState.ws.onerror = () => {};
}

// ─── WebSocket 消息处理 ───

function handleWsMessage(data, token) {
  if (data.type === 'event' && data.event === 'tick') return;

  // connect.challenge → 自动发送 connect 握手
  if (data.type === 'event' && data.event === 'connect.challenge') {
    sendConnectRequest(token);
    return;
  }

  if (data.type === 'res') {
    const cb = chatState.pendingReqCallbacks[data.id];
    if (cb) {
      delete chatState.pendingReqCallbacks[data.id];
      if (data.ok === false || data.error) {
        cb.reject(data.error || { message: 'Request failed' });
      } else {
        cb.resolve(data.payload || data.result || data);
      }
    }

    if (!chatState.authenticated &&
        (data.id === chatState.connectReqId ||
         data.method === 'connect' ||
         (data.result && data.result.protocol) ||
         (data.payload && data.payload.protocol))) {
      chatState.authenticated = true;
      updateStatusBar('running');
      clearChatMessages();
      loadChatHistory();
      updateUI();
    }
    return;
  }

  if (data.type === 'event') {
    const p = data.payload || {};

    // ── agent 事件（OpenClaw 核心流式协议） ──
    if (data.event === 'agent') {
      const stream = p.stream;
      const d = p.data || {};
      if (stream === 'assistant' && d.delta !== undefined) {
        updateStreamingBubble(d.delta, false);
      } else if (stream === 'lifecycle') {
        if (d.phase === 'end') handleChatDone(p);
        else if (d.phase === 'error') handleChatError({ message: d.error || d.message || 'Agent error' });
      } else if (stream === 'tool_call') {
        handleToolCall(d);
      } else if (stream === 'tool_result') {
        handleToolResult(d);
      }
      return;
    }

    // ── chat 事件（聊天状态同步，避免重复处理） ──
    if (data.event === 'chat') {
      return;
    }

    // ── 兼容旧式事件名 ──
    switch (data.event) {
      case 'chat.delta':
        if (p.delta !== undefined) updateStreamingBubble(p.delta, false);
        break;
      case 'tool.call':
        handleToolCall(p);
        break;
      case 'tool.result':
        handleToolResult(p);
        break;
      case 'chat.done':
        handleChatDone(p);
        break;
      case 'chat.error':
        handleChatError(p);
        break;
    }
  }
}

function sendConnectRequest(token) {
  const id = nextMsgId();
  const req = {
    type: 'req', id, method: 'connect',
    params: {
      minProtocol: 3, maxProtocol: 3,
      client: { id: 'openclaw-control-ui', version: 'control-ui', platform: navigator.platform || 'unknown', mode: 'webchat', instanceId: crypto.randomUUID() },
      role: 'operator',
      scopes: ['operator.admin','operator.read','operator.write','operator.approvals','operator.pairing'],
      caps: ['tool-events'],
      auth: { token },
      userAgent: navigator.userAgent,
      locale: navigator.language || 'en'
    }
  };
  wsSend(req);
  chatState.connectReqId = id;
  chatState.pendingReqCallbacks[id] = {
    resolve: () => {
      chatState.authenticated = true;
      updateStatusBar('running');
      clearChatMessages();
      loadChatHistory();
      updateUI();
    },
    reject: (err) => {
      const errMsg = err.message || JSON.stringify(err);
      updateStatusBar('error', '握手失败: ' + errMsg);
      // 握手失败（含 token 无效），清空 token 并回到输入面板
      chatState.openclawToken = '';
      clearSavedToken();
      chatState.sandboxStatus = 'running'; // 沙箱本身还是 running 的
      if (chatState.ws) { chatState.ws.close(); }
      showTokenPanel('认证失败: ' + errMsg + '\\n请检查 Token 是否正确');
    }
  };
}

function wsSend(data) {
  if (chatState.ws && chatState.ws.readyState === WebSocket.OPEN) {
    chatState.ws.send(JSON.stringify(data));
  }
}

// ─── 发送消息 ───

btnSend.addEventListener('click', () => {
  chatState.isStreaming ? chatAbort() : chatSend();
});

chatInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    if (!btnSend.disabled && !chatState.isStreaming) chatSend();
  }
});

chatInput.addEventListener('input', () => {
  chatInput.style.height = 'auto';
  chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + 'px';
});

function chatSend() {
  const text = chatInput.value.trim();
  if (!text || !chatState.authenticated) return;
  addUserMessage(text);
  chatInput.value = '';
  chatInput.style.height = 'auto';

  const id = nextMsgId();
  wsSend({
    type: 'req', id, method: 'chat.send',
    params: { message: text, sessionKey: chatState.sessionKey, deliver: false, idempotencyKey: crypto.randomUUID() }
  });

  chatState.pendingReqCallbacks[id] = {
    resolve: (result) => {
      const runId = result && (result.runId || (result.payload && result.payload.runId));
      if (runId) chatState.currentRunId = runId;
      chatState.isStreaming = true;
      updateUI();
    },
    reject: (err) => addSystemMessage('❌ 发送失败: ' + (err.message || JSON.stringify(err)))
  };
}

function chatAbort() {
  if (!chatState.currentRunId) return;
  wsSend({ type: 'req', id: nextMsgId(), method: 'chat.abort', params: { sessionKey: chatState.sessionKey } });
  chatState.isStreaming = false;
  chatState.currentRunId = null;
  updateStreamingBubble(null, true);
  updateUI();
}

function loadChatHistory() {
  const id = nextMsgId();
  wsSend({ type: 'req', id, method: 'chat.history', params: { sessionKey: chatState.sessionKey, limit: 50 } });
  chatState.pendingReqCallbacks[id] = {
    resolve: (result) => {
      if (result && Array.isArray(result.messages)) {
        result.messages.forEach(msg => {
          const text = extractContentText(msg.content);
          if (msg.role === 'user') addUserMessage(text, true);
          else if (msg.role === 'assistant') addAssistantMessage(text, true);
        });
      }
    },
    reject: () => {}
  };
}

// 从 content 中提取纯文本 — content 可能是字符串、对象数组 [{type:'text',text:'...'}] 或对象
function extractContentText(content) {
  if (!content) return '';
  if (typeof content === 'string') return content;
  if (Array.isArray(content)) {
    return content
      .filter(block => block && block.type === 'text' && block.text)
      .map(block => block.text)
      .join('\\n');
  }
  if (typeof content === 'object') {
    if (content.text) return content.text;
    return JSON.stringify(content, null, 2);
  }
  return String(content);
}

// ─── 消息渲染 ───

let currentStreamBubble = null;
let currentStreamText = '';

function clearChatMessages() {
  chatMessages.innerHTML = '';
  currentStreamBubble = null;
  currentStreamText = '';
}

function addUserMessage(text, isHistory) {
  removeEmpty();
  const el = document.createElement('div');
  el.className = 'chat-msg user';
  el.innerHTML = '<div class="msg-role">You</div><div class="msg-bubble"></div>';
  el.querySelector('.msg-bubble').textContent = typeof text === 'string' ? text : extractContentText(text);
  chatMessages.appendChild(el);
  trimMessages();
  if (!isHistory) scrollBottom();
}

function addAssistantMessage(text, isHistory) {
  removeEmpty();
  const el = document.createElement('div');
  el.className = 'chat-msg assistant';
  el.innerHTML = '<div class="msg-role">Assistant</div><div class="msg-bubble"></div>';
  el.querySelector('.msg-bubble').textContent = typeof text === 'string' ? text : extractContentText(text);
  chatMessages.appendChild(el);
  trimMessages();
  if (!isHistory) scrollBottom();
}

function addSystemMessage(text) {
  removeEmpty();
  const el = document.createElement('div');
  el.className = 'chat-msg assistant';
  el.innerHTML = '<div class="msg-role">System</div><div class="msg-bubble"></div>';
  el.querySelector('.msg-bubble').textContent = text;
  chatMessages.appendChild(el);
  trimMessages();
  scrollBottom();
}

function trimMessages() {
  let msgs = chatMessages.querySelectorAll('.chat-msg');
  while (msgs.length > MAX_MESSAGES) {
    msgs[0].remove();
    msgs = chatMessages.querySelectorAll('.chat-msg');
  }
}

function removeEmpty() {
  const e = chatMessages.querySelector('.chat-empty');
  if (e) e.remove();
}

function getOrCreateStreamBubble() {
  if (currentStreamBubble) return currentStreamBubble;
  removeEmpty();
  const el = document.createElement('div');
  el.className = 'chat-msg assistant streaming';
  el.innerHTML = '<div class="msg-role">Assistant</div><div class="msg-bubble"></div>';
  chatMessages.appendChild(el);
  currentStreamBubble = el;
  currentStreamText = '';
  return el;
}

function updateStreamingBubble(text, finish) {
  if (text !== null && text !== undefined) {
    const bubble = getOrCreateStreamBubble();
    currentStreamText += text;
    bubble.querySelector('.msg-bubble').textContent = currentStreamText;
    scrollBottom();
  }
  if (finish && currentStreamBubble) {
    currentStreamBubble.classList.remove('streaming');
    currentStreamBubble = null;
    currentStreamText = '';
  }
}

function handleToolCall(payload) {
  if (!payload) return;
  const card = document.createElement('div');
  card.className = 'tool-card';
  card.dataset.toolCallId = payload.id || '';
  card.dataset.tool = payload.tool || payload.name || 'unknown';
  const ps = payload.params ? JSON.stringify(payload.params, null, 2) : payload.arguments ? JSON.stringify(payload.arguments, null, 2) : '{}';
  card.innerHTML = '<div class="tool-header"><span class="tool-icon">▶</span><span class="tool-name">' + esc(payload.tool || payload.name || 'tool') + '</span><span class="tool-status running">running...</span></div><div class="tool-body"><div class="tool-section-label">Parameters</div><pre class="tool-json">' + esc(ps) + '</pre><div class="tool-section-label" style="display:none">Result</div><pre class="tool-json tool-result-json" style="display:none"></pre></div>';
  card.querySelector('.tool-header').addEventListener('click', () => card.classList.toggle('expanded'));
  const bubble = getOrCreateStreamBubble();
  bubble.appendChild(card);
  scrollBottom();
}

function handleToolResult(payload) {
  if (!payload) return;
  const tid = payload.id || '';
  const tn = payload.tool || payload.name || '';
  const cards = chatMessages.querySelectorAll('.tool-card');
  let card = null;
  for (let i = cards.length - 1; i >= 0; i--) {
    if ((tid && cards[i].dataset.toolCallId === tid) || (tn && cards[i].dataset.tool === tn)) { card = cards[i]; break; }
  }
  if (!card) for (let i = cards.length - 1; i >= 0; i--) { const s = cards[i].querySelector('.tool-status'); if (s && s.classList.contains('running')) { card = cards[i]; break; } }
  if (!card) return;
  const st = card.querySelector('.tool-status');
  st.textContent = 'done'; st.classList.remove('running'); st.classList.add('done');
  const rl = card.querySelectorAll('.tool-section-label')[1];
  const rj = card.querySelector('.tool-result-json');
  if (rl && rj) { rl.style.display = ''; rj.style.display = ''; rj.textContent = payload.result ? JSON.stringify(payload.result, null, 2) : payload.output || '(no result)'; }
}

function handleChatDone(payload) {
  chatState.isStreaming = false;
  chatState.currentRunId = null;
  updateStreamingBubble(null, true);
  const d = (payload && payload.data) || payload || {};
  const u = d.usage || (payload && payload.usage);
  if (u) {
    const el = document.createElement('div');
    el.className = 'chat-usage';
    el.textContent = 'prompt: ' + (u.promptTokens||u.prompt_tokens||0) + '  completion: ' + (u.completionTokens||u.completion_tokens||0) + '  total: ' + (u.totalTokens||u.total_tokens||0);
    const msgs = chatMessages.querySelectorAll('.chat-msg.assistant');
    if (msgs.length) msgs[msgs.length-1].appendChild(el);
  }
  updateUI();
  scrollBottom();
}

function handleChatError(payload) {
  chatState.isStreaming = false;
  chatState.currentRunId = null;
  updateStreamingBubble(null, true);
  const errMsg = (payload && typeof payload.message === 'string') ? payload.message
               : (payload ? JSON.stringify(payload) : 'Unknown error');
  addSystemMessage('❌ Error: ' + errMsg);
  updateUI();
}

function scrollBottom() { requestAnimationFrame(() => { chatMessages.scrollTop = chatMessages.scrollHeight; }); }
function esc(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

function updateUI() {
  const ok = chatState.authenticated;
  chatInput.disabled = !ok;
  btnSend.disabled = !ok;
  if (chatState.isStreaming) {
    btnSend.textContent = '⏹ 停止';
    btnSend.className = 'btn-send stop';
    btnSend.disabled = false;
  } else {
    btnSend.textContent = '发送';
    btnSend.className = 'btn-send send';
    btnSend.disabled = !ok;
  }
}
`;

// ---------------------------------------------------------------------------
// Express 应用
// ---------------------------------------------------------------------------

const manager = new SandboxManager();
const app = express();
app.use(cors());
app.use(express.json());

// ─── 管理员界面 ───

app.get('/', (_req, res) => {
  res.setHeader('Content-Type', 'text/html');
  res.send(getAdminHtml());
});

// ─── 管理员 API ───

app.get('/api/admin/status', (_req, res) => {
  res.json({ assignments: manager.getAllAssignments() });
});

app.get('/api/admin/events', (req, res) => {
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.flushHeaders();
  res.write(`data: ${JSON.stringify({ assignments: manager.getAllAssignments() })}\n\n`);
  manager.addAdminSseClient(res);
  req.on('close', () => manager.removeAdminSseClient(res));
});

app.post('/api/admin/assign', (req, res) => {
  const { userId, sandboxId } = req.body;
  if (!userId || !sandboxId) {
    res.status(400).json({ error: '缺少 userId 或 sandboxId' });
    return;
  }
  manager.assign(userId, sandboxId);
  res.json({ ok: true });
});

app.post('/api/admin/unassign', (req, res) => {
  const { userId } = req.body;
  if (!userId) {
    res.status(400).json({ error: '缺少 userId' });
    return;
  }
  manager.unassign(userId);
  res.json({ ok: true });
});

// ─── 用户聊天页面 ───

app.get('/chat', (req, res) => {
  const userId = req.query.user as string;
  if (!userId) {
    res.status(400).send('缺少 ?user= 参数');
    return;
  }
  res.setHeader('Content-Type', 'text/html');
  res.send(getChatHtml(userId));
});

// ─── 用户 API ───

app.get('/api/user/:userId/status', (req, res) => {
  const userId = req.params.userId;
  res.json(manager.getUserStatus(userId));
});

app.get('/api/user/:userId/events', (req, res) => {
  const userId = req.params.userId;
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.flushHeaders();
  res.write(`data: ${JSON.stringify(manager.getUserStatus(userId))}\n\n`);
  manager.addUserSseClient(userId, res);
  req.on('close', () => manager.removeUserSseClient(userId, res));
});

app.get('/api/user/:userId/chat-config', (req, res) => {
  const userId = req.params.userId;
  const userStatus = manager.getUserStatus(userId);
  if (!userStatus.sandboxId) {
    res.status(404).json({ error: `用户 ${userId} 未分配沙箱` });
    return;
  }
  res.json({
    userId,
    wsUrl: `/sandbox/${encodeURIComponent(userId)}/`,
    status: userStatus.status,
  });
});

app.post('/api/user/:userId/connect', async (req, res) => {
  const userId = req.params.userId;
  try {
    await manager.connectUser(userId);
    res.json({ ok: true });
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

app.post('/api/user/:userId/disconnect', (req, res) => {
  const userId = req.params.userId;
  manager.disconnectUser(userId);
  res.json({ ok: true });
});

// ─── 沙箱代理路由 ───
//
// /sandbox/:userId/* — 按用户 ID 路由 HTTP 请求到对应沙箱的 proxy 实例
//

app.use('/sandbox/:userId', (req, res) => {
  const userId = req.params.userId;
  // 重写 URL：去掉 /sandbox/:userId 前缀
  req.url = req.url || '/';
  manager.proxyHttpRequest(userId, req, res);
});

// ---------------------------------------------------------------------------
// 启动服务器
// ---------------------------------------------------------------------------

const server = app.listen(PORT, () => {
  console.log(`\n🛸 Multi-OpenClaw 多用户沙箱路由中心已启动`);
  console.log(`   管理界面:   http://localhost:${PORT}`);
  console.log(`   聊天入口:   http://localhost:${PORT}/chat?user=<userId>`);
  console.log(`   管理 API:   http://localhost:${PORT}/api/admin/*`);
  console.log(`   用户 API:   http://localhost:${PORT}/api/user/:userId/*`);
  console.log(`   沙箱代理:   http://localhost:${PORT}/sandbox/:userId/*`);
  console.log('   按 Ctrl+C 退出\n');
});

// ─── WebSocket upgrade 路由 ───
//
// 这是整个系统最关键的路由点：
//
// Node.js 的 HTTP server 在收到 WebSocket upgrade 请求时触发 'upgrade' 事件。
// 此事件不经过 Express 路由中间件，必须在 server 级别手动处理。
//
// 流程：
// 1. 浏览器发起 ws://host/sandbox/:userId/ 连接
// 2. server 收到 upgrade 事件
// 3. 从 URL 中解析出 userId
// 4. SandboxManager 查找该用户的 proxy 实例
// 5. 调用 proxy.ws(req, socket, head) 完成 WebSocket 握手和代理
//
// 之后，浏览器 ↔ 中心服务 ↔ 沙箱 之间的 WebSocket 帧将透明双向转发。

server.on('upgrade', (req, socket, head) => {
  manager.handleWsUpgrade(req, socket, head);
});
