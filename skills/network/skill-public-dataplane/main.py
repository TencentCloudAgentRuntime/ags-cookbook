"""
skill-noauth-sandbox: start a sandbox that requires no X-Access-Token.

AGS supports three data-plane authentication modes (from ``StartSandboxInstance.AuthMode``):

  * ``DEFAULT`` / ``TOKEN`` — every data-plane request must carry
    ``X-Access-Token: <token>``.  This is the safe default.
  * ``NONE``    — no token required; ANY request to the data-plane URL gets
    through.  Suitable only for internal networks where the data plane is
    reachable exclusively by trusted callers (per ``basic/noauth_test.go``).

This skill starts an instance with ``AuthMode=NONE``, demonstrates accessing
the data plane with and without a token, and then stops the instance.

> **AKSK-only.** AuthMode is a control-plane parameter.

Skills exposed:
  - start_noauth(tool_name="code-interpreter-v1", timeout="10m")
  - probe_noauth(instance_id, path="/health")
  - stop_noauth(instance_id)
"""

import json
import logging

import httpx

from ags_client import (
    build_port_url,
    credential_mode,
    start_instance,
    stop_instance,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

_NGINX_PORT = 9000
_UVICORN_PORT = 49999


# ---------------------------------------------------------------------------
# Skill: start_noauth
# ---------------------------------------------------------------------------

def start_noauth(
    tool_name: str = "code-interpreter-v1",
    timeout: str = "10m",
) -> dict:
    """Start an instance with ``AuthMode=NONE``; return the base data-plane URLs."""
    if credential_mode() != "aksk":
        raise RuntimeError("start_noauth requires AKSK mode")

    instance_id = start_instance(
        tool_name=tool_name,
        timeout=timeout,
        auth_mode="NONE",
    )
    return {
        "instance_id": instance_id,
        "auth_mode": "NONE",
        "nginx_base": build_port_url(instance_id, _NGINX_PORT, "/"),
        "uvicorn_execute": build_port_url(instance_id, _UVICORN_PORT, "/execute"),
    }


# ---------------------------------------------------------------------------
# Skill: probe_noauth — demonstrate token-less access
# ---------------------------------------------------------------------------

def probe_noauth(
    instance_id: str,
    path: str = "/health",
    port: int = _NGINX_PORT,
) -> dict:
    """GET ``https://{port}-{instance_id}.<suffix>/{path}`` with AND without a token.

    When the instance was started with ``AuthMode=NONE`` both calls should
    return 200 (or whatever the upstream service returns); when started under
    ``TOKEN`` mode the no-token call should return 401/403.

    Returns ``{with_token, without_token, same_status}``.
    """
    if credential_mode() != "aksk":
        raise RuntimeError("probe_noauth requires AKSK mode")

    url = build_port_url(instance_id, port, path)
    from ags_client import acquire_token
    token = acquire_token(instance_id)
    with httpx.Client(timeout=30.0) as client:
        r_with = client.get(url, headers={"X-Access-Token": token})
        r_without = client.get(url)
    return {
        "url": url,
        "with_token": {"status": r_with.status_code, "body_head": r_with.text[:200]},
        "without_token": {"status": r_without.status_code, "body_head": r_without.text[:200]},
        "same_status": r_with.status_code == r_without.status_code,
        "token_required_for_access": r_with.status_code == 200 and r_without.status_code != 200,
    }


# ---------------------------------------------------------------------------
# Skill: stop_noauth
# ---------------------------------------------------------------------------

def stop_noauth(instance_id: str) -> dict:
    """Stop an instance started by :func:`start_noauth`."""
    if credential_mode() != "aksk":
        raise RuntimeError("stop_noauth requires AKSK mode")

    stop_instance(instance_id)
    return {"instance_id": instance_id, "stopped": True}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if credential_mode() != "aksk":
        raise SystemExit("skill-noauth-sandbox requires AKSK mode.")

    log.info("=== Demo: start AuthMode=NONE → probe with & without token → stop ===")
    started = start_noauth()
    print("\n=== Skill Result: start_noauth ===")
    print(json.dumps(started, indent=2, ensure_ascii=False))

    try:
        probed = probe_noauth(started["instance_id"], path="/health")
        print("\n=== Skill Result: probe_noauth ===")
        print(json.dumps(probed, indent=2, ensure_ascii=False))
    finally:
        stopped = stop_noauth(started["instance_id"])
        print("\n=== Skill Result: stop_noauth ===")
        print(json.dumps(stopped, indent=2, ensure_ascii=False))
