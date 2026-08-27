import importlib.util
import json
import os
import socket
import socketserver
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path


EXAMPLE_ROOT = Path(__file__).resolve().parents[1]
PROXY_PATH = (
    EXAMPLE_ROOT
    / "overlay"
    / "OSWorld"
    / "desktop_env"
    / "providers"
    / "ags"
    / "cdp_proxy.py"
)
PROVIDER_PATH = PROXY_PATH.with_name("provider.py")
WRAPPER_PATH = PROXY_PATH.with_name("socat_wrapper.sh")
MAKEFILE_PATH = EXAMPLE_ROOT / "Makefile"
AGS_LOCK_PATH = EXAMPLE_ROOT / "overlay" / "OSWorld" / "requirements-ags.lock"


def load_proxy_module():
    spec = importlib.util.spec_from_file_location("ags_osworld_cdp_proxy", PROXY_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def recv_until(sock, marker):
    data = b""
    while marker not in data:
        chunk = sock.recv(65536)
        if not chunk:
            break
        data += chunk
    return data


class FakeChromeHandler(socketserver.BaseRequestHandler):
    def handle(self):
        request = recv_until(self.request, b"\r\n\r\n")
        self.server.requests.append(request)
        if b"Upgrade: websocket" in request:
            self.request.sendall(
                b"HTTP/1.1 101 Switching Protocols\r\n"
                b"Upgrade: websocket\r\n"
                b"Connection: Upgrade\r\n\r\n"
            )
            payload = self.request.recv(4)
            self.request.sendall(payload)
            return

        request_path = request.split(b" ", 2)[1]
        target = {
            "id": "test-page",
            "webSocketDebuggerUrl": (
                f"ws://localhost:{self.server.server_address[1]}/devtools/page/test-page"
            ),
            "devtoolsFrontendUrl": (
                "/devtools/inspector.html?"
                f"ws=localhost:{self.server.server_address[1]}/devtools/page/test-page"
            ),
        }
        if request_path.startswith(b"/json/list"):
            payload = [target]
        else:
            payload = {
                "Browser": "Fake Chrome",
                "webSocketDebuggerUrl": (
                    f"ws://localhost:{self.server.server_address[1]}/devtools/browser/test-browser"
                ),
            }
        body = json.dumps(payload).encode("utf-8")
        self.request.sendall(
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: application/json\r\n"
            + f"Content-Length: {len(body)}\r\n".encode()
            + b"\r\n"
            + body
        )


class ThreadingTestServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


class CDPProxyTest(unittest.TestCase):
    def setUp(self):
        self.proxy_module = load_proxy_module()
        self.chrome_server = ThreadingTestServer(("127.0.0.1", 0), FakeChromeHandler)
        self.chrome_server.requests = []
        self.proxy_module.CHROME_PORT = self.chrome_server.server_address[1]
        self.proxy_server = self.proxy_module.ThreadingTCPServer(
            ("127.0.0.1", 0), self.proxy_module.CDPProxyHandler
        )
        self.chrome_thread = threading.Thread(target=self.chrome_server.serve_forever, daemon=True)
        self.proxy_thread = threading.Thread(target=self.proxy_server.serve_forever, daemon=True)
        self.chrome_thread.start()
        self.proxy_thread.start()

    def tearDown(self):
        self.proxy_server.shutdown()
        self.proxy_server.server_close()
        self.chrome_server.shutdown()
        self.chrome_server.server_close()
        self.proxy_thread.join(timeout=2)
        self.chrome_thread.join(timeout=2)

    def connect_proxy(self):
        return socket.create_connection(self.proxy_server.server_address, timeout=2)

    def test_json_list_rewrites_host_and_real_devtools_frontend_url(self):
        authority = "9222-instance.ap-guangzhou.tencentags.com"
        with self.connect_proxy() as client:
            client.sendall(
                b"GET /json/list HTTP/1.1\r\n"
                b"Host: internal-route.example\r\n"
                + f"X-Forwarded-Host: {authority}\r\n".encode()
                + b"X-Forwarded-Proto: https\r\nConnection: close\r\n\r\n"
            )
            response = b""
            while True:
                chunk = client.recv(65536)
                if not chunk:
                    break
                response += chunk

        headers, body = response.split(b"\r\n\r\n", 1)
        payload = json.loads(body)[0]
        self.assertIn(b"HTTP/1.1 200 OK", headers)
        self.assertEqual(
            payload["webSocketDebuggerUrl"],
            f"wss://{authority}/devtools/page/test-page",
        )
        self.assertEqual(
            payload["devtoolsFrontendUrl"],
            f"/devtools/inspector.html?wss={authority}/devtools/page/test-page",
        )
        upstream_request = self.chrome_server.requests[0]
        expected_host = f"Host: 127.0.0.1:{self.chrome_server.server_address[1]}".encode()
        self.assertIn(expected_host, upstream_request)
        self.assertNotIn(b"Host: internal-route.example", upstream_request)

    def test_frontend_url_rewrite_preserves_remote_assets_and_normalizes_ws_scheme(self):
        authority = "9222-instance.ap-guangzhou.tencentags.com"
        remote_frontend = (
            "https://chrome-devtools-frontend.appspot.com/serve_rev/revision/inspector.html?"
            "ws=localhost:1337/devtools/page/test-page&panel=network#elements"
        )
        self.assertEqual(
            self.proxy_module.rewrite_cdp_url(remote_frontend, authority, "wss"),
            "https://chrome-devtools-frontend.appspot.com/serve_rev/revision/inspector.html?"
            f"wss={authority}/devtools/page/test-page&panel=network#elements",
        )

        loopback_frontend = (
            "http://127.0.0.1:1337/devtools/inspector.html?"
            "wss=localhost:1337/devtools/page/test-page"
        )
        self.assertEqual(
            self.proxy_module.rewrite_cdp_url(loopback_frontend, authority, "ws"),
            f"http://{authority}/devtools/inspector.html?"
            f"ws={authority}/devtools/page/test-page",
        )

    def test_non_json_fallback_rewrites_embedded_websocket_scheme(self):
        authority = "9222-instance.ap-guangzhou.tencentags.com"
        chrome_port = self.proxy_module.CHROME_PORT
        content = (
            "not-json /devtools/inspector.html?"
            f"ws=localhost:{chrome_port}/devtools/page/test-page "
            f"ws://localhost:{chrome_port}/devtools/page/test-page"
        ).encode()
        rewritten = self.proxy_module.rewrite_cdp_payload(content, authority, "wss").decode()
        self.assertIn(f"?wss={authority}/devtools/page/test-page", rewritten)
        self.assertIn(f"wss://{authority}/devtools/page/test-page", rewritten)

    def test_websocket_upgrade_is_tunneled(self):
        with self.connect_proxy() as client:
            client.sendall(
                b"GET /devtools/browser/test-browser HTTP/1.1\r\n"
                b"Host: 9222-instance.ap-guangzhou.tencentags.com\r\n"
                b"Connection: Upgrade\r\n"
                b"Upgrade: websocket\r\n\r\n"
            )
            response_headers = recv_until(client, b"\r\n\r\n")
            self.assertIn(b"101 Switching Protocols", response_headers)
            client.sendall(b"ping")
            self.assertEqual(client.recv(4), b"ping")

        upstream_request = self.chrome_server.requests[0]
        expected_host = f"Host: 127.0.0.1:{self.chrome_server.server_address[1]}".encode()
        self.assertIn(expected_host, upstream_request)

    def test_sandbox_proxy_has_no_third_party_imports(self):
        source = PROXY_PATH.read_text(encoding="utf-8")
        self.assertNotIn("aiohttp", source)

    def test_provider_deploys_proxy_without_installing_packages(self):
        source = PROVIDER_PATH.read_text(encoding="utf-8")
        self.assertNotIn("pip3 install --quiet aiohttp", source)
        self.assertNotIn("cat > /tmp/cdp_proxy.py", source)
        self.assertIn('/setup/upload', source)
        self.assertIn("upload_file(", source)
        self.assertIn('with_name("socat_wrapper.sh")', source)
        self.assertIn("validate CDP proxy prerequisites", source)
        self.assertIn("validate sandbox sudo access", source)
        self.assertIn("/bin/bash -n /tmp/socat_wrapper", source)
        self.assertIn("hashlib.sha256", source)
        self.assertEqual(source.count("web.Application(client_max_size=1024 ** 3)"), 2)

        wrapper = WRAPPER_PATH.read_text(encoding="utf-8")
        self.assertIn('nohup python3 -S "$PROXY_PATH"', wrapper)
        self.assertIn('echo "CDP proxy failed to listen on port $PROXY_PORT;', wrapper)
        self.assertIn("exit 1", wrapper)

    def test_setup_uses_upstream_requirements_and_adds_only_ags_lock(self):
        makefile = MAKEFILE_PATH.read_text(encoding="utf-8")
        self.assertIn("uv venv --clear", makefile)
        self.assertIn("-r requirements.txt", makefile)
        self.assertIn("-r requirements-ags.lock", makefile)
        self.assertNotIn("uv sync", makefile)
        self.assertNotIn("submodule update", makefile)
        self.assertNotIn("-r requirements.lock", makefile)
        self.assertFalse((EXAMPLE_ROOT / "overlay" / "OSWorld" / "requirements.txt").exists())
        self.assertFalse((EXAMPLE_ROOT / "overlay" / "OSWorld" / "requirements.lock").exists())

        locked = AGS_LOCK_PATH.read_text(encoding="utf-8")
        self.assertIn("e2b-code-interpreter==", locked)
        self.assertIn("aiohttp==", locked)
        self.assertNotIn("torch==", locked)
        self.assertNotIn("nvidia-", locked)

    def test_socat_wrapper_reuses_a_running_proxy(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            proxy_path = temp_path / "fake_proxy.py"
            pidfile = temp_path / "proxy.pid"
            log_path = temp_path / "proxy.log"
            with socket.socket() as port_socket:
                port_socket.bind(("127.0.0.1", 0))
                proxy_port = port_socket.getsockname()[1]

            proxy_path.write_text(
                "import os, socket\n"
                "port = int(os.environ['OSWORLD_CDP_PROXY_PORT'])\n"
                "with socket.create_server(('127.0.0.1', port)) as server:\n"
                "    while True:\n"
                "        connection, _ = server.accept()\n"
                "        connection.close()\n",
                encoding="utf-8",
            )
            env = os.environ.copy()
            env.update(
                {
                    "OSWORLD_CDP_PROXY_PATH": str(proxy_path),
                    "OSWORLD_CDP_PROXY_LOG": str(log_path),
                    "OSWORLD_CDP_PROXY_PIDFILE": str(pidfile),
                    "OSWORLD_CDP_PROXY_PORT": str(proxy_port),
                }
            )
            command = ["bash", str(WRAPPER_PATH), "tcp-listen:9222,fork"]
            proxy_pid = None
            try:
                first = subprocess.run(command, env=env, capture_output=True, text=True, timeout=15)
                self.assertEqual(first.returncode, 0, first.stderr)
                proxy_pid = int(pidfile.read_text().strip())

                second = subprocess.run(command, env=env, capture_output=True, text=True, timeout=5)
                self.assertEqual(second.returncode, 0, second.stderr)
                self.assertEqual(int(pidfile.read_text().strip()), proxy_pid)
            finally:
                if proxy_pid is not None:
                    try:
                        os.kill(proxy_pid, 15)
                    except ProcessLookupError:
                        pass
                    for _ in range(20):
                        try:
                            os.kill(proxy_pid, 0)
                        except ProcessLookupError:
                            break
                        time.sleep(0.05)

    def test_batch_runner_has_done_mock_without_llm_construction(self):
        source = (EXAMPLE_ROOT / "overlay" / "OSWorld" / "run_multienv.py").read_text()
        self.assertIn("OSWORLD_MOCK_LLM_DONE", source)
        self.assertIn('return "DONE", ["DONE"]', source)
        self.assertIn("agent = create_agent(args)", source)
        self.assertIn("env.vm_machine = env.controller.get_vm_machine()", source)


if __name__ == "__main__":
    unittest.main()
