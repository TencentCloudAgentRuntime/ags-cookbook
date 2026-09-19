#!/usr/bin/env python3
from __future__ import annotations

import http.server
import json
import os
import secrets
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib import request

from tencentcloud.ags.v20250920 import ags_client, models
from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".state"

WORKLOAD_TUNNEL_PORT = int(os.getenv("WORKLOAD_TUNNEL_PORT", "18080"))
REMOTE_TUNNEL_PORT = int(os.getenv("REMOTE_TUNNEL_PORT", "18081"))
ENVD_PORT = int(os.getenv("ENVD_PORT", "49983"))
SANDBOX_TIMEOUT = os.getenv("INSTANCE_TIMEOUT", "30m")
NETWORK_MODE = os.getenv("NETWORK_MODE", "SANDBOX")
TOOL_START_COMMAND = (
    f"/envd -port {ENVD_PORT} >/tmp/envd.log 2>&1 & "
    "exec /mnt/tunnel/bin/ags-tunnel-server"
)


def need(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"{name} is required")
    return value


def tc_client() -> ags_client.AgsClient:
    cred = credential.Credential(need("TENCENTCLOUD_SECRET_ID"), need("TENCENTCLOUD_SECRET_KEY"))
    http_profile = HttpProfile()
    http_profile.endpoint = os.getenv("AGS_CLOUD_ENDPOINT", "ags.tencentcloudapi.com")
    profile = ClientProfile()
    profile.httpProfile = http_profile
    return ags_client.AgsClient(cred, os.getenv("TENCENTCLOUD_REGION", os.getenv("AGS_REGION", "ap-guangzhou")), profile)


def env_var(name: str, value: str) -> models.EnvVar:
    item = models.EnvVar()
    item.Name = name
    item.Value = value
    return item


def port(name: str, value: int) -> models.PortConfiguration:
    item = models.PortConfiguration()
    item.Name = name
    item.Port = value
    item.Protocol = "TCP"
    return item


def image_mount(name: str, mount_path: str, reference: str, registry_type: str, sub_path: str) -> models.StorageMount:
    image = models.ImageStorageSource()
    image.Reference = reference
    image.ImageRegistryType = registry_type
    image.SubPath = sub_path

    source = models.StorageSource()
    source.Image = image

    mount = models.StorageMount()
    mount.Name = name
    mount.MountPath = mount_path
    mount.ReadOnly = True
    mount.StorageSource = source
    return mount


def probe() -> models.ProbeConfiguration:
    http_get = models.HttpGetAction()
    http_get.Path = "/health"
    http_get.Port = ENVD_PORT
    http_get.Scheme = "HTTP"

    item = models.ProbeConfiguration()
    item.HttpGet = http_get
    item.ReadyTimeoutMs = 30000
    item.ProbeTimeoutMs = 2000
    item.ProbePeriodMs = 1000
    item.SuccessThreshold = 1
    item.FailureThreshold = 60
    return item


def write(path: Path, value: str) -> None:
    STATE.mkdir(exist_ok=True)
    path.write_text(value, encoding="utf-8")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def tunnel_token() -> str:
    existing = os.getenv("AGS_TUNNEL_TOKEN")
    if existing:
        write(STATE / "tunnel_token", existing)
        return existing
    token_file = STATE / "tunnel_token"
    if token_file.exists():
        return read(token_file)
    token = secrets.token_urlsafe(32)
    write(token_file, token)
    return token


