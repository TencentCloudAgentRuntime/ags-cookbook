"""Provider-neutral CDP proxy for AGS OSWorld sandboxes.

The proxy deliberately uses only the Python standard library so it can run in
the sandbox without installing packages. It rewrites Chrome's loopback-only
Host header and publishes the external AGS authority in ``/json/*`` responses.
"""

import ipaddress
import json
import re
import select
import socket
import socketserver
import sys

from contextlib import suppress
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


CHROME_HOST = "127.0.0.1"
CHROME_PORT = 1337
LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 9222
BUFFER_SIZE = 65536


def log(message):
    print(message, file=sys.stderr, flush=True)


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


def request_header_value(request_bytes, name):
    request_text = request_bytes.decode("latin1", errors="replace")
    match = re.search(rf"(?im)^{re.escape(name)}:\s*([^\r\n]+)", request_text)
    return match.group(1).strip() if match else ""


def first_header_value(value):
    return value.split(",", 1)[0].strip()


def external_authority(request_bytes):
    forwarded_host = first_header_value(request_header_value(request_bytes, "X-Forwarded-Host"))
    if forwarded_host:
        return forwarded_host
    return request_header_value(request_bytes, "Host") or f"127.0.0.1:{LISTEN_PORT}"


def external_ws_scheme(request_bytes, authority):
    proto = first_header_value(request_header_value(request_bytes, "X-Forwarded-Proto")).lower()
    if proto == "https" or request_header_value(request_bytes, "X-Forwarded-Ssl").lower() == "on":
        return "wss"

    hostname = authority.rsplit("@", 1)[-1].rsplit(":", 1)[0].strip("[]").lower()
    if hostname and hostname not in {"localhost", "127.0.0.1", "::1"}:
        try:
            ipaddress.ip_address(hostname)
        except ValueError:
            return "wss"
    return "ws"


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
    return header_bytes + b"\r\n\r\n" + body


def rewrite_devtools_query(query, authority, ws_scheme):
    rewritten = []
    for key, value in parse_qsl(query, keep_blank_values=True):
        if key in {"ws", "wss"} and value:
            target = urlparse(value if "://" in value else f"//{value}")
            value = authority + target.path
            if target.query:
                value += f"?{target.query}"
            if target.fragment:
                value += f"#{target.fragment}"
            key = "wss" if ws_scheme == "wss" else "ws"
        rewritten.append((key, value))
    return urlencode(rewritten, doseq=True, safe="/:[]")


def is_loopback_hostname(hostname):
    if not hostname:
        return False
    if hostname.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def rewrite_cdp_url(value, authority, ws_scheme):
    if not isinstance(value, str):
        return value
    parsed = urlparse(value)
    query = rewrite_devtools_query(parsed.query, authority, ws_scheme)
    if parsed.scheme in {"ws", "wss"}:
        return urlunparse((ws_scheme, authority, parsed.path, "", query, parsed.fragment))
    if parsed.scheme in {"http", "https"}:
        if not is_loopback_hostname(parsed.hostname):
            return urlunparse(
                (parsed.scheme, parsed.netloc, parsed.path, parsed.params, query, parsed.fragment)
            )
        scheme = "https" if ws_scheme == "wss" else "http"
        return urlunparse((scheme, authority, parsed.path, "", query, parsed.fragment))
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, query, parsed.fragment))


def rewrite_cdp_payload(content, authority, ws_scheme):
    try:
        payload = json.loads(content.decode("utf-8"))
    except Exception:
        content_text = content.decode("utf-8", errors="replace")
        content_text = re.sub(r'wss?://[^/\s"]+', f"{ws_scheme}://{authority}", content_text)
        content_text = content_text.replace(f"localhost:{CHROME_PORT}", authority)
        query_key = "wss" if ws_scheme == "wss" else "ws"
        content_text = re.sub(r"([?&])wss?=", rf"\1{query_key}=", content_text)
        return content_text.encode("utf-8")

    def rewrite_item(item):
        if not isinstance(item, dict):
            return item
        rewritten = dict(item)
        for key in ("webSocketDebuggerUrl", "devtoolsFrontendUrl"):
            if key in rewritten:
                rewritten[key] = rewrite_cdp_url(rewritten[key], authority, ws_scheme)
        return rewritten

    if isinstance(payload, list):
        payload = [rewrite_item(item) for item in payload]
    elif isinstance(payload, dict):
        payload = rewrite_item(payload)
    return json.dumps(payload).encode("utf-8")


def replace_header(header_text, name, value):
    pattern = re.compile(rf"(?im)^{re.escape(name)}:\s*[^\r\n]*")
    replacement = f"{name}: {value}"
    if pattern.search(header_text):
        return pattern.sub(replacement, header_text, count=1)
    return header_text + f"\r\n{name}: {value}"


def rewrite_http_response(response_bytes, path, authority, ws_scheme):
    if b"\r\n\r\n" not in response_bytes or not path.startswith("/json"):
        return response_bytes
    header_bytes, body = response_bytes.split(b"\r\n\r\n", 1)
    rewritten_body = rewrite_cdp_payload(body, authority, ws_scheme)
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
            for source in readable:
                destination = right if source is left else left
                data = source.recv(BUFFER_SIZE)
                if not data:
                    return
                destination.sendall(data)
    finally:
        for current_socket in sockets:
            with suppress(OSError):
                current_socket.shutdown(socket.SHUT_RDWR)
            with suppress(OSError):
                current_socket.close()


class CDPProxyHandler(socketserver.BaseRequestHandler):
    def handle(self):
        request_bytes = recv_until(self.request, b"\r\n\r\n")
        if not request_bytes:
            return

        path = parse_request_path(request_bytes)
        authority = external_authority(request_bytes)
        ws_scheme = external_ws_scheme(request_bytes, authority)
        try:
            upstream = socket.create_connection((CHROME_HOST, CHROME_PORT), timeout=10)
        except OSError as exc:
            log(f"connect chrome failed: {exc}")
            self.request.sendall(
                b"HTTP/1.1 502 Bad Gateway\r\nContent-Type: text/plain\r\nContent-Length: 11\r\n\r\nBad Gateway"
            )
            return

        with upstream:
            upstream.sendall(rewrite_host_header(request_bytes))
            if is_websocket_upgrade(request_bytes):
                response = recv_until(upstream, b"\r\n\r\n")
                self.request.sendall(response)
                tunnel(self.request, upstream)
                return
            response = read_http_response(upstream)
            self.request.sendall(rewrite_http_response(response, path, authority, ws_scheme))


class ThreadingTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    with ThreadingTCPServer((LISTEN_HOST, LISTEN_PORT), CDPProxyHandler) as server:
        log(f"CDP proxy listening on {LISTEN_HOST}:{LISTEN_PORT}")
        server.serve_forever()


if __name__ == "__main__":
    main()
