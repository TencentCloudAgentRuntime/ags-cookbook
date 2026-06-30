#!/usr/bin/env python3
"""Embeddable HTTP proxy for an exposed AGS sandbox tunnel port.

It accepts local HTTP requests, forwards them to the AGS data-plane URL, and
injects the sandbox instance access token required by the gateway.
"""

from __future__ import annotations

import argparse
import contextlib
import http.server
import os
import select
import socket
import ssl
import sys
import urllib.error
import urllib.request
from typing import Dict


HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


def default_gateway_domain() -> str:
    explicit = os.getenv("AGS_GATEWAY_DOMAIN")
    if explicit:
        return explicit
    region = os.getenv("AGR_REGION") or os.getenv("AGS_REGION") or "ap-guangzhou"
    domain = os.getenv("AGR_DOMAIN") or os.getenv("AGS_DOMAIN") or "tencentags.com"
    return f"{region}.{domain}"


def clean_headers(headers) -> Dict[str, str]:  # type: ignore[no-untyped-def]
    out: Dict[str, str] = {}
    for key, value in headers.items():
        lower = key.lower()
        if lower in HOP_BY_HOP_HEADERS:
            continue
        if lower == "host":
            continue
        out[key] = value
    return out


def is_websocket_upgrade(headers) -> bool:  # type: ignore[no-untyped-def]
    return (
        headers.get("Upgrade", "").lower() == "websocket"
        and "upgrade" in headers.get("Connection", "").lower()
    )


def split_target_host(target_host: str, scheme: str) -> tuple[str, int]:
    default_port = 443 if scheme == "https" else 80
    if target_host.startswith("["):
        end = target_host.find("]")
        if end != -1 and len(target_host) > end + 2 and target_host[end + 1] == ":":
            return target_host[1:end], int(target_host[end + 2 :])
        return target_host.strip("[]"), default_port
    host, sep, port_text = target_host.rpartition(":")
    if sep and port_text.isdigit():
        return host, int(port_text)
    return target_host, default_port


class ProxyHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "AGSTunnelProxy/0.1"

    def do_GET(self) -> None:  # noqa: N802
        self.proxy()

    def do_POST(self) -> None:  # noqa: N802
        self.proxy()

    def do_PUT(self) -> None:  # noqa: N802
        self.proxy()

    def do_PATCH(self) -> None:  # noqa: N802
        self.proxy()

    def do_DELETE(self) -> None:  # noqa: N802
        self.proxy()

    def do_HEAD(self) -> None:  # noqa: N802
        self.proxy()

    def proxy(self) -> None:
        if is_websocket_upgrade(self.headers):
            self.proxy_websocket()
            return

        target_host = self.server.target_host  # type: ignore[attr-defined]
        access_token = self.server.access_token  # type: ignore[attr-defined]
        target_scheme = self.server.target_scheme  # type: ignore[attr-defined]
        timeout = self.server.upstream_timeout  # type: ignore[attr-defined]
        context = self.server.tls_context  # type: ignore[attr-defined]

        body = None
        length = int(self.headers.get("Content-Length") or "0")
        if length > 0:
            body = self.rfile.read(length)

        target_url = f"{target_scheme}://{target_host}{self.path}"
        headers = clean_headers(self.headers)
        headers["Host"] = target_host
        headers["X-Access-Token"] = access_token
        request = urllib.request.Request(target_url, data=body, headers=headers, method=self.command)

        try:
            with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
                self.relay_response(response.status, response.headers, response.read())
        except urllib.error.HTTPError as exc:
            self.relay_response(exc.code, exc.headers, exc.read())
        except Exception as exc:  # noqa: BLE001
            message = b"Bad Gateway"
            self.log_error("proxy error: %s", exc)
            self.send_response(502)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(message)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(message)

    def proxy_websocket(self) -> None:
        target_host = self.server.target_host  # type: ignore[attr-defined]
        access_token = self.server.access_token  # type: ignore[attr-defined]
        target_scheme = self.server.target_scheme  # type: ignore[attr-defined]
        timeout = self.server.upstream_timeout  # type: ignore[attr-defined]
        context = self.server.tls_context  # type: ignore[attr-defined]

        connect_host, target_port = split_target_host(target_host, target_scheme)
        raw_sock = None
        upstream = None
        try:
            raw_sock = socket.create_connection((connect_host, target_port), timeout=timeout)
            upstream = context.wrap_socket(raw_sock, server_hostname=connect_host) if target_scheme == "https" else raw_sock
            headers = clean_headers(self.headers)
            headers["Host"] = target_host
            headers["Upgrade"] = "websocket"
            headers["Connection"] = "Upgrade"
            headers["X-Access-Token"] = access_token
            request_lines = [f"{self.command} {self.path} HTTP/1.1"]
            request_lines.extend(f"{key}: {value}" for key, value in headers.items())
            request_lines.append("")
            request_lines.append("")
            upstream.sendall("\r\n".join(request_lines).encode("iso-8859-1"))

            response = bytearray()
            while b"\r\n\r\n" not in response:
                chunk = upstream.recv(4096)
                if not chunk:
                    break
                response.extend(chunk)
                if len(response) > 64 * 1024:
                    raise RuntimeError("websocket response headers too large")
            if not response:
                raise RuntimeError("empty websocket response from upstream")
            self.connection.sendall(response)
            self.close_connection = True
            sockets = [self.connection, upstream]
            while True:
                readable, _, _ = select.select(sockets, [], [], timeout)
                if not readable:
                    continue
                for sock in readable:
                    data = sock.recv(64 * 1024)
                    if not data:
                        return
                    peer = upstream if sock is self.connection else self.connection
                    peer.sendall(data)
        except Exception as exc:  # noqa: BLE001
            self.log_error("websocket proxy error: %s", exc)
            if not self.close_connection:
                message = b"Bad Gateway"
                self.send_response(502)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(message)))
                self.end_headers()
                self.wfile.write(message)
        finally:
            if upstream is not None:
                with contextlib.suppress(Exception):
                    upstream.close()
            elif raw_sock is not None:
                with contextlib.suppress(Exception):
                    raw_sock.close()

    def relay_response(self, status: int, headers, body: bytes) -> None:  # type: ignore[no-untyped-def]
        self.send_response(status)
        sent_length = False
        for key, value in headers.items():
            lower = key.lower()
            if lower in HOP_BY_HOP_HEADERS:
                continue
            if lower == "content-length":
                sent_length = True
            self.send_header(key, value)
        if not sent_length:
            self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)


