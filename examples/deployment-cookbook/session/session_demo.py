#!/usr/bin/env python3
"""Validate one Brain and Hands conversation persisted by Agent Runtime Session."""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from typing import Any


REGION = os.environ.get("AGR_REGION", "ap-shanghai")
DOMAIN = os.environ.get("AGR_DOMAIN", "tencentags.com")
API_ENDPOINT = os.environ.get("SESSION_API_ENDPOINT", "ags.tencentcloudapi.com")
SPACE_ID = os.environ["SESSION_SPACE_ID"]
USER_ID = os.environ.get("SESSION_USER_ID", "dsh-demo-user")
DEPLOYMENT_ID = os.environ["DSH_DEPLOYMENT_ID"]
AFFINITY_ID = os.environ["DSH_AFFINITY_ID"]

FIRST_QUESTION = "What is 37 + 58?"
FIRST_PROMPT = (
    f"{FIRST_QUESTION} Use hands_write_file to store the numerical answer in "
    "session-value.txt, then answer with only the number."
)
SECOND_QUESTION = (
    "Use hands_read_file to read session-value.txt. Multiply the stored number by 3, "
    "then answer with only the result."
)
THIRD_QUESTION = (
    "What arithmetic question was contained in my first message? Exclude any answer-format "
    "instructions. Return only this JSON object: "
    '{"first_question":"<exact first question>","answer":<number>}'
)


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


def acquire_deployment_token() -> str:
    return agr_call("AcquireDeploymentToken", {"DeploymentId": DEPLOYMENT_ID})["Token"]


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
                "X-Tencent-Agr-Affinity-Id": AFFINITY_ID,
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


def main() -> None:
    client = DSHClient(acquire_deployment_token())
    session_id = client.create_session()
    print(f"Session: {session_id}")

    last_seq = -1
    answers: list[str] = []
    for turn, prompt in enumerate([FIRST_PROMPT, SECOND_QUESTION, THIRD_QUESTION]):
        client.prompt(session_id, prompt)
        last_seq, answer = client.wait_for_assistant(session_id, last_seq)
        print(f"  user: {prompt}")
        print(f"  assistant: {answer}")
        answers.append(answer)

    if answers[0].strip().rstrip(".") != "95":
        raise RuntimeError(f"first answer was not 95: {answers[0]!r}")
    if answers[1].strip().rstrip(".") != "285":
        raise RuntimeError(f"second answer did not use the previous result: {answers[1]!r}")
    try:
        recalled = json.loads(answers[2].strip().removeprefix("```json").removesuffix("```").strip())
    except json.JSONDecodeError as error:
        raise RuntimeError(f"third answer was not valid JSON: {answers[2]!r}") from error
    if recalled != {"first_question": FIRST_QUESTION, "answer": 95}:
        raise RuntimeError(f"third answer did not recall the first question: {recalled!r}")

    sessions = agr_call("DescribeSessions", {
        "SpaceId": SPACE_ID,
        "Filters": [{
            "Name": "metadata:ae.tencentcloud.com/brain-deployment-id",
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
    if primary_metadata.get("ae.tencentcloud.com/hands-deployment-id") is None:
        raise RuntimeError("Session does not contain Hands Deployment metadata")
    primary_affinity = primary_metadata.get("ae.tencentcloud.com/hands-affinity-id")
    if not primary_affinity:
        raise RuntimeError("Session does not contain Hands affinity metadata")
    event_content = json.dumps(events, ensure_ascii=False)
    if "hands_write_file" not in event_content or "hands_read_file" not in event_content:
        raise RuntimeError("Session Events do not contain Hands write and read operations")

    isolated_brain_session_id = client.create_session()
    client.prompt(
        isolated_brain_session_id,
        "Use hands_read_file to read session-value.txt. If it does not exist, answer only MISSING.",
    )
    _, isolated_answer = client.wait_for_assistant(isolated_brain_session_id, -1)
    if isolated_answer.strip().rstrip(".") != "MISSING":
        raise RuntimeError(f"new conversation unexpectedly found the original workspace: {isolated_answer!r}")
    isolated_metadata = metadata_map(describe_session(isolated_brain_session_id))
    isolated_affinity = isolated_metadata.get("ae.tencentcloud.com/hands-affinity-id")
    if not isolated_affinity or isolated_affinity == primary_affinity:
        raise RuntimeError("new conversation did not receive an isolated Hands affinity")

    print(f"Isolated Session: {isolated_brain_session_id}")
    print("Brain conversation persistence, Hands workspace continuity, and isolation passed")


if __name__ == "__main__":
    main()
