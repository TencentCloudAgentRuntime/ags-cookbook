#!/usr/bin/env python3
"""User-side WebSocket tunnel client for AGS local-service-tunnel.

The client connects to the sandbox-side Go tunnel server over WebSocket,
receives HTTP request frames from sandbox workloads, enforces local allowlists,
forwards allowed requests to a configured upstream, injects local credentials,
and streams response frames back to the sandbox.
"""

from __future__ import annotations

import argparse
import base64
import ipaddress
import json
import os
import socket
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional, Tuple

try:
    import websocket
except ImportError as exc:  # pragma: no cover - exercised by user environment.
    raise SystemExit("missing dependency: pip install websocket-client") from exc


DROP_REQUEST_HEADERS = {
    "authorization",
    "cookie",
    "host",
    "proxy-authorization",
    "x-api-key",
    "anthropic-auth-token",
}
DROP_RESPONSE_HEADERS = {
    "connection",
    "content-encoding",
    "content-length",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}
SAFE_REQUEST_HEADER_NAMES = {"content-type", "user-agent", "accept"}
SAFE_REQUEST_HEADER_PREFIXES = ("anthropic-",)
DEFAULT_ALLOWED_UPSTREAM_HOSTS = "api.deepseek.com,api.anthropic.com"
DEFAULT_ALLOWED_UPSTREAM_PORTS = "443"
DEFAULT_ALLOWED_UPSTREAM_PATHS = "/v1/messages,/v1/messages/count_tokens,/v1/models"
DEFAULT_REMOTE_TUNNEL_PORT = 18081


def split_csv(value: str) -> set[str]:
    return {item.strip().lower() for item in value.split(",") if item.strip()}


def split_ports(value: str) -> set[int]:
    out: set[int] = set()
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        port = int(item)
        if port < 1 or port > 65535:
            raise ValueError(f"invalid port: {port}")
        out.add(port)
    return out


def split_cidrs(value: str) -> list[ipaddress._BaseNetwork]:
    out: list[ipaddress._BaseNetwork] = []
    for item in value.split(","):
        item = item.strip()
        if item:
            out.append(ipaddress.ip_network(item, strict=False))
    return out


def env_truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "y", "on"}


