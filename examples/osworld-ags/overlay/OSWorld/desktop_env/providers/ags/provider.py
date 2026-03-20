"""
Derived from xlang-ai/OSWorld under Apache-2.0.
Modified and redistributed by Agent Sandbox Cookbook as part of the OSWorld AGS overlay.
"""

import atexit
import logging
import signal
import time
import threading
import socket
import re
import requests
import weakref

from desktop_env.providers.base import Provider
from desktop_env.providers.ags.config import (
    AGS_TIMEOUT,
    SERVER_PORT,
    CHROMIUM_PORT,
    VNC_PORT,
    VLC_PORT,
)

logger = logging.getLogger("desktopenv.providers.ags.AGSProvider")
logger.setLevel(logging.INFO)
# Ensure logger has a handler to output logs
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)

# Global registry of active AGS providers for cleanup
_active_providers = weakref.WeakSet()
_cleanup_done = False


def _cleanup_all_providers():
    """Cleanup all active AGS sandboxes."""
    global _cleanup_done
    if _cleanup_done:
        return
    _cleanup_done = True

    providers = list(_active_providers)
    if not providers:
        return

    logger.info("Cleaning up %d AGS sandbox(es)...", len(providers))
    for provider in providers:
        try:
            if provider.sandbox:
                sandbox_id = provider.sandbox_id
                logger.info("Killing sandbox: %s", sandbox_id)
                provider.sandbox.kill()
                logger.info("Sandbox killed: %s", sandbox_id)
        except Exception as e:
            logger.error("Error killing sandbox: %s", e)


def _signal_handler(signum, frame):
    """Handle SIGTERM/SIGINT to cleanup sandboxes before exit."""
    logger.info("Received signal %d, cleaning up sandboxes...", signum)
    _cleanup_all_providers()
    # Re-raise to let the default handler terminate the process
    signal.signal(signum, signal.SIG_DFL)
    signal.raise_signal(signum)


# Register cleanup handlers
atexit.register(_cleanup_all_providers)

# Register signal handlers (but don't override if already set by parent)
try:
    # Only set if current handler is default
    if signal.getsignal(signal.SIGTERM) == signal.SIG_DFL:
        signal.signal(signal.SIGTERM, _signal_handler)
except (OSError, ValueError):
    pass  # May fail in some contexts (e.g., non-main thread)

# Check if aiohttp is available for CDP proxy
try:
    import asyncio
    import aiohttp
    from aiohttp import web
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    logger.warning("aiohttp package not available, CDP proxy will have limited functionality")


def find_available_port(start_port: int) -> int:
    """Find an available port starting from start_port."""
    port = start_port
    while port < 65535:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("localhost", port))
                return port
            except OSError:
                port += 1
    raise RuntimeError(f"No available port found starting from {start_port}")


def find_and_bind_port(start_port: int, max_retries: int = 100) -> socket.socket:
    """
    Find an available port and return a socket bound to it.

    This function atomically finds and binds to a port, avoiding race conditions
    in concurrent scenarios where multiple processes try to bind to the same port.

    Args:
        start_port: Port number to start searching from
        max_retries: Maximum number of ports to try

    Returns:
        A socket bound to the port. Caller must close this socket before starting
        the actual server, or use SO_REUSEADDR.
    """
    port = start_port
    for _ in range(max_retries):
        if port >= 65535:
            port = start_port  # Wrap around
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("localhost", port))
            return sock
        except OSError:
            sock.close()
            port += 1
    raise RuntimeError(f"No available port found starting from {start_port}")


