import io
import json
import os
import subprocess
import time
import unittest
from unittest import mock

import session_demo
from session_demo import CloudError, Demo, PiContainer, part_text, pi_extension


def agr_output(failure=None, response=None):
    body = {"Status": "failed", "Failure": failure} if failure else \
        {"Status": "succeeded", "Data": {"Response": {"Response": response or {}}}}
    return subprocess.CompletedProcess([], 1 if failure else 0, stdout=json.dumps(body), stderr="")


class FakeProcess:
    """A pi process whose stdout is a canned list of RPC records."""

    def __init__(self, records, exit_status=0):
        self.stdin = io.BytesIO()
        self.stdout = io.BytesIO(b"".join(json.dumps(r).encode() + b"\n" for r in records))
        self.exit_status = exit_status
        self.killed = False

    def wait(self, timeout=None):
        return self.exit_status

    def kill(self):
        self.killed = True


def container(records, **kwargs):
    with mock.patch("session_demo.subprocess.Popen", return_value=FakeProcess(records, **kwargs)):
        return PiContainer(["docker"])


def assistant_end(text, **extra):
    return {"type": "message_end", "message": {"role": "assistant", "content": [{"type": "text", "text": text}], **extra}}


class PiContainerTests(unittest.TestCase):
    def test_turn_sends_the_prompt_and_returns_the_reply_when_pi_settles(self):
        pi = container([{"type": "message_end", "message": {"role": "user"}}, assistant_end("ACK"), {"type": "agent_settled"}])
        self.assertEqual(pi.turn("hello", float("inf")), "ACK")
        sent = json.loads(pi.process.stdin.getvalue())
        self.assertEqual((sent["type"], sent["message"]), ("prompt", "hello"))

    def test_a_refused_prompt_is_an_error(self):
        pi = container([{"type": "response", "id": "req-1", "success": False, "error": "busy"}])
        with mock.patch("session_demo.uuid.uuid4", return_value="req-1"):
            with self.assertRaisesRegex(RuntimeError, "pi refused the prompt: busy"):
                pi.turn("hello", float("inf"))

    def test_a_failed_model_call_is_an_error(self):
        pi = container([assistant_end("", stopReason="error", errorMessage="401 unauthorized"), {"type": "agent_settled"}])
        with self.assertRaisesRegex(RuntimeError, "model call failed: 401 unauthorized"):
            pi.turn("hello", float("inf"))

    def test_an_extension_save_failure_is_an_error(self):
        pi = container([{"type": "extension_ui_request", "method": "notify", "notifyType": "error",
                         "message": "saving session s failed: denied"}])
        with self.assertRaisesRegex(RuntimeError, "pi extension reported: saving session s failed"):
            pi.turn("hello", float("inf"))

    def test_settling_without_a_reply_is_an_error(self):
        with self.assertRaisesRegex(RuntimeError, "without an assistant reply"):
            container([{"type": "agent_settled"}]).turn("hello", float("inf"))

    def test_a_silent_pi_times_out_instead_of_blocking(self):
        process = subprocess.Popen(["sleep", "30"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        pi = PiContainer.__new__(PiContainer)
        pi.process = process
        started = time.monotonic()
        try:
            with self.assertRaises(TimeoutError):
                list(pi.records(time.monotonic() + 0.05))
        finally:
            process.kill()
        self.assertLess(time.monotonic() - started, 5)

    @mock.patch("session_demo.subprocess.run")
    def test_abort_removes_the_named_container_before_reaping_the_client(self, run):
        process = FakeProcess([])
        with mock.patch("session_demo.subprocess.Popen", return_value=process):
            pi = PiContainer(["docker", "run", "--name", "pi-x", "image"])
        pi.abort()
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0], ["docker", "rm", "-f", "pi-x"])
        self.assertTrue(process.killed)

    def test_pi_closing_its_output_early_is_an_error(self):
        with self.assertRaisesRegex(RuntimeError, "closed its output"):
            container([]).turn("hello", float("inf"))

    def test_records_split_on_lf_only(self):
        pi = container([])
        pi.process.stdout = io.BytesIO('{"a": "x y"}\n'.encode())
        self.assertEqual(list(pi.records()), [{"a": "x y"}])


