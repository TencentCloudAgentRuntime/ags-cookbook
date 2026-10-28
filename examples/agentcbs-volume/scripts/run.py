#!/usr/bin/env python3
"""Start a sandbox with an AgentCBS Volume mounted through a VolumeTemplate.

1. Create an AgentCBS VolumeTemplate.
2. Create a custom SandboxTool from the public code interpreter image. Its
   StorageMounts reference the template with ReuseKey=${metadata.reuse_key}.
3. Start a sandbox with metadata reuse_key=<SESSION_ID>. AGS derives the Volume
   for that key (or reuses it) and mounts it at /workspace.
4. Write and read a file on the Volume with run_code, then kill the sandbox.
   The Volume is retained; the next start with the same key mounts it again.

The template and Tool IDs are stored in .state/ and reused by later runs.
"""

from __future__ import annotations

import os
import time
from importlib.metadata import version
from typing import Any

from e2b_code_interpreter import Sandbox
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException

from common import (
    ags_client,
    call,
    derived_volumes,
    e2b_domain,
    need,
    read_state,
    remove_state,
    wait_active,
    write_state,
)

# Public code interpreter image from the AGS guide "Create a custom sandbox".
DEFAULT_IMAGE = "ccr.ccs.tencentyun.com/ags-image/sandbox-code:latest"
RUN_CODE_PORT = 49999
ENVD_PORT = 49983
MOUNT_PATH = "/workspace"
NOTES = f"{MOUNT_PATH}/notes.txt"

SESSION_ID = os.getenv("SESSION_ID", "").strip() or "session-s001"
VOLUME_CAPACITY = os.getenv("VOLUME_CAPACITY", "").strip() or "10Gi"


def find_volume_template(client) -> dict[str, Any] | None:
    """Look up the recorded template by ID, or by name if only the name was saved."""
    template_id = read_state("volume_template_id")
    name = read_state("volume_template_name")
    if template_id:
        query = {"VolumeTemplateIds": [template_id]}
    elif name:
        query = {"VolumeTemplateNames": [name]}
    else:
        return None
    templates = call(client, "DescribeVolumeTemplateList", query).get("VolumeTemplateSet") or []
    return templates[0] if templates else None


def ensure_volume_template(client) -> dict[str, Any]:
    template = find_volume_template(client)
    if template:
        print(
            f"Reusing VolumeTemplate {template['VolumeTemplateName']} "
            f"({template['VolumeTemplateId']})"
        )
    else:
        name = f"agentcbs-ws-{time.strftime('%m%d%H%M%S')}"
        template = call(
            client,
            "CreateVolumeTemplate",
            {
                "VolumeTemplateName": name,
                "StorageType": "AgentCbs",
                "StorageSpec": {"AgentCbs": {"Capacity": VOLUME_CAPACITY}},
                # Must contain ${reuse_key}: one derived Volume per reuse key.
                "VolumeNamePattern": "ws-${reuse_key}",
                # AgentCBS templates only support ReadWriteOnce + Retain.
                "AccessMode": "ReadWriteOnce",
                "ReclaimPolicy": "Retain",
                "ClientToken": f"create-{name}",
            },
        )["VolumeTemplate"]
        print(f"Created VolumeTemplate {name} ({VOLUME_CAPACITY}): {template['VolumeTemplateId']}")
        # A Tool recorded earlier is bound to the previous template; create a new one.
        remove_state("tool_id")
    # Always record both, so an interrupted earlier run cannot leave cleanup without the ID.
    write_state("volume_template_id", template["VolumeTemplateId"])
    write_state("volume_template_name", template["VolumeTemplateName"])

    def status() -> str:
        resp = call(
            client,
            "DescribeVolumeTemplateList",
            {"VolumeTemplateIds": [template["VolumeTemplateId"]]},
        )
        return (resp.get("VolumeTemplateSet") or [{}])[0].get("Status", "")

    wait_active("volume template", status)
    return template


def tool_status(client, tool_id: str) -> str:
    resp = call(client, "DescribeSandboxToolList", {"ToolIds": [tool_id]})
    return (resp.get("SandboxToolSet") or [{}])[0].get("Status", "")


