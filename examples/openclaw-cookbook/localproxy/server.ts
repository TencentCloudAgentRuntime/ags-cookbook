import 'dotenv/config';
import { config } from 'dotenv';
config({ override: true });
import express from 'express';
import cors from 'cors';
import http from 'http';
import { ags } from 'tencentcloud-sdk-nodejs-ags';
import httpProxy from 'http-proxy';

const AgsClient = ags.v20250920.Client;

// ---------------------------------------------------------------------------
// 常量
// ---------------------------------------------------------------------------

const MANAGEMENT_PORT = 3001;
const OPENCLAW_PORT = 8080;
const LOG_RING_BUFFER_SIZE = 200;

// ---------------------------------------------------------------------------
// 状态机
// ---------------------------------------------------------------------------

type SandboxStatus = 'idle' | 'starting' | 'connecting' | 'running' | 'pausing' | 'paused' | 'resuming' | 'stopping';
type SandboxMode = 'created' | 'connected';

interface SandboxState {
  status: SandboxStatus;
  mode?: SandboxMode;
  sandboxId?: string;
  startedAt?: number;
  logs: string[];
  error?: string;
}

let state: SandboxState = {
  status: 'idle',
  logs: [],
};

function appendLog(msg: string) {
  state.logs.push(`[${new Date().toISOString()}] ${msg}`);
  if (state.logs.length > LOG_RING_BUFFER_SIZE) {
    state.logs = state.logs.slice(-LOG_RING_BUFFER_SIZE);
  }
  broadcast();
  console.log(msg);
}

function setState(patch: Partial<SandboxState>) {
  state = { ...state, ...patch };
  broadcast();
}

// ---------------------------------------------------------------------------
// SSE 广播
// ---------------------------------------------------------------------------

const sseClients = new Set<express.Response>();

function broadcast() {
  const data = JSON.stringify(state);
  for (const res of sseClients) {
    res.write(`data: ${data}\n\n`);
  }
}

// ---------------------------------------------------------------------------
// 代理（挂在 Express /sandbox 路由上）
// ---------------------------------------------------------------------------

let sandboxProxy: ReturnType<typeof httpProxy.createProxyServer> | null = null;
let sandboxWsHandler: ((req: http.IncomingMessage, socket: any, head: Buffer) => void) | null = null;

function startProxyServer(remoteHost: string, accessToken: string): void {
  const proxy = httpProxy.createProxyServer({
    target: `https://${remoteHost}`,
    changeOrigin: true,
    secure: true,
    ws: true,
  });

  proxy.on('proxyReq', (proxyReq, req) => {
    proxyReq.setHeader('X-Access-Token', accessToken);
    appendLog(`Proxying: ${req.method} ${req.url}`);
  });

  proxy.on('proxyReqWs', (proxyReq) => {
    proxyReq.setHeader('X-Access-Token', accessToken);
  });

  proxy.on('proxyRes', (proxyRes) => {
    delete proxyRes.headers['x-frame-options'];
    delete proxyRes.headers['X-Frame-Options'];
    delete proxyRes.headers['content-security-policy'];
    delete proxyRes.headers['Content-Security-Policy'];
  });

  proxy.on('error', (err, _req, res) => {
    appendLog(`Proxy error: ${err.message}`);
    if (res && 'writeHead' in res) {
      (res as http.ServerResponse).writeHead(502);
      (res as http.ServerResponse).end('Bad Gateway: ' + err.message);
    }
  });

  sandboxProxy = proxy;

  // WebSocket upgrade 转发
  sandboxWsHandler = (req, socket, head) => {
    // 只处理 /sandbox 前缀的 upgrade
    if (!req.url?.startsWith('/sandbox')) return;
    req.url = req.url.slice('/sandbox'.length) || '/';
    socket.on('error', (err: Error) => appendLog(`WebSocket error: ${err.message}`));
    proxy.ws(req, socket, head);
  };

  appendLog(`✅ 沙箱代理已挂载到 /sandbox`);
  appendLog(`🌐 OpenClaw Dashboard: http://localhost:${MANAGEMENT_PORT}/sandbox/__openclaw__`);
}

function stopProxyServer(): void {
  if (sandboxProxy) {
    sandboxProxy.close();
    sandboxProxy = null;
  }
  sandboxWsHandler = null;
  appendLog('✅ 沙箱代理已卸载');
}

// ---------------------------------------------------------------------------
// 健康探针
// ---------------------------------------------------------------------------

async function waitForOpenClaw(remoteHost: string, accessToken: string, timeoutMs = 60000): Promise<void> {
  const url = `https://${remoteHost}/`;
  appendLog(`⏳ 等待 OpenClaw 就绪（最多 ${timeoutMs / 1000}s）... ${url}`);
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
        appendLog(`✅ OpenClaw 已就绪（HTTP ${res.status}），共等待 ${attempt} 次探针`);
        return;
      }
    } catch {
      // 网络未通，继续重试
    }
    appendLog(`  探针 #${attempt}...`);
    await new Promise(resolve => setTimeout(resolve, 2000));
  }
  appendLog('⚠️  OpenClaw 启动超时，但仍继续启动代理');
}

// ---------------------------------------------------------------------------
// 并发锁
// ---------------------------------------------------------------------------

let actionInFlight = false;

// ---------------------------------------------------------------------------
// AGS Client + 沙箱工具函数
// ---------------------------------------------------------------------------

function createAgsClient() {
  return new AgsClient({
    credential: {
      secretId: process.env.TENCENTCLOUD_SECRET_ID!,
      secretKey: process.env.TENCENTCLOUD_SECRET_KEY!,
    },
    region: process.env.TENCENTCLOUD_REGION || 'ap-shanghai',
  });
}

function getRemoteHost(instanceId: string, port: number): string {
  const region = process.env.TENCENTCLOUD_REGION || 'ap-shanghai';
  return `${port}-${instanceId}.${region}.tencentags.com`;
}

async function acquireToken(instanceId: string): Promise<string> {
  const client = createAgsClient();
  const resp = await client.AcquireSandboxInstanceToken({ InstanceId: instanceId });
  if (!resp.Token) throw new Error('AcquireSandboxInstanceToken 未返回 Token');
  return resp.Token;
}

// ---------------------------------------------------------------------------
// 内嵌 HTML
// ---------------------------------------------------------------------------

