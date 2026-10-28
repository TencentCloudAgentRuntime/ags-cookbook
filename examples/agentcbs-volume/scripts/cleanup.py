#!/usr/bin/env python3
"""Delete everything run.py created: the Tool, all derived Volumes, and the template.

Deleting a Volume deletes its data.
"""

from __future__ import annotations

from typing import Any

from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException

from common import ags_client, call, derived_volumes, read_state, remove_state


def delete(client, action: str, params: dict[str, Any], label: str) -> None:
    try:
        call(client, action, params)
        print(f"{label} deleted")
    except TencentCloudSDKException as exc:
        if not (exc.code or "").startswith("ResourceNotFound"):
            raise
        print(f"{label} already deleted")


def main() -> int:
    tool_id = read_state("tool_id")
    template_id = read_state("volume_template_id")
    if not (tool_id or template_id):
        print("Nothing to clean up (.state/ is empty)")
        return 0

    client = ags_client()
    # Delete the Tool first so that no new sandbox derives Volumes from the template.
    if tool_id:
        delete(client, "DeleteSandboxTool", {"ToolId": tool_id}, f"Tool {tool_id}")
        remove_state("tool_id")

    if template_id:
        # ReclaimPolicy=Retain keeps derived Volumes after sandboxes stop, so
        # delete them explicitly before the template. A Volume that is still
        # mounted by a running sandbox fails with ResourceInUse.
        for volume in derived_volumes(client, template_id):
            delete(
                client,
                "DeleteVolume",
                {"VolumeId": volume["VolumeId"]},
                f"Volume {volume['VolumeId']} (reuse_key={volume.get('ReuseKey')})",
            )
        delete(
            client,
            "DeleteVolumeTemplate",
            {"VolumeTemplateId": template_id},
            f"VolumeTemplate {template_id}",
        )
        remove_state("volume_template_id")
        remove_state("volume_template_name")

    remove_state("region")
    print("CLEANUP_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
