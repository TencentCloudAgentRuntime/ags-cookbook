import json
import os
import subprocess
import unittest
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


class RecoveryEvidenceTests(unittest.TestCase):
    def test_chunks_do_not_count_as_a_completed_persisted_turn(self):
        self.assertIsNone(completed_turn([{"seq": 0, "type": "assistant/chunk"}], -1))

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