def ensure_tool(client, template_name: str) -> str:
    tool_id = read_state("tool_id")
    status = tool_status(client, tool_id) if tool_id else ""
    if status == "FAILED":
        # For example, the image could not be pulled. Replace only the Tool so
        # that a corrected ROLE_ARN or image takes effect; the template and its
        # Volumes (and their data) are kept.
        print(f"SandboxTool {tool_id} is FAILED; creating a new one")
        try:
            call(client, "DeleteSandboxTool", {"ToolId": tool_id})
        except TencentCloudSDKException as exc:
            print(f"Could not delete the failed Tool {tool_id}: {exc.code}")
    if status and status not in {"FAILED", "DELETING", "DELETED"}:
        print(f"Reusing SandboxTool {tool_id}")
    else:
        name = f"agentcbs-code-{time.strftime('%m%d%H%M%S')}"
        tool_id = call(
            client,
            "CreateSandboxTool",
            {
                "ToolName": name,
                "ToolType": "custom",
                "Description": "Code interpreter image with an AgentCBS workspace",
                "DefaultTimeout": "30m",
                "NetworkConfiguration": {"NetworkMode": "PUBLIC"},
                # AGS assumes this role to pull the image.
                "RoleArn": need("ROLE_ARN"),
                "CustomConfiguration": {
                    "Image": os.getenv("SANDBOX_IMAGE_REF", "").strip() or DEFAULT_IMAGE,
                    "ImageRegistryType": os.getenv("SANDBOX_IMAGE_REGISTRY_TYPE", "").strip()
                    or "personal",
                    # S6-Overlay entry point of the code interpreter image.
                    "Command": ["/init"],
                    "Args": ["sleep", "infinity"],
                    "Ports": [
                        {"Name": "run-code", "Port": RUN_CODE_PORT, "Protocol": "TCP"},
                        {"Name": "envd", "Port": ENVD_PORT, "Protocol": "TCP"},
                    ],
                    "Resources": {"CPU": "2", "Memory": "1Gi"},
                    # Probe run-code so run_code() works as soon as the sandbox is ready.
                    "Probe": {
                        "HttpGet": {"Path": "/health", "Port": RUN_CODE_PORT, "Scheme": "HTTP"},
                        "ReadyTimeoutMs": 30000,
                        "ProbeTimeoutMs": 1000,
                        "ProbePeriodMs": 1000,
                        "SuccessThreshold": 1,
                        "FailureThreshold": 30,
                    },
                },
                "StorageMounts": [
                    {
                        "Name": "workspace",
                        "VolumeTemplate": {
                            "VolumeTemplateName": template_name,
                            # Filled from the sandbox start metadata "reuse_key".
                            "ReuseKey": "${metadata.reuse_key}",
                        },
                        "MountPath": MOUNT_PATH,
                        "ReadOnly": False,
                    }
                ],
                "ClientToken": f"create-{name}",
            },
        )["ToolId"]
        print(f"Created SandboxTool {name}: {tool_id}")
        write_state("tool_id", tool_id)

    wait_active("tool", lambda: tool_status(client, tool_id), timeout_seconds=900)
    return tool_id


def check_e2b_version() -> None:
    """e2b 2.25-2.45 rejects AGS API keys ("ark_..."); stop before creating resources."""
    major, minor = (int(x) for x in version("e2b").split(".")[:2])
    if major == 2 and 25 <= minor <= 45:
        raise SystemExit(
            f"e2b {version('e2b')} rejects AGS API keys. Upgrade it: "
            'pip install -U "e2b>=2.55.1" "e2b-code-interpreter>=2.11.5"'
        )


def main() -> int:
    check_e2b_version()
    api_key = need("E2B_API_KEY")
    client = ags_client()

    template = ensure_volume_template(client)
    tool_id = ensure_tool(client, template["VolumeTemplateName"])

    print(f"\n== Start a sandbox with reuse_key={SESSION_ID} ==")
    started = time.time()
    sandbox = Sandbox.create(
        template=tool_id,
        timeout=600,
        metadata={
            # Fills ${metadata.reuse_key} in the Tool's VolumeTemplate mount.
            "reuse_key": SESSION_ID,
            # Required whenever an AgentCBS Volume is mounted; lowercase "true".
            "x-ags-agent-cbs-system-disk": "true",
        },
        api_key=api_key,
        domain=e2b_domain(),
    )
    print(f"Sandbox started: {sandbox.sandbox_id} ({time.time() - started:.1f}s)")
    try:
        mount = sandbox.commands.run(
            f"grep ' {MOUNT_PATH} ' /proc/mounts; df -h {MOUNT_PATH} | tail -1", user="root"
        )
        print(f"Mount:\n{mount.stdout.rstrip()}")

        volume = next(
            (
                v
                for v in derived_volumes(client, template["VolumeTemplateId"])
                if v.get("ReuseKey") == SESSION_ID
            ),
            {},
        )
        print(
            f"Volume: {volume.get('VolumeId')} ({volume.get('VolumeName')}, "
            f"{volume.get('Capacity')}, mounted_by={volume.get('MountedInstanceId', '-')})"
        )

        execution = sandbox.run_code(f"""
import datetime
with open({NOTES!r}, "a") as f:
    f.write(f"{{datetime.datetime.now():%F %T}} written by {sandbox.sandbox_id}\\n")
print(open({NOTES!r}).read(), end="")
""")
        if execution.error:
            raise SystemExit(f"run_code failed: {execution.error.name}: {execution.error.value}")
        print(f"{NOTES}:\n{''.join(execution.logs.stdout).rstrip()}")
    finally:
        sandbox.kill()
        print(f"Sandbox killed: {sandbox.sandbox_id} (the Volume is retained)")

    print("AGENTCBS_VOLUME_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
