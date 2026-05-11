"""
Multi-Tenant API Key CredentialProvider — Complete Demo

Demonstrates the end-to-end workflow for managing multi-tenant static API keys
through AGS CredentialProvider, covering all four phases:

  Phase 1: One-time setup
           CreateWorkloadIdentity + CreateCredentialProvider (API_KEY_MULTI_USER)

  Phase 2: Key management
           Set / List / Rotate API keys per user

  Phase 3: Runtime — WAT issuance
           CreateWorkloadAccessTokenForUserId

  Phase 4: Runtime — Agent retrieves API key
           GetAPIKeyFromCredentialProvider (WAT → plaintext API key)
"""

import json
import os
import random
import string
import sys

from dotenv import load_dotenv
from tencentcloud.common import credential
from tencentcloud.common.common_client import CommonClient
from tencentcloud.common.exception.tencent_cloud_sdk_exception import (
    TencentCloudSDKException,
)
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile


load_dotenv()

SECRET_ID = os.getenv("TENCENTCLOUD_SECRET_ID", "")
SECRET_KEY = os.getenv("TENCENTCLOUD_SECRET_KEY", "")
REGION = os.getenv("TENCENTCLOUD_REGION", "ap-guangzhou")
ENDPOINT = os.getenv("TENCENTCLOUD_ENDPOINT", "ags.tencentcloudapi.com")

if not SECRET_ID or not SECRET_KEY:
    print("ERROR: TENCENTCLOUD_SECRET_ID and TENCENTCLOUD_SECRET_KEY are required.")
    print("Copy .env.example to .env and fill in your credentials.")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Helper: Tencent Cloud API V3 common client
# ---------------------------------------------------------------------------

_API_VERSION = "2025-09-20"
_SERVICE = "ags"


def _random_suffix(n: int = 6) -> str:
    """Generate a short random suffix for resource names to avoid conflicts."""
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


def _build_client() -> CommonClient:
    """Return a CommonClient targeting the AGS credential endpoint."""
    cred = credential.Credential(SECRET_ID, SECRET_KEY)
    http_profile = HttpProfile()
    http_profile.endpoint = ENDPOINT
    client_profile = ClientProfile()
    client_profile.httpProfile = http_profile
    return CommonClient(_SERVICE, _API_VERSION, cred, REGION, profile=client_profile)


def call_api(action: str, params: dict) -> dict:
    """Call a cloud API action and return the Response dict."""
    client = _build_client()
    try:
        result = client.call_json(action, params)
        resp = json.loads(result) if isinstance(result, str) else result
        if "Response" in resp:
            if "Error" in resp["Response"]:
                err = resp["Response"]["Error"]
                print(f"  ERROR [{err['Code']}]: {err['Message']}")
                return resp["Response"]
            return resp["Response"]
        return resp
    except TencentCloudSDKException as e:
        print(f"  SDK Exception: {e}")
        return {}


# ===========================================================================
# Phase 1: One-time Setup
# ===========================================================================


def phase1_setup() -> tuple[str, str]:
    """Create WorkloadIdentity and CredentialProvider (API_KEY_MULTI_USER)."""
    print("=" * 60)
    print("Phase 1: One-time Setup")
    print("=" * 60)

    # Step 1: Create WorkloadIdentity
    suffix = _random_suffix()
    print("\n[1/2] Creating WorkloadIdentity...")
    wi_resp = call_api("CreateWorkloadIdentity", {
        "Name": f"multi-tenant-demo-{suffix}",
    })
    wi_id = wi_resp.get("WorkloadIdentityId", "")
    if wi_id:
        print(f"  Created WorkloadIdentity: {wi_id}")
    else:
        print("  Failed to create WorkloadIdentity")
        sys.exit(1)

    # Step 2: Create CredentialProvider (API_KEY_MULTI_USER)
    print("\n[2/2] Creating CredentialProvider (API_KEY_MULTI_USER)...")
    cp_resp = call_api("CreateCredentialProvider", {
        "Name": f"demo-customer-keys-{suffix}",
        "Type": "API_KEY_MULTI_USER",
        "Description": "Multi-tenant API keys for demo agent",
        "Config": [{"Key": "description", "Value": "per-user api keys"}],
    })
    cp_id = cp_resp.get("ProviderId", "")
    if cp_id:
        print(f"  Created CredentialProvider: {cp_id}")
    else:
        print("  Failed to create CredentialProvider")
        sys.exit(1)

    print(f"\n  Record these IDs for later use:")
    print(f"    WorkloadIdentityId   = {wi_id}")
    print(f"    CredentialProviderId  = {cp_id}")
    return wi_id, cp_id


# ===========================================================================
# Phase 2: Key Management
# ===========================================================================


