#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shlex
import time
from pathlib import Path
from typing import Any
from urllib import request

from e2b import Sandbox
from e2b.connection_config import ConnectionConfig
from e2b.sandbox.commands.command_handle import CommandExitException, CommandResult
from packaging.version import Version
from tencentcloud.ags.v20250920 import ags_client, models
from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".state"

ENVD_PORT = int(os.getenv("ENVD_PORT", "49983"))
HTTP_PORT = int(os.getenv("DEMO_HTTP_PORT", "8080"))
SANDBOX_TIMEOUT = os.getenv("INSTANCE_TIMEOUT", "1h")
CLAUDE_BIN = "/nix/claude-code/nix-env/bin/claude"
WORKDIR = os.getenv("AGENT_WORKDIR", "/workspace")
REPORT_DIR = "/workspace/report"
REPORT_FILE = f"{REPORT_DIR}/index.html"
TOPIC = (
    os.getenv("TASK_TOPIC")
    or os.getenv("DEMO_TOPIC")
    or "最近 24 小时最重要的 AI 行业新闻"
)
TASK = os.getenv(
    "AGENT_TASK",
    "Use WebSearch no more than twice to find three important AI industry news items "
    "published in the last 24 hours. Then immediately write a Chinese briefing of no "
    "more than 600 Chinese characters. Include a title, generation time, three concise "
    "items, likely impact, and a source URL for each item. Clearly separate facts from "
    "analysis, mention uncertainty, and do not provide investment advice.",
)


def need(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"{name} is required")
    return value


def anthropic_key() -> str:
    value = os.getenv("ANTHROPIC_AUTH_TOKEN") or os.getenv("ANTHROPIC_API_KEY")
    if not value:
        raise SystemExit("ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN is required")
    return value


def tc_client() -> ags_client.AgsClient:
    cred = credential.Credential(
        need("TENCENTCLOUD_SECRET_ID"), need("TENCENTCLOUD_SECRET_KEY")
    )
    http_profile = HttpProfile()
    http_profile.endpoint = os.getenv("AGS_CLOUD_ENDPOINT", "ags.tencentcloudapi.com")
    profile = ClientProfile()
    profile.httpProfile = http_profile
    return ags_client.AgsClient(
        cred, os.getenv("TENCENTCLOUD_REGION", "ap-guangzhou"), profile
    )


def port(name: str, value: int) -> models.PortConfiguration:
    item = models.PortConfiguration()
    item.Name = name
    item.Port = value
    item.Protocol = "TCP"
    return item


def envd_probe() -> models.ProbeConfiguration:
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


def sandbox_command() -> str:
    return (
        f"/usr/bin/envd -port {ENVD_PORT} & "
        f"exec python3 -m http.server {HTTP_PORT} --bind 0.0.0.0 "
        f"--directory {shlex.quote(REPORT_DIR)}"
    )


def claude_mount() -> models.StorageMount:
    image = models.ImageStorageSource()
    image.Reference = need("CLAUDE_CODE_VOLUME_IMAGE_REF")
    image.ImageRegistryType = os.getenv(
        "CLAUDE_CODE_VOLUME_IMAGE_REGISTRY_TYPE", "personal"
    )
    image.SubPath = "/nix"

    source = models.StorageSource()
    source.Image = image

    mount = models.StorageMount()
    mount.Name = "claude-code-nix"
    mount.MountPath = "/nix"
    mount.ReadOnly = True
    mount.StorageSource = source
    return mount


def write(path: Path, value: str) -> None:
    STATE.mkdir(exist_ok=True)
    path.write_text(value, encoding="utf-8")


def create_tool(client: ags_client.AgsClient) -> str:
    req = models.CreateSandboxToolRequest()
    req.ToolName = os.getenv(
        "TOOL_NAME", f"claude-code-agent-volume-{time.strftime('%m%d%H%M%S')}"
    )
    req.ToolType = "custom"
    req.Description = (
        "Claude Code from a Nix volume with envd and a static report server"
    )
    req.DefaultTimeout = SANDBOX_TIMEOUT
    req.Persistent = False
    req.RoleArn = need("ROLE_ARN")

    network = models.NetworkConfiguration()
    network.NetworkMode = "PUBLIC"
    req.NetworkConfiguration = network

    custom = models.CustomConfiguration()
    custom.Image = need("MAIN_IMAGE_REF")
    custom.ImageRegistryType = os.getenv("MAIN_IMAGE_REGISTRY_TYPE", "personal")
    custom.Command = ["/bin/sh", "-c"]
    custom.Args = [sandbox_command()]
    custom.Ports = [port("envd", ENVD_PORT), port("result", HTTP_PORT)]
    custom.Probe = envd_probe()

    resources = models.ResourceConfiguration()
    resources.CPU = os.getenv("RUNTIME_CPU", "2")
    resources.Memory = os.getenv("RUNTIME_MEMORY", "4Gi")
    custom.Resources = resources
    req.CustomConfiguration = custom
    req.StorageMounts = [claude_mount()]

    resp = client.CreateSandboxTool(req)
    tool_id = resp.ToolId
    write(STATE / "tool_id", tool_id)
    write(STATE / "tool_name", req.ToolName)
    write(STATE / "tool-create.json", resp.to_json_string())
    print(f"TOOL_ID={tool_id}")
    return tool_id