@mock.patch.dict(os.environ, {"SESSION_SPACE_ID": "space-test", "SESSION_USER_ID": "user-test", "SESSION_AGENT_ID": "a"})
class DemoTests(unittest.TestCase):
    @mock.patch("session_demo.time.sleep")
    @mock.patch("session_demo.subprocess.run")
    def test_rate_limited_calls_are_retried(self, run, _sleep):
        run.side_effect = [agr_output({"Code": "RequestLimitExceeded"}), agr_output(response={"TotalCount": 0})]
        self.assertEqual(Demo().cloud("DescribeEvents"), {"TotalCount": 0})
        self.assertEqual(run.call_count, 2)

    @mock.patch("session_demo.subprocess.run")
    def test_other_failures_surface_their_api_code(self, run):
        run.return_value = agr_output({"Code": "AuthFailure"})
        with self.assertRaises(CloudError) as raised:
            Demo().cloud("DescribeEvents")
        self.assertEqual(raised.exception.code, "AuthFailure")
        self.assertEqual(run.call_count, 1)

    def test_every_container_gets_a_unique_name(self):
        demo = Demo()
        commands = [demo.docker_command("s") for _ in range(5)]
        self.assertEqual(len({c[c.index("--name") + 1] for c in commands}), 5)

    def test_the_container_is_removed_when_pi_exits_and_carries_the_session_id(self):
        command = Demo().docker_command("session-1")
        self.assertIn("--rm", command)
        self.assertIn("PI_SESSION_ID=session-1", command)
        self.assertNotIn("-v", command)

    def test_a_failed_turn_kills_the_container(self):
        pi = mock.Mock()
        pi.turn.side_effect = RuntimeError("model call failed")
        with mock.patch("session_demo.PiContainer", return_value=pi):
            with self.assertRaises(RuntimeError):
                Demo().converse("s", "hi")
        pi.abort.assert_called_once()

    def test_a_nonzero_exit_after_the_turn_is_an_error(self):
        pi = mock.Mock()
        pi.turn.return_value = "ACK"
        pi.close.return_value = 1
        with mock.patch("session_demo.PiContainer", return_value=pi):
            with self.assertRaisesRegex(RuntimeError, "exited with status 1"):
                Demo().converse("s", "hi")

    def test_events_must_be_contiguous(self):
        def row(seq):
            return {"Extensions": json.dumps({"pi": {"seq": seq}})}
        demo = Demo()
        demo.cloud = lambda action, **payload: {"Events": [row(2), row(0)], "TotalCount": 2}
        with self.assertRaisesRegex(RuntimeError, "not contiguous"):
            demo.events("s")
        demo.cloud = lambda action, **payload: {"Events": [row(1), row(0)], "TotalCount": 2}
        self.assertEqual([pi_extension(r)["seq"] for r in demo.events("s")], [0, 1])

    def test_projection_helpers(self):
        row = {"Content": {"Parts": [{"Text": "a"}, {"Text": ""}, {"Text": "b"}]}, "Extensions": '{"pi": {"seq": 3}}'}
        self.assertEqual(part_text(row), "a\nb")
        self.assertEqual(pi_extension(row)["seq"], 3)
        self.assertEqual(part_text({}), "")

    def test_cleanup_filters_by_agent_and_collects_all_pages(self):
        demo = Demo()
        pages = [{"Sessions": [{"SessionId": "a1"}], "TotalCount": 2}, {"Sessions": [{"SessionId": "a2"}], "TotalCount": 2}]
        calls = []
        def cloud(action, **payload):
            calls.append((action, payload))
            return pages.pop(0) if action == "DescribeSessions" else {}
        demo.cloud = cloud
        with mock.patch("builtins.print"):
            demo.cleanup(delete=True)
        self.assertEqual(calls[0][1]["Filters"], [{"Name": "metadata:example.com/pi-agent-id", "Values": ["a"]}])
        self.assertEqual([p["SessionId"] for a, p in calls if a == "DeleteSession"], ["a1", "a2"])


if __name__ == "__main__":
    unittest.main()
