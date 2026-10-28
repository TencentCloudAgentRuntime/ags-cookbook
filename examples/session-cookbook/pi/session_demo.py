#!/usr/bin/env python3
"""Verify cloud persistence, then history loading through a fresh pi container."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
import uuid


AGENT_METADATA_KEY = "example.com/pi-agent-id"
DEFAULT_IMAGE = "pi-session:local"
TURN_TIMEOUT_SECONDS = 180
SHUTDOWN_TIMEOUT_SECONDS = 60


def json_object(value):
    return json.loads(value) if isinstance(value, str) else (value or {})


def pi_extension(row):
    return json_object(row.get("Extensions")).get("pi", {})


def part_text(row):
    """All text a stored Event carries in Content.Parts."""
    parts = (row.get("Content") or {}).get("Parts") or []
    return "\n".join(part.get("Text", "") for part in parts if part.get("Text"))


class CloudError(RuntimeError):
    def __init__(self, action, failure):
        failure = failure or {}
        self.code = failure.get("Code", "")
        self.retryable = bool(failure.get("Retryable")) or self.code.startswith("RequestLimitExceeded")
        super().__init__(f"{action} failed: {failure}")


class PiContainer:
    """One pi container driven over RPC: JSON lines on stdin and stdout."""

    def __init__(self, command):
        # Killing the `docker run` client does not stop the container, so keep its name to remove it.
        self.name = command[command.index("--name") + 1] if "--name" in command else None
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=None)

    def send(self, command):
        self.process.stdin.write(json.dumps(command).encode() + b"\n")
        self.process.stdin.flush()

    def records(self, deadline=None):
        """Yield stdout records; raise TimeoutError when none arrives before the deadline.

        A blocking read cannot be interrupted, so a thread reads the pipe and the caller waits on a queue.
        """
        if not hasattr(self, "lines"):
            self.lines = queue.Queue()
            threading.Thread(target=self.pump, args=(self.process.stdout,), daemon=True).start()
        while True:
            wait = None if deadline is None else deadline - time.monotonic()
            try:
                line = self.lines.get(timeout=None if wait is None else max(wait, 0))
            except queue.Empty:
                raise TimeoutError(f"No output from pi in {TURN_TIMEOUT_SECONDS} seconds; inspect the container log and model credentials") from None
            if line is None:
                return
            if line:
                yield json.loads(line)

    def pump(self, stream):
        # Records are split on LF only; stdout is read as bytes, as the RPC protocol requires.
        for line in stream:
            self.lines.put(line.rstrip(b"\r\n"))
        self.lines.put(None)

    def turn(self, text, deadline):
        """Send one prompt and return the assistant's reply once pi has settled."""
        request_id = str(uuid.uuid4())
        self.send({"id": request_id, "type": "prompt", "message": text})
        reply = None
        for record in self.records(deadline):
            kind = record.get("type")
            if kind == "response" and record.get("id") == request_id and not record.get("success"):
                raise RuntimeError(f"pi refused the prompt: {record.get('error')}")
            if kind == "extension_ui_request" and record.get("method") == "notify" and record.get("notifyType") == "error":
                raise RuntimeError(f"pi extension reported: {record.get('message')}")
            if kind == "message_end" and record.get("message", {}).get("role") == "assistant":
                message = record["message"]
                if message.get("stopReason") in {"error", "aborted"}:
                    raise RuntimeError(f"model call failed: {message.get('errorMessage') or message.get('stopReason')}")
                blocks = [b.get("text", "") for b in message.get("content", []) if b.get("type") == "text"]
                reply = "".join(blocks)
            if kind == "agent_settled":
                if reply is None:
                    raise RuntimeError("pi settled without an assistant reply")
                return reply
        raise RuntimeError("pi closed its output before the turn settled")

    def close(self):
        """Close stdin so pi shuts down in order, which flushes the last entries to the cloud."""
        self.process.stdin.close()
        try:
            return self.process.wait(timeout=SHUTDOWN_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            self.abort()
            raise

    def abort(self):
        """Remove the container, then reap the docker client. Used on every failure path."""
        if self.name:
            subprocess.run(["docker", "rm", "-f", self.name], capture_output=True, timeout=60)
        self.process.kill()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass


class Demo:
    def __init__(self):
        self.key = {"SpaceId": os.environ["SESSION_SPACE_ID"], "UserId": os.environ["SESSION_USER_ID"]}
        self.agent_id = os.environ.get("SESSION_AGENT_ID", "").strip()
        self.image = os.environ.get("PI_SESSION_IMAGE", DEFAULT_IMAGE)
        self.env_file = os.environ.get("PI_ENV_FILE", ".env")

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

    def docker_command(self, session_id):
        # --rm removes the container as soon as pi exits, so nothing on its disk survives.
        return ["docker", "run", "-i", "--rm", "--name", f"pi-session-demo-{uuid.uuid4().hex[:12]}",
                "--platform", "linux/amd64", "--env-file", self.env_file,
                "-e", f"PI_SESSION_ID={session_id}", self.image]

    def converse(self, session_id, text):
        """Start a fresh container for the session, run one turn, and remove the container."""
        container = PiContainer(self.docker_command(session_id))
        try:
            reply = container.turn(text, time.monotonic() + TURN_TIMEOUT_SECONDS)
        except BaseException:
            container.abort()
            raise
        status = container.close()
        if status != 0:
            raise RuntimeError(f"pi container exited with status {status}")
        return reply

    def owns_session(self, session):
        return not self.agent_id or any(
            item.get("Name") == AGENT_METADATA_KEY and item.get("Value") == self.agent_id
            for item in session.get("Metadata", [])
        )

    def events(self, session_id):
        rows = []
        while True:
            response = self.cloud("DescribeEvents", **self.key, SessionId=session_id, Offset=len(rows), Limit=100)
            page = response.get("Events", [])
            rows.extend(page)
            if not page or len(rows) >= int(response.get("TotalCount", len(rows))):
                rows.sort(key=lambda row: pi_extension(row).get("seq", -1))
                if [pi_extension(row).get("seq") for row in rows] != list(range(len(rows))):
                    raise RuntimeError("Cloud pi history is not contiguous")
                return rows

    def verify_session(self, session_id):
        response = self.cloud("DescribeSession", **self.key, SessionId=session_id)
        if not self.owns_session(response["Session"]):
            raise RuntimeError("Cloud Session is not tagged with SESSION_AGENT_ID; check the extension version")
        state = json_object(response["Session"]["State"]["CustomState"])
        if state.get("piHeader", {}).get("id") != session_id:
            raise RuntimeError("Cloud Session is missing the matching pi header")

    def seed(self, path):
        if path.exists():
            raise RuntimeError(f"{path} already exists; use a different --state path for a new run")
        session_id = str(uuid.uuid4())
        marker = "session-proof-" + uuid.uuid4().hex
        # Save identifiers before the run so interrupted runs remain inspectable.
        path.parent.mkdir(parents=True, exist_ok=True)
        state = {**self.key, "agentId": self.agent_id, "sessionId": session_id, "marker": marker}
        path.write_text(json.dumps(state, indent=2))
        self.converse(session_id, f"Remember this marker for our next turn: {marker}. Reply with only ACK. Do not use tools.")
        self.verify_session(session_id)
        rows = self.events(session_id)
        if marker not in "\n".join(part_text(row) for row in rows if row.get("Author") == "user"):
            raise RuntimeError("The marker is missing from the stored user message")
        if not any(row.get("Author") == "assistant" for row in rows):
            raise RuntimeError("No assistant message was stored")
        state["completedEvents"] = len(rows)
        path.write_text(json.dumps(state, indent=2))
        print(f"Session: {session_id}\nCloud header and {len(rows)} events verified. State: {path}")
        print("The container was removed. Run resume to continue the conversation in a fresh one.")

    def resume(self, path):
        state = json.loads(path.read_text())
        if any(state[k] != v for k, v in self.key.items()):
            raise RuntimeError("SpaceId/UserId differ from the seed run")
        if state.get("agentId", "") != self.agent_id:
            raise RuntimeError("AgentId differs from the seed run")
        if "completedEvents" not in state:
            raise RuntimeError("Seed did not finish; inspect the recorded Session before retrying")
        session_id = state["sessionId"]
        reply = self.converse(session_id, "What marker did I ask you to remember? Reply with only that marker. Do not use tools.")
        if reply.strip() != state["marker"]:
            raise RuntimeError(f"History loaded, but model recall did not match: {reply!r}")
        rows = self.events(session_id)
        if len(rows) <= state["completedEvents"]:
            raise RuntimeError("The new turn was not appended to the cloud Session")
        print(f"Session: {session_id}\nPersisted history loaded and a new turn completed: {reply}")
        print(f"The Session now holds {len(rows)} events (was {state['completedEvents']}).")
        print("This verifies sequential recovery, not concurrent writers or automatic failover.")

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
