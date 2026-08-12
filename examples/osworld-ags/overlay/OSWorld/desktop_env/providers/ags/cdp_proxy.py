"""Standard-library Chrome CDP proxy deployed inside the AGS sandbox."""

import json
import re
import select
import socket
import socketserver
import sys
from urllib.parse import urlparse, urlunparse

CHROME_HOST = "127.0.0.1"
CHROME_PORT = 1337
LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 9222
BUFFER_SIZE = 65536


def log(message):
    print(message, file=sys.stderr, flush=True)


def rewrite_cdp_url(value, local_port=9222):
    if not isinstance(value, str):
        return value
    parsed = urlparse(value)
    if parsed.scheme in {"ws", "wss"}:
        return urlunparse(("ws", f"127.0.0.1:{local_port}", parsed.path, "", parsed.query, parsed.fragment))
    if parsed.scheme in {"http", "https"}:
        return urlunparse(("http", f"127.0.0.1:{local_port}", parsed.path, "", parsed.query, parsed.fragment))
    return value


def rewrite_cdp_payload(content, local_port=9222):
    try:
        payload = json.loads(content.decode("utf-8"))
    except Exception:
        content_str = content.decode("utf-8", errors="replace")
        content_str = re.sub(r"wss?://[^/\\s\"]+:1337", "ws://127.0.0.1:9222", content_str)
        content_str = content_str.replace(f"localhost:{CHROME_PORT}", "127.0.0.1:9222")
        return content_str.encode("utf-8")

    def rewrite_item(item):
        if isinstance(item, dict):
            rewritten = dict(item)
            for key in ("webSocketDebuggerUrl", "devtoolsFrontendUrl"):
                if key in rewritten:
                    rewritten[key] = rewrite_cdp_url(rewritten[key], local_port)
            return rewritten
        return item

    if isinstance(payload, list):
        payload = [rewrite_item(item) for item in payload]
    elif isinstance(payload, dict):
        payload = rewrite_item(payload)

    return json.dumps(payload).encode("utf-8")


def recv_until(sock, marker):
    data = b""
    while marker not in data:
        chunk = sock.recv(BUFFER_SIZE)
        if not chunk:
            break
        data += chunk
    return data


def rewrite_host_header(request_bytes):
    return re.sub(
        br"(?im)^Host:\s*[^\r\n]+",
        f"Host: {CHROME_HOST}:{CHROME_PORT}".encode(),
        request_bytes,
        count=1,
    )


def parse_request_path(request_bytes):
    first_line = request_bytes.split(b"\r\n", 1)[0].decode("latin1", errors="replace")
    parts = first_line.split()
    return parts[1] if len(parts) >= 2 else "/"


def is_websocket_upgrade(request_bytes):
    return bool(re.search(br"(?im)^Upgrade:\s*websocket\s*$", request_bytes))


def read_http_response(sock):
    data = recv_until(sock, b"\r\n\r\n")
    if b"\r\n\r\n" not in data:
        return data

    header_bytes, body = data.split(b"\r\n\r\n", 1)
    headers = header_bytes.decode("latin1", errors="replace").split("\r\n")
    content_length = None
    chunked = False
    for line in headers[1:]:
        name, _, value = line.partition(":")
        if name.lower() == "content-length":
            try:
                content_length = int(value.strip())
            except ValueError:
                content_length = None
        elif name.lower() == "transfer-encoding" and "chunked" in value.lower():
            chunked = True

    if content_length is not None:
        while len(body) < content_length:
            chunk = sock.recv(BUFFER_SIZE)
            if not chunk:
                break
            body += chunk
    elif chunked:
        while b"\r\n0\r\n\r\n" not in body:
            chunk = sock.recv(BUFFER_SIZE)
            if not chunk:
                break
            body += chunk
    else:
        while True:
            chunk = sock.recv(BUFFER_SIZE)
            if not chunk:
                break
            body += chunk

    return header_bytes + b"\r\n\r\n" + body


def replace_header(header_text, name, value):
    pattern = re.compile(rf"(?im)^{re.escape(name)}:\s*[^\r\n]*")
    replacement = f"{name}: {value}"
    if pattern.search(header_text):
        return pattern.sub(replacement, header_text, count=1)
    return header_text + f"\r\n{name}: {value}"


def rewrite_http_response(response_bytes, path):
    if b"\r\n\r\n" not in response_bytes or not path.startswith("/json"):
        return response_bytes
    header_bytes, body = response_bytes.split(b"\r\n\r\n", 1)
    rewritten_body = rewrite_cdp_payload(body, LISTEN_PORT)
    header_text = header_bytes.decode("latin1", errors="replace")
    header_text = re.sub(r"(?im)^Transfer-Encoding:\s*chunked\r?\n?", "", header_text)
    header_text = replace_header(header_text, "Content-Length", str(len(rewritten_body)))
    return header_text.encode("latin1") + b"\r\n\r\n" + rewritten_body


def tunnel(left, right):
    sockets = [left, right]
    try:
        while True:
            readable, _, _ = select.select(sockets, [], [], 60)
            if not readable:
                continue
            for src in readable:
                dst = right if src is left else left
                data = src.recv(BUFFER_SIZE)
                if not data:
                    return
                dst.sendall(data)
    finally:
        for sock in sockets:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass


class CDPProxyHandler(socketserver.BaseRequestHandler):
    def handle(self):
        request_bytes = recv_until(self.request, b"\r\n\r\n")
        if not request_bytes:
            return
        path = parse_request_path(request_bytes)
        upstream_request = rewrite_host_header(request_bytes)
        try:
            upstream = socket.create_connection((CHROME_HOST, CHROME_PORT), timeout=10)
        except OSError as exc:
            log(f"connect chrome failed: {exc}")
            self.request.sendall(
                b"HTTP/1.1 502 Bad Gateway\r\nContent-Type: text/plain\r\nContent-Length: 11\r\n\r\nBad Gateway"
            )
            return

        with upstream:
            upstream.sendall(upstream_request)
            if is_websocket_upgrade(request_bytes):
                response = recv_until(upstream, b"\r\n\r\n")
                self.request.sendall(response)
                tunnel(self.request, upstream)
                return

            response = read_http_response(upstream)
            self.request.sendall(rewrite_http_response(response, path))


class ThreadingTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    with ThreadingTCPServer((LISTEN_HOST, LISTEN_PORT), CDPProxyHandler) as server:
        log(f"CDP proxy listening on {LISTEN_HOST}:{LISTEN_PORT}")
        server.serve_forever()
