"""
skill-cos-sandbox: sandbox with a COS (Cloud Object Storage) mount.

COS-backed sandboxes let multiple instances share persistent storage: anything
written under the mount path survives instance teardown and is visible to the
next instance that mounts the same bucket/path.

Two-step flow (per ``e2e/storage/cos_mount/*``):

  1. ``CreateSandboxTool`` with ``StorageMounts=[{Name, StorageSource: {Cos: {BucketName, BucketPath}}, MountPath}]``
  2. ``StartSandboxInstance`` referencing that Tool (or override MountOptions
     on a per-instance basis via ``start_instance(mount_options=…)``).

> **AKSK-only.** COS mount configuration is a control-plane-only feature.

Skills exposed:
  - start_cos_sandbox(cos_bucket, cos_path, mount_path, …, role_arn, …)
  - write_then_read_across_instances(cos_bucket, cos_path, mount_path, content)
  - stop_cos_sandbox(instance_id, tool_id=None, delete_tool_after=False)
"""

import json
import logging
import os
import uuid

from ags_client import (
    SandboxSession,
    acquire_token,
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
    return f"agsskill-cos-{uuid.uuid4().hex[:10]}"


def _storage_mounts(cos_bucket: str, cos_path: str, mount_path: str,
                    name: str = "cos-data", read_only: bool = False) -> list[dict]:
    return [{
        "Name": name,
        "StorageSource": {
            "Cos": {"BucketName": cos_bucket, "BucketPath": cos_path},
        },
        "MountPath": mount_path,
        "ReadOnly": read_only,
    }]


# ---------------------------------------------------------------------------
# Skill: start_cos_sandbox
# ---------------------------------------------------------------------------

def start_cos_sandbox(
    cos_bucket: str,
    cos_path: str,
    mount_path: str,
    *,
    role_arn: str | None = None,
    tool_type: str = "code-interpreter",
    tool_name: str | None = None,
    timeout: str = "10m",
    read_only: bool = False,
) -> dict:
    """Create a tool with a COS mount and start an instance of it.

    ``role_arn`` is required in most deployments for COS access; it falls
    back to ``AGS_ROLE_ARN`` from the environment.

    Returns ``{tool_id, instance_id, mount_path, cos_bucket, cos_path}``.
    """
    if credential_mode() != "aksk":
        raise RuntimeError("start_cos_sandbox requires AKSK mode")

    role_arn = role_arn or os.environ.get("AGS_ROLE_ARN")
    if not role_arn:
        raise ValueError(
            "role_arn is required for COS mounts "
            "(or set AGS_ROLE_ARN in the environment)."
        )

    tool_name = tool_name or _generate_tool_name()
    storage_mounts = _storage_mounts(cos_bucket, cos_path, mount_path,
                                     read_only=read_only)

    log.info("CreateSandboxTool (cos): %s → %s:%s@%s",
             tool_name, cos_bucket, cos_path, mount_path)
    tool_id = create_tool(
        tool_name=tool_name,
        tool_type=tool_type,
        storage_mounts=storage_mounts,
        role_arn=role_arn,
    )

    instance_id = start_instance(tool_id=tool_id, timeout=timeout)
    return {
        "tool_id": tool_id,
        "tool_name": tool_name,
        "instance_id": instance_id,
        "mount_path": mount_path,
        "cos_bucket": cos_bucket,
        "cos_path": cos_path,
        "read_only": read_only,
    }


# ---------------------------------------------------------------------------
# Skill: write_then_read_across_instances
# ---------------------------------------------------------------------------

def write_then_read_across_instances(
    cos_bucket: str,
    cos_path: str,
    mount_path: str,
    content: str = "hello from instance-1",
    *,
    role_arn: str | None = None,
    timeout: str = "10m",
) -> dict:
    """Prove COS persistence by writing from one instance and reading in another.

    Creates ONE tool with a COS mount, then:

      * starts instance A, writes ``content`` to ``mount_path/shared.txt``,
        stops A
      * starts instance B (same tool, same COS path), reads the file, stops B

    Returns ``{written_in, read_from, match, round_trip_bytes}``.
    """
    if credential_mode() != "aksk":
        raise RuntimeError("write_then_read_across_instances requires AKSK mode")

    role_arn = role_arn or os.environ.get("AGS_ROLE_ARN")
    if not role_arn:
        raise ValueError(
            "role_arn is required for COS mounts "
            "(or set AGS_ROLE_ARN in the environment)."
        )

    tool_name = _generate_tool_name()
    storage_mounts = _storage_mounts(cos_bucket, cos_path, mount_path)
    tool_id = create_tool(
        tool_name=tool_name,
        tool_type="code-interpreter",
        storage_mounts=storage_mounts,
        role_arn=role_arn,
    )

    try:
        # Instance A — write
        a_id = start_instance(tool_id=tool_id, timeout=timeout)
        try:
            token_a = acquire_token(a_id)  # noqa: F841 — kept for observability
            # Connect the *existing* instance via SandboxSession-like plumbing:
            # here we just use a code-exec approach via a throwaway sandbox.
            # For simplicity, we run the write as a shell command through a
            # brand-new SandboxSession whose underlying instance is `a_id`.
            # BUT SandboxSession() always starts its own instance — we don't
            # want that. Do a direct data-plane call via the e2b SDK:
            from packaging.version import Version
            from e2b.connection_config import ConnectionConfig
            from e2b_code_interpreter import Sandbox as _SB
            from ags_client import sandbox_host_suffix
            cfg = ConnectionConfig(
                domain=sandbox_host_suffix(),
                access_token=token_a,
                extra_sandbox_headers={"X-Access-Token": token_a},
            )
            sbx_a = _SB(
                sandbox_id=a_id,
                envd_version=Version("0.1.0"),
                envd_access_token=token_a,
                sandbox_domain=sandbox_host_suffix(),
                connection_config=cfg,
            )
            write_path = f"{mount_path.rstrip('/')}/shared.txt"
            sbx_a.files.write(write_path, content)
            log.info("instance A wrote %d bytes → %s", len(content), write_path)
        finally:
            stop_instance(a_id)

        # Instance B — read
        b_id = start_instance(tool_id=tool_id, timeout=timeout)
        try:
            token_b = acquire_token(b_id)
            from packaging.version import Version
            from e2b.connection_config import ConnectionConfig
            from e2b_code_interpreter import Sandbox as _SB
            from ags_client import sandbox_host_suffix
            cfg = ConnectionConfig(
                domain=sandbox_host_suffix(),
                access_token=token_b,
                extra_sandbox_headers={"X-Access-Token": token_b},
            )
            sbx_b = _SB(
                sandbox_id=b_id,
                envd_version=Version("0.1.0"),
                envd_access_token=token_b,
                sandbox_domain=sandbox_host_suffix(),
                connection_config=cfg,
            )
            read_path = f"{mount_path.rstrip('/')}/shared.txt"
            retrieved = sbx_b.files.read(read_path)
        finally:
            stop_instance(b_id)

        return {
            "tool_id": tool_id,
            "written_in": a_id,
            "read_from": b_id,
            "expected": content,
            "retrieved": retrieved,
            "match": retrieved == content,
            "round_trip_bytes": len(retrieved),
        }
    finally:
        try:
            delete_tool(tool_id)
        except Exception as e:  # noqa: BLE001
            log.error("delete_tool failed: %s", e)


# ---------------------------------------------------------------------------
# Skill: stop_cos_sandbox
# ---------------------------------------------------------------------------

def stop_cos_sandbox(
    instance_id: str,
    tool_id: str | None = None,
    delete_tool_after: bool = False,
) -> dict:
    """Stop ``instance_id`` and optionally delete the owning tool."""
    if credential_mode() != "aksk":
        raise RuntimeError("stop_cos_sandbox requires AKSK mode")

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
        raise SystemExit("skill-cos-sandbox requires AKSK mode.")

    bucket = os.environ.get("AGS_DEMO_COS_BUCKET")
    path = os.environ.get("AGS_DEMO_COS_PATH", "skills-demo/")
    mount = os.environ.get("AGS_DEMO_COS_MOUNT", "/mnt/cos")

    if not bucket:
        raise SystemExit(
            "Please set AGS_DEMO_COS_BUCKET (e.g. 'my-bucket-1300000000'). "
            "Also ensure AGS_ROLE_ARN grants read/write on the bucket/path."
        )

    log.info("=== Demo: write in instance A, read in instance B via COS mount ===")
    out = write_then_read_across_instances(
        cos_bucket=bucket,
        cos_path=path,
        mount_path=mount,
        content=f"cross-instance @ {uuid.uuid4().hex}",
    )
    print("\n=== Skill Result: write_then_read_across_instances ===")
    print(json.dumps(out, indent=2, ensure_ascii=False))
