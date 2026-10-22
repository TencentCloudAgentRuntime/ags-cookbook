import json
import os
import subprocess
import unittest
import urllib.error
from unittest import mock

from session_demo import CloudError, Demo, completed_turn, dsh_events


def agr_output(failure=None, response=None):
    body = {"Status": "failed", "Failure": failure} if failure else \
        {"Status": "succeeded", "Data": {"Response": {"Response": response or {}}}}
    return subprocess.CompletedProcess([], 1 if failure else 0, stdout=json.dumps(body), stderr="")


@mock.patch.dict(os.environ, {"SESSION_SPACE_ID": "space-test", "SESSION_USER_ID": "user-test"})
class CloudCallTests(unittest.TestCase):
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

    @mock.patch("session_demo.time.sleep")
    @mock.patch("session_demo.subprocess.run")
    def test_wait_turn_waits_for_the_cloud_session_to_be_created(self, run, _sleep):
        end = {"Extensions": json.dumps({"dshEvent": {"seq": 0, "type": "turn/end", "data": {}}})}
        message = {"Extensions": json.dumps({"dshEvent": {"seq": 1, "type": "assistant/message",
                                                          "data": {"message": {"content": []}}}})}
        run.side_effect = [agr_output({"Code": "ResourceNotFound.SessionNotExist"}),
                           agr_output(response={"Events": [end, message], "TotalCount": 2})]
        with self.assertRaisesRegex(RuntimeError, "no assistant message"):
            Demo().wait_turn("session-test", -1)
        self.assertEqual(run.call_count, 2)


@mock.patch.dict(os.environ, {"SESSION_SPACE_ID": "space-test", "SESSION_USER_ID": "user-test", "SESSION_AGENT_ID": "a"})
class CleanupTests(unittest.TestCase):
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
        self.assertEqual(calls[0][1]["Filters"], [{"Name": "metadata:example.com/dsh-agent-id", "Values": ["a"]}])
        self.assertEqual([p["SessionId"] for a, p in calls if a == "DeleteSession"], ["a1", "a2"])

    def test_cleanup_preview_does_not_delete(self):
        demo = Demo()
        demo.cloud = mock.Mock(return_value={"Sessions": [{"SessionId": "a1"}], "TotalCount": 1})
        with mock.patch("builtins.print"):
            demo.cleanup()
        self.assertEqual([c.args[0] for c in demo.cloud.call_args_list], ["DescribeSessions"])


class DshRpcTests(unittest.TestCase):
    @staticmethod
    def response(value):
        def urlopen(request, timeout):
            body = json.loads(request.data)
            urlopen.requests.append((request, body))
            reply = json.dumps({"rpcId": body["rpcId"], "result": {"ok": True, "value": value}}).encode()
            return mock.MagicMock(**{"__enter__.return_value.read.return_value": reply})
        urlopen.requests = []
        return urlopen

    @mock.patch.dict(os.environ, {"SESSION_SPACE_ID": "s", "SESSION_USER_ID": "u",
                                  "DSH_LAUNCH_URL": "http://10.0.0.7:3080/?token=launch-1"}, clear=True)
    def test_requests_sign_in_and_use_the_0_2_rpc_shape(self):
        urlopen = self.response({"sessionId": "id-1"})
        demo = Demo()
        demo.sign_in = mock.Mock(return_value="dsh-auth-x=signed")
        with mock.patch("session_demo.urllib.request.urlopen", urlopen):
            demo.create("id-1")
            demo.prompt("id-1", "hello")
            demo.history("id-1", 9)
        calls = [(request.full_url.rsplit("/api/", 1)[1], body["payload"]["args"]["request"])
                 for request, body in urlopen.requests]
        self.assertEqual(calls[0], ("session/create", {"sessionId": "id-1"}))
        self.assertEqual(calls[1][0], "session/prompt")
        self.assertEqual(set(calls[1][1]), {"requestId", "sessionId", "mode", "content"})
        self.assertEqual(calls[2], ("session/page", {"address": {"kind": "session", "sessionId": "id-1"},
                                                     "throughSeq": 9, "maxMessages": 100}))
        self.assertEqual({request.get_header("Cookie") for request, _ in urlopen.requests}, {"dsh-auth-x=signed"})

    @mock.patch.dict(os.environ, {"SESSION_SPACE_ID": "s", "SESSION_USER_ID": "u",
                                  "DSH_LAUNCH_URL": "http://10.0.0.7:3080/?token=launch-1"}, clear=True)
    def test_sign_in_exchanges_the_token_at_the_base_url(self):
        redirect = urllib.error.HTTPError("http://127.0.0.1:18080/?token=launch-1", 303, "See Other",
                                          {"Set-Cookie": "dsh-auth-x=signed; Path=/; HttpOnly"}, None)
        opener = mock.Mock(**{"open.side_effect": redirect})
        with mock.patch("session_demo.urllib.request.build_opener", return_value=opener):
            demo = Demo()
            self.assertEqual(demo.sign_in(), "dsh-auth-x=signed")
            self.assertEqual(demo.sign_in(), "dsh-auth-x=signed")
        opener.open.assert_called_once_with("http://127.0.0.1:18080/?token=launch-1", timeout=30)

    @mock.patch.dict(os.environ, {"SESSION_SPACE_ID": "s", "SESSION_USER_ID": "u"}, clear=True)
    def test_sign_in_requires_the_launch_url(self):
        with self.assertRaisesRegex(RuntimeError, "DSH_LAUNCH_URL"):
            Demo().sign_in()


class RecoveryEvidenceTests(unittest.TestCase):
    def test_attempts_do_not_count_as_a_completed_persisted_turn(self):
        self.assertIsNone(completed_turn([{"seq": 0, "type": "assistant/attempt"}], -1))

    def test_previous_turn_cannot_satisfy_resume(self):
        self.assertIsNone(completed_turn([{"seq": 5, "type": "turn/end"}], 5))

    def test_error_turn_is_not_success(self):
        with self.assertRaisesRegex(RuntimeError, "error"):
            completed_turn([{"seq": 1, "type": "turn/end", "data": {"reason": {"kind": "error"}}}], -1)

    def test_completed_reply_uses_only_current_turn(self):
        events = [
            {"seq": 3, "type": "assistant/message", "data": {"message": {"content": [{"type": "text", "text": "marker"}]}}},
            {"seq": 4, "type": "turn/end", "data": {}},
        ]
        self.assertEqual(completed_turn(events, 2), (4, "marker"))

    def test_extensions_accept_both_wire_shapes_and_ignore_other_events(self):
        rows = [{"Extensions": '{"dshEvent":{"seq":1}}'}, {"Extensions": {}},
                {"Extensions": {"dshEvent": {"seq": 0}}}]
        self.assertEqual(dsh_events(rows), [{"seq": 0}, {"seq": 1}])


if __name__ == "__main__":
    unittest.main()