const CSS = `* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

:root {
  --bg: #0f1117;
  --surface: #1a1d27;
  --surface2: #22263a;
  --border: #2e3250;
  --text: #e2e8f0;
  --text-muted: #94a3b8;
  --accent: #6366f1;
  --accent-hover: #818cf8;
  --danger: #ef4444;
  --danger-hover: #f87171;
  --success: #22c55e;
  --warning: #f59e0b;
  --radius: 8px;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

body {
  background: var(--bg);
  color: var(--text);
  min-height: 100vh;
}

/* ── Layout ── */
.app {
  display: grid;
  grid-template-rows: auto 1fr;
  min-height: 100vh;
  max-width: 1400px;
  margin: 0 auto;
  width: 100%;
  padding: 0 16px;
}

.app-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 0;
  border-bottom: 1px solid var(--border);
  margin-bottom: 20px;
}

.app-header h1 {
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--text);
}

.app-header .subtitle {
  font-size: 0.8rem;
  color: var(--text-muted);
}

.app-body {
  display: grid;
  grid-template-columns: 340px 1fr;
  gap: 16px;
  padding-bottom: 24px;
  min-height: 0;
  height: calc(100vh - 90px);
}

.left-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
  overflow-y: auto;
}

/* ── Card ── */
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px;
}

.card-title {
  font-size: 0.7rem;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-muted);
  margin-bottom: 12px;
}

/* ── StatusCard ── */
.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  border: 1px solid transparent;
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
}

.status-idle .status-badge    { background: rgba(148,163,184,.15); border-color: rgba(148,163,184,.3); }
.status-idle .status-dot       { background: var(--text-muted); }

.status-starting .status-badge { background: rgba(245,158,11,.12); border-color: rgba(245,158,11,.4); color: #fcd34d; }
.status-starting .status-dot   { background: var(--warning); animation: pulse 1s infinite; }

.status-connecting .status-badge { background: rgba(245,158,11,.12); border-color: rgba(245,158,11,.4); color: #fcd34d; }
.status-connecting .status-dot   { background: var(--warning); animation: pulse 1s infinite; }

.status-running .status-badge  { background: rgba(34,197,94,.12); border-color: rgba(34,197,94,.4); color: #86efac; }
.status-running .status-dot    { background: var(--success); animation: pulse 1.5s infinite; }

.status-stopping .status-badge { background: rgba(239,68,68,.12); border-color: rgba(239,68,68,.4); color: #fca5a5; }
.status-stopping .status-dot   { background: var(--danger); animation: pulse 1s infinite; }

.status-pausing .status-badge  { background: rgba(245,158,11,.12); border-color: rgba(245,158,11,.4); color: #fcd34d; }
.status-pausing .status-dot    { background: var(--warning); animation: pulse 1s infinite; }

.status-paused .status-badge   { background: rgba(99,102,241,.12); border-color: rgba(99,102,241,.4); color: #a5b4fc; }
.status-paused .status-dot     { background: var(--accent); }

.status-resuming .status-badge { background: rgba(245,158,11,.12); border-color: rgba(245,158,11,.4); color: #fcd34d; }
.status-resuming .status-dot   { background: var(--warning); animation: pulse 1s infinite; }

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.status-info {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.info-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.8rem;
}

.info-label {
  color: var(--text-muted);
}

.info-value {
  color: var(--text);
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 0.75rem;
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.error-box {
  margin-top: 10px;
  padding: 8px 10px;
  background: rgba(239,68,68,.1);
  border: 1px solid rgba(239,68,68,.3);
  border-radius: 6px;
  font-size: 0.75rem;
  color: #fca5a5;
  word-break: break-all;
}

/* ── ActionPanel ── */
.action-buttons {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 9px 16px;
  border-radius: var(--radius);
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
  border: none;
  transition: background 0.15s, opacity 0.15s;
  width: 100%;
}

.btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.btn-primary {
  background: var(--accent);
  color: #fff;
}
.btn-primary:not(:disabled):hover {
  background: var(--accent-hover);
}

.btn-danger {
  background: var(--danger);
  color: #fff;
}
.btn-danger:not(:disabled):hover {
  background: var(--danger-hover);
}

.btn-secondary {
  background: var(--surface2);
  color: var(--text);
  border: 1px solid var(--border);
}
.btn-secondary:not(:disabled):hover {
  background: var(--border);
}

.connect-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 4px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
}

.connect-label {
  font-size: 0.75rem;
  color: var(--text-muted);
}

.connect-input {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text);
  font-size: 0.8rem;
  padding: 8px 10px;
  width: 100%;
  font-family: 'SF Mono', 'Fira Code', monospace;
  outline: none;
  transition: border-color 0.15s;
}

.connect-input:focus {
  border-color: var(--accent);
}

.connect-input::placeholder {
  color: var(--text-muted);
}

/* ── Tab Layout ── */
.right-panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.tab-bar {
  display: flex;
  gap: 0;
  border-bottom: 1px solid var(--border);
  margin-bottom: 0;
  background: var(--surface);
  border-radius: var(--radius) var(--radius) 0 0;
  padding: 0 4px;
  flex-shrink: 0;
}

.tab-btn {
  position: relative;
  padding: 10px 18px;
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--text-muted);
  background: transparent;
  border: none;
  cursor: pointer;
  transition: color 0.2s;
  display: flex;
  align-items: center;
  gap: 6px;
}

.tab-btn:hover {
  color: var(--text);
}

.tab-btn.active {
  color: var(--accent);
}

.tab-btn.active::after {
  content: '';
  position: absolute;
  bottom: -1px;
  left: 8px;
  right: 8px;
  height: 2px;
  background: var(--accent);
  border-radius: 2px 2px 0 0;
}

.tab-btn .tab-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--success);
  display: none;
  animation: pulse 1.5s infinite;
}

.tab-btn .tab-dot.visible {
  display: inline-block;
}

.tab-content {
  flex: 1;
  min-height: 0;
  display: none;
  background: var(--surface);
  border: 1px solid var(--border);
  border-top: none;
  border-radius: 0 0 var(--radius) var(--radius);
  padding: 16px;
  overflow: hidden;
}

.tab-content.active {
  display: flex;
  flex-direction: column;
}

/* ── LogPanel ── */
.log-panel {
  flex: 1;
  overflow-y: auto;
  background: var(--bg);
  border-radius: 6px;
  padding: 10px;
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 0.72rem;
  line-height: 1.6;
  border: 1px solid var(--border);
}

.log-line {
  color: #94a3b8;
  word-break: break-all;
}

.log-line:hover {
  color: var(--text);
}

.log-empty {
  color: var(--text-muted);
  font-style: italic;
  text-align: center;
  padding-top: 20px;
}

.log-header {
  font-size: 0.7rem;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-muted);
  margin-bottom: 8px;
  flex-shrink: 0;
}

/* ── ConsolePanel ── */
.console-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.console-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--accent);
  text-decoration: none;
  padding: 9px 16px;
  border-radius: var(--radius);
  border: 1px solid rgba(99,102,241,.4);
  background: rgba(99,102,241,.08);
  transition: background 0.15s, border-color 0.15s;
  width: fit-content;
}
.console-link:hover {
  background: rgba(99,102,241,.18);
  border-color: rgba(99,102,241,.7);
}
.console-link.disabled {
  opacity: 0.35;
  pointer-events: none;
}

.console-placeholder {
  color: var(--text-muted);
  font-size: 0.85rem;
}

/* ── Chat Panel ── */
.chat-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.chat-connect-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  margin-bottom: 10px;
  flex-shrink: 0;
}

.chat-connect-bar .conn-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text-muted);
  flex-shrink: 0;
  transition: background 0.3s;
}

.chat-connect-bar .conn-dot.connected {
  background: var(--success);
  box-shadow: 0 0 6px rgba(34,197,94,.5);
}

.chat-token-input {
  flex: 1;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text);
  font-size: 0.75rem;
  padding: 6px 8px;
  font-family: 'SF Mono', 'Fira Code', monospace;
  outline: none;
  transition: border-color 0.15s;
  min-width: 0;
}

.chat-token-input:focus {
  border-color: var(--accent);
}

.chat-token-input::placeholder {
  color: var(--text-muted);
}

.chat-conn-btn {
  padding: 6px 14px;
  font-size: 0.75rem;
  font-weight: 600;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s, opacity 0.15s;
  white-space: nowrap;
  flex-shrink: 0;
}

.chat-conn-btn.connect {
  background: var(--accent);
  color: #fff;
}
.chat-conn-btn.connect:hover {
  background: var(--accent-hover);
}

.chat-conn-btn.disconnect {
  background: var(--danger);
  color: #fff;
}
.chat-conn-btn.disconnect:hover {
  background: var(--danger-hover);
}

.chat-conn-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* ── Chat Messages ── */
.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 8px 4px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 0;
}

.chat-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-muted);
  font-size: 0.85rem;
  text-align: center;
  line-height: 1.6;
}

.chat-msg {
  display: flex;
  flex-direction: column;
  max-width: 85%;
  animation: msgIn 0.2s ease-out;
}

@keyframes msgIn {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: translateY(0); }
}

.chat-msg.user {
  align-self: flex-end;
}

.chat-msg.assistant {
  align-self: flex-start;
}

.chat-msg .msg-role {
  font-size: 0.65rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
  margin-bottom: 3px;
  padding: 0 4px;
}

.chat-msg.user .msg-role {
  text-align: right;
}

.chat-msg .msg-bubble {
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 0.82rem;
  line-height: 1.6;
  word-break: break-word;
  white-space: pre-wrap;
}

.chat-msg.user .msg-bubble {
  background: rgba(99,102,241,.2);
  border: 1px solid rgba(99,102,241,.3);
  border-bottom-right-radius: 4px;
}

.chat-msg.assistant .msg-bubble {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-bottom-left-radius: 4px;
}

/* streaming cursor */
.chat-msg.assistant.streaming .msg-bubble::after {
  content: '▌';
  color: var(--accent);
  animation: blink 0.8s step-end infinite;
  margin-left: 1px;
}

@keyframes blink {
  50% { opacity: 0; }
}

/* ── Tool Call Card ── */
.tool-card {
  margin: 6px 0;
  border-left: 3px solid var(--accent);
  background: rgba(99,102,241,.06);
  border-radius: 0 var(--radius) var(--radius) 0;
  overflow: hidden;
  font-size: 0.78rem;
}

.tool-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  cursor: pointer;
  user-select: none;
  transition: background 0.15s;
}

.tool-header:hover {
  background: rgba(99,102,241,.1);
}

.tool-icon {
  font-size: 0.7rem;
  transition: transform 0.2s;
}

.tool-card.expanded .tool-icon {
  transform: rotate(90deg);
}

.tool-name {
  font-weight: 600;
  color: var(--accent);
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 0.75rem;
}

.tool-status {
  margin-left: auto;
  font-size: 0.65rem;
  color: var(--text-muted);
}

.tool-status.running {
  color: var(--warning);
}

.tool-status.done {
  color: var(--success);
}

.tool-body {
  display: none;
  padding: 0 10px 8px 10px;
}

.tool-card.expanded .tool-body {
  display: block;
}

.tool-section-label {
  font-size: 0.65rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
  margin: 6px 0 3px 0;
}

.tool-json {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 6px 8px;
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 0.7rem;
  color: var(--text-muted);
  overflow-x: auto;
  max-height: 120px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-all;
}

/* ── Chat Usage ── */
.chat-usage {
  display: inline-flex;
  gap: 10px;
  padding: 4px 8px;
  margin-top: 4px;
  font-size: 0.65rem;
  color: var(--text-muted);
  background: rgba(148,163,184,.08);
  border-radius: 4px;
  font-family: 'SF Mono', 'Fira Code', monospace;
}

/* ── Chat Input ── */
.chat-input-area {
  display: flex;
  gap: 8px;
  align-items: flex-end;
  padding-top: 10px;
  border-top: 1px solid var(--border);
  margin-top: 8px;
  flex-shrink: 0;
}

.chat-input {
  flex: 1;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text);
  font-size: 0.82rem;
  padding: 8px 12px;
  outline: none;
  resize: vertical;
  min-height: 38px;
  max-height: 120px;
  line-height: 1.5;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  transition: border-color 0.15s;
}

.chat-input:focus {
  border-color: var(--accent);
}

.chat-input::placeholder {
  color: var(--text-muted);
}

.chat-input:disabled {
  opacity: 0.4;
}

.chat-send-btn {
  padding: 8px 16px;
  font-size: 0.82rem;
  font-weight: 600;
  border: none;
  border-radius: var(--radius);
  cursor: pointer;
  transition: background 0.15s, opacity 0.15s;
  white-space: nowrap;
  flex-shrink: 0;
  min-height: 38px;
}

.chat-send-btn.send {
  background: var(--accent);
  color: #fff;
}
.chat-send-btn.send:hover {
  background: var(--accent-hover);
}

.chat-send-btn.stop {
  background: var(--danger);
  color: #fff;
}
.chat-send-btn.stop:hover {
  background: var(--danger-hover);
}

.chat-send-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* ── Scrollbar ── */
::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}
::-webkit-scrollbar-track {
  background: transparent;
}
::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover {
  background: var(--text-muted);
}

/* ── Responsive ── */
@media (max-width: 900px) {
  .app-body {
    grid-template-columns: 1fr;
    height: auto;
  }
  .left-panel {
    overflow-y: visible;
  }
  .right-panel {
    min-height: 500px;
  }
}`;

