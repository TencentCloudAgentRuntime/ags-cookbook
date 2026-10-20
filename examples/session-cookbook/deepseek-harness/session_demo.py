#!/usr/bin/env python3
"""Verify cloud persistence, then history loading through a fresh DSH process."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request
import uuid


def json_object(value):
    return json.loads(value) if isinstance(value, str) else (value or {})


def dsh_events(rows):
    events = [json_object(row.get("Extensions")).get("dshEvent") for row in rows]
    return sorted((event for event in events if event is not None), key=lambda e: e["seq"])


def completed_turn(events, after_seq):
    ends = [e for e in events if e["seq"] > after_seq and e["type"] == "turn/end"]
    if not ends:
        return None
    end = ends[-1]
    reason = end.get("data", {}).get("reason", {}).get("kind")
    if reason in {"error", "aborted", "disposed", "interrupted"}:
        raise RuntimeError(f"DSH turn ended unsuccessfully: {reason}")
    messages = [e for e in events if after_seq < e["seq"] < end["seq"] and e["type"] == "assistant/message"]
    if not messages:
        raise RuntimeError("Completed turn has no assistant message")
    text = "".join(part.get("text", "") for part in messages[-1]["data"]["message"]["content"] if part.get("type") == "text")
    return end["seq"], text


class CloudError(RuntimeError):
    def __init__(self, action, failure):
        failure = failure or {}
        self.code = failure.get("Code", "")
        self.retryable = bool(failure.get("Retryable")) or self.code.startswith("RequestLimitExceeded")
        super().__init__(f"{action} failed: {failure}")


class Demo:
    def __init__(self):
        self.key = {"SpaceId": os.environ["SESSION_SPACE_ID"], "UserId": os.environ["SESSION_USER_ID"]}
        self.url = os.environ.get("DSH_BASE_URL", "http://127.0.0.1:18080").rstrip("/")

    def cloud(self, action, retries=5, **payload):
        for attempt in range(retries + 1):
            result = subprocess.run([
                "agr", "api", "call", action,
                "--region", os.environ.get("AGR_REGION", "ap-shanghai"),
                "--cloud-endpoint", os.environ.get("SESSION_API_ENDPOINT") or "ags.tencentcloudapi.com",
                "--request", json.dumps(payload), "--output", "json",
            ], capture_output=True, text=True, timeout=90)
            try:
                response = json.loads(result.stdout)
            except json.JSONDecodeError:
                raise RuntimeError(f"agr {action} failed: {(result.stderr or result.stdout).strip()}") from None
            if response.get("Status") == "succeeded":
                return response["Data"]["Response"]["Response"]
            error = CloudError(action, response.get("Failure"))
            if not error.retryable or attempt == retries:
                raise error
            time.sleep(0.5 * 2 ** attempt)

    def rpc(self, method, payload):
        rpc_id = str(uuid.uuid4())
        headers = {"Content-Type": "application/json"}
        if os.environ.get("DSH_ACCESS_TOKEN"):
            headers["X-Access-Token"] = os.environ["DSH_ACCESS_TOKEN"]
        request = urllib.request.Request(self.url + "/api/" + method, method="POST", headers=headers,
            data=json.dumps({"type": "client-request", "rpcId": rpc_id, "method": method, "payload": payload}).encode())
        with urllib.request.urlopen(request, timeout=180) as response:
            envelope = json.load(response)
        if envelope.get("rpcId") != rpc_id or not envelope.get("result", {}).get("ok"):
            raise RuntimeError(f"DSH {method} failed: {envelope.get('result')}")
        return envelope["result"]["value"]

    def events(self, session_id):
        rows = []
        while True:
            response = self.cloud("DescribeEvents", **self.key, SessionId=session_id, Offset=len(rows), Limit=100)
            page = response.get("Events", [])
            rows.extend(page)
            if not page or len(rows) >= int(response.get("TotalCount", len(rows))):
                events = dsh_events(rows)
                if [e["seq"] for e in events] != list(range(len(events))):
                    raise RuntimeError("Cloud DSH history is not contiguous")
                return events

    def wait_turn(self, session_id, after_seq):
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            try:
                events = self.events(session_id)
            except CloudError as error:
                if error.code != "ResourceNotFound.SessionNotExist":
                    raise
                events = []  # DSH has not created the cloud Session yet
            result = completed_turn(events, after_seq)
            if result is not None:
                return result
            time.sleep(2)
        raise TimeoutError("No complete persisted turn in 180 seconds; inspect DSH logs and model credentials")

    def prompt(self, session_id, text):
        self.rpc("session.prompt", {"sessionId": session_id, "mode": "queue", "content": [{"type": "text", "text": text}]})

    def seed(self, path):
        if path.exists():
            raise RuntimeError(f"{path} already exists; use a different --state path for a new run")
        session_id = str(uuid.uuid4())
        marker = "session-proof-" + uuid.uuid4().hex
        # Save identifiers before remote creation so interrupted runs remain inspectable.
        path.parent.mkdir(parents=True, exist_ok=True)
        state = {**self.key, "sessionId": session_id, "marker": marker}
        path.write_text(json.dumps(state, indent=2))
        created = self.rpc("session.create", {"sessionId": session_id})
        if created.get("sessionId") != session_id:
            raise RuntimeError("DSH returned a different Session ID")
        self.prompt(session_id, f"Remember this marker for our next turn: {marker}. Reply with only ACK. Do not use tools.")
        seq, _ = self.wait_turn(session_id, -1)
        response = self.cloud("DescribeSession", **self.key, SessionId=session_id)
        header = json_object(response["Session"]["State"]["CustomState"]).get("dshHeader", {})
        if header.get("id") != session_id:
            raise RuntimeError("Cloud Session is missing the matching DSH header")
        state["completedSeq"] = seq
        path.write_text(json.dumps(state, indent=2))
        print(f"Session: {session_id}\nCloud header and completed turn verified. State: {path}")
        print("Stop and remove the DSH container, start a fresh one without volumes, then run resume.")

    def resume(self, path):
        state = json.loads(path.read_text())
        if any(state[k] != v for k, v in self.key.items()):
            raise RuntimeError("SpaceId/UserId differ from the seed run")
        if "completedSeq" not in state:
            raise RuntimeError("Seed did not finish; inspect the recorded Session before retrying")
        session_id = state["sessionId"]
        history = self.rpc("session.history", {"sessionId": session_id, "maxMessages": 100})
        if state["marker"] not in json.dumps(history):
            raise RuntimeError("Fresh DSH did not load the persisted marker")
        before = self.events(session_id)
        self.prompt(session_id, "What marker did I ask you to remember? Reply with only that marker. Do not use tools.")
        _, reply = self.wait_turn(session_id, before[-1]["seq"])
        if reply.strip() != state["marker"]:
            raise RuntimeError(f"History loaded, but model recall did not match: {reply!r}")
        print(f"Session: {session_id}\nPersisted history loaded and a new turn completed: {reply}")
        print("This verifies sequential recovery, not concurrent writers or automatic failover.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["seed", "resume"])
    parser.add_argument("--state", type=Path, default=Path(".local/session.json"))
    args = parser.parse_args()
    getattr(Demo(), args.phase)(args.state)


if __name__ == "__main__":
    main()
