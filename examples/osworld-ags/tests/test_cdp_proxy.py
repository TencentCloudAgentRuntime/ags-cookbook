import importlib.util
import json
import socket
import socketserver
import threading
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

        body = json.dumps(
            {
                "Browser": "Fake Chrome",
                "webSocketDebuggerUrl": (
                    f"ws://localhost:{self.server.server_address[1]}/devtools/browser/test-browser"
                ),
                "devtoolsFrontendUrl": (
                    f"http://localhost:{self.server.server_address[1]}/devtools/inspector.html"
                ),
            }
        ).encode("utf-8")
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

    def test_json_version_rewrites_host_and_public_urls(self):
        authority = "9222-instance.ap-guangzhou.tencentags.com"
        with self.connect_proxy() as client:
            client.sendall(
                b"GET /json/version HTTP/1.1\r\n"
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
        payload = json.loads(body)
        self.assertIn(b"HTTP/1.1 200 OK", headers)
        self.assertEqual(
            payload["webSocketDebuggerUrl"],
            f"wss://{authority}/devtools/browser/test-browser",
        )
        self.assertEqual(
            payload["devtoolsFrontendUrl"],
            f"https://{authority}/devtools/inspector.html",
        )
        upstream_request = self.chrome_server.requests[0]
        expected_host = f"Host: 127.0.0.1:{self.chrome_server.server_address[1]}".encode()
        self.assertIn(expected_host, upstream_request)
        self.assertNotIn(b"Host: internal-route.example", upstream_request)

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
        self.assertIn('files={"file_data":', source)
        self.assertIn("nohup python3 -S /tmp/cdp_proxy.py", source)
        self.assertEqual(source.count("web.Application(client_max_size=1024 ** 3)"), 2)

    def test_batch_runner_has_done_mock_without_llm_construction(self):
        source = (EXAMPLE_ROOT / "overlay" / "OSWorld" / "run_multienv.py").read_text()
        self.assertIn("OSWORLD_MOCK_LLM_DONE", source)
        self.assertIn('return "DONE", ["DONE"]', source)
        self.assertIn("agent = create_agent(args)", source)
        self.assertIn("env.vm_machine = env.controller.get_vm_machine()", source)


if __name__ == "__main__":
    unittest.main()
