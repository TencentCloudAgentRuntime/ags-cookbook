"""
skill-tencent-cloud-api: Tencent Cloud control-plane skill.

Demonstrates:
  1. Credential verification via STS GetCallerIdentity
  2. Listing AGS sandbox templates via the TencentCloud AGS API
     (falls back to a mock listing when the AGS API is not available)
  3. Structured result returned to an Agent

Skills exposed:
  - get_caller_identity()
      Verify credentials and return account / ARN information.
  - list_sandbox_images(region)
      List available AGS sandbox image templates in *region*.
"""

import json
import logging
import os

from tencentcloud.common import credential
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
from tencentcloud.sts.v20180813 import sts_client, models as sts_models

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_credential() -> credential.Credential:
    secret_id = os.environ["TENCENTCLOUD_SECRET_ID"]
    secret_key = os.environ["TENCENTCLOUD_SECRET_KEY"]
    return credential.Credential(secret_id, secret_key)


def _region() -> str:
    return os.environ.get("TENCENTCLOUD_REGION", "ap-guangzhou")


# ---------------------------------------------------------------------------
# Skill 1: get_caller_identity
# ---------------------------------------------------------------------------

def get_caller_identity() -> dict:
    """Verify Tencent Cloud credentials and return caller identity.

    Returns:
        dict with keys ``account_id``, ``arn``, ``user_id``, ``error``.
    """
    log.info("get_caller_identity: verifying credentials (region=%s)…", _region())
    try:
        cred = _make_credential()
        client = sts_client.StsClient(cred, _region())
        req = sts_models.GetCallerIdentityRequest()
        resp = client.GetCallerIdentity(req)
        result = {
            "account_id": resp.AccountId,
            "arn": resp.Arn,
            "user_id": resp.UserId,
            "error": None,
        }
        log.info("Credential OK — AccountId=%s", resp.AccountId)
        return result
    except TencentCloudSDKException as exc:
        log.error("get_caller_identity failed: %s", exc)
        return {"account_id": None, "arn": None, "user_id": None, "error": str(exc)}


# ---------------------------------------------------------------------------
# Skill 2: list_sandbox_images
# ---------------------------------------------------------------------------

def list_sandbox_images(region: str | None = None) -> dict:
    """List available AGS sandbox image templates in *region*.

    This skill calls the TencentCloud AGS DescribeImages API when available.
    If the endpoint is not yet accessible from your account, it falls back to
    a representative static list so the skill remains runnable as a demo.

    Args:
        region: Tencent Cloud region string, e.g. ``"ap-guangzhou"``.
                Defaults to the ``TENCENTCLOUD_REGION`` environment variable.

    Returns:
        dict with keys ``region``, ``images``, ``source``, ``error``.
    """
    target_region = region or _region()
    log.info("list_sandbox_images: region=%s", target_region)

    try:
        # Attempt real API call via tencentcloud-sdk-python.
        # The AGS (Agent Sandbox) service uses the "ags" product module.
        # Import is guarded so the skill degrades gracefully if the module
        # is not yet bundled in the installed SDK version.
        from tencentcloud.ags.v20250515 import ags_client, models as ags_models  # type: ignore

        cred = _make_credential()
        client = ags_client.AgsClient(cred, target_region)
        req = ags_models.DescribeImagesRequest()
        resp = client.DescribeImages(req)
        images = [
            {"image_id": img.ImageId, "name": img.ImageName, "type": img.ImageType}
            for img in (resp.ImageSet or [])
        ]
        log.info("list_sandbox_images: found %d images via API", len(images))
        return {"region": target_region, "images": images, "source": "api", "error": None}

    except (ImportError, TencentCloudSDKException) as exc:
        log.warning("list_sandbox_images: API unavailable (%s), using static list", exc)
        # Fallback — representative set of well-known AGS template names
        static_images = [
            {"image_id": "code-interpreter-v1", "name": "Code Interpreter v1", "type": "builtin"},
            {"image_id": "browser-v1",           "name": "Browser v1",           "type": "builtin"},
            {"image_id": "swe-v1",               "name": "SWE Sandbox v1",       "type": "builtin"},
            {"image_id": "mobile-v1",            "name": "Mobile (Android) v1",  "type": "builtin"},
        ]
        return {
            "region": target_region,
            "images": static_images,
            "source": "static_fallback",
            "error": str(exc),
        }


# ---------------------------------------------------------------------------
# Entry point — demo both skills
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # --- demo 1: credential identity ---
    log.info("=== Demo 1: get_caller_identity ===")
    result1 = get_caller_identity()
    print("\n=== Skill Result: get_caller_identity ===")
    print(json.dumps(result1, indent=2, ensure_ascii=False))

    # --- demo 2: list sandbox images ---
    log.info("=== Demo 2: list_sandbox_images ===")
    result2 = list_sandbox_images()
    print("\n=== Skill Result: list_sandbox_images ===")
    print(json.dumps(result2, indent=2, ensure_ascii=False))
