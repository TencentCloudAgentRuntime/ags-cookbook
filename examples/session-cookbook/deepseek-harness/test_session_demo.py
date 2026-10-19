import unittest
from session_demo import completed_turn, dsh_events


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