def tool_status(client: ags_client.AgsClient, tool_id: str) -> str:
    req = models.DescribeSandboxToolListRequest()
    req.ToolIds = [tool_id]
    resp = client.DescribeSandboxToolList(req)
    return resp.SandboxToolSet[0].Status if resp.SandboxToolSet else ""


def wait_tool(client: ags_client.AgsClient, tool_id: str) -> None:
    deadline = time.time() + int(os.getenv("TOOL_READY_TIMEOUT_SECONDS", "900"))
    while time.time() < deadline:
        status = tool_status(client, tool_id) or "unknown"
        print(f"tool status: {status}")
        if status in {"ACTIVE", "READY"}:
            return
        if status in {"FAILED", "DELETING", "DELETED", "ERROR"}:
            raise SystemExit(f"tool failed: {status}")
        time.sleep(10)
    raise SystemExit("tool did not become ACTIVE in time")


def start_instance(
    client: ags_client.AgsClient, tool_id: str, *, timeout: str | None
) -> tuple[str, bool]:
    req = models.StartSandboxInstanceRequest()
    req.ToolId = tool_id
    if timeout is not None:
        req.Timeout = timeout
    req.AuthMode = "PUBLIC"
    resp = client.StartSandboxInstance(req)
    instance = resp.Instance
    instance_id = instance.InstanceId
    write(STATE / "instance_id", instance_id)
    write(STATE / "instance-create.json", resp.to_json_string())
    print(f"INSTANCE_ID={instance_id}")
    return instance_id, bool(instance.Persistent)


def instance_status(client: ags_client.AgsClient, instance_id: str) -> str:
    req = models.DescribeSandboxInstanceListRequest()
    req.InstanceIds = [instance_id]
    resp = client.DescribeSandboxInstanceList(req)
    return resp.InstanceSet[0].Status if resp.InstanceSet else ""


def wait_instance(client: ags_client.AgsClient, instance_id: str) -> None:
    deadline = time.time() + int(os.getenv("INSTANCE_READY_TIMEOUT_SECONDS", "600"))
    while time.time() < deadline:
        status = instance_status(client, instance_id) or "unknown"
        print(f"instance status: {status}")
        if status in {"RUNNING", "READY", "ACTIVE"}:
            return
        if status in {"FAILED", "DELETING", "DELETED", "ERROR"}:
            raise SystemExit(f"instance failed: {status}")
        time.sleep(5)
    raise SystemExit("instance did not become RUNNING in time")


def acquire_envd_token(client: ags_client.AgsClient, instance_id: str) -> str:
    req = models.AcquireSandboxInstanceTokenRequest()
    req.InstanceId = instance_id
    token = client.AcquireSandboxInstanceToken(req).Token
    if not token:
        raise SystemExit("PUBLIC instance did not return an envd access token")
    return token


def gateway_domain() -> str:
    if domain := os.getenv("AGS_GATEWAY_DOMAIN") or os.getenv("E2B_DOMAIN"):
        return domain
    region = os.getenv("TENCENTCLOUD_REGION", "ap-guangzhou")
    return f"{region}.{os.getenv('AGS_DOMAIN', 'tencentags.com')}"


def result_url(instance_id: str) -> str:
    scheme = os.getenv("AGS_SANDBOX_PORT_SCHEME", "https")
    return f"{scheme}://{HTTP_PORT}-{instance_id}.{gateway_domain()}/"


