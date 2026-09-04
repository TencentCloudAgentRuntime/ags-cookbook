#!/usr/bin/env python3
"""Validate Session metadata lookup and Hands workspace routing."""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any


REGION = os.environ.get("AGR_REGION", "ap-shanghai")
DOMAIN = os.environ.get("AGR_DOMAIN", "tencentags.com")
API_ENDPOINT = os.environ.get("SESSION_API_ENDPOINT", "ags.tencentcloudapi.com")
SPACE_ID = os.environ["SESSION_SPACE_ID"]
USER_ID = os.environ.get("SESSION_USER_ID", "dsh-demo-user")
DEPLOYMENT_ID = os.environ["DSH_DEPLOYMENT_ID"]
HANDS_DEPLOYMENT_ID = os.environ["HANDS_DEPLOYMENT_ID"]

FIRST_PROMPT = (
    "What is 37 + 58? Use hands_write_file to store the numerical answer in "
    "session-value.txt, then answer with only the number."
)

BRAIN_DEPLOYMENT_METADATA = "example.com/brain-deployment-id"
HANDS_DEPLOYMENT_METADATA = "example.com/hands-deployment-id"
HANDS_AFFINITY_METADATA = "example.com/hands-affinity-id"


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


def acquire_deployment_token(deployment_id: str) -> str:
    return agr_call("AcquireDeploymentToken", {"DeploymentId": deployment_id})["Token"]


def describe_session(session_id: str) -> dict[str, Any]:
    response = agr_call("DescribeSession", {
        "SpaceId": SPACE_ID,
        "UserId": USER_ID,
        "SessionId": session_id,
    })
    session = response.get("Session")
    if not session:
        raise RuntimeError(f"Session {session_id} was not returned")
    return session


def metadata_map(session: dict[str, Any]) -> dict[str, str]:
    return {item["Name"]: item["Value"] for item in session.get("Metadata", [])}