def csv_from_config(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return ",".join(str(item) for item in value)
    return str(value)


def bool_from_config(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def load_yaml_mapping(path: str, label: str) -> dict[str, Any]:
    if not path:
        return {}
    if not path.endswith((".yaml", ".yml")):
        raise ValueError(f"{label} file must be YAML with .yaml or .yml extension")
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError("YAML files require PyYAML: pip install PyYAML") from exc
    data = yaml.safe_load(raw)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"{label} file must contain a YAML mapping")
    return data


def load_policy_file(path: str) -> dict[str, Any]:
    data = load_yaml_mapping(path, "policy")
    if "sessions" in data:
        raise ValueError("sessions must be configured with --session-file, not in the policy file")
    return data


def load_session_file(path: str) -> dict[str, Any]:
    return load_yaml_mapping(path, "session")


def clean_request_headers(headers: Dict[str, str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for key, value in headers.items():
        lower = key.lower()
        if lower in DROP_REQUEST_HEADERS:
            continue
        if lower not in SAFE_REQUEST_HEADER_NAMES and not lower.startswith(SAFE_REQUEST_HEADER_PREFIXES):
            continue
        out[key] = value
    return out


def clean_response_headers(headers) -> Dict[str, str]:  # type: ignore[no-untyped-def]
    out: Dict[str, str] = {}
    for key, value in headers.items():
        if key.lower() in DROP_RESPONSE_HEADERS:
            continue
        out[key] = value
    return out


def auth_headers(api_key: str, mode: str) -> Dict[str, str]:
    if mode == "authorization-bearer":
        return {"Authorization": f"Bearer {api_key}"}
    if mode == "x-api-key":
        return {"x-api-key": api_key}
    if mode == "both":
        return {"Authorization": f"Bearer {api_key}", "x-api-key": api_key}
    raise ValueError(f"unsupported auth mode: {mode}")


def default_upstream_base() -> str:
    return (
        os.getenv("DEEPSEEK_ANTHROPIC_BASE_URL")
        or os.getenv("ANTHROPIC_BASE_URL")
        or "https://api.deepseek.com/anthropic"
    )


def default_gateway_domain() -> str:
    explicit = os.getenv("AGS_GATEWAY_DOMAIN")
    if explicit:
        return explicit
    region = os.getenv("AGR_REGION") or os.getenv("AGS_REGION") or os.getenv("TENCENTCLOUD_REGION") or "ap-guangzhou"
    domain = os.getenv("AGR_DOMAIN") or os.getenv("AGS_DOMAIN") or "tencentags.com"
    return f"{region}.{domain}"


def build_control_url(instance_id: str, remote_port: int, gateway_domain: str, scheme: str) -> str:
    if not instance_id:
        raise ValueError("--instance-id is required when --control-url is not set")
    if remote_port <= 0 or remote_port > 65535:
        raise ValueError("--remote-port must be between 1 and 65535")
    if scheme not in {"ws", "wss"}:
        raise ValueError("--control-scheme must be ws or wss")
    return f"{scheme}://{remote_port}-{instance_id}.{gateway_domain}/ws"


def acquire_instance_access_token(instance_id: str) -> str:
    if not instance_id:
        raise ValueError("instance_id is required to acquire sandbox access token")
    try:
        from tencentcloud.ags.v20250920 import ags_client, models
        from tencentcloud.common import credential
        from tencentcloud.common.profile.client_profile import ClientProfile
        from tencentcloud.common.profile.http_profile import HttpProfile
    except ImportError as exc:
        raise RuntimeError("TencentCloud SDK is required to acquire sandbox access tokens") from exc

    sid = os.getenv("TENCENTCLOUD_SECRET_ID")
    skey = os.getenv("TENCENTCLOUD_SECRET_KEY")
    if not sid or not skey:
        raise ValueError("TENCENTCLOUD_SECRET_ID and TENCENTCLOUD_SECRET_KEY are required to acquire sandbox access tokens")
    region = os.getenv("TENCENTCLOUD_REGION") or os.getenv("AGS_REGION") or "ap-guangzhou"
    http_profile = HttpProfile()
    http_profile.endpoint = os.getenv("AGS_CLOUD_ENDPOINT", "ags.tencentcloudapi.com")
    profile = ClientProfile()
    profile.httpProfile = http_profile
    client = ags_client.AgsClient(credential.Credential(sid, skey), region, profile)
    req = models.AcquireSandboxInstanceTokenRequest()
    req.InstanceId = instance_id
    return client.AcquireSandboxInstanceToken(req).Token


def resolve_api_key(api_key_env: str) -> Tuple[str, str]:
    candidates = [api_key_env] if api_key_env else []
    candidates.extend(["DEEPSEEK_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY"])
    seen = set()
    for name in candidates:
        if not name or name in seen:
            continue
        seen.add(name)
        value = os.getenv(name)
        if value:
            return name, value
    raise KeyError(", ".join(candidates))


def join_url(base: str, path: str) -> str:
    base_parts = urllib.parse.urlparse(base)
    if not base_parts.scheme or not base_parts.netloc:
        raise ValueError("upstream_base must be an absolute URL")
    request_parts = urllib.parse.urlparse(path)
    base_path = base_parts.path.rstrip("/")
    request_path = request_parts.path
    if request_path == "/":
        out_path = base_path or "/"
    else:
        out_path = (base_path + "/" + request_path.lstrip("/")) if base_path else request_path
    return urllib.parse.urlunparse(
        (
            base_parts.scheme,
            base_parts.netloc,
            out_path,
            "",
            request_parts.query,
            "",
        )
    )


def resolve_host_ips(host: str, port: int) -> list[ipaddress._BaseAddress]:
    try:
        return [ipaddress.ip_address(host)]
    except ValueError:
        pass
    ips: list[ipaddress._BaseAddress] = []
    for family, _, _, _, sockaddr in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM):
        if family in {socket.AF_INET, socket.AF_INET6}:
            ips.append(ipaddress.ip_address(sockaddr[0]))
    return ips


@dataclass
class TunnelPolicy:
    allowed_hosts: set[str]
    allowed_ports: set[int]
    allowed_paths: set[str]
    allowed_path_prefixes: tuple[str, ...]
    allowed_methods: set[str]
    allowed_ip_cidrs: list[ipaddress._BaseNetwork]
    allow_insecure_upstream: bool

    def validate_upstream_base(self, base: str) -> None:
        parsed = urllib.parse.urlparse(base)
        if not parsed.scheme or not parsed.netloc or not parsed.hostname:
            raise ValueError("upstream_base must be an absolute URL")
        if parsed.scheme != "https" and not self.allow_insecure_upstream:
            raise ValueError("upstream_base must use https")
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        self.validate_host_port(parsed.hostname, port)

    def validate_host_port(self, host: str, port: int) -> None:
        host_l = host.lower()
        if self.allowed_hosts and host_l not in self.allowed_hosts:
            raise ValueError(f"upstream host is not allowed: {host}")
        ips = resolve_host_ips(host_l, port)
        if self.allowed_ip_cidrs:
            if not ips:
                raise ValueError(f"upstream host did not resolve to an IP: {host}")
            for ip in ips:
                if not any(ip in cidr for cidr in self.allowed_ip_cidrs):
                    raise ValueError(f"upstream IP is not allowed: {ip}")
        if not self.allowed_hosts and not self.allowed_ip_cidrs:
            raise ValueError("at least one upstream host or IP/CIDR allowlist is required")
        if port not in self.allowed_ports:
            raise ValueError(f"upstream port is not allowed: {port}")

    def validate_request(self, job: dict) -> None:
        method = str(job.get("method") or "").upper()
        path = urllib.parse.urlparse(str(job.get("path") or "")).path
        if method not in self.allowed_methods:
            raise ValueError(f"method is not allowed: {method}")
        if path in self.allowed_paths:
            return
        if any(path.startswith(prefix) for prefix in self.allowed_path_prefixes):
            return
        raise ValueError(f"path is not allowed: {path}")


@dataclass
class TunnelSessionConfig:
    name: str
    control_url: str
    token: str
    instance_access_token: str


class LocalTunnelClient:
    def __init__(
        self,
        name: str,
        control_url: str,
        upstream_base: str,
        api_key: str,
        policy: TunnelPolicy,
        token: str = "",
        instance_access_token: str = "",
        auth_mode: str = "authorization-bearer",
        upstream_timeout: float = 120.0,
        chunk_size: int = 64 * 1024,
    ) -> None:
        self.name = name
        self.control_url = control_url
        self.upstream_base = upstream_base
        self.api_key = api_key
        self.policy = policy
        self.token = token
        self.instance_access_token = instance_access_token
        self.auth_mode = auth_mode
        self.upstream_timeout = upstream_timeout
        self.chunk_size = chunk_size
        self._send_lock = threading.Lock()
        self.policy.validate_upstream_base(upstream_base)

    def _headers(self) -> list[str]:
        headers: list[str] = []
        if self.token:
            headers.append(f"Authorization: Bearer {self.token}")
        if self.instance_access_token:
            headers.append(f"X-Access-Token: {self.instance_access_token}")
        return headers

    def _send(self, ws: websocket.WebSocketApp, payload: dict) -> None:
        data = json.dumps(payload, separators=(",", ":"))
        with self._send_lock:
            ws.send(data)

    def _send_error(self, ws: websocket.WebSocketApp, request_id: str, message: str) -> None:
        self._send(ws, {"type": "error", "id": request_id, "error": message})

    def _forward_request(self, ws: websocket.WebSocketApp, job: dict) -> None:
        request_id = str(job.get("id") or "")
        if not request_id:
            return
        try:
            self.policy.validate_request(job)
            method = str(job["method"]).upper()
            target = join_url(self.upstream_base, str(job["path"]))
            body = base64.b64decode(job.get("body_b64") or "")
            headers = clean_request_headers(dict(job.get("headers") or {}))
            headers.update(auth_headers(self.api_key, self.auth_mode))
            req = urllib.request.Request(
                target,
                data=body if method not in {"GET", "HEAD"} else None,
                headers=headers,
                method=method,
            )
            context = ssl.create_default_context()
            try:
                resp_cm = urllib.request.urlopen(req, timeout=self.upstream_timeout, context=context)
            except urllib.error.HTTPError as exc:
                resp_cm = exc
            with resp_cm as resp:  # type: ignore[attr-defined]
                self._send(
                    ws,
                    {
                        "type": "response_start",
                        "id": request_id,
                        "status": resp.status if hasattr(resp, "status") else resp.code,
                        "headers": clean_response_headers(resp.headers),
                    },
                )
                while True:
                    chunk = resp.read(self.chunk_size)
                    if not chunk:
                        break
                    self._send(
                        ws,
                        {
                            "type": "response_body",
                            "id": request_id,
                            "body_b64": base64.b64encode(chunk).decode("ascii"),
                        },
                    )
                self._send(ws, {"type": "response_end", "id": request_id})
        except Exception as exc:  # noqa: BLE001 - report a bounded error to sandbox.
            print(f"request forwarding failed request_id={request_id}: {type(exc).__name__}: {exc}", file=sys.stderr)
            self._send_error(ws, request_id, "local tunnel upstream error")

    def run_forever(self, reconnect_sleep: float = 2.0) -> None:
        while True:
            connected = threading.Event()

            def on_open(_ws: websocket.WebSocketApp) -> None:
                connected.set()
                print(
                    f"local tunnel websocket connected session={self.name} "
                    f"control={self.control_url} upstream={self.upstream_base}",
                    flush=True,
                )

            def on_message(ws: websocket.WebSocketApp, raw: str) -> None:
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    print("invalid websocket payload from sandbox", file=sys.stderr)
                    return
                if payload.get("type") != "request":
                    return
                threading.Thread(target=self._forward_request, args=(ws, payload), daemon=True).start()

            def on_error(_ws: websocket.WebSocketApp, error: object) -> None:
                print(f"local tunnel websocket error session={self.name}: {error}", file=sys.stderr)

            def on_close(_ws: websocket.WebSocketApp, status: Optional[int], message: Optional[str]) -> None:
                print(
                    f"local tunnel websocket closed session={self.name} status={status} message={message}",
                    file=sys.stderr,
                )

            ws = websocket.WebSocketApp(
                self.control_url,
                header=self._headers(),
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
            )
            ws.run_forever(ping_interval=20, ping_timeout=10, http_proxy_host=None)
            time.sleep(reconnect_sleep)


class TunnelDaemon:
    def __init__(self, clients: list[LocalTunnelClient]) -> None:
        if not clients:
            raise ValueError("at least one tunnel session is required")
        self.clients = clients

    def run_forever(self) -> None:
        if len(self.clients) == 1:
            self.clients[0].run_forever()
            return
        for client in self.clients:
            thread = threading.Thread(target=client.run_forever, name=f"tunnel-{client.name}", daemon=True)
            thread.start()
        print(f"local tunnel daemon started sessions={len(self.clients)}", flush=True)
        while True:
            time.sleep(3600)


def policy_value(config: dict[str, Any], key: str, fallback: Any) -> Any:
    return config[key] if key in config else fallback


def make_policy(args: argparse.Namespace, config: dict[str, Any]) -> TunnelPolicy:
    allowed_hosts = csv_from_config(policy_value(config, "allowed_upstream_hosts", args.allowed_upstream_hosts))
    allowed_ports = csv_from_config(policy_value(config, "allowed_upstream_ports", args.allowed_upstream_ports))
    allowed_paths = csv_from_config(policy_value(config, "allowed_paths", args.allowed_paths))
    allowed_path_prefixes = csv_from_config(policy_value(config, "allowed_path_prefixes", args.allowed_path_prefixes))
    allowed_methods = csv_from_config(policy_value(config, "allowed_methods", args.allowed_methods))
    allowed_ip_cidrs = csv_from_config(policy_value(config, "allowed_ip_cidrs", args.allowed_ip_cidrs))
    return TunnelPolicy(
        allowed_hosts=split_csv(allowed_hosts),
        allowed_ports=split_ports(allowed_ports),
        allowed_paths=split_csv(allowed_paths),
        allowed_path_prefixes=tuple(item.strip() for item in allowed_path_prefixes.split(",") if item.strip()),
        allowed_methods={item.upper() for item in split_csv(allowed_methods)},
        allowed_ip_cidrs=split_cidrs(allowed_ip_cidrs),
        allow_insecure_upstream=bool_from_config(policy_value(config, "allow_insecure_upstream", args.allow_insecure_upstream)),
    )


SESSION_KEYS = {
    "name",
    "control_url",
    "instance_id",
    "remote_port",
    "gateway_domain",
    "control_scheme",
    "token_env",
    "instance_access_token_env",
    "access_token_env",
}
POLICY_KEYS = {
    "upstream_base",
    "allow_insecure_upstream",
    "allowed_upstream_hosts",
    "allowed_upstream_ports",
    "allowed_ip_cidrs",
    "allowed_paths",
    "allowed_path_prefixes",
    "allowed_methods",
}


def config_string(config: dict[str, Any], key: str, default: str = "") -> str:
    value = config.get(key, default)
    if value is None:
        return ""
    return str(value)


def config_int(config: dict[str, Any], key: str, default: int) -> int:
    value = config.get(key, default)
    return int(value)


def secret_from_config(config: dict[str, Any], direct_keys: tuple[str, ...], env_keys: tuple[str, ...], default: str) -> str:
    for key in direct_keys:
        value = config.get(key)
        if value:
            return str(value)
    for key in env_keys:
        env_name = config.get(key)
        if env_name:
            value = os.getenv(str(env_name))
            if value:
                return value
            raise ValueError(f"environment variable is not set: {env_name}")
    return default


def session_from_config(args: argparse.Namespace, item: dict[str, Any], index: int) -> TunnelSessionConfig:
    disallowed = (set(item) - SESSION_KEYS) | (set(item) & POLICY_KEYS)
    if disallowed:
        raise ValueError(
            "sessions may only contain connection fields; configure allowlist policy at top level: "
            + ", ".join(sorted(disallowed))
        )
    name = config_string(item, "name", f"session-{index + 1}")
    remote_port = config_int(item, "remote_port", args.remote_port)
    gateway_domain = config_string(item, "gateway_domain", args.gateway_domain)
    control_scheme = config_string(item, "control_scheme", args.control_scheme)
    instance_id = config_string(item, "instance_id", args.instance_id)
    control_url = config_string(item, "control_url", args.control_url)
    if not control_url:
        control_url = build_control_url(
            instance_id=instance_id,
            remote_port=remote_port,
            gateway_domain=gateway_domain,
            scheme=control_scheme,
        )
    token = secret_from_config(item, (), ("token_env",), args.token)
    instance_access_token = secret_from_config(
        item,
        (),
        ("instance_access_token_env", "access_token_env"),
        args.instance_access_token,
    )
    if not instance_access_token:
        instance_access_token = acquire_instance_access_token(instance_id)
    return TunnelSessionConfig(
        name=name,
        control_url=control_url,
        token=token,
        instance_access_token=instance_access_token,
    )


def make_sessions(args: argparse.Namespace, config: dict[str, Any]) -> list[TunnelSessionConfig]:
    raw = config.get("sessions")
    if raw is None:
        return [session_from_config(args, {}, 0)]
    if not isinstance(raw, list):
        raise ValueError("sessions must be a list")
    sessions: list[TunnelSessionConfig] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError("each session must be a YAML mapping")
        sessions.append(session_from_config(args, item, index))
    return sessions


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    argv_list = list(argv) if argv is not None else sys.argv[1:]
    if argv_list and argv_list[0] == "serve":
        argv_list = argv_list[1:]
    parser = argparse.ArgumentParser(description="Run the local side of the AGS WebSocket HTTP tunnel.")
    parser.add_argument(
        "--policy-file",
        default=os.getenv("AGS_TUNNEL_POLICY_FILE", ""),
        help="YAML policy file containing upstream and allowlist settings.",
    )
    parser.add_argument(
        "--session-file",
        default=os.getenv("AGS_TUNNEL_SESSION_FILE", ""),
        help="Optional YAML file containing sandbox tunnel sessions. If omitted, a single session is built from CLI args.",
    )
    parser.add_argument(
        "--control-url",
        default=os.getenv("AGS_TUNNEL_CONTROL_URL", ""),
        help="Direct WebSocket URL for the sandbox tunnel server. If omitted, it is built from instance id and remote port.",
    )
    parser.add_argument("--instance-id", default=os.getenv("INSTANCE_ID", ""))
    parser.add_argument(
        "--remote-port",
        type=int,
        default=int(os.getenv("REMOTE_TUNNEL_PORT", str(DEFAULT_REMOTE_TUNNEL_PORT))),
    )
    parser.add_argument("--gateway-domain", default=default_gateway_domain())
    parser.add_argument(
        "--control-scheme",
        choices=["ws", "wss"],
        default=os.getenv("AGS_TUNNEL_CONTROL_SCHEME", "wss"),
    )
    parser.add_argument("--upstream-base", default=default_upstream_base())
    parser.add_argument(
        "--allowed-upstream-hosts",
        default=os.getenv("AGS_TUNNEL_ALLOWED_UPSTREAM_HOSTS", DEFAULT_ALLOWED_UPSTREAM_HOSTS),
        help="Comma-separated allowlist for upstream domain names.",
    )
    parser.add_argument(
        "--allowed-upstream-ports",
        default=os.getenv("AGS_TUNNEL_ALLOWED_UPSTREAM_PORTS", DEFAULT_ALLOWED_UPSTREAM_PORTS),
        help="Comma-separated allowlist for upstream ports.",
    )
    parser.add_argument(
        "--allowed-ip-cidrs",
        default=os.getenv("AGS_TUNNEL_ALLOWED_IP_CIDRS", ""),
        help="Comma-separated allowlist for resolved upstream IP CIDRs.",
    )
    parser.add_argument(
        "--allowed-paths",
        default=os.getenv("AGS_TUNNEL_ALLOWED_PATHS", DEFAULT_ALLOWED_UPSTREAM_PATHS),
        help="Comma-separated exact request paths allowed from the sandbox.",
    )
    parser.add_argument(
        "--allowed-path-prefixes",
        default=os.getenv("AGS_TUNNEL_ALLOWED_PATH_PREFIXES", ""),
        help="Comma-separated path prefixes allowed from the sandbox.",
    )
    parser.add_argument(
        "--allowed-methods",
        default=os.getenv("AGS_TUNNEL_ALLOWED_METHODS", "POST,GET"),
        help="Comma-separated HTTP methods allowed from the sandbox.",
    )
    parser.add_argument(
        "--allow-insecure-upstream",
        action="store_true",
        default=env_truthy("AGS_TUNNEL_ALLOW_INSECURE_UPSTREAM"),
        help="Allow non-HTTPS upstreams. Intended only for local tests.",
    )
    parser.add_argument(
        "--api-key-env",
        default="",
        help="Env var containing the upstream API key. Defaults to DEEPSEEK_API_KEY, ANTHROPIC_AUTH_TOKEN, then ANTHROPIC_API_KEY.",
    )
    parser.add_argument(
        "--auth-mode",
        choices=["authorization-bearer", "x-api-key", "both"],
        default=os.getenv("AGS_TUNNEL_AUTH_MODE", "authorization-bearer"),
    )
    parser.add_argument("--token", default=os.getenv("AGS_TUNNEL_TOKEN", ""))
    parser.add_argument(
        "--instance-access-token",
        default=os.getenv("AGS_INSTANCE_ACCESS_TOKEN", ""),
        help="Optional sandbox instance access token when connecting directly to sandbox exposed-port URLs.",
    )
    parser.add_argument("--upstream-timeout", type=float, default=120.0)
    parser.add_argument("--chunk-size", type=int, default=64 * 1024)
    return parser.parse_args(argv_list)


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = parse_args(argv)
    try:
        policy_config = load_policy_file(args.policy_file)
        session_config = load_session_file(args.session_file)
        api_key_name, api_key = resolve_api_key(args.api_key_env)
        upstream_base = str(policy_value(policy_config, "upstream_base", args.upstream_base))
        policy = make_policy(args, policy_config)
        sessions = make_sessions(args, session_config)
        clients = [
            LocalTunnelClient(
                name=session.name,
                control_url=session.control_url,
                upstream_base=upstream_base,
                api_key=api_key,
                policy=policy,
                token=session.token,
                instance_access_token=session.instance_access_token,
                auth_mode=args.auth_mode,
                upstream_timeout=args.upstream_timeout,
                chunk_size=args.chunk_size,
            )
            for session in sessions
        ]
        daemon = TunnelDaemon(clients)
    except Exception as exc:  # noqa: BLE001 - config error.
        print(f"invalid tunnel client configuration: {exc}", file=sys.stderr)
        return 2
    print(f"using upstream api key from {api_key_name}", flush=True)
    daemon.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
