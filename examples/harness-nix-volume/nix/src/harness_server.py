#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


def command_output(args: list[str], timeout: int = 10) -> str:
    try:
        proc = subprocess.run(args, check=False, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return "not-found"
    except Exception as exc:  # pragma: no cover - diagnostic path
        return f"error: {exc}"
    text = (proc.stdout + proc.stderr).strip()
    return text.splitlines()[0] if text else f"exit={proc.returncode}"


def runtime_report() -> dict[str, Any]:
    return {
        "ok": True,
        "python": sys.version.split()[0],
        "node": command_output(["node", "--version"]),
        "claude": command_output(["claude", "--version"], timeout=20),
        "executables": {
            "python3": shutil.which("python3"),
            "node": shutil.which("node"),
            "claude": shutil.which("claude"),
        },
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "ags-harness-demo/0.1"

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/health":
            self._json({"ok": True})
            return
        if path == "/run":
            self._json(runtime_report())
            return
        self.send_response(404)
        self.end_headers()
        self.wfile.write(b"not-found")

    def log_message(self, fmt: str, *args: Any) -> None:
        print(fmt % args, flush=True)

    def _json(self, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve(host: str, port: int) -> None:
    print(json.dumps({"event": "starting", "host": host, "port": port, "runtime": runtime_report()}), flush=True)
    ThreadingHTTPServer((host, port), Handler).serve_forever()


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    serve_parser = sub.add_parser("serve")
    serve_parser.add_argument("--host", default="0.0.0.0")
    serve_parser.add_argument("--port", type=int, default=18080)
    sub.add_parser("run")
    args = parser.parse_args()

    if args.command == "serve":
        serve(args.host, args.port)
        return 0

    print(json.dumps(runtime_report(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