class ThreadingHTTPServer(http.server.ThreadingHTTPServer):
    daemon_threads = True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Forward a local HTTP port to an exposed AGS sandbox port.")
    parser.add_argument("--listen-host", default=os.getenv("AGS_TUNNEL_PROXY_LISTEN_HOST", "127.0.0.1"))
    parser.add_argument("--listen-port", type=int, default=int(os.getenv("AGS_TUNNEL_PROXY_LISTEN_PORT", "18081")))
    parser.add_argument("--instance-id", default=os.getenv("INSTANCE_ID", ""))
    parser.add_argument("--remote-port", type=int, default=int(os.getenv("REMOTE_TUNNEL_PORT", "18081")))
    parser.add_argument("--gateway-domain", default=default_gateway_domain())
    parser.add_argument("--target-host-override", default=os.getenv("AGS_TUNNEL_PROXY_TARGET_HOST", ""))
    parser.add_argument("--access-token", default=os.getenv("AGS_INSTANCE_ACCESS_TOKEN", ""))
    parser.add_argument("--target-scheme", choices=["https", "http"], default=os.getenv("AGS_TUNNEL_PROXY_SCHEME", "https"))
    parser.add_argument("--insecure-skip-verify", action="store_true")
    parser.add_argument("--upstream-timeout", type=float, default=120.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.instance_id:
        print("--instance-id or INSTANCE_ID is required", file=sys.stderr)
        return 2
    if not args.access_token:
        print("--access-token or AGS_INSTANCE_ACCESS_TOKEN is required", file=sys.stderr)
        return 2
    if args.remote_port <= 0 or args.remote_port > 65535:
        print("--remote-port must be between 1 and 65535", file=sys.stderr)
        return 2
    if args.listen_port <= 0 or args.listen_port > 65535:
        print("--listen-port must be between 1 and 65535", file=sys.stderr)
        return 2
    if args.listen_host not in {"127.0.0.1", "localhost", "::1"}:
        print(
            f"warning: binding to {args.listen_host} exposes the proxy and access token to the network",
            file=sys.stderr,
        )

    tls_context = None
    if args.target_scheme == "https":
        tls_context = ssl.create_default_context()
        if args.insecure_skip_verify:
            tls_context.check_hostname = False
            tls_context.verify_mode = ssl.CERT_NONE

    server = ThreadingHTTPServer((args.listen_host, args.listen_port), ProxyHandler)
    server.target_host = args.target_host_override or f"{args.remote_port}-{args.instance_id}.{args.gateway_domain}"  # type: ignore[attr-defined]
    server.access_token = args.access_token  # type: ignore[attr-defined]
    server.target_scheme = args.target_scheme  # type: ignore[attr-defined]
    server.upstream_timeout = args.upstream_timeout  # type: ignore[attr-defined]
    server.tls_context = tls_context  # type: ignore[attr-defined]

    print(
        f"Forwarding from {args.listen_host}:{args.listen_port} "
        f"-> {args.target_scheme}://{server.target_host}",
        flush=True,
    )
    with contextlib.suppress(KeyboardInterrupt):
        server.serve_forever()
    server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
