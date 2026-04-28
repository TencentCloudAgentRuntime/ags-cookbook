"""
skills-hello-world: minimal Skills integration example.

Demonstrates:
  1. Tencent Cloud credential validation via tencentcloud-sdk-python
  2. Code execution inside an AGS sandbox via e2b-code-interpreter
  3. Returning a structured skill result back to an Agent
"""

import os
import json
import logging
from e2b_code_interpreter import Sandbox
from tencentcloud.common import credential
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
from tencentcloud.sts.v20180813 import sts_client, models as sts_models

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Skill: run_code
# A skill exposes a plain callable that an Agent can invoke as a tool.
# ---------------------------------------------------------------------------

def run_code(code: str) -> dict:
    """Execute *code* inside an AGS sandbox and return stdout/stderr."""
    api_key = os.environ["E2B_API_KEY"]
    domain = os.environ.get("E2B_DOMAIN", "ap-guangzhou.tencentags.com")

    log.info("Creating sandbox (domain=%s)…", domain)
    with Sandbox(api_key=api_key, domain=domain) as sbx:
        execution = sbx.run_code(code)
        result = {
            "stdout": "".join(r.text for r in execution.results if hasattr(r, "text")),
            "logs": {
                "stdout": execution.logs.stdout,
                "stderr": execution.logs.stderr,
            },
            "error": execution.error.value if execution.error else None,
        }
    log.info("Sandbox closed.")
    return result


# ---------------------------------------------------------------------------
# Helper: verify Tencent Cloud credentials (optional, used as a health-check)
# ---------------------------------------------------------------------------

def verify_credentials() -> bool:
    """Return True when TENCENTCLOUD_* credentials are valid."""
    secret_id = os.environ.get("TENCENTCLOUD_SECRET_ID", "")
    secret_key = os.environ.get("TENCENTCLOUD_SECRET_KEY", "")
    region = os.environ.get("TENCENTCLOUD_REGION", "ap-guangzhou")

    if not secret_id or not secret_key:
        log.warning("TENCENTCLOUD_SECRET_ID / SECRET_KEY not set; skipping credential check.")
        return False

    try:
        cred = credential.Credential(secret_id, secret_key)
        client = sts_client.StsClient(cred, region)
        req = sts_models.GetCallerIdentityRequest()
        resp = client.GetCallerIdentity(req)
        log.info("Credential OK — AccountId=%s", resp.AccountId)
        return True
    except TencentCloudSDKException as e:
        log.error("Credential check failed: %s", e)
        return False


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    verify_credentials()

    code_snippet = "result = 23 * 17 - 19\nprint(result)"
    log.info("Running skill: run_code")
    output = run_code(code_snippet)

    print("\n=== Skill Result ===")
    print(json.dumps(output, indent=2, ensure_ascii=False))
