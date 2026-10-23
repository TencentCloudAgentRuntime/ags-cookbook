#!/usr/bin/env python3
"""Verify cloud persistence, then history loading through a fresh DSH process."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


AGENT_METADATA_KEY = "example.com/dsh-agent-id"


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
    if reason in {"error", "aborted", "interrupted", "blocked", "max-tokens"}:
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


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Demo:
    def __init__(self):
        self.key = {"SpaceId": os.environ["SESSION_SPACE_ID"], "UserId": os.environ["SESSION_USER_ID"]}
        self.agent_id = os.environ.get("SESSION_AGENT_ID", "").strip()
        self.url = os.environ.get("DSH_BASE_URL", "http://127.0.0.1:18080").rstrip("/")
        self.cookie = None

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
        # DSH 0.2 authenticates every RPC and reads its arguments from args.request.
        headers = {"Content-Type": "application/json", "Cookie": self.sign_in()}
        envelope = {"type": "client-request", "rpcId": rpc_id, "method": method, "payload": {"args": {"request": payload}}}
        request = urllib.request.Request(self.url + "/api/" + method, method="POST", headers=headers,
                                         data=json.dumps(envelope).encode())
        with urllib.request.urlopen(request, timeout=180) as response:
            envelope = json.load(response)
        if envelope.get("rpcId") != rpc_id or not envelope.get("result", {}).get("ok"):
            raise RuntimeError(f"DSH {method} failed: {envelope.get('result')}")
        return envelope["result"]["value"]

    def sign_in(self):
        """Exchange the launch token printed by DSH for a sign-in cookie, once per run."""
        if self.cookie is None:
            launch = os.environ.get("DSH_LAUNCH_URL", "").strip()
            if not launch:
                raise RuntimeError("Set DSH_LAUNCH_URL to the URL with ?token= printed in the DSH log")
            # The cookie is bound to the requested authority, so exchange the token at DSH_BASE_URL.
            query = urllib.parse.urlsplit(launch).query
            try:
                urllib.request.build_opener(NoRedirect).open(self.url + "/?" + query, timeout=30)
                raise RuntimeError("DSH did not redirect the launch URL")
            except urllib.error.HTTPError as response:
                cookie = response.headers.get("Set-Cookie")
                if response.code != 303 or not cookie:
                    raise RuntimeError(f"DSH refused the launch token ({response.code}); "
                                       "it changes on every container start") from None
            self.cookie = cookie.split(";", 1)[0]
        return self.cookie

    def create(self, session_id):
        return self.rpc("session/create", {"sessionId": session_id})

    def history(self, session_id, through_seq):
        return self.rpc("session/page", {"address": {"kind": "session", "sessionId": session_id},
                                         "throughSeq": through_seq, "maxMessages": 100})

    def owns_session(self, session):
        return not self.agent_id or any(
            item.get("Name") == AGENT_METADATA_KEY and item.get("Value") == self.agent_id
            for item in session.get("Metadata", [])
        )

    def cleanup(self, delete=False):
        """List this user's Sessions (only this Agent's when SESSION_AGENT_ID is set), then delete them."""
        query = {"SpaceId": self.key["SpaceId"], "UserIds": [self.key["UserId"]]}
        if self.agent_id:
            query["Filters"] = [{"Name": f"metadata:{AGENT_METADATA_KEY}", "Values": [self.agent_id]}]
        ids = []
        while True:
            response = self.cloud("DescribeSessions", **query, Offset=len(ids), Limit=100)
            page = response.get("Sessions", [])
            ids.extend(row["SessionId"] for row in page)
            if not page or len(ids) >= int(response.get("TotalCount", len(ids))):
                break
        print(f"SpaceId: {self.key['SpaceId']}  UserId: {self.key['UserId']}  AgentId: {self.agent_id or '(not set)'}")
        for session_id in ids:
            if delete:
                self.cloud("DeleteSession", **self.key, SessionId=session_id)
            print(f"{session_id}: {'deleted' if delete else 'to delete'}")
        if not delete:
            print("Preview only. Run again with --delete to delete these Sessions.")

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
        request = {"sessionId": session_id, "mode": "queue", "content": [{"type": "text", "text": text}]}
        self.rpc("session/prompt", {"requestId": str(uuid.uuid4()), **request})

    def seed(self, path):
        if path.exists():
            raise RuntimeError(f"{path} already exists; use a different --state path for a new run")
        session_id = str(uuid.uuid4())
        marker = "session-proof-" + uuid.uuid4().hex
        # Save identifiers before remote creation so interrupted runs remain inspectable.
        path.parent.mkdir(parents=True, exist_ok=True)
        state = {**self.key, "agentId": self.agent_id, "sessionId": session_id, "marker": marker}
        path.write_text(json.dumps(state, indent=2))
        created = self.create(session_id)
        if created.get("sessionId") != session_id:
            raise RuntimeError("DSH returned a different Session ID")
        self.prompt(session_id, f"Remember this marker for our next turn: {marker}. Reply with only ACK. Do not use tools.")
        seq, _ = self.wait_turn(session_id, -1)
        response = self.cloud("DescribeSession", **self.key, SessionId=session_id)
        if not self.owns_session(response["Session"]):
            raise RuntimeError("Cloud Session is not tagged with SESSION_AGENT_ID; check the image version")
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
        if state.get("agentId", "") != self.agent_id:
            raise RuntimeError("AgentId differs from the seed run")
        if "completedSeq" not in state:
            raise RuntimeError("Seed did not finish; inspect the recorded Session before retrying")
        session_id = state["sessionId"]
        before = self.events(session_id)
        history = self.history(session_id, before[-1]["seq"])
        if state["marker"] not in json.dumps(history):
            raise RuntimeError("Fresh DSH did not load the persisted marker")
        self.prompt(session_id, "What marker did I ask you to remember? Reply with only that marker. Do not use tools.")
        _, reply = self.wait_turn(session_id, before[-1]["seq"])
        if reply.strip() != state["marker"]:
            raise RuntimeError(f"History loaded, but model recall did not match: {reply!r}")
        print(f"Session: {session_id}\nPersisted history loaded and a new turn completed: {reply}")
        print("This verifies sequential recovery, not concurrent writers or automatic failover.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["seed", "resume", "cleanup"])
    parser.add_argument("--state", type=Path, default=Path(".local/session.json"))
    parser.add_argument("--delete", action="store_true", help="Delete Sessions instead of previewing cleanup")
    args = parser.parse_args()
    if args.phase == "cleanup":
        Demo().cleanup(delete=args.delete)
        return
    if args.delete:
        parser.error("--delete is only valid with cleanup")
    getattr(Demo(), args.phase)(args.state)


if __name__ == "__main__":
    main()
