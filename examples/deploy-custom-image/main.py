"""
One-click deploy: pull image → build wrapper (inject envd) → push to CCR → create/update AGS sandbox tool.
"""

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).parent.resolve()
ENVD_PORT = 49983
MAX_LIST_PAGES = 50

REQUIRED_VARS = [
    "SOURCE_IMAGE",
    "TENCENTCLOUD_REGISTRY",
    "TENCENTCLOUD_SECRET_ID",
    "TENCENTCLOUD_SECRET_KEY",
    "TENCENTCLOUD_REGION",
    "AGS_API_KEY",
    "AGS_DOMAIN",
    "TOOL_NAME",
    "TOOL_CPU",
    "TOOL_MEMORY",
    "ROLE_ARN",
]


def step(n: int, total: int, msg: str) -> None:
    print(f"\n\033[1;36m[{n}/{total}] {msg}\033[0m")


def die(msg: str, code: int = 1) -> None:
    print(f"\033[1;31mERROR: {msg}\033[0m", file=sys.stderr)
    sys.exit(code)


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    print(f"  \033[90m$ {shlex.join(cmd)}\033[0m")
    return subprocess.run(cmd, check=True, **kwargs)


def detect_container_engine() -> str:
    for engine in ["podman", "docker"]:
        if shutil.which(engine):
            return engine
    die("Neither 'podman' nor 'docker' found in PATH. Install one and re-run.")
    return ""


def load_config() -> dict[str, str]:
    env_file = SCRIPT_DIR / ".env"
    if not env_file.exists():
        die(
            "No .env found. Create one first:\n"
            "       cp .env.example .env\n"
            "       # then edit with your values"
        )

    load_dotenv(env_file)

    missing = [v for v in REQUIRED_VARS if not os.environ.get(v)]
    if missing:
        print("\033[1;31mMissing required environment variables:\033[0m")
        for var in missing:
            print(f"  - {var}")
        die("Edit .env to fill in the missing values.")

    return {v: os.environ[v] for v in REQUIRED_VARS}


# ---------------------------------------------------------------------------
# Step 1: Build wrapper image & push to CCR
# ---------------------------------------------------------------------------

def build_and_push(cfg: dict[str, str], engine: str) -> tuple[str, dict]:
    step(1, 3, "Build wrapper image & push to CCR")

    source_image = cfg["SOURCE_IMAGE"]
    target = cfg["TENCENTCLOUD_REGISTRY"].rstrip("/")
    image_latest = f"{target}:latest"

    # AGS runs linux/amd64 only; source image must provide an amd64 manifest
    run([engine, "pull", "--platform", "linux/amd64", source_image])

    print(f"\n  Inspecting source image: {source_image}")
    image_info = inspect_source_image(engine, source_image)

    run([
        engine, "build",
        "--platform", "linux/amd64",
        "--build-arg", f"SOURCE_IMAGE={source_image}",
        "-t", image_latest,
        str(SCRIPT_DIR),
    ])

    result = subprocess.run(
        [engine, "inspect", "--format={{.Id}}", image_latest],
        check=True,
        capture_output=True,
        text=True,
    )
    raw_id = result.stdout.strip()
    raw_hash = raw_id.replace("sha256:", "")[:12]
    image_hash_tag = f"{target}:{raw_hash}"

    print(f"\n  Image hash: {raw_hash}")

    run([engine, "tag", image_latest, image_hash_tag])
    run([engine, "push", image_latest])
    run([engine, "push", image_hash_tag])

    print(f"  \033[32m✓ Pushed: {image_latest}\033[0m")
    print(f"  \033[32m✓ Pushed: {image_hash_tag}\033[0m")
    return image_hash_tag, image_info


# ---------------------------------------------------------------------------
# Image inspection
# ---------------------------------------------------------------------------