const HTML_BODY = `<div class="app">
  <header class="app-header">
    <div><h1>🛸 LocalProxy</h1><div class="subtitle">OpenClaw Sandbox Manager</div></div>
  </header>
  <main class="app-body">
    <aside class="left-panel">
      <div id="status-card" class="card status-idle">
        <div class="card-title">Sandbox Status</div>
        <div class="status-badge"><span class="status-dot"></span><span id="status-text">Idle</span></div>
        <div class="status-info">
          <div id="row-sandboxId" class="info-row" style="display:none">
            <span class="info-label">Sandbox ID</span>
            <span class="info-value"></span>
          </div>
          <div id="row-mode" class="info-row" style="display:none">
            <span class="info-label">Mode</span>
            <span class="info-value"></span>
          </div>
          <div id="row-uptime" class="info-row" style="display:none">
            <span class="info-label">Uptime</span>
            <span class="info-value"></span>
          </div>
        </div>
        <div id="error-box" class="error-box" style="display:none"></div>
      </div>
      <div id="action-panel" class="card">
        <div class="card-title">Actions</div>
        <div class="action-buttons">
          <button id="btn-start"  class="btn btn-primary">🚀 Start Sandbox</button>
          <button id="btn-stop"   class="btn btn-danger">🛑 Stop Sandbox</button>
          <button id="btn-pause"  class="btn btn-secondary">⏸ Pause</button>
          <button id="btn-resume" class="btn btn-secondary">▶ Resume</button>
        </div>
        <div class="connect-form">
          <span class="connect-label">Mount subpath (optional):</span>
          <input id="subpath-input" class="connect-input" placeholder="e.g. my-project/workspace" />
        </div>
        <div class="connect-form">
          <span class="connect-label">Connect to existing sandbox:</span>
          <input id="connect-input" class="connect-input" placeholder="sandbox ID..." />
          <button id="btn-connect" class="btn btn-secondary">🔌 Connect</button>
        </div>
      </div>
    </aside>
    <div class="right-panel">
      <div class="tab-bar">
        <button class="tab-btn active" data-tab="logs">📋 Logs (<span id="log-count">0</span>)</button>
        <button class="tab-btn" data-tab="console">🖥 Console</button>
        <button class="tab-btn" data-tab="chat">💬 Chat <span id="chat-tab-dot" class="tab-dot"></span></button>
      </div>
      <div id="tab-logs" class="tab-content active">
        <div id="log-panel" class="log-panel">
          <div class="log-empty">No logs yet...</div>
        </div>
      </div>
      <div id="tab-console" class="tab-content">
        <div class="console-panel">
          <a id="console-link" href="/sandbox/__openclaw__"
             target="_blank" class="console-link disabled">↗ Open Dashboard</a>
          <div id="console-placeholder" class="console-placeholder">
            Start or connect to a sandbox to access the OpenClaw console.
          </div>
        </div>
      </div>
      <div id="tab-chat" class="tab-content">
        <div class="chat-container">
          <div class="chat-connect-bar">
            <span id="chat-conn-dot" class="conn-dot"></span>
            <input id="chat-token-input" type="password" class="chat-token-input"
                   placeholder="OpenClaw Token (gateway.auth.token)" />
            <button id="chat-conn-btn" class="chat-conn-btn connect">Connect</button>
          </div>
          <div id="chat-messages" class="chat-messages">
            <div class="chat-empty">输入 OpenClaw Token 并点击 Connect 开始对话</div>
          </div>
          <div class="chat-input-area">
            <textarea id="chat-input" class="chat-input" rows="1"
                      placeholder="Type a message... (Enter to send, Shift+Enter for newline)"
                      disabled></textarea>
            <button id="chat-send-btn" class="chat-send-btn send" disabled>Send</button>
          </div>
        </div>
      </div>
    </div>
  </main>
</div>`;

