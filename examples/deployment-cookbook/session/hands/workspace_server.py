#!/usr/bin/env python3
"""Minimal stateful workspace service used by the Hands Session cookbook."""

from __future__ import annotations

import json
import os
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


WORKSPACE = Path(os.environ.get("WORKSPACE_DIR", "/workspace")).resolve()
PORT = int(os.environ.get("PORT", "8080"))


def workspace_path(value: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("path must be relative to the workspace")
    target = (WORKSPACE / relative).resolve()
    if target != WORKSPACE and WORKSPACE not in target.parents:
        raise ValueError("path escapes the workspace")
    return target


class Handler(BaseHTTPRequestHandler):
    server_version = "hands-workspace/1.0"

    def send_json(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self.send_json(200, {"status": "ok"})
            return
        if parsed.path != "/files/read":
            self.send_json(404, {"error": "not found"})
            return
        try:
            name = parse_qs(parsed.query).get("path", [""])[0]
            target = workspace_path(name)
            self.send_json(200, {
                "path": name,
                "exists": target.is_file(),
                "content": target.read_text() if target.is_file() else None,
                "hostname": socket.gethostname(),
            })
        except (OSError, ValueError) as error:
            self.send_json(400, {"error": str(error)})

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if urlparse(self.path).path != "/files/write":
            self.send_json(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            name = str(payload["path"])
            content = str(payload["content"])
            target = workspace_path(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
            self.send_json(200, {
                "path": name,
                "content": content,
                "hostname": socket.gethostname(),
            })
        except (KeyError, TypeError, OSError, ValueError, json.JSONDecodeError) as error:
            self.send_json(400, {"error": str(error)})

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}", flush=True)


def main() -> None:
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Hands workspace service listening on {PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
