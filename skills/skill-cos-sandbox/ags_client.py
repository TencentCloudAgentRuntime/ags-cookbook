"""
ags_client.py — shared AGS client helpers with automatic credential detection.

This module is the single source of truth for creating AGS sandboxes across all
Skills examples.  It auto-detects which authentication mode is active at runtime:

  * If ``TENCENTCLOUD_SECRET_ID`` / ``TENCENTCLOUD_SECRET_KEY`` are set →
    **AKSK mode**: sandbox lifecycle is managed through the Tencent Cloud AGS
    control plane (``StartSandboxInstance`` → ``AcquireSandboxInstanceToken`` →
    ``StopSandboxInstance``).

  * Otherwise, if ``E2B_API_KEY`` / ``E2B_DOMAIN`` are set →
    **APIKey mode**: sandbox is created directly via ``e2b-code-interpreter``
    without going through the control plane.

Skills depend on a single pair of context managers:

  * :class:`SandboxSession` — yields a connected ``e2b_code_interpreter.Sandbox``
    for code / filesystem operations.
  * :class:`BrowserSandboxSession` — yields ``(instance_id, token, region)`` so
    callers can build their own CDP / VNC URLs.

And, for AKSK-only control-plane operations (Pause/Resume/List/Describe,
custom-image instance creation, mount options, AuthMode, etc.), the thin
wrappers in :mod:`ags_client` directly call AGS APIs without a session.

Every Skill directory carries an identical copy of this file.  The canonical
source lives at ``skills/ags_client.py``; per-skill copies exist so ``uv``
projects remain self-contained.

Public API
----------

``credential_mode()``        → ``"aksk"`` or ``"apikey"``
``make_ags_client()``        → ``tencentcloud.ags.v20250920.ags_client.AgsClient``
``SandboxSession(...)``      → context manager yielding ``Sandbox``
``BrowserSandboxSession(...)`` → context manager yielding ``(instance_id, token, region)``

Control-plane helpers (all AKSK-only, raise if called under APIKey mode):

``pause_instance(instance_id, mode=None)``
``resume_instance(instance_id)``
``stop_instance(instance_id)``
``describe_instances(instance_ids=None, tool_id=None, tool_name=None)``
``get_instance_status(instance_id)``
``start_instance(tool_name=None, tool_id=None, timeout="10m", auth_mode=None,
                 auto_pause=False, auto_resume=False, mount_options=None,
                 custom_configuration=None, role_arn=None)``
``acquire_token(instance_id)``
``create_tool(tool_name, tool_type="code-interpreter", network_mode="PUBLIC",
              custom_configuration=None, storage_mounts=None, role_arn=None,
              description=None, default_timeout="10m")``
``delete_tool(tool_id)``

Data-plane URL helpers:

``sandbox_host_suffix()``    → ``"{region}.tencentags.com"`` (auto-detected)
``build_port_url(instance_id, port, path="/")`` → ``https://{port}-{id}.{suffix}/{path}``
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# credential-mode detection
# ---------------------------------------------------------------------------

_AGS_ENDPOINT = "ags.tencentcloudapi.com"


def credential_mode() -> str:
    """Return ``"aksk"`` if AKSK env vars are set, else ``"apikey"``.

    The check is purely environment-based; no network calls are made.
    """
    if os.environ.get("TENCENTCLOUD_SECRET_ID") and os.environ.get("TENCENTCLOUD_SECRET_KEY"):
        return "aksk"
    return "apikey"


# ---------------------------------------------------------------------------
# AKSK control-plane client
# ---------------------------------------------------------------------------

def make_ags_client():
    """Build an ``AgsClient`` from ``TENCENTCLOUD_*`` environment variables.

    Raises ``KeyError`` if AKSK env vars are not present.
    """
    from tencentcloud.common import credential
    from tencentcloud.common.profile.client_profile import ClientProfile
    from tencentcloud.common.profile.http_profile import HttpProfile
    from tencentcloud.ags.v20250920 import ags_client as _ags_client

    secret_id = os.environ["TENCENTCLOUD_SECRET_ID"]
    secret_key = os.environ["TENCENTCLOUD_SECRET_KEY"]
    region = os.environ.get("TENCENTCLOUD_REGION", "ap-guangzhou")

    cred = credential.Credential(secret_id, secret_key)
    hp = HttpProfile()
    hp.endpoint = _AGS_ENDPOINT
    cp = ClientProfile()
    cp.httpProfile = hp
    return _ags_client.AgsClient(cred, region, cp)


# ---------------------------------------------------------------------------
# SandboxSession — for code sandboxes (yields a connected Sandbox)
# ---------------------------------------------------------------------------

@dataclass
class SandboxSession:
    """Start an AGS code-sandbox instance, yield a connected ``Sandbox``, then stop it.

    Usage::

        with SandboxSession(tool_name="code-interpreter-v1", timeout="10m") as sbx:
            result = sbx.run_code("print(42)")

    The underlying instance is released on exit regardless of whether the block
    raises.  The release path depends on the active credential mode:

    * AKSK mode → ``StopSandboxInstance`` is called via the control plane.
      ``Sandbox.kill()`` is intentionally NOT called because it requires
      ``E2B_API_KEY``; lifecycle is owned by the control plane.
    * APIKey mode → ``Sandbox.kill()`` is called.

    Parameters
    ----------
    tool_name:
        AGS sandbox template / tool name (e.g. ``"code-interpreter-v1"``).
    timeout:
        AKSK mode uses a human-readable duration (``"10m"``).  APIKey mode
        converts it to seconds; minimum ``300`` is enforced by the server.
    """

    tool_name: str = "code-interpreter-v1"
    timeout: str = "10m"
    _mode: str = field(default="", init=False, repr=False)
    _client: object | None = field(default=None, init=False, repr=False)
    _instance_id: str | None = field(default=None, init=False, repr=False)
    _sbx: object | None = field(default=None, init=False, repr=False)

    def __enter__(self):
        self._mode = credential_mode()
        log.info("SandboxSession: mode=%s tool=%s timeout=%s",
                 self._mode, self.tool_name, self.timeout)

        if self._mode == "aksk":
            return self._enter_aksk()
        return self._enter_apikey()

    # -- AKSK path --------------------------------------------------------

    def _enter_aksk(self):
        from packaging.version import Version
        from tencentcloud.ags.v20250920 import models as ags_models
        from e2b.connection_config import ConnectionConfig
        from e2b_code_interpreter import Sandbox

        self._client = make_ags_client()
        region = os.environ.get("TENCENTCLOUD_REGION", "ap-guangzhou")

        # 1. Start instance
        req = ags_models.StartSandboxInstanceRequest()
        req.ToolName = self.tool_name
        req.Timeout = self.timeout
        resp = self._client.StartSandboxInstance(req)
        self._instance_id = resp.Instance.InstanceId
        log.info("AKSK sandbox started: %s", self._instance_id)

        # 2. Acquire access token
        treq = ags_models.AcquireSandboxInstanceTokenRequest()
        treq.InstanceId = self._instance_id
        tresp = self._client.AcquireSandboxInstanceToken(treq)
        token: str = tresp.Token

        # 3. Connect data plane
        sandbox_domain = f"{region}.tencentags.com"
        cfg = ConnectionConfig(
            domain=sandbox_domain,
            access_token=token,
            extra_sandbox_headers={"X-Access-Token": token},
        )
        # e2b-code-interpreter requires an envd version for an existing sandbox;
        # any semver value is accepted — the real version is managed server-side.
        self._sbx = Sandbox(
            sandbox_id=self._instance_id,
            envd_version=Version("0.1.0"),
            envd_access_token=token,
            sandbox_domain=sandbox_domain,
            connection_config=cfg,
        )
        log.info("AKSK data plane connected (domain=%s).", sandbox_domain)
        return self._sbx

    # -- APIKey path ------------------------------------------------------

    def _enter_apikey(self):
        from e2b_code_interpreter import Sandbox

        # e2b wants seconds; server minimum is 300s.
        timeout_s = _parse_duration_seconds(self.timeout, minimum=300)
        self._sbx = Sandbox.create(template=self.tool_name, timeout=timeout_s)
        log.info("APIKey sandbox created (template=%s, timeout=%ds).",
                 self.tool_name, timeout_s)
        return self._sbx

    # -- cleanup ----------------------------------------------------------

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        try:
            if self._mode == "aksk" and self._instance_id and self._client is not None:
                from tencentcloud.ags.v20250920 import models as ags_models
                from tencentcloud.common.exception.tencent_cloud_sdk_exception import (
                    TencentCloudSDKException,
                )
                try:
                    sreq = ags_models.StopSandboxInstanceRequest()
                    sreq.InstanceId = self._instance_id
                    self._client.StopSandboxInstance(sreq)
                    log.info("AKSK sandbox stopped: %s", self._instance_id)
                except TencentCloudSDKException as e:
                    log.error("Failed to stop AKSK sandbox %s: %s", self._instance_id, e)
            elif self._mode == "apikey" and self._sbx is not None:
                try:
                    self._sbx.kill()
                    log.info("APIKey sandbox killed.")
                except Exception as e:  # noqa: BLE001
                    log.error("Failed to kill APIKey sandbox: %s", e)
        finally:
            self._sbx = None
            self._client = None
            self._instance_id = None
        return False  # do not suppress exceptions


# ---------------------------------------------------------------------------
# BrowserSandboxSession — yields (instance_id, token, region) for CDP / VNC
# ---------------------------------------------------------------------------

@dataclass
class BrowserSandboxSession:
    """Start a browser sandbox, yield ``(instance_id, token, region)``, then stop it.

    Callers construct their own CDP / VNC / NoVNC URLs from the tuple.  In
    APIKey mode, ``region`` is derived from ``E2B_DOMAIN`` (e.g.
    ``"ap-guangzhou.tencentags.com"`` → ``"ap-guangzhou"``).

    Usage::

        with BrowserSandboxSession(tool_name="browser-v1", timeout="10m") as (iid, tok, rgn):
            cdp_url = f"https://9000-{iid}.{rgn}.tencentags.com/cdp"
            ...

    In APIKey mode the instance is released via ``Sandbox.kill()``; in AKSK
    mode via ``StopSandboxInstance``.
    """

    tool_name: str = "browser-v1"
    timeout: str = "10m"
    _mode: str = field(default="", init=False, repr=False)
    _client: object | None = field(default=None, init=False, repr=False)
    _instance_id: str | None = field(default=None, init=False, repr=False)
    _e2b_sbx: object | None = field(default=None, init=False, repr=False)

    def __enter__(self) -> tuple[str, str, str]:
        self._mode = credential_mode()
        log.info("BrowserSandboxSession: mode=%s tool=%s timeout=%s",
                 self._mode, self.tool_name, self.timeout)

        if self._mode == "aksk":
            return self._enter_aksk()
        return self._enter_apikey()

    def _enter_aksk(self) -> tuple[str, str, str]:
        from tencentcloud.ags.v20250920 import models as ags_models

        self._client = make_ags_client()
        region = os.environ.get("TENCENTCLOUD_REGION", "ap-guangzhou")

        req = ags_models.StartSandboxInstanceRequest()
        req.ToolName = self.tool_name
        req.Timeout = self.timeout
        resp = self._client.StartSandboxInstance(req)
        self._instance_id = resp.Instance.InstanceId
        log.info("AKSK browser sandbox started: %s", self._instance_id)

        treq = ags_models.AcquireSandboxInstanceTokenRequest()
        treq.InstanceId = self._instance_id
        tresp = self._client.AcquireSandboxInstanceToken(treq)
        token: str = tresp.Token

        return self._instance_id, token, region

    def _enter_apikey(self) -> tuple[str, str, str]:
        from e2b import Sandbox as _ESandbox

        timeout_s = _parse_duration_seconds(self.timeout, minimum=300)
        self._e2b_sbx = _ESandbox.create(template=self.tool_name, timeout=timeout_s)
        self._instance_id = self._e2b_sbx.sandbox_id
        token = str(self._e2b_sbx._envd_access_token)

        # derive region from E2B_DOMAIN ("ap-guangzhou.tencentags.com" → "ap-guangzhou")
        domain = os.environ.get("E2B_DOMAIN", "")
        region = domain.split(".", 1)[0] if domain else "ap-guangzhou"

        log.info("APIKey browser sandbox created: %s (region=%s)",
                 self._instance_id, region)
        return self._instance_id, token, region

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        try:
            if self._mode == "aksk" and self._instance_id and self._client is not None:
                from tencentcloud.ags.v20250920 import models as ags_models
                from tencentcloud.common.exception.tencent_cloud_sdk_exception import (
                    TencentCloudSDKException,
                )
                try:
                    sreq = ags_models.StopSandboxInstanceRequest()
                    sreq.InstanceId = self._instance_id
                    self._client.StopSandboxInstance(sreq)
                    log.info("AKSK browser sandbox stopped: %s", self._instance_id)
                except TencentCloudSDKException as e:
                    log.error("Failed to stop AKSK browser sandbox %s: %s",
                              self._instance_id, e)
            elif self._mode == "apikey" and self._e2b_sbx is not None:
                try:
                    self._e2b_sbx.kill()
                    log.info("APIKey browser sandbox killed.")
                except Exception as e:  # noqa: BLE001
                    log.error("Failed to kill APIKey browser sandbox: %s", e)
        finally:
            self._e2b_sbx = None
            self._client = None
            self._instance_id = None
        return False


# ---------------------------------------------------------------------------
# duration parsing helper
# ---------------------------------------------------------------------------

def _parse_duration_seconds(value: str | int | float, minimum: int = 0) -> int:
    """Parse a duration string like ``"10m"`` / ``"30s"`` / ``"1h"`` into seconds.

    Plain ``int`` / ``float`` / digit strings are treated as seconds.  The
    result is clamped to ``minimum`` if smaller.
    """
    if isinstance(value, (int, float)):
        return max(int(value), minimum)

    s = str(value).strip().lower()
    if s.isdigit():
        return max(int(s), minimum)

    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    if s and s[-1] in units and s[:-1].isdigit():
        return max(int(s[:-1]) * units[s[-1]], minimum)

    raise ValueError(f"Unparseable duration: {value!r}")


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def sandbox_host_suffix() -> str:
    """Return ``"{region}.tencentags.com"`` for data-plane URL construction.

    The region is derived from (in order):
      1. ``TENCENTCLOUD_REGION``
      2. the first dot-segment of ``E2B_DOMAIN``
      3. ``"ap-guangzhou"`` as fallback.
    """
    region = os.environ.get("TENCENTCLOUD_REGION")
    if region:
        return f"{region}.tencentags.com"

    domain = os.environ.get("E2B_DOMAIN")
    if domain:
        return domain  # already in "<region>.tencentags.com" form

    return "ap-guangzhou.tencentags.com"


def build_port_url(instance_id: str, port: int, path: str = "/") -> str:
    """Build ``https://{port}-{instance_id}.{suffix}/{path}`` for an exposed port.

    The returned URL still requires the ``X-Access-Token`` header for
    authenticated endpoints; the token must be obtained separately via
    :class:`SandboxSession` / :class:`BrowserSandboxSession` or
    :func:`acquire_token`.
    """
    p = path.lstrip("/")
    return f"https://{port}-{instance_id}.{sandbox_host_suffix()}/{p}"


# ---------------------------------------------------------------------------
# AKSK-only control-plane helpers
# ---------------------------------------------------------------------------

def _require_aksk(fn_name: str) -> None:
    if credential_mode() != "aksk":
        raise RuntimeError(
            f"{fn_name}() requires AKSK mode "
            "(set TENCENTCLOUD_SECRET_ID / TENCENTCLOUD_SECRET_KEY)."
        )


def _set_if(obj: Any, name: str, value: Any) -> None:
    """Set attribute ``name`` on ``obj`` only if ``value`` is not None/empty."""
    if value is None:
        return
    if isinstance(value, (str, list, dict)) and len(value) == 0:
        return
    setattr(obj, name, value)


def pause_instance(instance_id: str, mode: str | None = None) -> None:
    """Call ``PauseSandboxInstance``. ``mode`` ∈ ``{"Full", "Disk", None}``."""
    _require_aksk("pause_instance")
    from tencentcloud.ags.v20250920 import models as ags_models

    req = ags_models.PauseSandboxInstanceRequest()
    req.InstanceId = instance_id
    if mode:
        req.Mode = mode
    make_ags_client().PauseSandboxInstance(req)
    log.info("PauseSandboxInstance OK: %s (mode=%s)", instance_id, mode or "default")


def resume_instance(instance_id: str) -> None:
    """Call ``ResumeSandboxInstance``."""
    _require_aksk("resume_instance")
    from tencentcloud.ags.v20250920 import models as ags_models

    req = ags_models.ResumeSandboxInstanceRequest()
    req.InstanceId = instance_id
    make_ags_client().ResumeSandboxInstance(req)
    log.info("ResumeSandboxInstance OK: %s", instance_id)


def stop_instance(instance_id: str) -> None:
    """Call ``StopSandboxInstance``."""
    _require_aksk("stop_instance")
    from tencentcloud.ags.v20250920 import models as ags_models

    req = ags_models.StopSandboxInstanceRequest()
    req.InstanceId = instance_id
    make_ags_client().StopSandboxInstance(req)
    log.info("StopSandboxInstance OK: %s", instance_id)


def acquire_token(instance_id: str) -> str:
    """Call ``AcquireSandboxInstanceToken`` and return the access token string."""
    _require_aksk("acquire_token")
    from tencentcloud.ags.v20250920 import models as ags_models

    req = ags_models.AcquireSandboxInstanceTokenRequest()
    req.InstanceId = instance_id
    resp = make_ags_client().AcquireSandboxInstanceToken(req)
    return resp.Token


def describe_instances(
    instance_ids: list[str] | None = None,
    tool_id: str | None = None,
    tool_name: str | None = None,
) -> list[dict]:
    """Call ``DescribeSandboxInstanceList`` and return instances as plain dicts.

    Each dict carries at minimum ``InstanceId``, ``ToolName`` / ``ToolId`` and
    ``Status`` (``Starting`` / ``Running`` / ``Pausing`` / ``Paused`` /
    ``Resuming`` / ``Stopped`` / ``Failed``). Exact fields depend on the AGS
    API version.
    """
    _require_aksk("describe_instances")
    from tencentcloud.ags.v20250920 import models as ags_models

    req = ags_models.DescribeSandboxInstanceListRequest()
    _set_if(req, "InstanceIds", instance_ids)
    _set_if(req, "ToolId", tool_id)
    _set_if(req, "ToolName", tool_name)

    resp = make_ags_client().DescribeSandboxInstanceList(req)

    instances = getattr(resp, "Instances", None) or []
    out: list[dict] = []
    for inst in instances:
        # SDK models support `_serialize()`; fall back to __dict__.
        if hasattr(inst, "_serialize"):
            try:
                out.append(inst._serialize())  # type: ignore[attr-defined]
                continue
            except Exception:  # noqa: BLE001
                pass
        out.append({k: v for k, v in vars(inst).items() if not k.startswith("_")})
    return out


def get_instance_status(instance_id: str) -> str:
    """Return the ``Status`` string for ``instance_id``, or ``""`` if not found."""
    _require_aksk("get_instance_status")
    items = describe_instances(instance_ids=[instance_id])
    if not items:
        return ""
    return items[0].get("Status", "") or items[0].get("status", "")


def start_instance(
    tool_name: str | None = None,
    tool_id: str | None = None,
    timeout: str = "10m",
    auth_mode: str | None = None,
    auto_pause: bool = False,
    auto_resume: bool = False,
    mount_options: list[dict] | None = None,
    custom_configuration: dict | None = None,
    role_arn: str | None = None,
) -> str:
    """Call ``StartSandboxInstance`` with the given options; return ``InstanceId``.

    Exactly one of ``tool_name`` or ``tool_id`` must be provided.  ``auth_mode``
    is one of ``{"DEFAULT", "TOKEN", "NONE"}``.
    """
    _require_aksk("start_instance")
    if not tool_name and not tool_id:
        raise ValueError("start_instance: either tool_name or tool_id is required")

    from tencentcloud.ags.v20250920 import models as ags_models

    req = ags_models.StartSandboxInstanceRequest()
    _set_if(req, "ToolName", tool_name)
    _set_if(req, "ToolId", tool_id)
    _set_if(req, "Timeout", timeout)
    _set_if(req, "AuthMode", auth_mode)
    if auto_pause:
        req.AutoPause = True
    if auto_resume:
        req.AutoResume = True
    _set_if(req, "MountOptions", mount_options)
    _set_if(req, "CustomConfiguration", custom_configuration)
    _set_if(req, "RoleArn", role_arn)

    resp = make_ags_client().StartSandboxInstance(req)
    instance_id = resp.Instance.InstanceId
    log.info("StartSandboxInstance OK: %s", instance_id)
    return instance_id


def create_tool(
    tool_name: str,
    tool_type: str = "code-interpreter",
    network_mode: str = "PUBLIC",
    custom_configuration: dict | None = None,
    storage_mounts: list[dict] | None = None,
    role_arn: str | None = None,
    description: str | None = None,
    default_timeout: str = "10m",
) -> str:
    """Call ``CreateSandboxTool`` and return the new ``ToolId``.

    For ``tool_type="custom"`` you must provide both ``custom_configuration``
    and ``role_arn`` (per AGS validation; see e2e/basic/custom tests).
    """
    _require_aksk("create_tool")
    from tencentcloud.ags.v20250920 import models as ags_models

    req = ags_models.CreateSandboxToolRequest()
    req.ToolName = tool_name
    req.ToolType = tool_type

    nc = ags_models.NetworkConfiguration()
    nc.NetworkMode = network_mode
    req.NetworkConfiguration = nc

    _set_if(req, "Description", description)
    _set_if(req, "DefaultTimeout", default_timeout)
    _set_if(req, "RoleArn", role_arn)
    _set_if(req, "CustomConfiguration", custom_configuration)
    _set_if(req, "StorageMounts", storage_mounts)

    resp = make_ags_client().CreateSandboxTool(req)
    tool_id = resp.ToolId
    log.info("CreateSandboxTool OK: %s (name=%s)", tool_id, tool_name)
    return tool_id


def delete_tool(tool_id: str) -> None:
    """Call ``DeleteSandboxTool``."""
    _require_aksk("delete_tool")
    from tencentcloud.ags.v20250920 import models as ags_models

    req = ags_models.DeleteSandboxToolRequest()
    req.ToolId = tool_id
    make_ags_client().DeleteSandboxTool(req)
    log.info("DeleteSandboxTool OK: %s", tool_id)