const CLIENT_JS = `
// ─── 状态缓存 ───
let cachedLogs = [];
let uptimeTimer = null;
let startedAt = null;
let currentSandboxStatus = 'idle';

// ─── SSE 订阅 ───
const es = new EventSource('/api/events');
es.onmessage = e => applyState(JSON.parse(e.data));

// 初始拉取
fetch('/api/status').then(r => r.json()).then(applyState);

// ─── DOM refs ───
const statusCard   = document.getElementById('status-card');
const statusText   = document.getElementById('status-text');
const rowSandbox   = document.getElementById('row-sandboxId');
const rowMode      = document.getElementById('row-mode');
const rowUptime    = document.getElementById('row-uptime');
const errorBox     = document.getElementById('error-box');
const btnStart     = document.getElementById('btn-start');
const btnStop      = document.getElementById('btn-stop');
const btnPause     = document.getElementById('btn-pause');
const btnResume    = document.getElementById('btn-resume');
const subpathInput = document.getElementById('subpath-input');
const connectInput = document.getElementById('connect-input');
const btnConnect   = document.getElementById('btn-connect');
const logPanel     = document.getElementById('log-panel');
const logCount     = document.getElementById('log-count');
const consoleLink  = document.getElementById('console-link');
const consolePh    = document.getElementById('console-placeholder');

// Chat DOM refs
const chatTabDot     = document.getElementById('chat-tab-dot');
const chatConnDot    = document.getElementById('chat-conn-dot');
const chatTokenInput = document.getElementById('chat-token-input');
const chatConnBtn    = document.getElementById('chat-conn-btn');
const chatMessages   = document.getElementById('chat-messages');
const chatInput      = document.getElementById('chat-input');
const chatSendBtn    = document.getElementById('chat-send-btn');

const STATUS_LABELS = {
  idle: 'Idle', starting: 'Starting', connecting: 'Connecting',
  running: 'Running', pausing: 'Pausing', paused: 'Paused',
  resuming: 'Resuming', stopping: 'Stopping'
};

// ─── Tab 切换 ───
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
  });
});

function applyState(s) {
  const prevStatus = currentSandboxStatus;
  currentSandboxStatus = s.status;

  // status badge
  statusCard.className = 'card status-' + s.status;
  statusText.textContent = STATUS_LABELS[s.status] || s.status;

  // info rows
  showInfo(rowSandbox, s.sandboxId);
  showInfo(rowMode,    s.mode);

  // uptime timer
  if (s.status === 'running' && s.startedAt) {
    startedAt = s.startedAt;
    if (!uptimeTimer) uptimeTimer = setInterval(tickUptime, 1000);
    rowUptime.style.display = '';
    tickUptime();
  } else {
    clearInterval(uptimeTimer); uptimeTimer = null; startedAt = null;
    rowUptime.style.display = 'none';
  }

  // error box
  if (s.error) {
    errorBox.style.display = '';
    errorBox.textContent = '❌ ' + s.error;
  } else {
    errorBox.style.display = 'none';
  }

  // logs (增量 append)
  if (s.logs.length !== cachedLogs.length ||
      s.logs[s.logs.length - 1] !== cachedLogs[cachedLogs.length - 1]) {
    const newLogs = s.logs.slice(cachedLogs.length);
    if (cachedLogs.length === 0) logPanel.innerHTML = '';
    newLogs.forEach(line => {
      const d = document.createElement('div');
      d.className = 'log-line';
      d.textContent = line;
      logPanel.appendChild(d);
    });
    cachedLogs = s.logs.slice();
    logCount.textContent = s.logs.length;
    if (logPanel.lastElementChild) {
      logPanel.lastElementChild.scrollIntoView({ behavior: 'smooth' });
    }
  }

  // buttons
  const busy = ['starting', 'connecting', 'pausing', 'resuming', 'stopping'].includes(s.status);
  btnStart.disabled     = s.status !== 'idle' || busy;
  btnStop.disabled      = !['running', 'paused'].includes(s.status) || busy;
  btnPause.disabled     = s.status !== 'running' || busy;
  btnResume.disabled    = s.status !== 'paused'  || busy;
  subpathInput.disabled = s.status !== 'idle' || busy;
  connectInput.disabled = s.status !== 'idle' || busy;
  btnConnect.disabled   = s.status !== 'idle' || busy || !connectInput.value.trim();

  // console panel
  const running = s.status === 'running';
  const sandboxActive = ['running', 'paused'].includes(s.status);
  consoleLink.classList.toggle('disabled', !running);
  consolePh.style.display = sandboxActive ? 'none' : '';

  // Chat tab dot — 沙箱运行中时显示绿点
  chatTabDot.classList.toggle('visible', running);

  // Chat 状态联动 — 沙箱停止时自动断开 Chat
  if (prevStatus === 'running' && s.status !== 'running' && chatState.ws) {
    chatDisconnect();
  }
  updateChatUI();
}

function showInfo(row, value) {
  if (value) {
    row.style.display = '';
    row.querySelector('.info-value').textContent = value;
  } else {
    row.style.display = 'none';
  }
}

function tickUptime() {
  if (!startedAt) return;
  const secs = Math.floor((Date.now() - startedAt) / 1000);
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  const txt = h > 0 ? h + 'h ' + m + 'm ' + s + 's'
            : m > 0 ? m + 'm ' + s + 's'
            : s + 's';
  rowUptime.querySelector('.info-value').textContent = txt;
}

// ─── 按钮事件 ───
btnStart.addEventListener('click', () => {
  const subpath = subpathInput.value.trim();
  fetch('/api/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ subpath: subpath || undefined }),
  });
});
btnStop.addEventListener('click',   () => fetch('/api/stop',   { method: 'POST' }));
btnPause.addEventListener('click',  () => fetch('/api/pause',  { method: 'POST' }));
btnResume.addEventListener('click', () => fetch('/api/resume', { method: 'POST' }));
btnConnect.addEventListener('click', doConnect);
connectInput.addEventListener('input', () => {
  btnConnect.disabled = !connectInput.value.trim();
});
connectInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !btnConnect.disabled) doConnect();
});

function doConnect() {
  const id = connectInput.value.trim();
  if (!id) return;
  fetch('/api/connect', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sandboxId: id })
  });
  connectInput.value = '';
}

// ═══════════════════════════════════════════════════════════════
// Chat 功能
// ═══════════════════════════════════════════════════════════════

const chatState = {
  ws: null,
  connected: false,
  authenticated: false,
  connectReqId: null,
  sessionKey: 'agent:default:main',
  currentRunId: null,
  isStreaming: false,
  msgCount: 0,
  pendingReqCallbacks: {},  // id -> {resolve, reject}
};

let msgIdCounter = 0;
function nextMsgId() {
  return 'msg-' + (++msgIdCounter) + '-' + Date.now();
}

// ─── Chat Connect / Disconnect ───

chatConnBtn.addEventListener('click', () => {
  if (chatState.ws) {
    chatDisconnect();
  } else {
    chatConnect();
  }
});

function chatConnect() {
  const token = chatTokenInput.value.trim();
  if (!token) {
    chatTokenInput.focus();
    return;
  }
  if (!['running', 'paused'].includes(currentSandboxStatus)) {
    addSystemMessage('⚠️ 沙箱未运行，请先启动或连接沙箱');
    return;
  }

  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = proto + '//' + location.host + '/sandbox/';

  chatState.ws = new WebSocket(wsUrl);
  chatState.connected = false;
  chatState.authenticated = false;
  updateChatUI();

  chatState.ws.onopen = () => {
    chatState.connected = true;
    updateChatUI();
  };

  chatState.ws.onmessage = (evt) => {
    let data;
    try { data = JSON.parse(evt.data); } catch { return; }
    handleWsMessage(data);
  };

  chatState.ws.onclose = () => {
    chatState.ws = null;
    chatState.connected = false;
    chatState.authenticated = false;
    chatState.connectReqId = null;
    chatState.isStreaming = false;
    chatState.currentRunId = null;
    updateChatUI();
  };

  chatState.ws.onerror = () => {
    // onclose will follow
  };
}

function chatDisconnect() {
  if (chatState.ws) {
    chatState.ws.close();
    chatState.ws = null;
  }
  chatState.connected = false;
  chatState.authenticated = false;
  chatState.connectReqId = null;
  chatState.isStreaming = false;
  chatState.currentRunId = null;
  updateChatUI();
}

// ─── WebSocket 消息处理 ───

function handleWsMessage(data) {
  // 心跳 tick — 忽略
  if (data.type === 'event' && data.event === 'tick') return;

  // connect.challenge -> 发送 connect 请求
  if (data.type === 'event' && data.event === 'connect.challenge') {
    sendConnectRequest(data.payload);
    return;
  }

  // 请求响应
  if (data.type === 'res') {
    const cb = chatState.pendingReqCallbacks[data.id];
    if (cb) {
      delete chatState.pendingReqCallbacks[data.id];
      if (data.ok === false || data.error) {
        cb.reject(data.error || { message: 'Request failed' });
      } else {
        // OpenClaw 响应格式: { type: "res", id, ok: true, payload: {...} }
        cb.resolve(data.payload || data.result || data);
      }
    }

    // connect 响应兜底检测（主逻辑在 sendConnectRequest 的 resolve 回调中）
    if (!chatState.authenticated &&
        (data.id === chatState.connectReqId ||
         data.method === 'connect' ||
         (data.result && data.result.protocol))) {
      chatState.authenticated = true;
      updateChatUI();
      clearChatMessages();
      loadChatHistory();
    }
    return;
  }

  // 事件
  if (data.type === 'event') {
    const p = data.payload || {};

    // ── agent 事件（OpenClaw 核心流式协议） ──
    if (data.event === 'agent') {
      const stream = p.stream;
      const d = p.data || {};

      if (stream === 'assistant') {
        // 流式文本增量
        if (d.delta !== undefined) {
          handleChatDelta({ delta: d.delta, text: d.text });
        }
      } else if (stream === 'lifecycle') {
        if (d.phase === 'end') {
          handleChatDone(p);
        } else if (d.phase === 'error') {
          handleChatError({ message: d.error || d.message || 'Agent error' });
        }
      } else if (stream === 'tool_call') {
        handleToolCall(d);
      } else if (stream === 'tool_result') {
        handleToolResult(d);
      }
      return;
    }

    // ── chat 事件（聊天状态同步，可用作备用） ──
    if (data.event === 'chat') {
      // chat 事件中也可能携带 assistant 消息增量
      if (p.state === 'delta' && p.message && p.message.role === 'assistant') {
        const content = p.message.content;
        if (Array.isArray(content)) {
          content.forEach(block => {
            if (block.type === 'text' && block.text) {
              // 已通过 agent 事件处理，此处可忽略以避免重复
            }
          });
        }
      }
      return;
    }

    // ── 兼容旧式事件名（如有） ──
    switch (data.event) {
      case 'chat.delta':
        handleChatDelta(p);
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

function sendConnectRequest(challenge) {
  const token = chatTokenInput.value.trim();
  const id = nextMsgId();
  const req = {
    type: 'req',
    id: id,
    method: 'connect',
    params: {
      minProtocol: 3,
      maxProtocol: 3,
      client: {
        id: 'openclaw-control-ui',
        version: 'control-ui',
        platform: navigator.platform || 'unknown',
        mode: 'webchat',
        instanceId: crypto.randomUUID()
      },
      role: 'operator',
      scopes: ['operator.admin', 'operator.read', 'operator.write', 'operator.approvals', 'operator.pairing'],
      caps: ['tool-events'],
      auth: { token: token },
      userAgent: navigator.userAgent,
      locale: navigator.language || 'en'
    }
  };
  wsSend(req);
  // 记录 connect 请求 ID，用于后续匹配响应
  chatState.connectReqId = id;
  // 注册回调
  chatState.pendingReqCallbacks[id] = {
    resolve: (result) => {
      chatState.authenticated = true;
      updateChatUI();
      clearChatMessages();
      loadChatHistory();
    },
    reject: (err) => {
      addSystemMessage('❌ 连接握手失败: ' + (err.message || JSON.stringify(err)));
    }
  };
}

function wsSend(data) {
  if (chatState.ws && chatState.ws.readyState === WebSocket.OPEN) {
    chatState.ws.send(JSON.stringify(data));
  }
}

// ─── Chat 发送消息 ───

chatSendBtn.addEventListener('click', () => {
  if (chatState.isStreaming) {
    chatAbort();
  } else {
    chatSend();
  }
});

chatInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    if (!chatSendBtn.disabled && !chatState.isStreaming) {
      chatSend();
    }
  }
});

// auto-resize textarea
chatInput.addEventListener('input', () => {
  chatInput.style.height = 'auto';
  chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + 'px';
});

function chatSend() {
  const text = chatInput.value.trim();
  if (!text || !chatState.authenticated) return;

  // 添加用户消息
  addUserMessage(text);
  chatInput.value = '';
  chatInput.style.height = 'auto';

  const id = nextMsgId();
  const req = {
    type: 'req',
    id: id,
    method: 'chat.send',
    params: {
      message: text,
      sessionKey: chatState.sessionKey,
      deliver: false,
      idempotencyKey: crypto.randomUUID()
    }
  };
  wsSend(req);

  chatState.pendingReqCallbacks[id] = {
    resolve: (result) => {
      // OpenClaw 实际响应: { ok: true, payload: { runId, status: "started" } }
      const runId = (result && (result.runId || (result.payload && result.payload.runId)));
      if (runId) {
        chatState.currentRunId = runId;
      }
      chatState.isStreaming = true;
      updateChatUI();
    },
    reject: (err) => {
      addSystemMessage('❌ 发送失败: ' + (err.message || JSON.stringify(err)));
    }
  };
}

function chatAbort() {
  if (!chatState.currentRunId) return;
  const id = nextMsgId();
  const req = {
    type: 'req',
    id: id,
    method: 'chat.abort',
    params: {
      sessionKey: chatState.sessionKey
    }
  };
  wsSend(req);
  chatState.isStreaming = false;
  chatState.currentRunId = null;
  updateStreamingBubble(null, true);
  updateChatUI();
}

// ─── Chat History ───

function loadChatHistory() {
  const id = nextMsgId();
  const req = {
    type: 'req',
    id: id,
    method: 'chat.history',
    params: {
      sessionKey: chatState.sessionKey,
      limit: 50
    }
  };
  wsSend(req);

  chatState.pendingReqCallbacks[id] = {
    resolve: (result) => {
      if (result && Array.isArray(result.messages)) {
        result.messages.forEach(msg => {
          if (msg.role === 'user') {
            addUserMessage(msg.content || '', true);
          } else if (msg.role === 'assistant') {
            addAssistantMessage(msg.content || '', true);
          }
        });
      }
    },
    reject: () => {}
  };
}

// ─── 消息渲染 ───

let currentStreamBubble = null;
let currentStreamText = '';

function clearChatMessages() {
  chatMessages.innerHTML = '';
  currentStreamBubble = null;
  currentStreamText = '';
  chatState.msgCount = 0;
}

function addUserMessage(text, isHistory) {
  removeEmptyPlaceholder();
  const msgEl = document.createElement('div');
  msgEl.className = 'chat-msg user';
  msgEl.innerHTML = '<div class="msg-role">You</div><div class="msg-bubble"></div>';
  msgEl.querySelector('.msg-bubble').textContent = text;
  chatMessages.appendChild(msgEl);
  chatState.msgCount++;
  trimMessages();
  if (!isHistory) scrollToBottom();
}

function addAssistantMessage(text, isHistory) {
  removeEmptyPlaceholder();
  const msgEl = document.createElement('div');
  msgEl.className = 'chat-msg assistant';
  msgEl.innerHTML = '<div class="msg-role">Assistant</div><div class="msg-bubble"></div>';
  msgEl.querySelector('.msg-bubble').textContent = text;
  chatMessages.appendChild(msgEl);
  chatState.msgCount++;
  trimMessages();
  if (!isHistory) scrollToBottom();
}

function addSystemMessage(text) {
  removeEmptyPlaceholder();
  const msgEl = document.createElement('div');
  msgEl.className = 'chat-msg assistant';
  msgEl.innerHTML = '<div class="msg-role">System</div><div class="msg-bubble"></div>';
  msgEl.querySelector('.msg-bubble').textContent = text;
  msgEl.querySelector('.msg-bubble').style.borderLeftColor = 'var(--warning)';
  chatMessages.appendChild(msgEl);
  scrollToBottom();
}

function removeEmptyPlaceholder() {
  const empty = chatMessages.querySelector('.chat-empty');
  if (empty) empty.remove();
}

function getOrCreateStreamBubble() {
  if (currentStreamBubble) return currentStreamBubble;
  removeEmptyPlaceholder();
  const msgEl = document.createElement('div');
  msgEl.className = 'chat-msg assistant streaming';
  msgEl.innerHTML = '<div class="msg-role">Assistant</div><div class="msg-bubble"></div>';
  chatMessages.appendChild(msgEl);
  currentStreamBubble = msgEl;
  currentStreamText = '';
  chatState.msgCount++;
  return msgEl;
}

function updateStreamingBubble(text, finish) {
  if (text !== null && text !== undefined) {
    const bubble = getOrCreateStreamBubble();
    currentStreamText += text;
    bubble.querySelector('.msg-bubble').textContent = currentStreamText;
    scrollToBottom();
  }
  if (finish && currentStreamBubble) {
    currentStreamBubble.classList.remove('streaming');
    currentStreamBubble = null;
    currentStreamText = '';
  }
}

function appendToolCardToStream(cardEl) {
  const bubble = getOrCreateStreamBubble();
  // 插入到 msg-bubble 之后
  bubble.appendChild(cardEl);
  scrollToBottom();
}

function scrollToBottom() {
  requestAnimationFrame(() => {
    chatMessages.scrollTop = chatMessages.scrollHeight;
  });
}

function trimMessages() {
  while (chatState.msgCount > 100 && chatMessages.children.length > 1) {
    chatMessages.removeChild(chatMessages.firstElementChild);
    chatState.msgCount--;
  }
}

// ─── 事件处理器 ───

function handleChatDelta(payload) {
  if (!payload) return;
  updateStreamingBubble(payload.delta || '', false);
}

function handleToolCall(payload) {
  if (!payload) return;
  const card = document.createElement('div');
  card.className = 'tool-card';
  card.dataset.toolCallId = payload.id || payload.runId || '';
  card.dataset.tool = payload.tool || payload.name || 'unknown';

  const paramsStr = payload.params ? JSON.stringify(payload.params, null, 2)
                  : payload.arguments ? JSON.stringify(payload.arguments, null, 2) : '{}';

  card.innerHTML =
    '<div class="tool-header">' +
      '<span class="tool-icon">▶</span>' +
      '<span class="tool-name">' + escHtml(payload.tool || payload.name || 'tool') + '</span>' +
      '<span class="tool-status running">running...</span>' +
    '</div>' +
    '<div class="tool-body">' +
      '<div class="tool-section-label">Parameters</div>' +
      '<pre class="tool-json">' + escHtml(paramsStr) + '</pre>' +
      '<div class="tool-section-label" style="display:none">Result</div>' +
      '<pre class="tool-json tool-result-json" style="display:none"></pre>' +
    '</div>';

  card.querySelector('.tool-header').addEventListener('click', () => {
    card.classList.toggle('expanded');
  });

  appendToolCardToStream(card);
}

function handleToolResult(payload) {
  if (!payload) return;
  const toolId = payload.id || payload.runId || '';
  const toolName = payload.tool || payload.name || '';

  // 找到对应的 tool card
  let card = null;
  const cards = chatMessages.querySelectorAll('.tool-card');
  for (let i = cards.length - 1; i >= 0; i--) {
    if ((toolId && cards[i].dataset.toolCallId === toolId) ||
        (toolName && cards[i].dataset.tool === toolName)) {
      card = cards[i];
      break;
    }
  }
  // fallback: 最后一个 running 的 card
  if (!card) {
    for (let i = cards.length - 1; i >= 0; i--) {
      const st = cards[i].querySelector('.tool-status');
      if (st && st.classList.contains('running')) {
        card = cards[i];
        break;
      }
    }
  }

  if (!card) return;

  const status = card.querySelector('.tool-status');
  status.textContent = 'done';
  status.classList.remove('running');
  status.classList.add('done');

  const resultLabel = card.querySelectorAll('.tool-section-label')[1];
  const resultJson = card.querySelector('.tool-result-json');
  if (resultLabel && resultJson) {
    resultLabel.style.display = '';
    resultJson.style.display = '';
    const resultStr = payload.result ? JSON.stringify(payload.result, null, 2)
                    : payload.output || '(no result)';
    resultJson.textContent = typeof resultStr === 'string' ? resultStr : JSON.stringify(resultStr, null, 2);
  }
}

function handleChatDone(payload) {
  chatState.isStreaming = false;
  chatState.currentRunId = null;
  updateStreamingBubble(null, true);

  // 显示 usage（可能在 payload.data.usage 或 payload.usage 中）
  const data = (payload && payload.data) || payload || {};
  const u = data.usage || (payload && payload.usage);
  if (u) {
    const usageEl = document.createElement('div');
    usageEl.className = 'chat-usage';
    usageEl.textContent =
      'prompt: ' + (u.promptTokens || u.prompt_tokens || 0) +
      '  completion: ' + (u.completionTokens || u.completion_tokens || 0) +
      '  total: ' + (u.totalTokens || u.total_tokens || 0);
    // 追加到最后一个 assistant 消息
    const msgs = chatMessages.querySelectorAll('.chat-msg.assistant');
    if (msgs.length > 0) {
      msgs[msgs.length - 1].appendChild(usageEl);
    }
  }

  updateChatUI();
  scrollToBottom();
}

function handleChatError(payload) {
  chatState.isStreaming = false;
  chatState.currentRunId = null;
  updateStreamingBubble(null, true);
  addSystemMessage('❌ Error: ' + (payload && payload.message || JSON.stringify(payload)));
  updateChatUI();
}

function escHtml(str) {
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}

// ─── Chat UI 状态更新 ───

function updateChatUI() {
  const sandboxActive = ['running', 'paused'].includes(currentSandboxStatus);
  const wsOpen = chatState.connected;
  const authed = chatState.authenticated;
  const streaming = chatState.isStreaming;

  // 连接指示器
  chatConnDot.classList.toggle('connected', authed);

  // Token 输入框
  chatTokenInput.disabled = wsOpen;

  // Connect/Disconnect 按钮
  if (wsOpen) {
    chatConnBtn.textContent = 'Disconnect';
    chatConnBtn.className = 'chat-conn-btn disconnect';
    chatConnBtn.disabled = false;
  } else {
    chatConnBtn.textContent = 'Connect';
    chatConnBtn.className = 'chat-conn-btn connect';
    chatConnBtn.disabled = !sandboxActive || !chatTokenInput.value.trim();
  }

  // 消息输入
  chatInput.disabled = !authed;
  chatSendBtn.disabled = !authed;

  // Send / Stop 按钮模式
  if (streaming) {
    chatSendBtn.textContent = '⏹ Stop';
    chatSendBtn.className = 'chat-send-btn stop';
    chatSendBtn.disabled = false;
  } else {
    chatSendBtn.textContent = 'Send';
    chatSendBtn.className = 'chat-send-btn send';
    chatSendBtn.disabled = !authed;
  }
}

// token 输入变化时更新按钮
chatTokenInput.addEventListener('input', updateChatUI);
`;

