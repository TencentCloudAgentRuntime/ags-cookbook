#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path

from tencentcloud.ags.v20250920 import ags_client, models
from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".state"


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def client() -> ags_client.AgsClient | None:
    sid = os.getenv("TENCENTCLOUD_SECRET_ID")
    skey = os.getenv("TENCENTCLOUD_SECRET_KEY")
    if not sid or not skey:
        return None
    http_profile = HttpProfile()
    http_profile.endpoint = os.getenv("AGS_CLOUD_ENDPOINT", "ags.tencentcloudapi.com")
    profile = ClientProfile()
    profile.httpProfile = http_profile
    return ags_client.AgsClient(
        credential.Credential(sid, skey),
        os.getenv("TENCENTCLOUD_REGION", "ap-guangzhou"),
        profile,
    )


def main() -> int:
    c = client()
    if c is None:
        print("Tencent Cloud credentials are not set; skip AGS cleanup")
        return 0

    instance_id = os.getenv("INSTANCE_ID") or read(STATE / "instance_id")
    if instance_id:
        req = models.StopSandboxInstanceRequest()
        req.InstanceId = instance_id
        try:
            c.StopSandboxInstance(req)
            print(f"Instance stopped: {instance_id}")
        except Exception as exc:
            print(f"failed to stop instance {instance_id}: {exc}")

    if os.getenv("DELETE_TOOL", "0").lower() in {"1", "true", "yes", "on"}:
        tool_id = os.getenv("TOOL_ID") or read(STATE / "tool_id")
        if tool_id:
            req = models.DeleteSandboxToolRequest()
            req.ToolId = tool_id
            try:
                c.DeleteSandboxTool(req)
                print(f"Tool deleted: {tool_id}")
            except Exception as exc:
                print(f"failed to delete tool {tool_id}: {exc}")

    print("CLEANUP_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
