import os
import unittest
from unittest.mock import patch

os.environ["SESSION_SPACE_ID"] = "space-test"
os.environ["HANDS_DEPLOYMENT_ID"] = "dpl-test"

import hands_demo


class HandsDemoTest(unittest.TestCase):
    @patch.object(hands_demo, "append_operation")
    @patch.object(hands_demo, "save_affinity")
    @patch.object(hands_demo, "invoke")
    @patch.object(hands_demo, "acquire_token", return_value="token-test")
    @patch.object(hands_demo, "create_session", return_value="session-a")
    def test_start_persists_returned_affinity(
        self,
        create_session,
        acquire_token,
        invoke,
        save_affinity,
        append_operation,
    ):
        invoke.return_value = ({"path": hands_demo.FILE_NAME, "content": "95"}, "affinity-a")

        hands_demo.start("95")

        create_session.assert_called_once_with("dpl-test")
        acquire_token.assert_called_once_with("dpl-test")
        save_affinity.assert_called_once_with("session-a", "dpl-test", "affinity-a")
        append_operation.assert_called_once()

    @patch.object(hands_demo, "append_operation")
    @patch.object(hands_demo, "save_affinity")
    @patch.object(hands_demo, "invoke")
    @patch.object(hands_demo, "acquire_token", return_value="token-test")
    @patch.object(hands_demo, "describe_session")
    def test_resume_uses_only_session_metadata(
        self,
        describe_session,
        acquire_token,
        invoke,
        save_affinity,
        append_operation,
    ):
        describe_session.return_value = {"Metadata": [
            {"Name": hands_demo.DEPLOYMENT_METADATA, "Value": "dpl-from-session"},
            {"Name": hands_demo.AFFINITY_METADATA, "Value": "affinity-a"},
        ]}
        invoke.return_value = ({"exists": True, "content": "95"}, "affinity-a")

        hands_demo.resume("session-a", "95")

        acquire_token.assert_called_once_with("dpl-from-session")
        self.assertEqual(invoke.call_args.kwargs["affinity_id"], "affinity-a")
        save_affinity.assert_not_called()
        append_operation.assert_called_once()

    @patch.object(hands_demo, "append_operation")
    @patch.object(hands_demo, "save_affinity")
    @patch.object(hands_demo, "invoke")
    @patch.object(hands_demo, "acquire_token", return_value="token-test")
    @patch.object(hands_demo, "create_session", return_value="session-b")
    @patch.object(hands_demo, "describe_session")
    def test_isolate_creates_a_distinct_empty_workspace(
        self,
        describe_session,
        create_session,
        acquire_token,
        invoke,
        save_affinity,
        append_operation,
    ):
        describe_session.return_value = {"Metadata": [
            {"Name": hands_demo.DEPLOYMENT_METADATA, "Value": "dpl-from-session"},
            {"Name": hands_demo.AFFINITY_METADATA, "Value": "affinity-a"},
        ]}
        invoke.return_value = ({"exists": False, "content": None}, "affinity-b")

        hands_demo.isolate("session-a")

        create_session.assert_called_once_with("dpl-from-session")
        self.assertIsNone(invoke.call_args.kwargs.get("affinity_id"))
        save_affinity.assert_called_once_with("session-b", "dpl-from-session", "affinity-b")
        append_operation.assert_called_once()


if __name__ == "__main__":
    unittest.main()