function getHtml(): string {
  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>LocalProxy — OpenClaw Manager</title>
  <style>${CSS}</style>
</head>
<body>
  ${HTML_BODY}
  <script>${CLIENT_JS}</script>
</body>
</html>`;
}

// ---------------------------------------------------------------------------
// Express 应用
// ---------------------------------------------------------------------------

const app = express();
app.use(cors());
app.use(express.json());

// GET / — 管理界面
app.get('/', (_req, res) => {
  res.setHeader('Content-Type', 'text/html');
  res.send(getHtml());
});

// /sandbox/* — 反向代理到沙箱
app.use('/sandbox', (req, res) => {
  if (!sandboxProxy) {
    res.status(503).send('Sandbox not running');
    return;
  }
  // 把 /sandbox/foo 转发为 /foo
  req.url = req.url || '/';
  sandboxProxy.web(req, res);
});

// GET /api/status — 当前状态快照
app.get('/api/status', (_req, res) => {
  res.json(state);
});

// GET /api/events — SSE 实时推送
app.get('/api/events', (req, res) => {
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.flushHeaders();

  // 立即发送当前状态
  res.write(`data: ${JSON.stringify(state)}\n\n`);

  sseClients.add(res);

  req.on('close', () => {
    sseClients.delete(res);
  });
});

// POST /api/start — 创建新沙箱（异步，进度走 SSE）
app.post('/api/start', async (req, res) => {
  if (actionInFlight) {
    res.status(409).json({ error: '已有操作进行中' });
    return;
  }
  if (state.status !== 'idle') {
    res.status(409).json({ error: `当前状态为 ${state.status}，无法启动` });
    return;
  }

  actionInFlight = true;
  res.json({ ok: true });

  try {
    setState({ status: 'starting', mode: 'created', sandboxId: undefined, error: undefined, logs: [] });
    appendLog('🚀 正在创建沙箱...');

    const client = createAgsClient();
    const { subpath } = req.body as { subpath?: string };
    const mountName = process.env.MOUNT_NAME;
    const mountOptions = mountName
      ? [{ Name: mountName, ...(subpath ? { SubPath: subpath } : {}) }]
      : undefined;
    if (mountOptions) appendLog(`📂 Mount: ${mountName}${subpath ? ` / subpath: ${subpath}` : ''}`);

    const startResp = await client.StartSandboxInstance({
      ToolName: process.env.TOOL_NAME || '',
      Timeout: '60m',
      ...(mountOptions ? { MountOptions: mountOptions } : {}),
    });
    const instanceId = startResp.Instance!.InstanceId;
    appendLog(`✅ 沙箱创建成功，ID: ${instanceId}`);
    setState({ sandboxId: instanceId, status: 'connecting' });

    const accessToken = await acquireToken(instanceId);
    const remoteHost = getRemoteHost(instanceId, OPENCLAW_PORT);

    await waitForOpenClaw(remoteHost, accessToken);

    appendLog('📝 启动本地代理服务器...');
    startProxyServer(remoteHost, accessToken);

    setState({ status: 'running', startedAt: Date.now() });
    appendLog('🎉 沙箱已就绪！');

    registerExitHandler(instanceId, 'created');
  } catch (err: any) {
    appendLog(`❌ 启动失败: ${err.message}`);
    setState({ status: 'idle', error: err.message });
  } finally {
    actionInFlight = false;
  }
});

// POST /api/connect — 连接已有沙箱
app.post('/api/connect', async (req, res) => {
  if (actionInFlight) {
    res.status(409).json({ error: '已有操作进行中' });
    return;
  }
  if (state.status !== 'idle') {
    res.status(409).json({ error: `当前状态为 ${state.status}，无法连接` });
    return;
  }

  const { sandboxId } = req.body as { sandboxId?: string };
  if (!sandboxId) {
    res.status(400).json({ error: '缺少 sandboxId' });
    return;
  }

  actionInFlight = true;
  res.json({ ok: true });

  try {
    setState({ status: 'connecting', mode: 'connected', sandboxId, error: undefined, logs: [] });
    appendLog(`🔌 正在连接沙箱 ${sandboxId}...`);

    const accessToken = await acquireToken(sandboxId);
    appendLog(`✅ 已获取 Token，沙箱 ID: ${sandboxId}`);

    const remoteHost = getRemoteHost(sandboxId, OPENCLAW_PORT);

    await waitForOpenClaw(remoteHost, accessToken);

    appendLog('📝 启动本地代理服务器...');
    startProxyServer(remoteHost, accessToken);

    setState({ status: 'running', startedAt: Date.now() });
    appendLog('🎉 已连接并就绪！');

    registerExitHandler(sandboxId, 'connected');
  } catch (err: any) {
    appendLog(`❌ 连接失败: ${err.message}`);
    setState({ status: 'idle', error: err.message });
  } finally {
    actionInFlight = false;
  }
});

// POST /api/stop — 停止/销毁沙箱
app.post('/api/stop', async (_req, res) => {
  if (actionInFlight) {
    res.status(409).json({ error: '已有操作进行中' });
    return;
  }
  if (!['running', 'paused'].includes(state.status)) {
    res.status(409).json({ error: `当前状态为 ${state.status}，无法停止` });
    return;
  }

  actionInFlight = true;
  res.json({ ok: true });

  await performStop();
  actionInFlight = false;
});

// POST /api/pause — 暂停沙箱
app.post('/api/pause', async (_req, res) => {
  if (actionInFlight) {
    res.status(409).json({ error: '已有操作进行中' });
    return;
  }
  if (state.status !== 'running') {
    res.status(409).json({ error: `当前状态为 ${state.status}，无法暂停` });
    return;
  }

  actionInFlight = true;
  res.json({ ok: true });

  try {
    setState({ status: 'pausing' });
    appendLog('⏸ 正在暂停沙箱...');

    stopProxyServer();

    const client = createAgsClient();
    await client.PauseSandboxInstance({ InstanceId: state.sandboxId! });
    appendLog('✅ 沙箱已暂停');

    setState({ status: 'paused', startedAt: undefined });
  } catch (err: any) {
    appendLog(`❌ 暂停失败: ${err.message}`);
    // 回滚：重新拿 token 挂代理
    try {
      const accessToken = await acquireToken(state.sandboxId!);
      const remoteHost = getRemoteHost(state.sandboxId!, OPENCLAW_PORT);
      startProxyServer(remoteHost, accessToken);
    } catch { /* ignore */ }
    setState({ status: 'running', error: err.message });
  } finally {
    actionInFlight = false;
  }
});

// POST /api/resume — 恢复暂停的沙箱
app.post('/api/resume', async (_req, res) => {
  if (actionInFlight) {
    res.status(409).json({ error: '已有操作进行中' });
    return;
  }
  if (state.status !== 'paused') {
    res.status(409).json({ error: `当前状态为 ${state.status}，无法恢复` });
    return;
  }
  if (!state.sandboxId) {
    res.status(409).json({ error: '缺少 sandboxId，无法恢复' });
    return;
  }

  actionInFlight = true;
  res.json({ ok: true });

  try {
    setState({ status: 'resuming' });
    appendLog('▶ 正在恢复沙箱...');

    const client = createAgsClient();
    await client.ResumeSandboxInstance({ InstanceId: state.sandboxId! });
    appendLog(`✅ 恢复指令已发送`);

    const accessToken = await acquireToken(state.sandboxId!);
    const remoteHost = getRemoteHost(state.sandboxId!, OPENCLAW_PORT);

    await waitForOpenClaw(remoteHost, accessToken);

    startProxyServer(remoteHost, accessToken);
    setState({ status: 'running', startedAt: Date.now() });
    appendLog('🎉 沙箱已就绪！');
  } catch (err: any) {
    appendLog(`❌ 恢复失败: ${err.message}`);
    setState({ status: 'paused', error: err.message });
  } finally {
    actionInFlight = false;
  }
});

// ---------------------------------------------------------------------------
// 停止逻辑
// ---------------------------------------------------------------------------

let currentInstanceId: string | null = null;
let currentMode: SandboxMode | null = null;
let exitHandlerRegistered = false;

function registerExitHandler(instanceId: string, mode: SandboxMode) {
  currentInstanceId = instanceId;
  currentMode = mode;

  if (exitHandlerRegistered) return;
  exitHandlerRegistered = true;

  const cleanup = async () => {
    console.log('\n\n🛑 正在关闭服务...');
    await performStop();
    process.exit(0);
  };

  process.on('SIGINT', cleanup);
  process.on('SIGTERM', cleanup);
}

async function performStop(): Promise<void> {
  setState({ status: 'stopping' });
  appendLog('🛑 正在停止...');

  stopProxyServer();
  appendLog('✅ 代理服务器已关闭');

  if (currentInstanceId && currentMode === 'created') {
    try {
      const client = createAgsClient();
      await client.StopSandboxInstance({ InstanceId: currentInstanceId });
      appendLog('✅ 沙箱已停止');
    } catch (err: any) {
      appendLog(`⚠️  停止沙箱失败: ${err.message}`);
    }
  } else if (currentMode === 'connected') {
    appendLog(`💡 沙箱 ${state.sandboxId} 仍在运行（connect 模式不停止）`);
  }

  currentInstanceId = null;
  currentMode = null;

  setState({
    status: 'idle',
    mode: undefined,
    sandboxId: undefined,
    startedAt: undefined,
    error: undefined,
  });
}

// ---------------------------------------------------------------------------
// 启动管理服务器
// ---------------------------------------------------------------------------

const server = app.listen(MANAGEMENT_PORT, () => {
  console.log(`\n🚀 LocalProxy 管理服务器已启动`);
  console.log(`   管理界面: http://localhost:${MANAGEMENT_PORT}`);
  console.log(`   API:      http://localhost:${MANAGEMENT_PORT}/api`);
  console.log('   按 Ctrl+C 退出\n');
});

server.on('upgrade', (req, socket, head) => {
  if (sandboxWsHandler) sandboxWsHandler(req, socket, head);
});
