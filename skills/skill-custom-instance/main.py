"""
skill-custom-instance: create and run a sandbox from a user-supplied image.

``CustomConfiguration`` on ``CreateSandboxTool`` lets you ship a fully custom
runtime: your own container image, entrypoint command + args, exposed ports,
CPU / memory request, and a readiness probe.  The flow (per e2e
``basic/custom/custom_tool_test.go``) is:

  1. CreateSandboxTool(ToolType="custom", CustomConfiguration={...}, RoleArn=…)
  2. StartSandboxInstance(ToolId=<new tool>)
  3. … use it via ``build_port_url`` on one of the exposed ports …
  4. StopSandboxInstance
  5. DeleteSandboxTool  (optional — tools can be reused)

> **AKSK-only.** Custom images require ``RoleArn`` and control-plane access.

Skills exposed:
  - start_custom(image, command, args=None, ports=None, resources=None,
                 probe=None, env=None, image_registry_type="enterprise",
                 role_arn, tool_name=None, timeout="10m")
  - stop_custom(instance_id, tool_id=None, delete_tool=False)
"""

import json
import logging
import os
import uuid
from typing import Any

from ags_client import (
    build_port_url,
    create_tool,
    credential_mode,
    delete_tool,
    start_instance,
    stop_instance,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)


def _generate_tool_name() -> str:
    return f"agsskill-custom-{uuid.uuid4().hex[:10]}"


# ---------------------------------------------------------------------------
# Skill: start_custom
# ---------------------------------------------------------------------------

def start_custom(
    image: str,
    command: list[str],
    role_arn: str | None = None,
    args: list[str] | None = None,
    ports: list[dict] | None = None,
    resources: dict | None = None,
    probe: dict | None = None,
    env: list[dict] | None = None,
    image_registry_type: str = "enterprise",
    tool_name: str | None = None,
    timeout: str = "10m",
) -> dict:
    """Create a custom tool and start one instance of it.

    Arguments mirror ``CustomConfiguration`` from the control-plane schema:

      * ``image`` / ``image_registry_type`` — container image reference and
        registry type (``"enterprise"``, ``"personal"``, or ``"system"``).
      * ``command`` / ``args`` — container entrypoint.
      * ``ports`` — list of ``{Name, Port, Protocol}`` (Protocol usually ``"TCP"``).
      * ``resources`` — ``{CPU: "1000m", Memory: "500Mi"}``.
      * ``probe`` — HTTP readiness probe spec; see
        :file:`e2e/basic/custom/custom_tool_test.go` for the full shape.
      * ``env`` — list of ``{Name, Value}``.

    Returns ``{tool_id, instance_id, status, ports, data_plane_urls}``.

    ``role_arn`` is required by AGS for custom images; leaving it ``None``
    will fall back to ``AGS_ROLE_ARN`` from the environment.
    """
    if credential_mode() != "aksk":
        raise RuntimeError("start_custom requires AKSK mode")

    role_arn = role_arn or os.environ.get("AGS_ROLE_ARN")
    if not role_arn:
        raise ValueError(
            "role_arn is required for custom images "
            "(or set AGS_ROLE_ARN in the environment)."
        )

    tool_name = tool_name or _generate_tool_name()
    default_ports = [{"Name": "http", "Port": 8000, "Protocol": "TCP"}]
    default_resources = {"CPU": "1000m", "Memory": "500Mi"}

    custom_configuration: dict[str, Any] = {
        "Image": image,
        "ImageRegistryType": image_registry_type,
        "Command": command,
        "Ports": ports or default_ports,
        "Resources": resources or default_resources,
    }
    if args is not None:
        custom_configuration["Args"] = args
    if env is not None:
        custom_configuration["Env"] = env
    if probe is not None:
        custom_configuration["Probe"] = probe

    log.info("CreateSandboxTool: name=%s image=%s", tool_name, image)
    tool_id = create_tool(
        tool_name=tool_name,
        tool_type="custom",
        custom_configuration=custom_configuration,
        role_arn=role_arn,
    )

    log.info("StartSandboxInstance: tool=%s", tool_id)
    instance_id = start_instance(tool_id=tool_id, timeout=timeout)

    ports_exposed = custom_configuration["Ports"]
    urls = {
        p["Name"] or f"port-{p['Port']}": build_port_url(instance_id, int(p["Port"]))
        for p in ports_exposed
    }

    return {
        "tool_id": tool_id,
        "tool_name": tool_name,
        "instance_id": instance_id,
        "image": image,
        "ports": ports_exposed,
        "data_plane_urls": urls,
    }


# ---------------------------------------------------------------------------
# Skill: stop_custom
# ---------------------------------------------------------------------------

def stop_custom(
    instance_id: str,
    tool_id: str | None = None,
    delete_tool_after: bool = False,
) -> dict:
    """Stop ``instance_id`` and optionally delete the owning tool."""
    if credential_mode() != "aksk":
        raise RuntimeError("stop_custom requires AKSK mode")

    stop_instance(instance_id)
    tool_deleted = False
    if delete_tool_after and tool_id:
        delete_tool(tool_id)
        tool_deleted = True

    return {
        "instance_id": instance_id,
        "stopped": True,
        "tool_id": tool_id,
        "tool_deleted": tool_deleted,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if credential_mode() != "aksk":
        raise SystemExit(
            "skill-custom-instance requires AKSK mode "
            "(TENCENTCLOUD_SECRET_ID / SECRET_KEY / REGION)."
        )

    # The default demo uses a *system* image (no RoleArn required in some
    # deployments) — adjust to match what your account has access to.
    demo_image = os.environ.get("AGS_DEMO_CUSTOM_IMAGE",
                                "ags-sandbox-image-pub/python-general:latest")
    demo_registry = os.environ.get("AGS_DEMO_CUSTOM_REGISTRY_TYPE", "system")
    demo_role = os.environ.get("AGS_ROLE_ARN", "qcs::cam::uin/0:roleName/agsdefault")

    log.info("=== Demo: start_custom → stop_custom ===")
    started = start_custom(
        image=demo_image,
        command=["/bin/bash"],
        args=["-c", "while true; do echo alive; sleep 5; done"],
        ports=[{"Name": "envd", "Port": 49983, "Protocol": "TCP"}],
        resources={"CPU": "1000m", "Memory": "500Mi"},
        image_registry_type=demo_registry,
        role_arn=demo_role,
    )
    print("\n=== Skill Result: start_custom ===")
    print(json.dumps(started, indent=2, ensure_ascii=False))

    stopped = stop_custom(
        instance_id=started["instance_id"],
        tool_id=started["tool_id"],
        delete_tool_after=True,
    )
    print("\n=== Skill Result: stop_custom ===")
    print(json.dumps(stopped, indent=2, ensure_ascii=False))
