#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from urllib import request

from tencentcloud.ags.v20250920 import ags_client, models
from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".state"

HARNESS_PORT = int(os.getenv("HARNESS_PORT", "18080"))
SANDBOX_TIMEOUT = os.getenv("INSTANCE_TIMEOUT", "30m")
NETWORK_MODE = os.getenv("NETWORK_MODE", "SANDBOX")


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
    return ags_client.AgsClient(cred, os.getenv("TENCENTCLOUD_REGION", "ap-guangzhou"), profile)


def port(name: str, value: int) -> models.PortConfiguration:
    item = models.PortConfiguration()
    item.Name = name
    item.Port = value
    item.Protocol = "TCP"
    return item


def probe() -> models.ProbeConfiguration:
    http_get = models.HttpGetAction()
    http_get.Path = "/health"
    http_get.Port = HARNESS_PORT
    http_get.Scheme = "HTTP"

    item = models.ProbeConfiguration()
    item.HttpGet = http_get
    item.ReadyTimeoutMs = 30000
    item.ProbeTimeoutMs = 2000
    item.ProbePeriodMs = 1000
    item.SuccessThreshold = 1
    item.FailureThreshold = 60
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


def write(path: Path, value: str) -> None:
    STATE.mkdir(exist_ok=True)
    path.write_text(value, encoding="utf-8")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def create_tool(client: ags_client.AgsClient) -> str:
    req = models.CreateSandboxToolRequest()
    req.ToolName = os.getenv("TOOL_NAME", f"harness-nix-volume-{time.strftime('%m%d%H%M%S')}")
    req.ToolType = "custom"
    req.Description = "Self-contained Harness mounted from a Nix image volume"
    req.DefaultTimeout = SANDBOX_TIMEOUT
    req.RoleArn = need("ROLE_ARN")

    network = models.NetworkConfiguration()
    network.NetworkMode = NETWORK_MODE
    req.NetworkConfiguration = network

    custom = models.CustomConfiguration()
    custom.Image = need("MAIN_IMAGE_REF")
    custom.ImageRegistryType = os.getenv("MAIN_IMAGE_REGISTRY_TYPE", "personal")
    custom.Command = ["/nix/harness/bin/harness-demo"]
    custom.Args = ["serve", "--host", "0.0.0.0", "--port", str(HARNESS_PORT)]
    custom.Ports = [port("harness", HARNESS_PORT)]
    custom.Probe = probe()

    resources = models.ResourceConfiguration()
    resources.CPU = os.getenv("RUNTIME_CPU", "2")
    resources.Memory = os.getenv("RUNTIME_MEMORY", "4Gi")
    custom.Resources = resources
    req.CustomConfiguration = custom

    req.StorageMounts = [
        image_mount(
            "harness-nix",
            "/nix",
            need("HARNESS_VOLUME_IMAGE_REF"),
            os.getenv("HARNESS_VOLUME_IMAGE_REGISTRY_TYPE", "personal"),
            "/nix",
        )
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
    deadline = time.time() + int(os.getenv("TOOL_READY_TIMEOUT_SECONDS", "900"))
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
    region = os.getenv("TENCENTCLOUD_REGION", "ap-guangzhou")
    domain = os.getenv("AGS_DOMAIN", "tencentags.com")
    return f"{region}.{domain}"


def sandbox_port_url(instance_id: str, path: str = "") -> str:
    scheme = os.getenv("AGS_SANDBOX_PORT_SCHEME", "https")
    return f"{scheme}://{HARNESS_PORT}-{instance_id}.{gateway_domain()}{path}"


def call_harness(instance_id: str, access_token: str, path: str) -> str:
    req = request.Request(sandbox_port_url(instance_id, path), headers={"X-Access-Token": access_token})
    with request.urlopen(req, timeout=int(os.getenv("HARNESS_REQUEST_TIMEOUT_SECONDS", "30"))) as resp:
        return resp.read().decode("utf-8", errors="replace")


def main() -> int:
    STATE.mkdir(exist_ok=True)
    client = tc_client()
    tool_id = os.getenv("TOOL_ID")
    if tool_id:
        write(STATE / "tool_id", tool_id)
    else:
        tool_id = create_tool(client)
    wait_tool(client, tool_id)

    instance_id = start_instance(client, tool_id)
    wait_instance(client, instance_id)
    access_token = acquire_token(client, instance_id)

    health = call_harness(instance_id, access_token, "/health")
    report = call_harness(instance_id, access_token, "/run")
    write(STATE / "health.json", health)
    write(STATE / "runtime-report.json", report)

    payload = json.loads(report)
    if payload.get("ok") is not True:
        raise SystemExit(f"harness report is not ok: {report}")
    for key in ["claude", "node", "python"]:
        if not payload.get(key) or payload[key] == "not-found":
            raise SystemExit(f"{key} was not available from mounted Harness runtime: {report}")

    print(f"HEALTH_OUTPUT={STATE / 'health.json'}")
    print(f"RUNTIME_REPORT={STATE / 'runtime-report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