def connect_envd(instance_id: str, token: str) -> Sandbox:
    domain = gateway_domain()
    headers = {
        "X-Access-Token": token,
        "E2b-Sandbox-Id": instance_id,
        "E2b-Sandbox-Port": str(ENVD_PORT),
    }
    config = ConnectionConfig(
        domain=domain,
        extra_sandbox_headers=headers,
        request_timeout=float(os.getenv("ENVD_REQUEST_TIMEOUT_SECONDS", "60")),
    )
    return Sandbox(
        sandbox_id=instance_id,
        sandbox_domain=domain,
        envd_version=Version(os.getenv("ENVD_VERSION", "0.5.14")),
        envd_access_token=token,
        connection_config=config,
    )


def result_text(result: object, secret: str = "") -> str:
    stdout = str(getattr(result, "stdout", "") or "")
    stderr = str(getattr(result, "stderr", "") or "")
    text = stdout + stderr
    return text.replace(secret, "<redacted>") if secret else text


def run_envd_command(sandbox: Sandbox, cmd: str, **kwargs: Any) -> CommandResult:
    try:
        return sandbox.commands.run(cmd, **kwargs)
    except CommandExitException as exc:
        return exc


def wait_public_file(url: str, *, filename: str = "") -> str:
    deadline = time.time() + int(os.getenv("PUBLIC_PAGE_READY_TIMEOUT_SECONDS", "120"))
    endpoint = f"{url}{filename}"
    last_error = ""
    while time.time() < deadline:
        try:
            with request.urlopen(endpoint, timeout=10) as response:
                content = response.read().decode("utf-8", errors="replace")
            if not filename or "<html" in content.lower():
                return content
            last_error = f"{endpoint} did not contain an HTML document"
        except Exception as exc:  # noqa: BLE001  # pragma: no cover
            last_error = str(exc)
        time.sleep(2)
    raise RuntimeError(f"public file did not become ready: {last_error}")


def inspect_claude(sandbox: Sandbox) -> tuple[str, str]:
    command = (
        "set -eu\n"
        f"test -x {shlex.quote(CLAUDE_BIN)}\n"
        f"printf 'path='; readlink -f {shlex.quote(CLAUDE_BIN)}\n"
        f"printf 'version='; {shlex.quote(CLAUDE_BIN)} --version"
    )
    result = run_envd_command(sandbox, command, cwd=WORKDIR, user="root")
    text = result_text(result)
    if result.exit_code != 0:
        raise RuntimeError(f"mounted Claude Code check failed:\n{text}")
    values = dict(line.split("=", 1) for line in text.splitlines() if "=" in line)
    path = values.get("path", "")
    version = values.get("version", "")
    if not path.startswith("/nix/store/") or not version:
        raise RuntimeError(f"unexpected Claude Code runtime:\n{text}")
    return path, version


def claude_environment(api_key: str, base_url: str, model: str) -> dict[str, str]:
    return {
        "ANTHROPIC_BASE_URL": base_url,
        # DeepSeek's Anthropic-compatible endpoint documents AUTH_TOKEN. Accept
        # API_KEY from the caller, but expose only AUTH_TOKEN to Claude Code.
        "ANTHROPIC_AUTH_TOKEN": api_key,
        "ANTHROPIC_MODEL": model,
        "ANTHROPIC_DEFAULT_OPUS_MODEL": os.getenv(
            "ANTHROPIC_DEFAULT_OPUS_MODEL", model
        ),
        "ANTHROPIC_DEFAULT_SONNET_MODEL": os.getenv(
            "ANTHROPIC_DEFAULT_SONNET_MODEL", model
        ),
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": os.getenv(
            "ANTHROPIC_DEFAULT_HAIKU_MODEL", model
        ),
        "CLAUDE_CODE_SUBAGENT_MODEL": os.getenv("CLAUDE_CODE_SUBAGENT_MODEL", model),
        "CLAUDE_CODE_EFFORT_LEVEL": os.getenv("CLAUDE_CODE_EFFORT_LEVEL", "medium"),
        "DISABLE_AUTOUPDATER": "1",
        "HOME": "/tmp/claude-home",
    }


def agent_prompt() -> str:
    return f"""You are responsible for both the analysis and its published report.
The task is not complete until you have written the final report to {REPORT_FILE}.

Topic:
{TOPIC}

Task:
{TASK}

Follow these steps:

1. Perform the task. Use WebSearch no more than the task allows.
2. Use the Write tool to create {REPORT_FILE} as a complete, standalone HTML5 page.
3. Write the report in Chinese with readable typography, concise sections, and clickable source links. Use inline CSS only; do not use JavaScript or external assets.
4. Do not write credentials, internal logs, or intermediate work into {REPORT_DIR}.
5. Return exactly PUBLISHED after the file has been written successfully.

Do not return the report instead of writing the file. The static HTTP server publishes that directory directly.
"""


