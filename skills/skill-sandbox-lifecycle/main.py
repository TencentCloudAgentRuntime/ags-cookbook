"""
skill-sandbox-lifecycle: AKSK-only control-plane skill for sandbox lifecycle.

Demonstrates full lifecycle management of AGS sandbox instances via the Tencent
Cloud AGS control plane:

  * start an instance (StartSandboxInstance)
  * pause it  (PauseSandboxInstance, Full / Disk mode)
  * resume it (ResumeSandboxInstance)
  * query its status (DescribeSandboxInstanceList)
  * list all instances for a tool
  * stop it (StopSandboxInstance)

See :file:`e2e/basic/auto_pause_resume_test.go` and
:file:`e2e/framework/pause_resume.go` for the e2e reference flow.

> **AKSK-only.** This skill does not create a data-plane session and does not
> run user code; it directly exercises the control-plane APIs. If only
> ``E2B_API_KEY`` is set, every function raises ``RuntimeError``.

Skills exposed:
  - start_and_get_status(tool_name, timeout, auto_pause, auto_resume)
  - pause_and_resume(instance_id, mode="Full", wait_s=30)
  - list_instances(tool_name=None, tool_id=None)
  - get_instance_status(instance_id)
  - stop(instance_id)
"""

import json
import logging
import time
from typing import Any

from ags_client import (
    acquire_token,
    credential_mode,
    describe_instances,
    get_instance_status as _get_instance_status,
    pause_instance,
    resume_instance,
    start_instance,
    stop_instance,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Skill: start_and_get_status
# ---------------------------------------------------------------------------

def start_and_get_status(
    tool_name: str = "code-interpreter-v1",
    timeout: str = "10m",
    auto_pause: bool = False,
    auto_resume: bool = False,
) -> dict:
    """Start a new instance and return its id + status.

    ``auto_pause`` / ``auto_resume`` let the platform pause the instance on idle
    timeout and resume it on data-plane access.
    """
    if credential_mode() != "aksk":
        raise RuntimeError("start_and_get_status requires AKSK mode")

    instance_id = start_instance(
        tool_name=tool_name,
        timeout=timeout,
        auto_pause=auto_pause,
        auto_resume=auto_resume,
    )
    status = _get_instance_status(instance_id)
    return {
        "instance_id": instance_id,
        "status": status,
        "auto_pause": auto_pause,
        "auto_resume": auto_resume,
    }


# ---------------------------------------------------------------------------
# Skill: pause_and_resume
# ---------------------------------------------------------------------------

def pause_and_resume(
    instance_id: str,
    mode: str = "Full",
    wait_s: int = 60,
) -> dict:
    """Pause ``instance_id`` (in ``Full`` or ``Disk`` mode), wait for PAUSED,
    then resume and wait for RUNNING.  Returns the observed status transitions.

    ``wait_s`` caps how long we wait for each transition.
    """
    if credential_mode() != "aksk":
        raise RuntimeError("pause_and_resume requires AKSK mode")

    transitions: list[dict[str, Any]] = []

    def _wait_for(target: str) -> str:
        deadline = time.time() + wait_s
        last = ""
        while time.time() < deadline:
            last = _get_instance_status(instance_id)
            transitions.append({"t": round(time.time(), 2), "status": last})
            if last == target:
                return last
            time.sleep(1.0)
        return last

    # Step 1: pause
    pause_instance(instance_id, mode=mode)
    reached_paused = _wait_for("PAUSED")
    if reached_paused != "PAUSED":
        return {
            "instance_id": instance_id,
            "ok": False,
            "step": "pause",
            "last_status": reached_paused,
            "transitions": transitions,
        }

    # Step 2: resume
    resume_instance(instance_id)
    reached_running = _wait_for("RUNNING")

    return {
        "instance_id": instance_id,
        "ok": reached_running == "RUNNING",
        "pause_mode": mode,
        "last_status": reached_running,
        "transitions": transitions,
    }


# ---------------------------------------------------------------------------
# Skill: list_instances
# ---------------------------------------------------------------------------

def list_instances(
    tool_name: str | None = None,
    tool_id: str | None = None,
) -> dict:
    """Return ``{instances: [...], count}`` for the given filter.

    If both ``tool_name`` and ``tool_id`` are ``None``, all visible instances
    are returned.  Each entry is a dict mirroring the SDK model (``InstanceId``,
    ``ToolName``, ``Status``, ...).
    """
    if credential_mode() != "aksk":
        raise RuntimeError("list_instances requires AKSK mode")

    items = describe_instances(tool_name=tool_name, tool_id=tool_id)
    return {"instances": items, "count": len(items)}


# ---------------------------------------------------------------------------
# Skill: get_instance_status
# ---------------------------------------------------------------------------

def get_instance_status(instance_id: str) -> dict:
    """Return the current status of a single instance."""
    if credential_mode() != "aksk":
        raise RuntimeError("get_instance_status requires AKSK mode")
    return {"instance_id": instance_id, "status": _get_instance_status(instance_id)}


# ---------------------------------------------------------------------------
# Skill: stop
# ---------------------------------------------------------------------------

def stop(instance_id: str) -> dict:
    """Stop an instance and return the final status (usually ``""`` once gone)."""
    if credential_mode() != "aksk":
        raise RuntimeError("stop requires AKSK mode")
    stop_instance(instance_id)
    return {"instance_id": instance_id, "stopped": True}


# ---------------------------------------------------------------------------
# Entry point — full lifecycle demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if credential_mode() != "aksk":
        raise SystemExit(
            "skill-sandbox-lifecycle requires AKSK mode. "
            "Please export TENCENTCLOUD_SECRET_ID / TENCENTCLOUD_SECRET_KEY."
        )

    log.info("=== Demo: full lifecycle (start → status → pause → resume → stop) ===")
    started = start_and_get_status(auto_pause=True, auto_resume=True)
    print("\n=== Skill Result: start_and_get_status ===")
    print(json.dumps(started, indent=2, ensure_ascii=False))

    iid = started["instance_id"]
    try:
        pr = pause_and_resume(iid, mode="Full", wait_s=120)
        print("\n=== Skill Result: pause_and_resume ===")
        print(json.dumps(pr, indent=2, ensure_ascii=False))

        listing = list_instances()
        # Trim to first 5 for display.
        display = {"count": listing["count"], "first": listing["instances"][:5]}
        print("\n=== Skill Result: list_instances (truncated) ===")
        print(json.dumps(display, indent=2, ensure_ascii=False, default=str))
    finally:
        stopped = stop(iid)
        print("\n=== Skill Result: stop ===")
        print(json.dumps(stopped, indent=2, ensure_ascii=False))