def create_tool(client: ags_client.AgsClient, token: str) -> str:
    req = models.CreateSandboxToolRequest()
    req.ToolName = os.getenv("TOOL_NAME", f"local-tunnel-{time.strftime('%m%d%H%M%S')}")
    req.ToolType = "custom"
    req.Description = "Local service tunnel with envd and YAML allowlist policy"
    req.DefaultTimeout = SANDBOX_TIMEOUT
    req.RoleArn = need("ROLE_ARN")

    network = models.NetworkConfiguration()
    network.NetworkMode = NETWORK_MODE
    req.NetworkConfiguration = network

    custom = models.CustomConfiguration()
    custom.Image = need("MAIN_IMAGE_REF")
    custom.ImageRegistryType = os.getenv("MAIN_IMAGE_REGISTRY_TYPE", "personal")
    custom.Command = ["/bin/sh"]
    custom.Args = ["-lc", os.getenv("TOOL_START_COMMAND", TOOL_START_COMMAND)]
    custom.Env = [
        env_var("AGS_TUNNEL_TOKEN", token),
        env_var("LLM_BASE_URL", f"http://127.0.0.1:{WORKLOAD_TUNNEL_PORT}"),
        env_var("ANTHROPIC_API_KEY", "placeholder"),
        env_var("ANTHROPIC_AUTH_TOKEN", "placeholder"),
    ]
    custom.Ports = [port("tunnel-control", REMOTE_TUNNEL_PORT), port("envd", ENVD_PORT)]
    resources = models.ResourceConfiguration()
    resources.CPU = os.getenv("RUNTIME_CPU", "2")
    resources.Memory = os.getenv("RUNTIME_MEMORY", "4Gi")
    custom.Resources = resources
    custom.Probe = probe()
    req.CustomConfiguration = custom

    req.StorageMounts = [
        image_mount(
            "tunnel-bin",
            "/mnt/tunnel",
            need("TUNNEL_IMAGE_REF"),
            os.getenv("TUNNEL_IMAGE_REGISTRY_TYPE", "personal"),
            "/tunnel",
        ),
        image_mount(
            "demo-workload-bin",
            "/mnt/workload",
            need("WORKLOAD_IMAGE_REF"),
            os.getenv("WORKLOAD_IMAGE_REGISTRY_TYPE", "personal"),
            os.getenv("WORKLOAD_IMAGE_SUBPATH", "/workload"),
        ),
        image_mount(
            "envd",
            "/envd",
            os.getenv("ENVD_IMAGE_REF", "ccr.ccs.tencentyun.com/ags-image/envd:v0.5.14"),
            os.getenv("ENVD_IMAGE_REGISTRY_TYPE", "personal"),
            os.getenv("ENVD_IMAGE_SUBPATH", "/usr/bin/envd"),
        ),
    ]

    resp = client.CreateSandboxTool(req)
    tool_id = resp.ToolId
    write(STATE / "tool_id", tool_id)
    write(STATE / "tool_name", req.ToolName)
    write(STATE / "tool-create.json", resp.to_json_string())
    print(f"TOOL_ID={tool_id}")
    return tool_id


def get_tool_status(client: ags_client.AgsClient, tool_id: str) -> str:
    req = models.DescribeSandboxToolListRequest()
    req.ToolIds = [tool_id]
    resp = client.DescribeSandboxToolList(req)
    if not resp.SandboxToolSet:
        return ""
    return resp.SandboxToolSet[0].Status or ""


def wait_tool(client: ags_client.AgsClient, tool_id: str) -> None:
    deadline = time.time() + 900
    while time.time() < deadline:
        status = get_tool_status(client, tool_id)
        print(f"tool status: {status or 'unknown'}")
        if status in {"ACTIVE", "READY"}:
            return
        if status in {"FAILED", "DELETING", "DELETED", "ERROR"}:
            raise SystemExit(f"tool failed: {status}")
        time.sleep(10)
    raise SystemExit("tool did not become ACTIVE in time")


def start_instance(client: ags_client.AgsClient, tool_id: str) -> str:
    req = models.StartSandboxInstanceRequest()
    req.ToolId = tool_id
    req.Timeout = SANDBOX_TIMEOUT
    resp = client.StartSandboxInstance(req)
    instance_id = resp.Instance.InstanceId
    write(STATE / "instance_id", instance_id)
    write(STATE / "instance-create.json", resp.to_json_string())
    print(f"INSTANCE_ID={instance_id}")
    return instance_id


def get_instance_status(client: ags_client.AgsClient, instance_id: str) -> str:
    req = models.DescribeSandboxInstanceListRequest()
    req.InstanceIds = [instance_id]
    resp = client.DescribeSandboxInstanceList(req)
    if not resp.InstanceSet:
        return ""
    return resp.InstanceSet[0].Status or ""


def wait_instance(client: ags_client.AgsClient, instance_id: str) -> None:
    deadline = time.time() + int(os.getenv("INSTANCE_READY_TIMEOUT_SECONDS", "600"))
    while time.time() < deadline:
        status = get_instance_status(client, instance_id)
        print(f"instance status: {status or 'unknown'}")
        if status in {"RUNNING", "READY", "ACTIVE"}:
            return
        if status in {"FAILED", "DELETING", "DELETED", "ERROR"}:
            raise SystemExit(f"instance failed: {status}")
        time.sleep(5)
    raise SystemExit("instance did not become RUNNING in time")


