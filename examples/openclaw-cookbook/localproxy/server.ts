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
  grid-template-rows: auto 1fr;
  gap: 16px;
  padding-bottom: 24px;
}

.left-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
  grid-row: 1 / 3;
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

/* ── LogPanel ── */
.log-panel {
  height: 260px;
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
    grid-template-rows: auto;
  }
  .left-panel {
    grid-row: auto;
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
    <div class="right-top">
      <div class="card">
        <div class="card-title">Logs (<span id="log-count">0</span>)</div>
        <div id="log-panel" class="log-panel">
          <div class="log-empty">No logs yet...</div>
        </div>
      </div>
    </div>
    <div class="right-bottom">
      <div class="card console-panel">
        <div class="card-title">OpenClaw Console</div>
        <a id="console-link" href="/sandbox/__openclaw__"
           target="_blank" class="console-link disabled">↗ Open Dashboard</a>
        <div id="console-placeholder" class="console-placeholder">
          Start or connect to a sandbox to access the OpenClaw console.
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

const STATUS_LABELS = {
  idle: 'Idle', starting: 'Starting', connecting: 'Connecting',
  running: 'Running', pausing: 'Pausing', paused: 'Paused',
  resuming: 'Resuming', stopping: 'Stopping'
};

function applyState(s) {
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