def inspect_source_image(engine: str, source_image: str) -> dict:
    """Extract CMD, ENTRYPOINT, ExposedPorts, and Healthcheck from the source image."""
    result = subprocess.run(
        [engine, "inspect", "--format={{json .Config}}", source_image],
        check=True, capture_output=True, text=True,
    )
    config_raw = result.stdout.strip()
    config = json.loads(config_raw) if config_raw and config_raw != "null" else {}
    if not config:
        print("  Warning: could not read image config, proceeding with defaults")

    entrypoint = config.get("Entrypoint") or []
    cmd = config.get("Cmd") or []
    exposed_ports = config.get("ExposedPorts") or {}
    healthcheck = config.get("Healthcheck")

    ports: list[tuple[int, str]] = []
    for port_spec in exposed_ports:
        parts = port_spec.split("/")
        if len(parts) != 2:
            print(f"  Warning: skipping unexpected port spec: {port_spec!r}")
            continue
        try:
            ports.append((int(parts[0]), parts[1].upper()))
        except ValueError:
            print(f"  Warning: skipping invalid port number: {parts[0]!r}")

    print(f"  Entrypoint : {entrypoint or '(none)'}")
    print(f"  Cmd        : {cmd or '(none)'}")
    print(f"  Ports      : {[f'{p}/{t.lower()}' for p, t in ports] or '(none)'}")
    print(f"  Healthcheck: {'yes' if healthcheck else 'no'}")

    return {
        "entrypoint": entrypoint,
        "cmd": cmd,
        "ports": ports,
        "healthcheck": healthcheck,
    }


# ---------------------------------------------------------------------------
# Step 2: Create / Update AGS Sandbox Tool
# ---------------------------------------------------------------------------

def build_custom_config(cfg: dict[str, str], image_ref: str, image_info: dict, models):
    """Build the CustomConfiguration from image inspection results."""
    registry_type = os.environ.get("REGISTRY_TYPE", "personal")

    cc = models.CustomConfiguration()
    cc.Image = image_ref
    cc.ImageRegistryType = registry_type

    entrypoint = image_info["entrypoint"]
    cmd = image_info["cmd"]
    original_parts = entrypoint + cmd
    if original_parts:
        original_cmd = " ".join(shlex.quote(p) for p in original_parts)
        cc.Command = ["/bin/sh"]
        cc.Args = ["-c", f"/usr/bin/envd & exec {original_cmd}"]
    else:
        cc.Command = ["/usr/bin/envd"]

    res = models.ResourceConfiguration()
    res.CPU = cfg["TOOL_CPU"]
    res.Memory = cfg["TOOL_MEMORY"]
    cc.Resources = res

    image_ports = list(image_info["ports"])
    port_nums = {p for p, _ in image_ports}
    if ENVD_PORT not in port_nums:
        image_ports.append((ENVD_PORT, "TCP"))

    port_configs = []
    for port_num, proto in sorted(image_ports):
        pc = models.PortConfiguration()
        pc.Name = f"port-{port_num}"
        pc.Protocol = proto
        pc.Port = port_num
        port_configs.append(pc)
    cc.Ports = port_configs

    healthcheck = image_info["healthcheck"]
    probe_port = ENVD_PORT
    probe_path = "/health"

    if healthcheck and healthcheck.get("Test"):
        test_cmd = healthcheck["Test"]
        test_str = test_cmd[-1] if test_cmd else ""
        m = re.search(
            r"https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0):(\d+)(/\S*)?",
            test_str,
        )
        if m:
            probe_port = int(m.group(1))
            probe_path = m.group(2) or "/"
            print(f"  Using image healthcheck: port={probe_port}, path={probe_path}")
        else:
            print(f"  Warning: cannot parse healthcheck command: {test_str!r}")
            print(f"  Falling back to envd probe (port {ENVD_PORT}, path /health)")

    http_get = models.HttpGetAction()
    http_get.Scheme = "HTTP"
    http_get.Port = probe_port
    http_get.Path = probe_path

    probe = models.ProbeConfiguration()
    probe.HttpGet = http_get
    probe.ReadyTimeoutMs = 30000
    probe.ProbeTimeoutMs = 3000
    probe.ProbePeriodMs = 3000
    probe.FailureThreshold = 100
    probe.SuccessThreshold = 1
    cc.Probe = probe

    return cc


def find_tool_by_name(client, models, tool_name: str):
    """Paginate through all tools and find by exact ToolName match."""
    offset = 0
    for _ in range(MAX_LIST_PAGES):
        req = models.DescribeSandboxToolListRequest()
        req.Limit = 100
        req.Offset = offset
        resp = client.DescribeSandboxToolList(req)
        tools = resp.SandboxToolSet or []
        for t in tools:
            if t.ToolName == tool_name:
                return t
        offset += len(tools)
        if not tools or offset >= resp.TotalCount:
            return None
    return None


