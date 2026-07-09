"""
Run Windows Agent Arena against a Windows sandbox provided by AGS.

This file is distributed by Agent Sandbox Cookbook as part of the WAA AGS overlay.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import aiohttp
import requests
from aiohttp import web
from dotenv import load_dotenv

CLIENT_DIR = Path(__file__).resolve().parent
EXAMPLE_DIR = CLIENT_DIR.parents[3]


def load_runtime_env() -> None:
    load_dotenv(EXAMPLE_DIR / ".env")


load_runtime_env()

logger = logging.getLogger("waa.ags")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

SERVER_PORT = int(os.environ.get("WAA_SERVER_PORT", "5000"))
CDP_PORT = int(os.environ.get("WAA_CDP_PORT", "9222"))
NOVNC_PORT = int(os.environ.get("WAA_NOVNC_PORT", "8006"))
VLC_PORT = int(os.environ.get("WAA_VLC_PORT", "8080"))


class LocalProxyServer:
    def __init__(
        self,
        local_host: str,
        local_port: int,
        target_host: str,
        access_token: str | None,
        rewrite_cdp: bool = False,
    ):
        self.local_host = local_host
        self.local_port = local_port
        self.target_host = target_host
        self.access_token = access_token
        self.rewrite_cdp = rewrite_cdp
        self.thread: threading.Thread | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.runner: web.AppRunner | None = None
        self._start_event = threading.Event()
        self._start_error: Exception | None = None

    def start(self) -> None:
        self.thread = threading.Thread(target=self._run_server, daemon=True)
        self.thread.start()
        self._start_event.wait(timeout=10)
        if self._start_error:
            raise self._start_error
        logger.info("Proxy started: http://%s:%d -> https://%s", self.local_host, self.local_port, self.target_host)

    def _run_server(self) -> None:
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._start_server())
            self._start_event.set()
            self.loop.run_forever()
        except Exception as exc:
            self._start_error = exc
            self._start_event.set()
        finally:
            if self.loop and not self.loop.is_closed():
                self.loop.close()

    async def _start_server(self) -> None:
        app = web.Application()
        app.router.add_route("*", "/{path:.*}", self._handle_request)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, self.local_host, self.local_port)
        await site.start()

    async def _handle_request(self, request: web.Request) -> web.StreamResponse:
        path = "/" + request.match_info.get("path", "")
        if request.query_string:
            path += "?" + request.query_string
        if request.headers.get("Upgrade", "").lower() == "websocket":
            return await self._handle_websocket(request, path)
        return await self._handle_http(request, path)

    def _headers(self, request: web.Request | None = None) -> dict[str, str]:
        headers: dict[str, str] = {}
        if request is not None:
            for key, value in request.headers.items():
                if key.lower() not in ("host", "transfer-encoding", "content-length"):
                    headers[key] = value
        if self.access_token:
            headers["X-Access-Token"] = self.access_token
        return headers

    async def _handle_http(self, request: web.Request, path: str) -> web.Response:
        target_url = f"https://{self.target_host}{path}"
        body = await request.read()
        try:
            async with aiohttp.ClientSession() as session:
                async with session.request(
                    request.method,
                    target_url,
                    headers=self._headers(request),
                    data=body if body else None,
                    timeout=aiohttp.ClientTimeout(total=300, connect=30),
                ) as response:
                    content = await response.read()
                    if self.rewrite_cdp and path.startswith("/json") and response.status == 200:
                        content_text = content.decode("utf-8")
                        content_text = re.sub(
                            r"wss?://[^/\s\"]+",
                            f"ws://{self.local_host}:{self.local_port}",
                            content_text,
                        )
                        content = content_text.encode("utf-8")
                    resp_headers = {
                        key: value
                        for key, value in response.headers.items()
                        if key.lower() not in ("transfer-encoding", "content-encoding", "content-length")
                    }
                    return web.Response(body=content, status=response.status, headers=resp_headers)
        except Exception as exc:
            logger.error("Proxy HTTP error for %s: %s", path, exc)
            return web.Response(text=str(exc), status=502)

    async def _handle_websocket(self, request: web.Request, path: str) -> web.WebSocketResponse:
        ws_client = web.WebSocketResponse()
        await ws_client.prepare(request)
        remote_url = f"wss://{self.target_host}{path}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(remote_url, headers=self._headers()) as ws_remote:
                    async def client_to_remote() -> None:
                        async for msg in ws_client:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                await ws_remote.send_str(msg.data)
                            elif msg.type == aiohttp.WSMsgType.BINARY:
                                await ws_remote.send_bytes(msg.data)

                    async def remote_to_client() -> None:
                        async for msg in ws_remote:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                await ws_client.send_str(msg.data)
                            elif msg.type == aiohttp.WSMsgType.BINARY:
                                await ws_client.send_bytes(msg.data)

                    await asyncio.gather(client_to_remote(), remote_to_client(), return_exceptions=True)
        except Exception as exc:
            logger.debug("Proxy WebSocket closed for %s: %s", path, exc)
        return ws_client

    def stop(self) -> None:
        if not self.loop:
            return
        if self.runner:
            try:
                future = asyncio.run_coroutine_threadsafe(self.runner.cleanup(), self.loop)
                future.result(timeout=5)
            except Exception as exc:
                logger.debug("Proxy cleanup error: %s", exc)
        if not self.loop.is_closed():
            self.loop.call_soon_threadsafe(self.loop.stop)
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=3)


def can_bind(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def local_host_candidates() -> list[str]:
    configured = os.environ.get("WAA_LOCAL_HOST")
    if configured:
        return [configured]

    candidates = ["127.0.0.1"]
    try:
        output = subprocess.check_output(["ifconfig"], text=True, timeout=5)
        for match in re.finditer(r"\binet\s+(\d+\.\d+\.\d+\.\d+)", output):
            host = match.group(1)
            if host != "127.0.0.1" and host not in candidates:
                candidates.append(host)
    except Exception as exc:
        logger.debug("Failed to inspect local interface addresses: %s", exc)
    return candidates


def select_local_host() -> str:
    ports = [SERVER_PORT, CDP_PORT, NOVNC_PORT, VLC_PORT]
    for host in local_host_candidates():
        if all(can_bind(host, port) for port in ports):
            return host
    raise RuntimeError(f"no available local host for ports: {ports}")


def wait_for_server(local_host: str, timeout: int = 300) -> None:
    deadline = time.time() + timeout
    url = f"http://{local_host}:{SERVER_PORT}/probe"
    while time.time() < deadline:
        try:
            response = requests.get(url, timeout=7)
            if response.status_code == 200:
                logger.info("WAA Windows server is ready: %s", response.text[:200])
                return
        except Exception as exc:
            logger.info("Waiting for WAA Windows server: %s", exc)
        time.sleep(5)
    raise TimeoutError(f"WAA Windows server did not become ready within {timeout}s")


def add_default_args(args: list[str], local_host: str) -> list[str]:
    if "--emulator_ip" not in args:
        args = [*args, "--emulator_ip", local_host]
    return args


def configure_ags_e2b_compatibility() -> None:
    domain = os.environ.get("E2B_DOMAIN", "")
    api_key = os.environ.get("E2B_API_KEY", "")
    if domain.endswith("tencentags.com") and api_key.startswith(("ark_", "ark-")):
        os.environ.setdefault("E2B_VALIDATE_API_KEY", "false")


def should_retry_sandbox_create(exc: Exception) -> bool:
    message = str(exc)
    return any(status in message for status in ("502", "503", "504", "Bad Gateway", "Gateway Timeout"))


# Default HTTP request_timeout for Sandbox.create.
#
# The e2b SDK ships with a 30-second default that matches stgw's idle timeout.
# For heavy templates such as `waa` (Windows Server boot), CXM sometimes needs
# 60-120s to bring the VM to Running state, which causes stgw to return a 502
# *while the backend keeps creating the VM successfully*. A naive client retry
# then leaks duplicate sandbox instances (observed in production: a single user
# request created two real CXM VMs).
#
# Raising request_timeout to 180s reliably covers the WAA cold-start budget so
# the SDK waits for the actual `201 Created` instead of hitting stgw's gateway
# timeout. Override via WAA_AGS_REQUEST_TIMEOUT if needed.
DEFAULT_REQUEST_TIMEOUT = float(os.environ.get("WAA_AGS_REQUEST_TIMEOUT", "180"))

# Optional opt-in to RFC 7240 `Prefer: respond-async` semantics.
#
# When enabled, run_ags requests asynchronous creation from sandportal:
#   - Server returns 202 Accepted with state="creating" almost immediately;
#   - run_ags then polls GET /sandboxes/{id} until state becomes "running".
#
# This sidesteps the stgw idle-timeout issue entirely. If the server does not
# recognize the Prefer header (older sandportal), it silently falls back to the
# synchronous path and our wait_until_running() short-circuits.
ASYNC_CREATE_ENABLED = os.environ.get("WAA_AGS_ASYNC_CREATE", "0") == "1"
ASYNC_CREATE_POLL_INTERVAL = float(os.environ.get("WAA_AGS_ASYNC_POLL_INTERVAL", "5"))
ASYNC_CREATE_DEADLINE = float(os.environ.get("WAA_AGS_ASYNC_DEADLINE", "900"))

# Whether to retry on 502/503/504 from the create endpoint. Disabled by default
# because retries on 5xx have been observed to silently duplicate sandboxes.
# Re-enable only if you know the server is idempotent for your case.
RETRY_ON_5XX_ENABLED = os.environ.get("WAA_AGS_RETRY_ON_5XX", "0") == "1"


def _sandbox_create_kwargs(template: str, timeout: int) -> dict:
    kwargs: dict = {
        "template": template,
        "timeout": timeout,
        "request_timeout": DEFAULT_REQUEST_TIMEOUT,
    }
    if ASYNC_CREATE_ENABLED:
        # e2b SDK >=0.x exposes `api_headers` for arbitrary HTTP header
        # injection. We use it here to flip on async creation without needing a
        # custom SDK fork.
        kwargs["api_headers"] = {"Prefer": "respond-async"}
    return kwargs


def _sandbox_state(sandbox) -> str:
    """Best-effort read of the current sandbox lifecycle state.

    Different e2b SDK versions expose this differently; we probe a few common
    accessors and fall back to '' if none of them are available. An empty
    string is treated by wait_until_running() as 'no state machine, assume
    running' (matches the legacy synchronous path).
    """
    for attr in ("state", "_state", "status"):
        value = getattr(sandbox, attr, None)
        if isinstance(value, str) and value:
            return value
    info_fn = getattr(sandbox, "get_info", None)
    if callable(info_fn):
        try:
            info = info_fn()
            value = getattr(info, "state", None) or (
                info.get("state") if isinstance(info, dict) else None
            )
            if isinstance(value, str) and value:
                return value
        except Exception as exc:
            logger.debug("get_info() failed while probing sandbox state: %s", exc)
    return ""


def wait_until_running(sandbox, deadline: float = ASYNC_CREATE_DEADLINE) -> None:
    """Poll the sandbox until it reaches the 'running' terminal state.

    No-op for sandboxes that are already running (or for SDK versions that do
    not expose a state field, in which case we trust the create() return).
    """
    state = _sandbox_state(sandbox)
    if state in ("", "running"):
        return
    if state == "creation_failed":
        error_code = getattr(sandbox, "error_code", "") or ""
        error_message = getattr(sandbox, "error_message", "") or ""
        raise RuntimeError(
            f"AGS sandbox creation failed: code={error_code or 'unknown'} "
            f"message={error_message or 'no detail'}"
        )

    logger.info(
        "AGS sandbox is in async state=%s, polling up to %.0fs for 'running'",
        state,
        deadline,
    )
    end_at = time.time() + deadline
    while time.time() < end_at:
        time.sleep(ASYNC_CREATE_POLL_INTERVAL)
        state = _sandbox_state(sandbox)
        if state == "running":
            logger.info("AGS sandbox transitioned to running")
            return
        if state == "creation_failed":
            error_code = getattr(sandbox, "error_code", "") or ""
            error_message = getattr(sandbox, "error_message", "") or ""
            raise RuntimeError(
                f"AGS sandbox creation failed: code={error_code or 'unknown'} "
                f"message={error_message or 'no detail'}"
            )
        logger.info("... still %s", state or "<unknown>")
    raise TimeoutError(f"AGS sandbox did not become running within {deadline:.0f}s")


def create_sandbox_with_retry(sandbox_cls, template: str, timeout: int, attempts: int = 3):
    # We default to a single attempt now: 5xx responses from POST /sandboxes
    # frequently coincide with successful backend creations, so retrying tends
    # to leak duplicate VMs. Set WAA_AGS_RETRY_ON_5XX=1 to opt back in.
    if not RETRY_ON_5XX_ENABLED:
        attempts = 1
    for attempt in range(1, attempts + 1):
        try:
            return sandbox_cls.create(**_sandbox_create_kwargs(template, timeout))
        except Exception as exc:
            if attempt >= attempts or not should_retry_sandbox_create(exc):
                raise
            delay = min(30, attempt * 5)
            logger.warning(
                "AGS sandbox create failed on attempt %d/%d, retrying in %ss: %s",
                attempt,
                attempts,
                delay,
                exc,
            )
            time.sleep(delay)


def main() -> int:
    load_runtime_env()
    client_dir = CLIENT_DIR

    template = os.environ.get("AGS_TEMPLATE", "waa")
    timeout = int(os.environ.get("AGS_TIMEOUT", str(10 * 60 * 60)))

    configure_ags_e2b_compatibility()

    from e2b_code_interpreter import Sandbox

    logger.info(
        "Creating AGS Windows sandbox with template: %s (async=%s, request_timeout=%ss)",
        template,
        ASYNC_CREATE_ENABLED,
        DEFAULT_REQUEST_TIMEOUT,
    )
    sandbox = create_sandbox_with_retry(Sandbox, template=template, timeout=timeout)
    if ASYNC_CREATE_ENABLED:
        wait_until_running(sandbox)
    access_token = getattr(sandbox, "_envd_access_token", None) or getattr(
        sandbox, "_SandboxBase__envd_access_token", None
    )

    proxies: list[LocalProxyServer] = []
    child: subprocess.Popen | None = None

    def cleanup(signum: int | None = None, _frame=None) -> None:
        if signum is not None:
            logger.info("Received signal %s, cleaning up...", signum)
        if child and child.poll() is None:
            child.terminate()
        for proxy in proxies:
            proxy.stop()
        try:
            sandbox.kill()
            logger.info("AGS sandbox killed: %s", sandbox.sandbox_id)
        except Exception as exc:
            logger.warning("Failed to kill AGS sandbox cleanly: %s", exc)

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, cleanup)

    try:
        local_host = select_local_host()
        proxies = [
            LocalProxyServer(local_host, SERVER_PORT, sandbox.get_host(SERVER_PORT), access_token),
            LocalProxyServer(local_host, CDP_PORT, sandbox.get_host(CDP_PORT), access_token, rewrite_cdp=True),
            LocalProxyServer(local_host, NOVNC_PORT, sandbox.get_host(NOVNC_PORT), access_token),
            LocalProxyServer(local_host, VLC_PORT, sandbox.get_host(VLC_PORT), access_token),
        ]
        for proxy in proxies:
            proxy.start()
        wait_for_server(local_host)
        logger.info("noVNC URL: http://%s:%d", local_host, NOVNC_PORT)

        env = os.environ.copy()
        env["WAA_AGS_REMOTE"] = "1"
        cmd = [sys.executable, "run.py", *add_default_args(sys.argv[1:], local_host)]
        logger.info("Starting WAA client: %s", " ".join(cmd))
        child = subprocess.Popen(cmd, cwd=client_dir, env=env)
        return child.wait()
    finally:
        cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