def phase2_manage_keys(cp_id: str):
    """Demonstrate setting, listing, and rotating API keys per user."""
    print("\n" + "=" * 60)
    print("Phase 2: Key Management")
    print("=" * 60)

    # Set API Key for customer-001
    print("\n[1/4] Setting API Key for customer-001...")
    call_api("SetAPIKeyToCredentialProvider", {
        "CredentialProviderId": cp_id,
        "UserId": "customer-001",
        "APIKey": "sk-demo-key-for-customer-001",
        "OverwriteAllowed": False,
    })
    print("  Done.")

    # Set API Key for customer-002
    print("\n[2/4] Setting API Key for customer-002...")
    call_api("SetAPIKeyToCredentialProvider", {
        "CredentialProviderId": cp_id,
        "UserId": "customer-002",
        "APIKey": "sk-demo-key-for-customer-002",
        "OverwriteAllowed": False,
    })
    print("  Done.")

    # List all API keys (masked)
    print("\n[3/4] Listing API Keys (masked)...")
    list_resp = call_api("DescribeCredentialProviderAPIKeyList", {
        "CredentialProviderId": cp_id,
        "Offset": 0,
        "Limit": 20,
    })
    total = list_resp.get("TotalCount", 0)
    keys = list_resp.get("APIKeySet", [])
    print(f"  TotalCount: {total}")
    for item in keys:
        print(
            f"    UserId={item['UserId']}  "
            f"MaskedKey={item['MaskedAPIKey']}  "
            f"CreatedAt={item['CreatedAt']}"
        )

    # Rotate: overwrite API Key for customer-001
    print("\n[4/4] Rotating API Key for customer-001 (OverwriteAllowed=true)...")
    call_api("SetAPIKeyToCredentialProvider", {
        "CredentialProviderId": cp_id,
        "UserId": "customer-001",
        "APIKey": "sk-rotated-key-for-customer-001",
        "OverwriteAllowed": True,
    })
    print("  Done. Next GetAPIKey call will return the new key.")


# ===========================================================================
# Phase 3: Runtime — WAT Issuance
# ===========================================================================


def phase3_issue_wat(wi_id: str, user_id: str) -> str:
    """Issue a Workload Access Token for the specified user."""
    print("\n" + "=" * 60)
    print(f"Phase 3: Issue WAT for user '{user_id}'")
    print("=" * 60)

    print("\n  Calling CreateWorkloadAccessTokenForUserId...")
    resp = call_api("CreateWorkloadAccessTokenForUserId", {
        "WorkloadIdentityId": wi_id,
        "UserId": user_id,
    })
    wat = resp.get("WorkloadAccessToken", "")
    if wat:
        print(f"  WAT issued (first 40 chars): {wat[:40]}...")
        print(f"  WAT length: {len(wat)} bytes")
    else:
        print("  Failed to issue WAT")
    return wat


# ===========================================================================
# Phase 4: Runtime — Agent Retrieves API Key
# ===========================================================================


def phase4_get_apikey(cp_id: str, wat: str) -> str:
    """
    Use the WAT to retrieve the plaintext API key.

    In production, this call is made by the Agent runtime using a
    least-privilege sub-account AKSK that only has GetAPIKey permission.
    The service extracts UserId from the WAT JWT claims, so the Agent
    cannot forge another user's identity.
    """
    print("\n" + "=" * 60)
    print("Phase 4: Agent Retrieves API Key via WAT")
    print("=" * 60)

    print("\n  Calling GetAPIKeyFromCredentialProvider...")
    resp = call_api("GetAPIKeyFromCredentialProvider", {
        "CredentialProviderId": cp_id,
        "WorkloadIdentityToken": wat,
    })
    api_key = resp.get("APIKey", "")
    if api_key:
        masked = api_key[:7] + "****" + api_key[-4:] if len(api_key) > 11 else "****"
        print(f"  Retrieved API Key (masked): {masked}")
    else:
        print("  Failed to retrieve API Key")
    return api_key


# ===========================================================================
# Main
# ===========================================================================


def main():
    print("Multi-Tenant API Key CredentialProvider — Complete Demo")
    print("=" * 60)
    print()
    print("This demo walks through 4 phases:")
    print("  1. One-time setup   (create WorkloadIdentity + CredentialProvider)")
    print("  2. Key management   (set / list / rotate API keys per user)")
    print("  3. WAT issuance     (create Workload Access Token for a user)")
    print("  4. Get API key      (Agent retrieves plaintext key via WAT)")
    print()

    # Phase 1
    wi_id, cp_id = phase1_setup()

    # Phase 2
    phase2_manage_keys(cp_id)

    # Phase 3
    wat = phase3_issue_wat(wi_id, "customer-001")
    if not wat:
        print("\nCannot proceed without a WAT. Exiting.")
        sys.exit(1)

    # Phase 4
    api_key = phase4_get_apikey(cp_id, wat)

    # Summary
    print("\n" + "=" * 60)
    print("Demo Complete")
    print("=" * 60)
    print()
    if api_key:
        masked = api_key[:7] + "****" + api_key[-4:] if len(api_key) > 11 else "****"
        print(f"  Retrieved API Key: {masked}")
        print()
        print("  In production the Agent uses this key to call the target API:")
        print(f"    Authorization: Bearer {masked}")
        print("    POST https://api.example.com/v1/chat/completions")
    else:
        print("  API Key retrieval failed — see error messages above.")
    print()
    print(f"  WorkloadIdentityId:   {wi_id}")
    print(f"  CredentialProviderId: {cp_id}")


if __name__ == "__main__":
    main()