def ags_create_or_update(cfg: dict[str, str], image_ref: str, image_info: dict) -> None:
    step(2, 3, "Create / Update AGS Sandbox Tool")

    from tencentcloud.common import credential
    from tencentcloud.ags.v20250920 import ags_client, models

    cred = credential.Credential(
        cfg["TENCENTCLOUD_SECRET_ID"],
        cfg["TENCENTCLOUD_SECRET_KEY"],
    )
    client = ags_client.AgsClient(cred, cfg["TENCENTCLOUD_REGION"])

    tool_name = cfg["TOOL_NAME"]
    print(f"  Searching for tool '{tool_name}' ...")
    existing = find_tool_by_name(client, models, tool_name)

    cc = build_custom_config(cfg, image_ref, image_info, models)

    net = models.NetworkConfiguration()
    net.NetworkMode = "PUBLIC"

    if not existing:
        print(f"  Tool '{tool_name}' not found -> Creating ...")
        req = models.CreateSandboxToolRequest()
        req.ToolName = tool_name
        req.ToolType = "custom"
        req.CustomConfiguration = cc
        req.RoleArn = cfg["ROLE_ARN"]
        req.NetworkConfiguration = net
        client.CreateSandboxTool(req)
        print(f"  \033[32m✓ Created tool: {tool_name}\033[0m")
    else:
        tool_id = existing.ToolId
        print(f"  Tool '{tool_name}' exists (ID: {tool_id}) -> Updating image ...")
        req = models.UpdateSandboxToolRequest()
        req.ToolId = tool_id
        req.CustomConfiguration = cc
        req.NetworkConfiguration = net
        client.UpdateSandboxTool(req)
        print(f"  \033[32m✓ Updated tool: {tool_name} -> {image_ref}\033[0m")


# ---------------------------------------------------------------------------
# Step 3: Print summary
# ---------------------------------------------------------------------------

def print_summary(cfg: dict[str, str], image_ref: str, image_info: dict) -> None:
    step(3, 3, "Done! Summary")

    tool_name = cfg["TOOL_NAME"]
    domain = cfg["AGS_DOMAIN"]

    # Only show application ports; ENVD_PORT (49983) is internal and not printed
    app_ports = [(p, t) for p, t in image_info["ports"] if p != ENVD_PORT]
    port_list = ", ".join(str(p) for p, _ in sorted(app_ports)) or "(none)"

    print(f"\n  Tool Name : {tool_name}")
    print(f"  Image     : {image_ref}")
    print(f"  Domain    : {domain}")
    print(f"  Region    : {cfg['TENCENTCLOUD_REGION']}")
    print(f"  Ports     : {port_list}")
    print()
    # e2b_code_interpreter is the AGS-compatible Python SDK for creating sandbox instances.
    # Install separately: pip install e2b-code-interpreter
    print("  \033[1;33mTo create a sandbox instance (Python):\033[0m")
    print()
    print('  \033[90mfrom e2b_code_interpreter import Sandbox  # pip install e2b-code-interpreter')
    print()
    print(f'  sandbox = Sandbox.create(template="{tool_name}", api_key="<YOUR_AGS_API_KEY>", domain="{domain}")')
    print('  token = sandbox._envd_access_token  # NOTE: private API, no public alternative yet')
    for port_num, _ in sorted(app_ports):
        print(f'  print(f"port {port_num}: https://{{sandbox.get_host({port_num})}}/?" + f"access_token={{token}}")')
    print('\033[0m')


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("\033[1;35m╔═══════════════════════════════════════════════╗\033[0m")
    print("\033[1;35m║  AGS Custom Image  ·  One-click Deployment    ║\033[0m")
    print("\033[1;35m╚═══════════════════════════════════════════════╝\033[0m")

    engine = detect_container_engine()
    cfg = load_config()

    print(f"\n  Engine   : {engine}")
    print(f"  Source   : {cfg['SOURCE_IMAGE']}")
    print(f"  Target   : {cfg['TENCENTCLOUD_REGISTRY']}")
    print(f"  Tool     : {cfg['TOOL_NAME']}")
    print(f"  Region   : {cfg['TENCENTCLOUD_REGION']}")

    try:
        image_ref, image_info = build_and_push(cfg, engine)
        ags_create_or_update(cfg, image_ref, image_info)
        print_summary(cfg, image_ref, image_info)
    except subprocess.CalledProcessError as exc:
        die(f"Command failed: {exc.cmd}\n       Return code: {exc.returncode}")
    except Exception as exc:  # noqa: BLE001
        code = getattr(exc, "code", None) or type(exc).__name__
        message = getattr(exc, "message", None) or str(exc)
        die(f"API error [{code}]: {message}")

    print("\033[1;32m✅  All done!\033[0m")


if __name__ == "__main__":
    main()
