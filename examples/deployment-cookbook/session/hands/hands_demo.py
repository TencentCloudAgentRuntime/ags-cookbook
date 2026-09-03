#!/usr/bin/env python3
"""Persist and restore a Hands workspace through Agent Runtime Session."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any


REGION = os.environ.get("AGR_REGION", "ap-shanghai")
DOMAIN = os.environ.get("AGR_DOMAIN", "tencentags.com")
API_ENDPOINT = os.environ.get("SESSION_API_ENDPOINT", "ags.tencentcloudapi.com")
SPACE_ID = os.environ.get("SESSION_SPACE_ID", "")
USER_ID = os.environ.get("SESSION_USER_ID", "hands-demo-user")
DEPLOYMENT_ID = os.environ.get("HANDS_DEPLOYMENT_ID", "")
AFFINITY_HEADER = "X-Tencent-Agr-Affinity-Id"
DEPLOYMENT_METADATA = "ae.tencentcloud.com/hands-deployment-id"
AFFINITY_METADATA = "ae.tencentcloud.com/hands-affinity-id"
FILE_NAME = "session-value.txt"


def agr_call(action: str, payload: dict[str, Any]) -> dict[str, Any]:
    completed = subprocess.run(
        [
            "agr", "api", "call", action,
            "--region", REGION,
            "--cloud-endpoint", API_ENDPOINT,
            "--request", json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            "--output", "json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    envelope = json.loads(completed.stdout)
    if envelope.get("Status") != "succeeded":
        raise RuntimeError(f"{action} failed: {envelope.get('Failure')}")
    return envelope["Data"]["Response"]["Response"]


def session_request(session_id: str, **extra: Any) -> dict[str, Any]:
    if not SPACE_ID:
        raise RuntimeError("SESSION_SPACE_ID is required")
    return {
        "SpaceId": SPACE_ID,
        "UserId": USER_ID,
        "SessionId": session_id,
        **extra,
    }


def metadata_map(session: dict[str, Any]) -> dict[str, str]:
    return {item["Name"]: item["Value"] for item in session.get("Metadata", [])}


def create_session(deployment_id: str) -> str:
    session_id = str(uuid.uuid4())
    agr_call("CreateSession", session_request(
        session_id,
        Title=f"Hands workspace {session_id[:8]}",
        Metadata=[{"Name": DEPLOYMENT_METADATA, "Value": deployment_id}],
    ))
    return session_id


def describe_session(session_id: str) -> dict[str, Any]:
    response = agr_call("DescribeSession", session_request(session_id))
    session = response.get("Session")
    if not session:
        raise RuntimeError(f"Session {session_id} was not returned")
    return session


def save_affinity(session_id: str, deployment_id: str, affinity_id: str) -> None:
    agr_call("ModifySession", session_request(
        session_id,
        Metadata=[
            {"Name": DEPLOYMENT_METADATA, "Value": deployment_id},
            {"Name": AFFINITY_METADATA, "Value": affinity_id},
        ],
    ))


def acquire_token(deployment_id: str) -> str:
    return agr_call("AcquireDeploymentToken", {"DeploymentId": deployment_id})["Token"]


def invoke(
    deployment_id: str,
    token: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    affinity_id: str | None = None,
) -> tuple[dict[str, Any], str]:
    body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode()
    headers = {"X-Access-Token": token}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if affinity_id:
        headers[AFFINITY_HEADER] = affinity_id
    request = urllib.request.Request(
        f"https://8080-{deployment_id}.{REGION}.agents.{DOMAIN}{path}",
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            result = json.load(response)
            returned_affinity = response.headers.get(AFFINITY_HEADER)
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace")
        raise RuntimeError(f"Hands returned HTTP {error.code}: {detail}") from error
    if not returned_affinity:
        raise RuntimeError(f"Hands response did not include {AFFINITY_HEADER}")
    return result, returned_affinity


def append_operation(
    session_id: str,
    operation: str,
    arguments: dict[str, Any],
    result: dict[str, Any],
) -> None:
    invocation_id = str(uuid.uuid4())
    call_id = str(uuid.uuid4())
    agr_call("AppendEvent", session_request(session_id, Event={
        "EventId": f"hands-{call_id}-call",
        "InvocationId": invocation_id,
        "Author": "client",
        "Content": {
            "Role": "assistant",
            "Parts": [{"FunctionCall": json.dumps({
                "Name": operation,
                "Args": arguments,
            }, separators=(",", ":"))}],
        },
        "Metadata": json.dumps({"source": "hands-session-cookbook", "phase": "call"}),
    }))
    agr_call("AppendEvent", session_request(session_id, Event={
        "EventId": f"hands-{call_id}-result",
        "InvocationId": invocation_id,
        "Author": "hands",
        "Content": {
            "Role": "tool",
            "Parts": [{"FunctionResponse": json.dumps({
                "Name": operation,
                "Response": result,
            }, separators=(",", ":"))}],
        },
        "Metadata": json.dumps({"source": "hands-session-cookbook", "phase": "result"}),
    }))


def start(value: str) -> None:
    if not DEPLOYMENT_ID:
        raise RuntimeError("HANDS_DEPLOYMENT_ID is required for start")
    session_id = create_session(DEPLOYMENT_ID)
    token = acquire_token(DEPLOYMENT_ID)
    result, affinity_id = invoke(
        DEPLOYMENT_ID,
        token,
        "POST",
        "/files/write",
        {"path": FILE_NAME, "content": value},
    )
    save_affinity(session_id, DEPLOYMENT_ID, affinity_id)
    append_operation(session_id, "workspace.write_file", {"path": FILE_NAME, "content": value}, result)
    print(f"Session A: {session_id}")
    print(f"Created {FILE_NAME} with value {value}")
    print("Hands Deployment ID and affinity were persisted to Session A")


def resume(session_id: str, expected: str) -> None:
    metadata = metadata_map(describe_session(session_id))
    deployment_id = metadata.get(DEPLOYMENT_METADATA)
    affinity_id = metadata.get(AFFINITY_METADATA)
    if not deployment_id or not affinity_id:
        raise RuntimeError("Session does not contain Hands Deployment and affinity metadata")
    token = acquire_token(deployment_id)
    query = urllib.parse.urlencode({"path": FILE_NAME})
    result, returned_affinity = invoke(
        deployment_id,
        token,
        "GET",
        f"/files/read?{query}",
        affinity_id=affinity_id,
    )
    if returned_affinity != affinity_id:
        save_affinity(session_id, deployment_id, returned_affinity)
    append_operation(session_id, "workspace.read_file", {"path": FILE_NAME}, result)
    if not result.get("exists") or result.get("content") != expected:
        raise RuntimeError(f"Session A did not restore the expected workspace: {result!r}")
    print(f"Restored Session A: {session_id}")
    print(f"Read {FILE_NAME}: {result['content']}")
    print("Workspace recovery passed")


def isolate(reference_session_id: str) -> None:
    reference = metadata_map(describe_session(reference_session_id))
    deployment_id = reference.get(DEPLOYMENT_METADATA)
    reference_affinity = reference.get(AFFINITY_METADATA)
    if not deployment_id or not reference_affinity:
        raise RuntimeError("Reference Session does not contain Hands Deployment and affinity metadata")
    session_id = create_session(deployment_id)
    token = acquire_token(deployment_id)
    query = urllib.parse.urlencode({"path": FILE_NAME})
    result, affinity_id = invoke(deployment_id, token, "GET", f"/files/read?{query}")
    save_affinity(session_id, deployment_id, affinity_id)
    append_operation(session_id, "workspace.read_file", {"path": FILE_NAME}, result)
    if affinity_id == reference_affinity:
        raise RuntimeError("Session B unexpectedly received Session A's affinity")
    if result.get("exists"):
        raise RuntimeError(f"Session B unexpectedly accessed Session A's file: {result!r}")
    print(f"Session B: {session_id}")
    print(f"{FILE_NAME} was not found in the new workspace")
    print("Workspace isolation passed")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    start_parser = subparsers.add_parser("start", help="create Session A and write a workspace file")
    start_parser.add_argument("--value", default="95")
    resume_parser = subparsers.add_parser("resume", help="restore Session A and read its workspace file")
    resume_parser.add_argument("--session-id", required=True)
    resume_parser.add_argument("--expected", default="95")
    isolate_parser = subparsers.add_parser("isolate", help="create Session B and verify workspace isolation")
    isolate_parser.add_argument("--reference-session-id", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "start":
        start(args.value)
    elif args.command == "resume":
        resume(args.session_id, args.expected)
    else:
        isolate(args.reference_session_id)


if __name__ == "__main__":
    main()