class LocalProxyServer:
    """
    Local proxy server for AGS sandbox, supporting both HTTP and WebSocket.

    Uses aiohttp to handle HTTP requests and WebSocket connections on the same port.
    This is essential for services like noVNC that use WebSocket (websockify).
    """

    def __init__(self, local_port: int, target_host: str, access_token: str):
        self.local_port = local_port
        self.target_host = target_host
        self.access_token = access_token
        self.thread = None
        self.loop = None
        self.runner = None
        self._start_error = None
        self._start_event = None

    def start(self, max_retries: int = 500):
        """
        Start the proxy server in a background thread.

        Args:
            max_retries: Maximum number of port binding retries if address is in use
        """
        if not AIOHTTP_AVAILABLE:
            logger.error("aiohttp not available, local proxy cannot start")
            return

        self._start_error = None
        self._start_event = threading.Event()
        self._max_retries = max_retries

        self.thread = threading.Thread(target=self._run_server, daemon=True)
        self.thread.start()

        # Wait for server to start or fail
        self._start_event.wait(timeout=10)

        if self._start_error:
            raise self._start_error

        logger.info(
            "Local proxy started: localhost:%d -> %s",
            self.local_port,
            self.target_host,
        )

    def _run_server(self):
        """Run the aiohttp server in a dedicated event loop."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        try:
            self.loop.run_until_complete(self._start_server())
            self._start_event.set()
            self.loop.run_forever()
        except Exception as e:
            logger.error("Local proxy server error: %s", e)
            self._start_error = e
            self._start_event.set()
        finally:
            if not self.loop.is_closed():
                self.loop.close()

    async def _start_server(self):
        """Start the aiohttp web server with retry on port conflict."""
        import random
        app = web.Application()

        # Route all requests through our handler
        app.router.add_route('*', '/{path:.*}', self._handle_request)

        self.runner = web.AppRunner(app)
        await self.runner.setup()

        last_error = None
        base_port = self.local_port
        random_offset = random.randint(0, 1000)
        current_port = base_port + random_offset
        max_retries = getattr(self, '_max_retries', 500)

        for attempt in range(max_retries):
            if current_port >= 65535:
                current_port = base_port + (current_port - 65535)
            try:
                site = web.TCPSite(self.runner, 'localhost', current_port)
                await site.start()
                self.local_port = current_port
                return
            except OSError as e:
                last_error = e
                if e.errno in (98, 48):
                    current_port += 1
                    continue
                raise

        raise OSError(f"Failed to bind after {max_retries} retries: {last_error}")

    async def _handle_request(self, request: web.Request):
        """Handle incoming HTTP or WebSocket request."""
        path = "/" + request.match_info.get('path', '')
        if request.query_string:
            path += '?' + request.query_string

        # Check if this is a WebSocket upgrade request
        if request.headers.get('Upgrade', '').lower() == 'websocket':
            return await self._handle_websocket(request, path)
        else:
            return await self._handle_http(request, path)

    async def _handle_http(self, request: web.Request, path: str):
        """Handle HTTP request by proxying to the remote sandbox."""
        target_url = f"https://{self.target_host}{path}"
        headers = {"X-Access-Token": self.access_token}

        # Forward original headers (except host)
        for key, value in request.headers.items():
            if key.lower() not in ("host", "transfer-encoding"):
                headers[key] = value
        headers["X-Access-Token"] = self.access_token

        body = await request.read()

        logger.debug("Proxy HTTP %s: %s -> %s", request.method, path, target_url)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.request(
                    request.method,
                    target_url,
                    headers=headers,
                    data=body if body else None,
                    timeout=aiohttp.ClientTimeout(total=300, connect=30),
                ) as response:
                    content = await response.read()

                    if response.status >= 500:
                        logger.warning(
                            "Remote returned error %d for %s: %s",
                            response.status, path,
                            content.decode('utf-8', errors='replace')[:500]
                        )
                    elif response.status >= 400:
                        logger.debug(
                            "Remote returned %d for %s",
                            response.status, path,
                        )

                    resp_headers = {}
                    for key, value in response.headers.items():
                        if key.lower() not in ("transfer-encoding", "content-encoding", "content-length"):
                            resp_headers[key] = value

                    return web.Response(
                        body=content,
                        status=response.status,
                        headers=resp_headers,
                    )
        except Exception as e:
            logger.error("Proxy HTTP error for %s: %s", path, e)
            return web.Response(text=str(e), status=502)

    async def _handle_websocket(self, request: web.Request, path: str):
        """Handle WebSocket connection by bidirectional proxying."""
        ws_client = web.WebSocketResponse()
        await ws_client.prepare(request)

        remote_url = f"wss://{self.target_host}{path}"
        headers = {"X-Access-Token": self.access_token}

        logger.debug("Proxy WebSocket: %s -> %s", path, remote_url)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(remote_url, headers=headers) as ws_remote:
                    async def forward_client_to_remote():
                        try:
                            async for msg in ws_client:
                                if msg.type == aiohttp.WSMsgType.TEXT:
                                    await ws_remote.send_str(msg.data)
                                elif msg.type == aiohttp.WSMsgType.BINARY:
                                    await ws_remote.send_bytes(msg.data)
                                elif msg.type == aiohttp.WSMsgType.CLOSE:
                                    break
                        except Exception as e:
                            logger.debug("Client->Remote forward ended: %s", e)

                    async def forward_remote_to_client():
                        try:
                            async for msg in ws_remote:
                                if msg.type == aiohttp.WSMsgType.TEXT:
                                    await ws_client.send_str(msg.data)
                                elif msg.type == aiohttp.WSMsgType.BINARY:
                                    await ws_client.send_bytes(msg.data)
                                elif msg.type == aiohttp.WSMsgType.CLOSE:
                                    break
                        except Exception as e:
                            logger.debug("Remote->Client forward ended: %s", e)

                    await asyncio.gather(
                        forward_client_to_remote(),
                        forward_remote_to_client(),
                        return_exceptions=True,
                    )

        except Exception as e:
            logger.error("Proxy WebSocket error: %s", e)

        return ws_client

    def stop(self):
        """Stop the proxy server."""
        if not self.loop:
            self.runner = None
            self.thread = None
            return

        # Cancel all pending tasks
        try:
            async def _cancel_all():
                tasks = [t for t in asyncio.all_tasks(self.loop)
                         if t is not asyncio.current_task()]
                for t in tasks:
                    t.cancel()
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)

            future = asyncio.run_coroutine_threadsafe(_cancel_all(), self.loop)
            future.result(timeout=5)
        except Exception as e:
            logger.debug("Local proxy cancel tasks: %s", e)

        # Cleanup aiohttp runner
        if self.runner:
            try:
                future = asyncio.run_coroutine_threadsafe(
                    self.runner.cleanup(),
                    self.loop
                )
                future.result(timeout=5)
            except Exception as e:
                logger.debug("Local proxy cleanup error: %s", e)

        # Stop the event loop
        self.loop.call_soon_threadsafe(self.loop.stop)

        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=3)

        if not self.loop.is_closed():
            self.loop.close()

        self.runner = None
        self.loop = None
        self.thread = None


class CDPProxyServer:
    """
    CDP (Chrome DevTools Protocol) proxy server that supports both HTTP and WebSocket.

    Uses aiohttp to handle both HTTP requests and WebSocket connections on the same port.
    """

    def __init__(self, local_port: int, target_host: str, access_token: str):
        self.local_port = local_port
        self.target_host = target_host
        self.access_token = access_token
        self.thread = None
        self.loop = None
        self.runner = None
        self._start_error = None
        self._start_event = None

    def start(self, max_retries: int = 50):
        """
        Start the CDP proxy server in a background thread.

        Args:
            max_retries: Maximum number of port binding retries if address is in use
        """
        if not AIOHTTP_AVAILABLE:
            logger.error("aiohttp not available, CDP proxy cannot start")
            return

        self._start_error = None
        self._start_event = threading.Event()
        self._max_retries = max_retries

        self.thread = threading.Thread(target=self._run_server, daemon=True)
        self.thread.start()

        # Wait for server to start or fail
        self._start_event.wait(timeout=10)

        if self._start_error:
            raise self._start_error

        logger.info(
            "CDP proxy started: localhost:%d -> %s",
            self.local_port,
            self.target_host,
        )

    def _run_server(self):
        """Run the aiohttp server."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        try:
            self.loop.run_until_complete(self._start_server())
            self._start_event.set()  # Signal successful start
            self.loop.run_forever()
        except Exception as e:
            logger.error("CDP proxy server error: %s", e)
            self._start_error = e
            self._start_event.set()  # Signal failed start
        finally:
            if not self.loop.is_closed():
                self.loop.close()

    async def _start_server(self):
        """Start the aiohttp web server with retry on port conflict."""
        import random
        app = web.Application()

        # Route all requests through our handler
        app.router.add_route('*', '/{path:.*}', self._handle_request)

        self.runner = web.AppRunner(app)
        await self.runner.setup()

        # Try to bind with retries to handle concurrent port conflicts
        # Use random offset to reduce collision probability in concurrent scenarios
        last_error = None
        base_port = self.local_port
        random_offset = random.randint(0, 1000)
        current_port = base_port + random_offset
        max_retries = getattr(self, '_max_retries', 500)

        for attempt in range(max_retries):
            if current_port >= 65535:
                current_port = base_port + (current_port - 65535)
            try:
                site = web.TCPSite(self.runner, 'localhost', current_port)
                await site.start()
                self.local_port = current_port  # Update to the actual bound port
                return
            except OSError as e:
                last_error = e
                # errno 98 on Linux, errno 48 on macOS = Address already in use
                if e.errno in (98, 48):
                    current_port += 1
                    continue
                raise

        raise OSError(f"Failed to bind after {max_retries} retries: {last_error}")

    async def _handle_request(self, request: web.Request):
        """Handle incoming HTTP or WebSocket request."""
        path = "/" + request.match_info.get('path', '')
        if request.query_string:
            path += '?' + request.query_string

        # Check if this is a WebSocket upgrade request
        if request.headers.get('Upgrade', '').lower() == 'websocket':
            return await self._handle_websocket(request, path)
        else:
            return await self._handle_http(request, path)

    async def _handle_http(self, request: web.Request, path: str):
        """Handle HTTP request."""
        target_url = f"https://{self.target_host}{path}"
        # Note: Host header is handled by the internal proxy in the sandbox
        headers = {"X-Access-Token": self.access_token}

        logger.debug("CDP HTTP: %s -> %s", path, target_url)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(target_url, headers=headers) as response:
                    content = await response.read()

                    # If remote returns error, log it clearly
                    if response.status >= 400:
                        logger.error("Remote CDP returned error %d: %s",
                                   response.status, content.decode('utf-8', errors='replace')[:500])

                    # Rewrite WebSocket URLs in /json/* responses
                    if path.startswith("/json") and response.status == 200:
                        content_str = content.decode("utf-8")
                        logger.debug("CDP /json response: %s", content_str[:200])

                        # Replace remote WebSocket URLs with local
                        # Pattern matches wss://host or ws://host followed by path
                        content_str = re.sub(
                            r'wss?://[^/\s"]+',
                            f'ws://localhost:{self.local_port}',
                            content_str
                        )
                        logger.debug("CDP /json rewritten: %s", content_str[:200])
                        content = content_str.encode("utf-8")

                    return web.Response(
                        body=content,
                        status=response.status,
                        content_type=response.content_type
                    )
        except Exception as e:
            logger.error("CDP HTTP proxy error: %s", e, exc_info=True)
            return web.Response(text=str(e), status=502)

    async def _handle_websocket(self, request: web.Request, path: str):
        """Handle WebSocket connection."""
        ws_client = web.WebSocketResponse()
        await ws_client.prepare(request)

        remote_url = f"wss://{self.target_host}{path}"
        # Note: Host header is handled by the internal proxy in the sandbox
        headers = {"X-Access-Token": self.access_token}

        logger.debug("CDP WebSocket: %s -> %s", path, remote_url)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(remote_url, headers=headers) as ws_remote:
                    # Create tasks for bidirectional forwarding
                    async def forward_client_to_remote():
                        try:
                            async for msg in ws_client:
                                if msg.type == aiohttp.WSMsgType.TEXT:
                                    await ws_remote.send_str(msg.data)
                                elif msg.type == aiohttp.WSMsgType.BINARY:
                                    await ws_remote.send_bytes(msg.data)
                                elif msg.type == aiohttp.WSMsgType.CLOSE:
                                    break
                        except Exception as e:
                            logger.debug("Client->Remote forward ended: %s", e)

                    async def forward_remote_to_client():
                        try:
                            async for msg in ws_remote:
                                if msg.type == aiohttp.WSMsgType.TEXT:
                                    await ws_client.send_str(msg.data)
                                elif msg.type == aiohttp.WSMsgType.BINARY:
                                    await ws_client.send_bytes(msg.data)
                                elif msg.type == aiohttp.WSMsgType.CLOSE:
                                    break
                        except Exception as e:
                            logger.debug("Remote->Client forward ended: %s", e)

                    # Run both forwarding tasks
                    await asyncio.gather(
                        forward_client_to_remote(),
                        forward_remote_to_client(),
                        return_exceptions=True
                    )

        except Exception as e:
            logger.error("CDP WebSocket proxy error: %s", e)

        return ws_client

    def stop(self):
        """Stop the CDP proxy server."""
        if not self.loop:
            self.runner = None
            self.thread = None
            return

        # Step 1: 取消所有 pending tasks，避免 "Task was destroyed but it is pending"
        try:
            async def _cancel_all():
                tasks = [t for t in asyncio.all_tasks(self.loop)
                         if t is not asyncio.current_task()]
                for t in tasks:
                    t.cancel()
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)

            future = asyncio.run_coroutine_threadsafe(_cancel_all(), self.loop)
            future.result(timeout=5)
        except Exception as e:
            logger.debug("CDP proxy cancel tasks: %s", e)

        # Step 2: 清理 aiohttp runner
        if self.runner:
            try:
                future = asyncio.run_coroutine_threadsafe(
                    self.runner.cleanup(),
                    self.loop
                )
                future.result(timeout=5)
            except Exception as e:
                logger.debug("CDP proxy cleanup error: %s", e)

        # Step 3: 停止事件循环
        self.loop.call_soon_threadsafe(self.loop.stop)

        # Step 4: 等待后台线程结束
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=3)

        # Step 5: 关闭事件循环
        if not self.loop.is_closed():
            self.loop.close()

        # 清空引用
        self.runner = None
        self.loop = None
        self.thread = None