def run_claude(sandbox: Sandbox, *, api_key: str, base_url: str, model: str) -> str:
    prepare = run_envd_command(
        sandbox,
        f"mkdir -p /tmp/claude-home {shlex.quote(REPORT_DIR)} && "
        f"rm -f {shlex.quote(REPORT_FILE)}",
        cwd=WORKDIR,
        user="root",
    )
    if prepare.exit_code != 0:
        raise RuntimeError(result_text(prepare))

    command = shlex.join(
        [
            CLAUDE_BIN,
            "-p",
            "--output-format=json",
            "--no-session-persistence",
            "--safe-mode",
            "--permission-mode=dontAsk",
            "--tools=WebSearch,Write,Bash",
            "--allowedTools=WebSearch,Write,Bash",
            "--max-turns",
            os.getenv("CLAUDE_MAX_TURNS", "8"),
            "--model",
            model,
            "--",
            agent_prompt(),
        ]
    )
    result = run_envd_command(
        sandbox,
        command,
        cwd=WORKDIR,
        envs=claude_environment(api_key, base_url, model),
        user="root",
        timeout=float(os.getenv("CLAUDE_RUN_TIMEOUT_SECONDS", "600")),
        request_timeout=float(os.getenv("CLAUDE_RUN_TIMEOUT_SECONDS", "600")) + 30,
    )
    text = result_text(result, api_key).strip()
    write(STATE / "claude-output.json", text + "\n")
    if result.exit_code != 0:
        raise RuntimeError(f"Claude Code failed:\n{text[-4000:]}")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Claude Code did not return JSON:\n{text[-4000:]}") from exc
    final_text = payload.get("result")
    if payload.get("is_error") or not isinstance(final_text, str):
        raise RuntimeError(f"Claude Code returned an error:\n{text[-4000:]}")
    if final_text.strip() != "PUBLISHED":
        raise RuntimeError(f"Claude Code did not confirm publication:\n{text[-4000:]}")
    return command


def main() -> int:
    STATE.mkdir(exist_ok=True)
    llm_key = anthropic_key()
    base_url = need("ANTHROPIC_BASE_URL")
    model = need("ANTHROPIC_MODEL")

    client = tc_client()
    tool_id = os.getenv("TOOL_ID", "").strip()
    tool_source = "existing" if tool_id else "created"
    if tool_id:
        print(f"Reusing TOOL_ID={tool_id}")
        write(STATE / "tool_id", tool_id)
    else:
        tool_id = create_tool(client)
    wait_tool(client, tool_id)

    instance_id, persistent = start_instance(
        client,
        tool_id,
        timeout=SANDBOX_TIMEOUT if tool_source == "created" else None,
    )
    wait_instance(client, instance_id)
    sandbox = connect_envd(instance_id, acquire_envd_token(client, instance_id))

    envd_check = run_envd_command(sandbox, "printf 'ENVD_READY\\n'", user="root")
    if envd_check.exit_code != 0 or "ENVD_READY" not in result_text(envd_check):
        raise SystemExit("envd command execution check failed")

    url = result_url(instance_id)
    write(STATE / "result_url", url)
    print(f"RESULT_URL={url}", flush=True)
    wait_public_file(url)

    claude_path, claude_version = inspect_claude(sandbox)
    command = run_claude(sandbox, api_key=llm_key, base_url=base_url, model=model)
    report_html = wait_public_file(url, filename="index.html")
    write(STATE / "report.html", report_html)

    summary = {
        "result_url": url,
        "auth_mode": "PUBLIC",
        "network_mode": "PUBLIC",
        "persistent": persistent,
        "tool_source": tool_source,
        "envd": "ready",
        "claude_profile": CLAUDE_BIN,
        "claude_store_path": claude_path,
        "claude_version": claude_version,
        "model": model,
        "topic": TOPIC,
        "status": "complete",
        "report_publisher": "claude-code",
        "report_file": REPORT_FILE,
        "report_server": "python-http.server",
        "command_uses_absolute_path": command.startswith(CLAUDE_BIN),
    }
    summary_text = json.dumps(summary, ensure_ascii=False, indent=2)
    write(STATE / "runtime-report.json", summary_text + "\n")
    print(summary_text)
    print(f"RESULT_URL={url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
