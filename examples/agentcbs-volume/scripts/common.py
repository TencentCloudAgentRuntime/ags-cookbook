"""Shared helpers for the AgentCBS VolumeTemplate example.

The Volume control-plane actions (CreateVolumeTemplate, DescribeVolumeList, ...)
are called through the Tencent Cloud ``CommonClient``, so the example does not
depend on a ``tencentcloud-sdk-python-ags`` release that ships typed Volume models.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".state"


def load_dotenv(path: Path = ROOT / ".env") -> None:
    """Load KEY=VALUE lines from .env. Variables already set in the shell win."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.split(" #", 1)[0].strip().strip("\"'")  # drop inline comments
        os.environ.setdefault(key.strip(), value)


load_dotenv()

from tencentcloud.common import credential  # noqa: E402
from tencentcloud.common.common_client import CommonClient  # noqa: E402
from tencentcloud.common.profile.client_profile import ClientProfile  # noqa: E402
from tencentcloud.common.profile.http_profile import HttpProfile  # noqa: E402

AGS_API_VERSION = "2025-09-20"


def need(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value or value.startswith("your_") or "<" in value:
        raise SystemExit(f"{name} is not set; fill it in .env (see .env.example)")
    return value


def region() -> str:
    return os.getenv("TENCENTCLOUD_REGION", "").strip() or "ap-guangzhou"


def e2b_domain() -> str:
    return os.getenv("E2B_DOMAIN", "").strip() or f"{region()}.tencentags.com"


def ags_client() -> CommonClient:
    cred = credential.Credential(need("TENCENTCLOUD_SECRET_ID"), need("TENCENTCLOUD_SECRET_KEY"))
    http_profile = HttpProfile()
    http_profile.endpoint = "ags.tencentcloudapi.com"
    return CommonClient(
        "ags", AGS_API_VERSION, cred, region(), ClientProfile(httpProfile=http_profile)
    )


def call(client: CommonClient, action: str, params: dict[str, Any]) -> dict[str, Any]:
    return client.call_json(action, params)["Response"]


# IDs of the resources created by run.py, so later runs and cleanup reuse them.
def read_state(name: str) -> str:
    try:
        return (STATE / name).read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def write_state(name: str, value: str) -> None:
    if not STATE.is_dir():
        STATE.mkdir(parents=True)
    (STATE / name).write_text(value + "\n", encoding="utf-8")


def remove_state(name: str) -> None:
    (STATE / name).unlink(missing_ok=True)


def derived_volumes(client: CommonClient, template_id: str) -> list[dict[str, Any]]:
    """All Volumes that AGS derived from one VolumeTemplate."""
    volumes: list[dict[str, Any]] = []
    while True:
        resp = call(
            client,
            "DescribeVolumeList",
            {
                "Filters": [{"Name": "volume-template-id", "Values": [template_id]}],
                "Offset": len(volumes),
                "Limit": 100,
            },
        )
        page = resp.get("VolumeSet") or []
        volumes.extend(page)
        if not page or len(volumes) >= resp.get("TotalCount", 0):
            return volumes


def wait_active(label: str, status: Callable[[], str], timeout_seconds: int = 600) -> None:
    deadline = time.time() + timeout_seconds
    last = ""
    while time.time() < deadline:
        current = status() or "UNKNOWN"
        if current != last:
            print(f"{label} status: {current}", flush=True)
            last = current
        if current == "ACTIVE":
            return
        if current in {"FAILED", "DELETING", "DELETED"}:
            raise SystemExit(f"{label} entered {current}")
        time.sleep(3)
    raise SystemExit(f"{label} did not become ACTIVE within {timeout_seconds}s")
