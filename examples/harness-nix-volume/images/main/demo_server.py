#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

DEFAULT_STATE = {
    "status": "waiting",
    "topic": "",
    "message": "Sandbox is ready. Waiting for Claude Code to start.",
    "report": "",
    "claude_path": "",
    "started_at": "",
    "completed_at": "",
}

PAGE = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Claude Code · AGS Agent Volume</title>
  <style>
    :root { color-scheme: light; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }
    body { margin: 0; background: #f4f6f8; color: #17202a; }
    main { width: min(960px, calc(100% - 32px)); margin: 36px auto; }
    header, section { background: white; border: 1px solid #e3e8ee; border-radius: 16px; box-shadow: 0 8px 30px rgba(18, 38, 63, .06); }
    header { padding: 28px 30px; background: linear-gradient(135deg, #152238, #244d74); color: white; }
    h1 { margin: 0 0 10px; font-size: clamp(25px, 4vw, 38px); }
    header p { margin: 0; color: #dce9f5; }
    .badges { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 20px; }
    .badge { padding: 6px 10px; border-radius: 999px; background: rgba(255,255,255,.13); font-size: 13px; }
    section { margin-top: 18px; padding: 24px 28px; }
    .row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
    #status { font-weight: 700; padding: 7px 11px; border-radius: 999px; background: #eef2f6; }
    #status.running { color: #8a5200; background: #fff1cc; }
    #status.complete { color: #096b3b; background: #dff7e9; }
    #status.error { color: #a12424; background: #fde6e6; }
    h2 { margin: 0 0 14px; font-size: 19px; }
    dl { display: grid; grid-template-columns: 110px 1fr; gap: 8px 14px; margin: 18px 0 0; }
    dt { color: #667582; } dd { margin: 0; word-break: break-word; }
    #report { font-size: 15px; line-height: 1.7; overflow-wrap: anywhere; }
    #report h3 { margin: 22px 0 8px; font-size: 18px; }
    #report p { margin: 8px 0; }
    #report ul { margin: 8px 0; padding-left: 24px; }
    #report a { color: #1769aa; }
    #report .empty { color: #7d8993; }
    footer { margin: 18px 4px; color: #71808d; font-size: 13px; text-align: center; }
  </style>
</head>
<body>
<main>
  <header>
    <h1>Claude Code 分析结果</h1>
    <p>Claude Code 由只读 Nix 镜像卷提供，通过 envd 在 AGS 沙箱内启动。</p>
    <div class="badges">
      <span class="badge">Runtime: /nix</span>
      <span class="badge">Command: envd</span>
      <span class="badge">Result: HTTP 8080</span>
    </div>
  </header>

  <section>
    <div class="row"><h2>任务状态</h2><span id="status">等待中</span></div>
    <dl>
      <dt>分析主题</dt><dd id="topic">-</dd>
      <dt>当前信息</dt><dd id="message">正在读取状态…</dd>
      <dt>Claude Code</dt><dd id="claude-path">-</dd>
      <dt>开始时间</dt><dd id="started-at">-</dd>
      <dt>完成时间</dt><dd id="completed-at">-</dd>
    </dl>
  </section>

  <section><h2>分析结果</h2><div id="report"></div></section>
  <footer>本页面内容由模型生成，仅供参考，不构成投资建议。</footer>
</main>
<script>
  const labels = {waiting: "等待中", running: "分析中", complete: "已完成", error: "失败"};
  function appendInline(parent, text) {
    const pattern = /\[([^\]]+)\]\((https?:\/\/[^)]+)\)|\*\*([^*]+)\*\*/g;
    let offset = 0;
    for (const match of text.matchAll(pattern)) {
      parent.append(document.createTextNode(text.slice(offset, match.index)));
      if (match[1]) {
        const link = document.createElement('a');
        link.textContent = match[1];
        link.href = match[2];
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        parent.append(link);
      } else {
        const strong = document.createElement('strong');
        strong.textContent = match[3];
        parent.append(strong);
      }
      offset = match.index + match[0].length;
    }
    parent.append(document.createTextNode(text.slice(offset)));
  }
  function renderReport(markdown) {
    const root = document.getElementById('report');
    root.replaceChildren();
    if (!markdown) {
      const empty = document.createElement('p');
      empty.className = 'empty';
      empty.textContent = 'Claude Code 的分析结果会显示在这里。';
      root.append(empty);
      return;
    }
    let list = null;
    for (const rawLine of markdown.split('\n')) {
      const line = rawLine.trim();
      if (!line) { list = null; continue; }
      if (/^-{3,}$/.test(line)) { root.append(document.createElement('hr')); list = null; continue; }
      if (line.startsWith('- ')) {
        if (!list) { list = document.createElement('ul'); root.append(list); }
        const item = document.createElement('li');
        appendInline(item, line.slice(2));
        list.append(item);
        continue;
      }
      list = null;
      const heading = line.match(/^#{1,3}\s+(.+)$/);
      const block = document.createElement(heading ? 'h3' : 'p');
      appendInline(block, heading ? heading[1] : line);
      root.append(block);
    }
  }
  async function refresh() {
    try {
      const response = await fetch('/api/status', {cache: 'no-store'});
      const data = await response.json();
      const status = data.status || 'waiting';
      const badge = document.getElementById('status');
      badge.textContent = labels[status] || status;
      badge.className = status;
      document.getElementById('topic').textContent = data.topic || '-';
      document.getElementById('message').textContent = data.message || '-';
      document.getElementById('claude-path').textContent = data.claude_path || '-';
      document.getElementById('started-at').textContent = data.started_at || '-';
      document.getElementById('completed-at').textContent = data.completed_at || '-';
      renderReport(data.report || '');
    } catch (error) {
      document.getElementById('message').textContent = '读取状态失败：' + error;
    }
  }
  refresh();
  setInterval(refresh, 2000);
</script>
</body>
</html>
""".encode()


def state_path() -> Path:
    return Path(os.getenv("DEMO_STATE_DIR", "/workspace/demo-result")) / "status.json"


def now() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")


def read_state() -> dict[str, Any]:
    state = dict(DEFAULT_STATE)
    try:
        saved = json.loads(state_path().read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return state
    if isinstance(saved, dict):
        state.update(saved)
    return state


def write_state(args: argparse.Namespace) -> None:
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    state = read_state()
    state.update(
        {
            "status": args.status,
            "topic": args.topic if args.topic is not None else state["topic"],
            "message": args.message,
            "claude_path": (
                args.claude_path
                if args.claude_path is not None
                else state["claude_path"]
            ),
        }
    )
    if args.status == "running":
        state["started_at"] = now()
        state["completed_at"] = ""
        state["report"] = ""
    elif args.status in {"complete", "error"}:
        if args.report_file is not None:
            report = args.report_file.read_text(encoding="utf-8")
        else:
            report = os.getenv("DEMO_REPORT", "")
        if args.status == "complete" and not report.strip():
            raise SystemExit("a completed report cannot be empty")
        state["completed_at"] = now()
        state["report"] = report

    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


class Handler(BaseHTTPRequestHandler):
    server_version = "ags-claude-demo/1.0"

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(PAGE)))
            self.end_headers()
            self.wfile.write(PAGE)
            return
        if path == "/api/status":
            body = json.dumps(read_state(), ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/health":
            body = b'{"ok":true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, fmt: str, *args: Any) -> None:
        print(fmt % args, flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8080)
    write = sub.add_parser("write")
    write.add_argument(
        "--status", choices=["waiting", "running", "complete", "error"], required=True
    )
    write.add_argument("--topic")
    write.add_argument("--message", required=True)
    write.add_argument("--claude-path")
    write.add_argument("--report-file", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "write":
        write_state(args)
        return 0
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
