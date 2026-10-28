"""
Multi-Tenant ManagedSecret CredentialProvider — Complete Demo

Demonstrates the end-to-end workflow for managing multi-tenant managed
secrets through AGS CredentialProvider, covering all four phases:

  Phase 1: One-time setup
           CreateWorkloadIdentity + CreateCredentialProvider (SecretMultiUser)

  Phase 2: ManagedSecret management
           Set / List / Rotate managed secrets per user (with Scope + Metadata)

  Phase 3: Runtime — WAT issuance
           CreateWorkloadAccessTokenForUserId

  Phase 4: Runtime — Agent retrieves managed secret
           GetManagedSecret (WAT + Scope → plaintext secret)

Concepts:
    - Scope:    REQUIRED for Set / Get; optional for Delete / List filter.
                A non-empty string used to namespace secrets per user (e.g.
                "openai", "github"). One user can own multiple secrets, one
                per Scope.
    - Metadata: optional list of {Name, Value} entries attached to the
                secret (e.g. email, client_id). Returned by Get / List.
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

# Demo-wide Scope. ManagedSecret requires a non-empty Scope for Set/Get.
# In a real platform you would choose a Scope per target API
# (e.g. "openai", "anthropic", "github") so one user can own multiple secrets.
DEMO_SCOPE = "openai"


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
    """Create WorkloadIdentity and CredentialProvider (SecretMultiUser)."""
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

    # Step 2: Create CredentialProvider (SecretMultiUser)
    print("\n[2/2] Creating CredentialProvider (SecretMultiUser)...")
    cp_resp = call_api("CreateCredentialProvider", {
        "Name": f"demo-customer-keys-{suffix}",
        "Type": "SecretMultiUser",
        "Description": "Multi-tenant managed secrets for demo agent",
        "Config": [{"Key": "description", "Value": "per-user managed secrets"}],
    })
    cp_id = cp_resp.get("ProviderId", "")
    if cp_id:
        print(f"  Created CredentialProvider: {cp_id}")
    else:
        print("  Failed to create CredentialProvider")
        sys.exit(1)

    print(f"\n  Record these IDs for later use:")
    print(f"    WorkloadIdentityId   = {wi_id}")
    print(f"    CredentialProviderId = {cp_id}")
    return wi_id, cp_id


# ===========================================================================
# Phase 2: ManagedSecret Management
# ===========================================================================


def phase2_manage_keys(cp_id: str):
    """Demonstrate setting, listing, and rotating managed secrets per user."""
    print("\n" + "=" * 60)
    print("Phase 2: ManagedSecret Management")
    print("=" * 60)

    # Set ManagedSecret for customer-001
    print("\n[1/4] Setting ManagedSecret for customer-001 (scope=%s)..." % DEMO_SCOPE)
    call_api("SetManagedSecret", {
        "CredentialProviderId": cp_id,
        "UserId": "customer-001",
        "Secret": "sk-demo-key-for-customer-001",
        "Scope": DEMO_SCOPE,
        "OverwriteAllowed": False,
        # Optional Metadata: arbitrary KVs returned by Get / List.
        "Metadata": [
            {"Name": "email", "Value": "customer-001@example.com"},
            {"Name": "plan", "Value": "pro"},
        ],
    })
    print("  Done.")

    # Set ManagedSecret for customer-002
    print("\n[2/4] Setting ManagedSecret for customer-002 (scope=%s)..." % DEMO_SCOPE)
    call_api("SetManagedSecret", {
        "CredentialProviderId": cp_id,
        "UserId": "customer-002",
        "Secret": "sk-demo-key-for-customer-002",
        "Scope": DEMO_SCOPE,
        "OverwriteAllowed": False,
        "Metadata": [
            {"Name": "email", "Value": "customer-002@example.com"},
        ],
    })
    print("  Done.")

    # List all ManagedSecrets (masked) — filter by scope
    print("\n[3/4] Listing ManagedSecrets (masked, scope=%s)..." % DEMO_SCOPE)
    list_resp = call_api("DescribeManagedSecretList", {
        "CredentialProviderId": cp_id,
        "Offset": 0,
        "Limit": 20,
        "Filters": [
            {"Name": "scope", "Values": [DEMO_SCOPE]},
        ],
    })
    total = list_resp.get("TotalCount", 0)
    secrets = list_resp.get("ManagedSecretSet", [])
    print(f"  TotalCount: {total}")
    for item in secrets:
        meta_pairs = [
            f"{m['Name']}={m['Value']}" for m in item.get("Metadata", [])
        ]
        meta_str = ", ".join(meta_pairs) if meta_pairs else "<none>"
        print(
            f"    UserId={item['UserId']}  "
            f"Scope={item.get('Scope', '')}  "
            f"MaskedSecret={item['MaskedSecret']}  "
            f"CreatedAt={item['CreatedAt']}  "
            f"Metadata=[{meta_str}]"
        )

    # Rotate: overwrite ManagedSecret for customer-001
    print("\n[4/4] Rotating ManagedSecret for customer-001 (OverwriteAllowed=true)...")
    call_api("SetManagedSecret", {
        "CredentialProviderId": cp_id,
        "UserId": "customer-001",
        "Secret": "sk-rotated-key-for-customer-001",
        "Scope": DEMO_SCOPE,
        "OverwriteAllowed": True,
        "Metadata": [
            {"Name": "email", "Value": "customer-001@example.com"},
            {"Name": "plan", "Value": "pro"},
            {"Name": "rotated", "Value": "true"},
        ],
    })
    print("  Done. Next GetManagedSecret call will return the new secret.")


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
# Phase 4: Runtime — Agent Retrieves ManagedSecret
# ===========================================================================


def phase4_get_secret(cp_id: str, wat: str) -> str:
    """
    Use the WAT to retrieve the plaintext managed secret.

    In production, this call is made by the Agent runtime using a
    least-privilege sub-account AKSK that only has GetManagedSecret
    permission. The service extracts UserId from the WAT JWT claims, so
    the Agent cannot forge another user's identity.
    """
    print("\n" + "=" * 60)
    print("Phase 4: Agent Retrieves ManagedSecret via WAT")
    print("=" * 60)

    print("\n  Calling GetManagedSecret (scope=%s)..." % DEMO_SCOPE)
    resp = call_api("GetManagedSecret", {
        "CredentialProviderId": cp_id,
        "WorkloadIdentityToken": wat,
        "Scope": DEMO_SCOPE,
    })
    secret = resp.get("Secret", "")
    if secret:
        masked = secret[:7] + "****" + secret[-4:] if len(secret) > 11 else "****"
        print(f"  Retrieved Secret (masked): {masked}")
        meta = resp.get("Metadata", [])
        if meta:
            print("  Metadata:")
            for entry in meta:
                print(f"    {entry['Name']}={entry['Value']}")
    else:
        print("  Failed to retrieve managed secret")
    return secret


# ===========================================================================
# Main
# ===========================================================================


def main():
    print("Multi-Tenant ManagedSecret CredentialProvider — Complete Demo")
    print("=" * 60)
    print()
    print("This demo walks through 4 phases:")
    print("  1. One-time setup   (create WorkloadIdentity + CredentialProvider)")
    print("  2. Secret management (set / list / rotate managed secrets per user)")
    print("  3. WAT issuance     (create Workload Access Token for a user)")
    print("  4. Get secret       (Agent retrieves plaintext secret via WAT)")
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
    secret = phase4_get_secret(cp_id, wat)

    # Summary
    print("\n" + "=" * 60)
    print("Demo Complete")
    print("=" * 60)
    print()
    if secret:
        masked = secret[:7] + "****" + secret[-4:] if len(secret) > 11 else "****"
        print(f"  Retrieved Secret: {masked}")
        print()
        print("  In production the Agent uses this secret to call the target API:")
        print(f"    Authorization: Bearer {masked}")
        print("    POST https://api.example.com/v1/chat/completions")
    else:
        print("  ManagedSecret retrieval failed — see error messages above.")
    print()
    print(f"  WorkloadIdentityId:   {wi_id}")
    print(f"  CredentialProviderId: {cp_id}")
    print(f"  Scope:                {DEMO_SCOPE}")


if __name__ == "__main__":
    main()