def acquire_token(client: ags_client.AgsClient, instance_id: str) -> str:
    req = models.AcquireSandboxInstanceTokenRequest()
    req.InstanceId = instance_id
    resp = client.AcquireSandboxInstanceToken(req)
    return resp.Token


def gateway_domain() -> str:
    explicit = os.getenv("AGS_GATEWAY_DOMAIN")
    if explicit:
        return explicit
    region = os.getenv("AGR_REGION") or os.getenv("AGS_REGION") or os.getenv("TENCENTCLOUD_REGION", REGION)
    domain = os.getenv("AGR_DOMAIN") or os.getenv("AGS_DOMAIN") or "tencentags.com"
    return f"{region}.{domain}"


def sandbox_port_url(instance_id: str, path: str = "") -> str:
    scheme = os.getenv("AGS_SANDBOX_PORT_SCHEME", "https")
    return f"{scheme}://{REMOTE_TUNNEL_PORT}-{instance_id}.{gateway_domain()}{path}"


def start_process(name: str, args: list[str], env: dict[str, str] | None = None) -> subprocess.Popen[Any]:
    STATE.mkdir(exist_ok=True)
    log = open(STATE / f"{name}.log", "w", encoding="utf-8")
    proc = subprocess.Popen(args, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    write(STATE / f"{name}.pid", str(proc.pid))
    print(f"{name.upper().replace('-', '_')}_PID={proc.pid}")
    return proc


def wait_http(url: str, tunnel_token_value: str, access_token: str) -> None:
    deadline = time.time() + 30
    last = ""
    while time.time() < deadline:
        try:
            req = request.Request(
                url,
                headers={
                    "Authorization": f"Bearer {tunnel_token_value}",
                    "X-Access-Token": access_token,
                },
            )
            with request.urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    return
        except Exception as exc:
            last = str(exc)
        time.sleep(1)
    raise SystemExit(f"health check failed: {last}")


class AllowlistHandler(http.server.BaseHTTPRequestHandler):
    allowed_path = "/allowlist-ok"

    def do_GET(self) -> None:
        if self.path.split("?", 1)[0] != self.allowed_path:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"not-found")
            return
        body = json.dumps({"ok": True, "source": "allowlist-upstream", "path": self.path}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: Any) -> None:
        print(fmt % args, flush=True)


class MultiTurnHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        if self.path.split("?", 1)[0] != "/v1/messages":
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"not-found")
            return
        length = int(self.headers.get("Content-Length") or "0")
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"invalid-json")
            return

        messages = payload.get("messages") or []
        flattened = json.dumps(messages, ensure_ascii=False)
        if "round two" in flattened and "turn-1-ok" in flattened:
            text = "turn-2-ok"
        elif "round one" in flattened:
            text = "turn-1-ok"
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"missing expected conversation context")
            return

        body = json.dumps(
            {
                "id": f"msg_mock_{text}",
                "type": "message",
                "role": "assistant",
                "model": "mock-local-service-tunnel",
                "content": [{"type": "text", "text": text}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: Any) -> None:
        print(fmt % args, flush=True)


def write_allowlist_policy() -> Path:
    policy = STATE / "allowlist-policy.yaml"
    upstream_port = int(os.getenv("ALLOWLIST_UPSTREAM_PORT", "18090"))
    allowed_path = os.getenv("ALLOWLIST_TEST_ALLOWED_PATH", "/allowlist-ok")
    allowed_cidrs = [item.strip() for item in os.getenv("ALLOWLIST_ALLOWED_IP_CIDRS", "127.0.0.1/32").split(",") if item.strip()]
    policy.write_text(
        "\n".join(
            [
                f'upstream_base: "http://127.0.0.1:{upstream_port}"',
                "allow_insecure_upstream: true",
                "allowed_upstream_hosts:",
                "  []",
                "allowed_upstream_ports:",
                f"  - {upstream_port}",
                "allowed_ip_cidrs:",
                *(f'  - "{cidr}"' for cidr in allowed_cidrs),
                "allowed_paths:",
                f'  - "{allowed_path}"',
                "allowed_path_prefixes:",
                "  []",
                "allowed_methods:",
                '  - "GET"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(f"AGS_TUNNEL_POLICY_FILE={policy}")
    return policy


def write_multi_turn_policy() -> Path:
    policy = STATE / "multi-turn-policy.yaml"
    upstream_port = int(os.getenv("MULTI_TURN_UPSTREAM_PORT", "18091"))
    allowed_cidrs = [item.strip() for item in os.getenv("MULTI_TURN_ALLOWED_IP_CIDRS", "127.0.0.1/32").split(",") if item.strip()]
    policy.write_text(
        "\n".join(
            [
                f'upstream_base: "http://127.0.0.1:{upstream_port}"',
                "allow_insecure_upstream: true",
                "allowed_upstream_hosts:",
                "  []",
                "allowed_upstream_ports:",
                f"  - {upstream_port}",
                "allowed_ip_cidrs:",
                *(f'  - "{cidr}"' for cidr in allowed_cidrs),
                "allowed_paths:",
                '  - "/v1/messages"',
                "allowed_path_prefixes:",
                "  []",
                "allowed_methods:",
                '  - "POST"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(f"AGS_TUNNEL_POLICY_FILE={policy}")
    return policy


def start_allowlist_upstream() -> subprocess.Popen[Any]:
    port_value = os.getenv("ALLOWLIST_UPSTREAM_PORT", "18090")
    path_value = os.getenv("ALLOWLIST_TEST_ALLOWED_PATH", "/allowlist-ok")
    code = (
        "import http.server, pathlib, sys; "
        "sys.path.insert(0, str(pathlib.Path.cwd())); "
        "from scripts.run import AllowlistHandler; "
        f"AllowlistHandler.allowed_path={path_value!r}; "
        f"http.server.ThreadingHTTPServer(('127.0.0.1',{int(port_value)}), AllowlistHandler).serve_forever()"
    )
    proc = start_process("allowlist-upstream", [sys.executable, "-c", code])
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", int(port_value)), timeout=1):
                return proc
        except OSError:
            time.sleep(0.2)
    raise SystemExit("allowlist upstream did not start")


def start_multi_turn_upstream() -> subprocess.Popen[Any]:
    port_value = os.getenv("MULTI_TURN_UPSTREAM_PORT", "18091")
    code = (
        "import http.server, pathlib, sys; "
        "sys.path.insert(0, str(pathlib.Path.cwd())); "
        "from scripts.run import MultiTurnHandler; "
        f"http.server.ThreadingHTTPServer(('127.0.0.1',{int(port_value)}), MultiTurnHandler).serve_forever()"
    )
    proc = start_process("multi-turn-upstream", [sys.executable, "-c", code])
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", int(port_value)), timeout=1):
                return proc
        except OSError:
            time.sleep(0.2)
    raise SystemExit("multi-turn upstream did not start")


def e2b_exec(instance_id: str, cmd: str) -> str:
    if not os.getenv("E2B_DOMAIN"):
        os.environ["E2B_DOMAIN"] = os.getenv("AGS_GATEWAY_DOMAIN", f"{os.getenv('TENCENTCLOUD_REGION', 'ap-guangzhou')}.tencentags.com")
    need("E2B_API_KEY")
    from e2b import Sandbox

    sandbox = Sandbox.connect(instance_id)
    result = sandbox.commands.run(cmd, user="sandbox", timeout=30)
    return result.stdout + result.stderr


def run_allowlist_test(instance_id: str) -> None:
    allowed_path = os.getenv("ALLOWLIST_TEST_ALLOWED_PATH", "/allowlist-ok")
    denied_path = os.getenv("ALLOWLIST_TEST_DENIED_PATH", "/blocked")
    allowed = e2b_exec(instance_id, f"curl -sS -i --max-time 30 http://127.0.0.1:{WORKLOAD_TUNNEL_PORT}{allowed_path}")
    denied = e2b_exec(instance_id, f"curl -sS -i --max-time 30 http://127.0.0.1:{WORKLOAD_TUNNEL_PORT}{denied_path}")
    write(STATE / "allowlist-allowed.txt", allowed)
    write(STATE / "allowlist-denied.txt", denied)
    if "HTTP/1.1 200" not in allowed or "allowlist-upstream" not in allowed:
        raise SystemExit(f"allowlist allowed request failed:\n{allowed}")
    if "HTTP/1.1 502" not in denied:
        raise SystemExit(f"allowlist denied request failed:\n{denied}")
    print(f"ALLOWLIST_TEST_ALLOWED_OUTPUT={STATE / 'allowlist-allowed.txt'}")
    print(f"ALLOWLIST_TEST_DENIED_OUTPUT={STATE / 'allowlist-denied.txt'}")


def run_multi_turn_test(instance_id: str) -> None:
    cmd = f"""cat >/tmp/turn1.json <<'JSON'
{{"model":"mock","max_tokens":64,"messages":[{{"role":"user","content":"round one"}}]}}
JSON
curl -sS -i --max-time 30 -H 'content-type: application/json' -d @/tmp/turn1.json http://127.0.0.1:{WORKLOAD_TUNNEL_PORT}/v1/messages
cat >/tmp/turn2.json <<'JSON'
{{"model":"mock","max_tokens":64,"messages":[{{"role":"user","content":"round one"}},{{"role":"assistant","content":[{{"type":"text","text":"turn-1-ok"}}]}},{{"role":"user","content":"round two"}}]}}
JSON
curl -sS -i --max-time 30 -H 'content-type: application/json' -d @/tmp/turn2.json http://127.0.0.1:{WORKLOAD_TUNNEL_PORT}/v1/messages
"""
    output = e2b_exec(instance_id, cmd)
    write(STATE / "multi-turn-output.txt", output)
    if output.count("HTTP/1.1 200") < 2 or "turn-1-ok" not in output or "turn-2-ok" not in output:
        raise SystemExit(f"multi-turn test failed:\n{output}")
    print(f"MULTI_TURN_TEST_OUTPUT={STATE / 'multi-turn-output.txt'}")


def run_demo(instance_id: str, access_token: str) -> None:
    prompt = os.getenv("PROMPT", "Reply with exactly: local-service-tunnel-ok")
    payload = json.dumps({"prompt": prompt}).encode()
    req = request.Request(
        sandbox_port_url(instance_id, "/demo/run"),
        data=payload,
        headers={
            "Authorization": f"Bearer {tunnel_token()}",
            "X-Access-Token": access_token,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=int(os.getenv("DEMO_TIMEOUT_SECONDS", "240"))) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        raise SystemExit(f"demo request failed: {exc}") from exc
    write(STATE / "demo-output.json", body)
    print(f"DEMO_OUTPUT={STATE / 'demo-output.json'}")
    if "local-service-tunnel-ok" not in body:
        raise SystemExit(f"demo did not produce local-service-tunnel-ok:\n{body}")


def enabled(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).lower() in {"1", "true", "yes", "on"}


def main() -> int:
    STATE.mkdir(exist_ok=True)
    if not os.getenv("INSTANCE_ID"):
        for name in ["instance_id", "instance-create.json"]:
            try:
                (STATE / name).unlink()
            except FileNotFoundError:
                pass
    client = tc_client()
    token = tunnel_token()
    policy = Path(os.getenv("AGS_TUNNEL_POLICY_FILE", str(ROOT / "config/tunnel-policy.yaml")))
    if enabled("RUN_ALLOWLIST_TEST"):
        policy = write_allowlist_policy()
        os.environ.setdefault("ANTHROPIC_API_KEY", "allowlist-test-placeholder")
        start_allowlist_upstream()
    elif enabled("RUN_MULTI_TURN_TEST"):
        policy = write_multi_turn_policy()
        os.environ.setdefault("ANTHROPIC_API_KEY", "multi-turn-test-placeholder")
        start_multi_turn_upstream()

    tool_id = os.getenv("TOOL_ID") or create_tool(client, token)
    wait_tool(client, tool_id)
    instance_id = start_instance(client, tool_id)
    wait_instance(client, instance_id)
    access_token = acquire_token(client, instance_id)

    wait_http(sandbox_port_url(instance_id, "/healthz"), token, access_token)
    env = os.environ.copy()
    env["AGS_TUNNEL_POLICY_FILE"] = str(policy)
    start_process(
        "ags-tunnel-client",
        [
            sys.executable,
            str(ROOT / "tunnel/ags-tunnel-client.py"),
            "--instance-id",
            instance_id,
            "--remote-port",
            str(REMOTE_TUNNEL_PORT),
            "--gateway-domain",
            gateway_domain(),
            "--policy-file",
            str(policy),
            f"--token={token}",
            f"--instance-access-token={access_token}",
        ],
        env=env,
    )
    time.sleep(2)

    if enabled("RUN_ALLOWLIST_TEST"):
        run_allowlist_test(instance_id)
    elif enabled("RUN_MULTI_TURN_TEST"):
        run_multi_turn_test(instance_id)
    elif enabled("RUN_DEMO", "1"):
        run_demo(instance_id, access_token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
