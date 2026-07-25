#!/usr/bin/env python3
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

STATE_HELPER = "/opt/claude-demo/demo_server.py"


def stop(processes: list[subprocess.Popen[bytes]]) -> None:
    for process in processes:
        if process.poll() is None:
            process.terminate()
    deadline = time.monotonic() + 5
    for process in processes:
        if process.poll() is not None:
            continue
        try:
            process.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            process.kill()
    for process in processes:
        process.wait()


def main() -> int:
    state_dir = Path(os.getenv("DEMO_STATE_DIR", "/workspace/demo-result"))
    http_port = os.getenv("DEMO_HTTP_PORT", "8080")
    envd_port = os.getenv("ENVD_PORT", "49983")
    state_dir.mkdir(parents=True, exist_ok=True)

    if not (state_dir / "status.json").exists():
        subprocess.run(
            [
                sys.executable,
                STATE_HELPER,
                "write",
                "--status",
                "waiting",
                "--message",
                "Sandbox is ready. Waiting for Claude Code to start.",
            ],
            check=True,
        )

    processes = [
        subprocess.Popen(["/usr/bin/envd", "-port", envd_port]),
        subprocess.Popen(
            [
                sys.executable,
                STATE_HELPER,
                "serve",
                "--host",
                "0.0.0.0",
                "--port",
                http_port,
            ]
        ),
    ]

    def handle_signal(_signum: int, _frame: object) -> None:
        stop(processes)
        raise SystemExit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    print(f"envd is listening on port {envd_port}", flush=True)
    print(f"result server is listening on port {http_port}", flush=True)

    try:
        while all(process.poll() is None for process in processes):
            time.sleep(0.5)
    finally:
        stop(processes)
    return next(
        (process.returncode for process in processes if process.returncode),
        0,
    )


if __name__ == "__main__":
    raise SystemExit(main())