class DSHClient:
    def __init__(self, token: str) -> None:
        self.base_url = f"https://3080-{DEPLOYMENT_ID}.{REGION}.agents.{DOMAIN}"
        self.token = token

    def rpc(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        rpc_id = str(uuid.uuid4())
        body = json.dumps(
            {"type": "client-request", "rpcId": rpc_id, "method": method, "payload": payload},
            separators=(",", ":"),
        ).encode()
        request = urllib.request.Request(
            f"{self.base_url}/api/{method}",
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-Access-Token": self.token,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                envelope = json.load(response)
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")
            raise RuntimeError(f"DSH {method} returned HTTP {error.code}: {detail}") from error
        if envelope.get("rpcId") != rpc_id:
            raise RuntimeError("DSH returned a mismatched rpcId")
        result = envelope.get("result", {})
        if not result.get("ok"):
            raise RuntimeError(f"DSH {method} failed: {result.get('error')}")
        return result["value"]

    def create_session(self) -> str:
        session_id = str(uuid.uuid4())
        result = self.rpc("session.create", {"sessionId": session_id})
        if result["sessionId"] != session_id:
            raise RuntimeError("DSH returned a different Session ID")
        return session_id

    def prompt(self, session_id: str, text: str) -> None:
        self.rpc("session.prompt", {
            "sessionId": session_id,
            "mode": "queue",
            "content": [{"type": "text", "text": text}],
        })

    def wait_for_assistant(self, session_id: str, after_seq: int) -> tuple[int, str]:
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            history = self.rpc("session.history", {"sessionId": session_id, "maxMessages": 50})
            new_events = [
                entry.get("event", {})
                for entry in history.get("events", [])
                if entry.get("event", {}).get("seq", -1) > after_seq
            ]
            turn_end = next(
                (event for event in reversed(new_events) if event.get("type") == "turn/end"),
                None,
            )
            if turn_end is not None:
                for event in reversed(new_events):
                    if event.get("seq", -1) > turn_end["seq"] or event.get("type") != "assistant/message":
                        continue
                    blocks = event.get("data", {}).get("message", {}).get("content", [])
                    text = "".join(
                        block.get("text", "")
                        for block in blocks
                        if block.get("type") == "text"
                    ).strip()
                    if text:
                        return int(turn_end["seq"]), text
            time.sleep(2)
        raise TimeoutError(f"DSH session {session_id} did not finish in 180 seconds")


def describe_all_events(session_id: str) -> list[dict[str, Any]]:
    """Read every Event page for a Session."""
    events: list[dict[str, Any]] = []
    offset = 0
    limit = 100
    while True:
        response = agr_call("DescribeEvents", {
            "SpaceId": SPACE_ID,
            "UserId": USER_ID,
            "SessionId": session_id,
            "Offset": offset,
            "Limit": limit,
        })
        page = response.get("Events", [])
        events.extend(page)
        total_count = response.get("TotalCount")
        if not page or (total_count is not None and len(events) >= int(total_count)):
            return events
        if total_count is None and len(page) < limit:
            return events
        offset += len(page)


def wait_for_persisted_events(session_id: str, expected_count: int) -> list[dict[str, Any]]:
    """Wait for asynchronous Event persistence to catch up with DSH history."""
    deadline = time.monotonic() + 60
    events: list[dict[str, Any]] = []
    while time.monotonic() < deadline:
        events = describe_all_events(session_id)
        if len(events) >= expected_count:
            return events
        time.sleep(2)
    raise TimeoutError(
        f"Agent Runtime persisted {len(events)} of {expected_count} DSH events in 60 seconds"
    )


def content_parts(event: dict[str, Any]) -> list[dict[str, Any]]:
    content = event.get("Content") or {}
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except json.JSONDecodeError:
            return []
    return content.get("Parts", []) if isinstance(content, dict) else []


def matching_function_events(
    events: list[dict[str, Any]], field: str, name: str | None = None,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for event in events:
        for part in content_parts(event):
            value = part.get(field)
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    continue
            if isinstance(value, dict) and (name is None or value.get("Name") == name):
                matches.append({"event": event, "value": value})
    return matches


def describe_deployment(deployment_id: str) -> dict[str, Any]:
    response = agr_call("DescribeDeployment", {"DeploymentId": deployment_id})
    deployment = response.get("Deployment")
    if not deployment or deployment.get("DeploymentId") != deployment_id:
        raise RuntimeError(f"Deployment {deployment_id} was not returned")
    return deployment


def read_hands_file(deployment_id: str, affinity_id: str, path: str) -> dict[str, Any]:
    token = acquire_deployment_token(deployment_id)
    query = urllib.parse.urlencode({"path": path})
    url = f"https://8080-{deployment_id}.{REGION}.agents.{DOMAIN}/files/read?{query}"
    request = urllib.request.Request(
        url,
        headers={
            "X-Access-Token": token,
            "X-Tencent-Agr-Affinity-Id": affinity_id,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            returned_affinity = response.headers.get("X-Tencent-Agr-Affinity-Id")
            result = json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace")
        raise RuntimeError(f"Hands returned HTTP {error.code}: {detail}") from error
    if returned_affinity != affinity_id:
        raise RuntimeError("Hands did not preserve the affinity restored from Session metadata")
    return result


def main() -> None:
    client = DSHClient(acquire_deployment_token(DEPLOYMENT_ID))
    session_id = client.create_session()
    print(f"Session: {session_id}")

    client.prompt(session_id, FIRST_PROMPT)
    last_seq, answer = client.wait_for_assistant(session_id, -1)
    print(f"  user: {FIRST_PROMPT}")
    print(f"  assistant: {answer}")
    if answer.strip().rstrip(".") != "95":
        raise RuntimeError(f"answer was not 95: {answer!r}")

    sessions = agr_call("DescribeSessions", {
        "SpaceId": SPACE_ID,
        "Filters": [{
            "Name": f"metadata:{BRAIN_DEPLOYMENT_METADATA}",
            "Values": [DEPLOYMENT_ID],
        }],
        "Offset": 0,
        "Limit": 20,
    }).get("Sessions", [])
    if not any(session.get("SessionId") == session_id for session in sessions):
        raise RuntimeError("Session was not found through Brain Deployment metadata")

    events = wait_for_persisted_events(session_id, last_seq + 1)
    print(f"Agent Runtime persisted {len(events)} DSH events")

    primary_metadata = metadata_map(describe_session(session_id))
    if primary_metadata.get(BRAIN_DEPLOYMENT_METADATA) != DEPLOYMENT_ID:
        raise RuntimeError("Session does not contain the expected Brain Deployment metadata")
    if primary_metadata.get(HANDS_DEPLOYMENT_METADATA) != HANDS_DEPLOYMENT_ID:
        raise RuntimeError("Session does not contain the expected Hands Deployment metadata")
    primary_affinity = primary_metadata.get(HANDS_AFFINITY_METADATA)
    if not primary_affinity:
        raise RuntimeError("Session does not contain Hands affinity metadata")

    hands_sessions = agr_call("DescribeSessions", {
        "SpaceId": SPACE_ID,
        "Filters": [{
            "Name": f"metadata:{HANDS_DEPLOYMENT_METADATA}",
            "Values": [HANDS_DEPLOYMENT_ID],
        }],
        "Offset": 0,
        "Limit": 20,
    }).get("Sessions", [])
    if not any(session.get("SessionId") == session_id for session in hands_sessions):
        raise RuntimeError("Session was not found through Hands Deployment metadata")

    write_calls = matching_function_events(events, "FunctionCall", "hands_write_file")
    if not write_calls:
        raise RuntimeError("Session Events do not contain a hands_write_file FunctionCall")
    write_args = write_calls[0]["value"].get("Args", {})
    if write_args.get("path") != "session-value.txt" or str(write_args.get("content")) != "95":
        raise RuntimeError(f"hands_write_file FunctionCall has unexpected arguments: {write_args!r}")
    call_ids = {item["event"].get("InvocationId") for item in write_calls}
    write_results = matching_function_events(events, "FunctionResponse")
    matching_results = [
        item for item in write_results if item["value"].get("Name") in call_ids
    ]
    if not matching_results:
        raise RuntimeError("Session Events do not contain a hands_write_file FunctionResponse")
    response = matching_results[0]["value"].get("Response", {})
    if response.get("isError"):
        raise RuntimeError(f"hands_write_file FunctionResponse contains an error: {response!r}")
    try:
        response_content = json.loads(response.get("content", ""))
    except json.JSONDecodeError as error:
        raise RuntimeError(f"hands_write_file returned invalid content: {response!r}") from error
    if response_content.get("path") != "session-value.txt" or response_content.get("content") != "95":
        raise RuntimeError(f"hands_write_file FunctionResponse has unexpected data: {response_content!r}")

    describe_deployment(DEPLOYMENT_ID)
    describe_deployment(HANDS_DEPLOYMENT_ID)
    restored = read_hands_file(HANDS_DEPLOYMENT_ID, primary_affinity, "session-value.txt")
    if not restored.get("exists") or restored.get("content") != "95":
        raise RuntimeError(f"restored Hands workspace returned unexpected data: {restored!r}")

    print(f"Hands Deployment: {HANDS_DEPLOYMENT_ID}")
    print("Restored session metadata routed the request to the original Hands workspace")


if __name__ == "__main__":
    main()