class AGSProvider(Provider):
    """
    AGS (Agent Sandbox) Provider for OSWorld.

    Uses E2B/Agent Sandbox SDK to create and manage cloud sandboxes.
    Creates local proxy servers to handle authentication transparently.

    Requires: pip install e2b-code-interpreter

    Environment variables:
    - E2B_API_KEY: API key for Agent Sandbox (required)
    - E2B_DOMAIN: Domain for Agent Sandbox (optional)
    - AGS_TEMPLATE: Template name (optional, default: osworld)
    """

    def __init__(self):
        super().__init__(None)
        self.sandbox = None
        self.sandbox_id = None
        self.envd_access_token = None

        # Local proxy servers
        self.proxy_servers = {}
        self.local_server_port = None
        self.local_chromium_port = None
        self.local_vnc_port = None
        self.local_vlc_port = None

        # Register for cleanup on exit
        _active_providers.add(self)

    def _get_sandbox_host(self, port: int) -> str:
        """Get the remote host URL for a specific port on the sandbox."""
        return self.sandbox.get_host(port)

    def _start_local_proxies(self):
        """Start local proxy servers for all required ports."""
        # HTTP + WebSocket proxies (aiohttp-based)
        http_port_mapping = [
            ("server", SERVER_PORT, 15000),
            ("vnc", VNC_PORT, 15910),
            ("vlc", VLC_PORT, 18080),
        ]

        for name, remote_port, local_start in http_port_mapping:
            remote_host = self._get_sandbox_host(remote_port)

            proxy = LocalProxyServer(local_start, remote_host, self.envd_access_token)
            proxy.start()  # This will retry and update local_port if needed
            self.proxy_servers[name] = proxy

            # Get the actual bound port from the proxy object
            if name == "server":
                self.local_server_port = proxy.local_port
            elif name == "vnc":
                self.local_vnc_port = proxy.local_port
            elif name == "vlc":
                self.local_vlc_port = proxy.local_port

        # CDP proxy for Chromium (supports WebSocket)
        chromium_remote_host = self._get_sandbox_host(CHROMIUM_PORT)
        cdp_proxy = CDPProxyServer(19222, chromium_remote_host, self.envd_access_token)
        cdp_proxy.start()  # This will retry and update local_port if needed
        self.proxy_servers["chromium"] = cdp_proxy
        self.local_chromium_port = cdp_proxy.local_port

    def _stop_local_proxies(self):
        """Stop all local proxy servers."""
        for name, proxy in self.proxy_servers.items():
            try:
                proxy.stop()
                logger.info("Stopped proxy: %s", name)
            except Exception as e:
                logger.error("Error stopping proxy %s: %s", name, e)
        self.proxy_servers = {}

    def _wait_for_vm_ready(self, timeout: int = 300):
        """Wait for VM to be ready by checking screenshot endpoint."""
        start_time = time.time()
        url = f"http://localhost:{self.local_server_port}/screenshot"

        while time.time() - start_time < timeout:
            try:
                response = requests.get(url, timeout=(10, 10))
                if response.status_code == 200:
                    logger.info("AGS sandbox VM is ready")
                    return True
            except Exception:
                pass
            logger.info("Waiting for AGS sandbox VM to be ready...")
            time.sleep(2)

        raise TimeoutError(f"AGS sandbox VM failed to become ready within {timeout}s")

    def _wait_for_chromium_ready(self, timeout: int = 60):
        """Wait for Chromium CDP to be ready."""
        start_time = time.time()
        url = f"http://localhost:{self.local_chromium_port}/json/version"

        while time.time() - start_time < timeout:
            try:
                response = requests.get(url, timeout=(5, 10))
                if response.status_code == 200:
                    logger.info("Chromium CDP is ready")
                    return True
                else:
                    logger.debug("Chromium CDP not ready, status: %d", response.status_code)
            except Exception as e:
                logger.debug("Chromium CDP not ready: %s", e)
            time.sleep(2)

        logger.warning("Chromium CDP failed to become ready within %ds", timeout)

    def _ensure_chromium_cdp_bridge(self):
        """
        Pre-deploy CDP proxy infrastructure for Chromium.

        Does NOT start Chrome — Chrome is started by task setup's config steps
        (e.g., "launch google-chrome --remote-debugging-port=1337").

        This method:
        1. Installs aiohttp dependency
        2. Deploys /tmp/cdp_proxy.py script (rewrites Host header for Chrome CDP)
        3. Uses sudo to replace /usr/bin/socat with a wrapper that intercepts
           "socat tcp-listen:9222,fork tcp:localhost:1337" calls from task setup,
           starts cdp_proxy.py instead, and passes other socat calls through.
        """
        import json as json_module
        exec_url = f"http://localhost:{self.local_server_port}/setup/execute"
        headers = {"Content-Type": "application/json"}

        def exec_shell(cmd: str) -> dict:
            """Execute a shell command in the sandbox."""
            try:
                payload = json_module.dumps({"command": cmd, "shell": True})
                resp = requests.post(exec_url, headers=headers, data=payload, timeout=120)
                if resp.status_code == 200:
                    result = resp.json()
                    logger.debug("exec '%s': %s", cmd[:50], result.get("output", "")[:200])
                    return result
                else:
                    logger.warning("exec '%s' failed: %s", cmd[:50], resp.text[:200])
                    return {"status": "error", "output": resp.text}
            except Exception as e:
                logger.warning("exec '%s' error: %s", cmd[:50], e)
                return {"status": "error", "output": str(e)}

        # Ensure aiohttp is installed
        exec_shell("python3 -c 'import aiohttp' 2>/dev/null || pip3 install --quiet aiohttp")

        # Create CDP proxy script that rewrites Host header
        proxy_script = r'''
import asyncio
import aiohttp
from aiohttp import web
import re

CHROME_HOST = "127.0.0.1"
CHROME_PORT = 1337

async def handle_http(request):
    path = request.path
    if request.query_string:
        path += "?" + request.query_string
    url = f"http://{CHROME_HOST}:{CHROME_PORT}{path}"
    headers = {"Host": f"localhost:{CHROME_PORT}"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                content = await resp.read()
                if path.startswith("/json"):
                    content_str = content.decode("utf-8")
                    content_str = re.sub(r"ws://[^/\s\"]+:1337", "ws://localhost:9222", content_str)
                    content_str = content_str.replace(f"localhost:{CHROME_PORT}", "localhost:9222")
                    content = content_str.encode("utf-8")
                return web.Response(body=content, status=resp.status, content_type=resp.content_type)
    except Exception as e:
        return web.Response(text=str(e), status=502)

async def handle_websocket(request):
    ws_client = web.WebSocketResponse()
    await ws_client.prepare(request)
    path = request.path
    url = f"ws://{CHROME_HOST}:{CHROME_PORT}{path}"
    headers = {"Host": f"localhost:{CHROME_PORT}"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(url, headers=headers) as ws_remote:
                async def forward_to_remote():
                    async for msg in ws_client:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            await ws_remote.send_str(msg.data)
                        elif msg.type == aiohttp.WSMsgType.BINARY:
                            await ws_remote.send_bytes(msg.data)
                        elif msg.type == aiohttp.WSMsgType.CLOSE:
                            break
                async def forward_to_client():
                    async for msg in ws_remote:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            await ws_client.send_str(msg.data)
                        elif msg.type == aiohttp.WSMsgType.BINARY:
                            await ws_client.send_bytes(msg.data)
                        elif msg.type == aiohttp.WSMsgType.CLOSE:
                            break
                await asyncio.gather(forward_to_remote(), forward_to_client(), return_exceptions=True)
    except Exception as e:
        print(f"WebSocket error: {e}")
    return ws_client

async def handle_request(request):
    if request.headers.get("Upgrade", "").lower() == "websocket":
        return await handle_websocket(request)
    return await handle_http(request)

app = web.Application()
app.router.add_route("*", "/{path:.*}", handle_request)
if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=9222, print=None)
'''
        # Write proxy script
        write_cmd = f"cat > /tmp/cdp_proxy.py << 'CDPPROXYSCRIPT'\n{proxy_script}\nCDPPROXYSCRIPT"
        exec_shell(write_cmd)

        # Install socat wrapper using sudo (password: password).
        # 1. Backup real socat binary
        # 2. Replace /usr/bin/socat with a bash wrapper that:
        #    - Intercepts "socat tcp-listen:9222,..." and starts cdp_proxy.py instead
        #    - Passes all other socat calls through to the real binary
        socat_wrapper = (
            '#!/bin/bash\n'
            'REAL=/usr/bin/socat.real\n'
            'for arg in "$@"; do\n'
            '  case "$arg" in\n'
            '    tcp-listen:9222*)\n'
            '      nohup python3 /tmp/cdp_proxy.py >/tmp/cdp_proxy.log 2>&1 &\n'
            '      for i in $(seq 1 50); do\n'
            '        ss -tlnp 2>/dev/null | grep -q ":9222 " && exit 0\n'
            '        sleep 0.2\n'
            '      done\n'
            '      exit 0\n'
            '      ;;\n'
            '  esac\n'
            'done\n'
            'exec "$REAL" "$@"\n'
        )
        # Write wrapper to /tmp first, then use sudo to install
        exec_shell(f"cat > /tmp/socat_wrapper << 'SOCATWRAPPER'\n{socat_wrapper}SOCATWRAPPER")
        exec_shell("chmod +x /tmp/socat_wrapper")
        exec_shell("echo password | sudo -S cp /usr/bin/socat /usr/bin/socat.real")
        exec_shell("echo password | sudo -S cp /tmp/socat_wrapper /usr/bin/socat")
        exec_shell("echo password | sudo -S chmod +x /usr/bin/socat")

        # Verify wrapper is installed
        result = exec_shell("file /usr/bin/socat && file /usr/bin/socat.real")
        logger.info("socat wrapper installed: %s", result.get("output", "").strip())

    def start_emulator(self, path_to_vm: str, headless: bool, os_type: str = None):
        """
        Start an AGS sandbox.

        Args:
            path_to_vm: Ignored, template is read from AGS_TEMPLATE env var
            headless: Ignored for AGS (always headless in cloud)
            os_type: Ignored for AGS
        """
        try:
            from e2b_code_interpreter import Sandbox
        except ImportError:
            raise ImportError(
                "e2b-code-interpreter package is required for AGS provider. "
                "Install it with: pip install e2b-code-interpreter"
            )

        from desktop_env.providers.ags.config import AGS_TEMPLATE
        template = AGS_TEMPLATE
        logger.info("Creating AGS sandbox with template: %s", template)

        # Create sandbox using Sandbox.create() (not constructor)
        self.sandbox = Sandbox.create(template=template, timeout=AGS_TIMEOUT)
        self.sandbox_id = self.sandbox.sandbox_id

        # Get access token
        self.envd_access_token = getattr(self.sandbox, "_envd_access_token", None)
        if not self.envd_access_token:
            self.envd_access_token = getattr(
                self.sandbox, "_SandboxBase__envd_access_token", None
            )

        logger.info("AGS sandbox created with ID: %s", self.sandbox_id)

        # Start local proxy servers
        self._start_local_proxies()

        # Wait for VM to be ready
        self._wait_for_vm_ready()

        # Deploy CDP proxy infrastructure (cdp_proxy.py + socat wrapper)
        # Does NOT start Chrome — Chrome will be started by task setup config steps
        self._ensure_chromium_cdp_bridge()

    def get_ip_address(self, path_to_vm: str) -> str:
        """
        Get the connection info for the sandbox.

        Returns localhost with local proxy ports in the format expected by DesktopEnv:
        host:server_port:chromium_port:vnc_port:vlc_port
        """
        if not self.sandbox:
            raise RuntimeError("Sandbox not started")

        return (
            f"localhost:{self.local_server_port}:{self.local_chromium_port}"
            f":{self.local_vnc_port}:{self.local_vlc_port}"
        )

    def save_state(self, path_to_vm: str, snapshot_name: str):
        raise NotImplementedError("Snapshots not available for AGS provider")

    def revert_to_snapshot(self, path_to_vm: str, snapshot_name: str):
        """Revert by stopping and restarting the sandbox."""
        logger.warning("AGS snapshot revert not supported, skipping...")

    def stop_emulator(self, path_to_vm: str, region=None, *args, **kwargs):
        """Stop and kill the AGS sandbox."""
        logger.info("stop_emulator called, sandbox_id=%s", self.sandbox_id)

        # Stop local proxies first
        self._stop_local_proxies()

        if self.sandbox:
            logger.info("Killing AGS sandbox: %s", self.sandbox_id)
            try:
                self.sandbox.kill()
                logger.info("AGS sandbox killed successfully: %s", self.sandbox_id)
            except Exception as e:
                logger.error("Error killing AGS sandbox %s: %s", self.sandbox_id, e)
            finally:
                self.sandbox = None
                self.sandbox_id = None
                self.envd_access_token = None
        else:
            logger.warning("stop_emulator called but sandbox is None")
