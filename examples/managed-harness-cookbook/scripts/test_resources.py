import argparse
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch

import resources


class ResourceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.path = self.root / "simple.json"
        self.env = patch.dict(os.environ, AGR_REGION="ap-chongqing")
        self.env.start()
        self.addCleanup(self.env.stop)

    def create(self, kind, state):
        args = argparse.Namespace(resource=kind, flags=["--name", "my-demo"])
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            resources.create(args, self.path, state)

    def test_nonzero_exit_still_records_returned_id_and_reports_failure(self):
        reply = {"Status": "succeeded", "Data": {"ModelProvider": {"ModelProviderId": "mp-owned"}}}
        state = {}
        with patch.object(resources, "execute", return_value=(1, reply)):
            with self.assertRaises(RuntimeError):
                self.create("model-provider", state)
        self.assertEqual(json.loads(self.path.read_text())["ModelProviderId"], "mp-owned")

    def test_duplicate_create_stops_before_calling_agr(self):
        with patch.object(resources, "execute") as execute:
            with self.assertRaises(RuntimeError):
                self.create("model-provider", {"Region": "ap-chongqing", "ModelProviderId": "mp-owned"})
        execute.assert_not_called()

    def test_get_without_state_has_an_actionable_error(self):
        with patch.object(resources, "ROOT", self.root), patch.object(sys, "argv", ["resources.py", "get", "simple", "ToolId"]), patch.object(resources, "execute") as execute:
            with self.assertRaisesRegex(RuntimeError, "No saved ToolId"):
                resources.main()
        execute.assert_not_called()

    def test_failed_publish_retains_harness_and_bindings(self):
        replies = [(1, {"Status": "failed", "Failure": {"Code": "WAIT_FAILED", "Details": {"HarnessId": "hns-owned"}}}),
                   (0, {"Status": "succeeded", "Data": {"Harness": {"ResourceInfo": {"ToolId": "sdt-owned", "DeploymentId": "dpl-owned"}}}})]
        state = {}
        with patch.object(resources, "execute", side_effect=replies):
            with self.assertRaises(RuntimeError):
                self.create("harness", state)
        saved = json.loads(self.path.read_text())
        self.assertEqual((saved["HarnessId"], saved["ToolId"], saved["DeploymentId"]),
                         ("hns-owned", "sdt-owned", "dpl-owned"))
        self.assertNotIn("Pending", saved)

    def test_unknown_create_result_is_kept_and_not_reported_as_cleaned(self):
        state = {}
        with patch.object(resources, "execute", side_effect=RuntimeError("connection lost")):
            with self.assertRaises(RuntimeError):
                self.create("model-provider", state)
        self.assertEqual(state["Pending"]["Name"], "my-demo")
        args = argparse.Namespace(scenario="simple", yes=True, dry_run=False)
        with redirect_stdout(io.StringIO()), self.assertRaises(RuntimeError):
            resources.cleanup(args, self.path, state)
        self.assertNotIn("Cleaned", state)

    def test_permission_error_is_not_treated_as_missing(self):
        reply = {"Status": "failed", "Failure": {"Code": "AuthFailure.UnauthorizedOperation"}}
        with patch.object(resources, "execute", return_value=(1, reply)) as execute:
            with self.assertRaises(RuntimeError):
                resources.remove("ap-chongqing", ["tool", "delete", "sdt-owned"], ["tool", "get", "sdt-owned"])
        self.assertEqual(execute.call_count, 1)

    def test_cleanup_without_yes_fails_before_api_calls(self):
        args = argparse.Namespace(scenario="simple", yes=False, dry_run=False)
        with patch.object(resources, "execute") as execute, self.assertRaises(RuntimeError):
            resources.cleanup(args, self.path, {"Region": "ap-chongqing", "HarnessId": "hns-owned"})
        execute.assert_not_called()

    def test_dry_run_only_reads_the_recorded_harness(self):
        args = argparse.Namespace(scenario="simple", yes=False, dry_run=True)
        reply = {"Status": "succeeded", "Data": {"Harness": {"ResourceInfo": {"ToolId": "sdt-owned"}}}}
        with patch.object(resources, "execute", return_value=(0, reply)) as execute, redirect_stdout(io.StringIO()):
            resources.cleanup(args, self.path, {"Region": "ap-chongqing", "HarnessId": "hns-owned"})
        self.assertEqual(execute.call_args.args, ("ap-chongqing", ["harness", "get", "hns-owned"]))
        self.assertEqual(execute.call_count, 1)

    def test_failed_instance_is_not_treated_as_stopped(self):
        args = argparse.Namespace(scenario="simple", yes=True, dry_run=False)
        reply = {"Status": "succeeded", "Data": {"Items": [{"InstanceId": "instance-owned", "ToolId": "sdt-owned", "Status": "FAILED"}]}}
        state = {"Region": "ap-chongqing", "ToolId": "sdt-owned"}
        with patch.object(resources, "execute", return_value=(0, reply)) as execute, redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, "FAILED"):
                resources.cleanup(args, self.path, state)
        self.assertEqual(execute.call_count, 1)
        self.assertNotIn("Cleaned", state)

    def test_unrelated_instance_stops_cleanup_before_deletion(self):
        args = argparse.Namespace(scenario="simple", yes=True, dry_run=False)
        reply = {"Status": "succeeded", "Data": {"Items": [{"InstanceId": "instance-other", "ToolId": "sdt-other", "Status": "RUNNING"}]}}
        state = {"Region": "ap-chongqing", "ToolId": "sdt-owned"}
        with patch.object(resources, "execute", return_value=(0, reply)) as execute, redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, "recorded ToolId"):
                resources.cleanup(args, self.path, state)
        self.assertEqual(execute.call_count, 1)
        self.assertNotIn("Cleaned", state)

    def test_empty_credential_provider_skips_secret_delete(self):
        args = argparse.Namespace(scenario="tool-market", yes=True, dry_run=False)
        state = {"Region": "ap-chongqing", "ProviderId": "agc-owned"}
        present = True
        calls = []

        def execute(region, command):
            nonlocal present
            calls.append(command)
            if command[:3] == ["credential", "secret", "list"]:
                return 0, {"Status": "succeeded", "Data": {"TotalCount": 0, "ManagedSecretSet": []}}
            self.assertNotEqual(command[:3], ["credential", "secret", "delete"])
            if command[:3] == ["credential", "provider", "delete"]:
                present = False
            if not present and command[:3] == ["credential", "provider", "get"]:
                return 1, {"Status": "failed", "Failure": {"Code": "PROVIDER_NOT_FOUND"}}
            return 0, {"Status": "succeeded", "Data": {}}

        with patch.object(resources, "execute", side_effect=execute), redirect_stdout(io.StringIO()):
            resources.cleanup(args, self.path, state)
        self.assertTrue(state["Cleaned"])
        self.assertIn(["credential", "provider", "update", "agc-owned", "--status", "DISABLED"], calls)

    def test_cleanup_is_scoped_ordered_and_repeatable(self):
        state = {"Region": "ap-chongqing", "HarnessId": "hns-owned", "ToolId": "sdt-owned",
                 "DeploymentId": "dpl-owned", "ModelProviderId": "mp-owned", "SpaceId": "space-owned", "ProviderId": "agc-owned"}
        existing = {"harness", "deployment", "tool", "model-provider", "space", "credential-provider"}
        sessions = {"session-one", "session-two"}
        calls = []
        instance = "PAUSING"
        provider_disabled = False

        def execute(region, args):
            nonlocal instance, provider_disabled
            self.assertEqual(region, "ap-chongqing")
            calls.append(args)
            success = lambda data: (0, {"Status": "succeeded", "Data": data})
            not_found = (1, {"Status": "failed", "Failure": {"Code": "ResourceNotFound"}})
            if args[:2] == ["instance", "list"]:
                self.assertEqual(args[2:], ["--tool-id", "sdt-owned", "--all"])
                current = instance
                if instance == "PAUSING":
                    instance = "PAUSED"
                return success({"Items": [{"InstanceId": "instance-owned", "ToolId": "sdt-owned", "Status": current}]})
            if args[:2] == ["instance", "delete"]:
                self.assertEqual(args[2], "instance-owned")
                instance = "STOPPED"
                return success({})
            if args[:2] == ["session", "list"]:
                self.assertIn("space-owned", args)
                self.assertIn("hns-owned", args)
                return success({"Sessions": [{"SessionId": item} for item in sorted(sessions)]})
            if args[:2] == ["session", "delete"]:
                sessions.remove(args[args.index("--session-id") + 1])
                return success({})
            if args[:2] == ["credential", "secret"]:
                self.assertIn("agc-owned", args)
                if args[2] == "list":
                    self.assertEqual(args[-4:], ["--user-ids", "harness-market", "--filter", "scope=github"])
                    return success({"TotalCount": 1, "ManagedSecretSet": [{"Scope": "github"}]})
                self.assertEqual(args[-4:], ["--user-id", "harness-market", "--scope", "github"])
                return success({})
            if args[:2] == ["session", "space"]:
                kind, verb = "space", args[2]
            elif args[:2] == ["credential", "provider"]:
                kind, verb = "credential-provider", args[2]
            else:
                kind, verb = args[:2]
            if kind not in existing:
                if kind == "credential-provider":
                    return 1, {"Status": "failed", "Failure": {"Code": "PROVIDER_NOT_FOUND"}}
                return not_found
            if kind == "credential-provider" and verb == "update":
                self.assertEqual(args[-2:], ["--status", "DISABLED"])
                provider_disabled = True
                return success({})
            if verb == "delete":
                if kind == "credential-provider":
                    self.assertTrue(provider_disabled)
                existing.remove(kind)
                return success({})
            if kind == "harness":
                return success({"Harness": {"ResourceInfo": {"ToolId": "sdt-owned", "DeploymentId": "dpl-owned"}}})
            return success({})

        args = argparse.Namespace(scenario="simple", yes=True, dry_run=False)
        with patch.object(resources, "execute", side_effect=execute), patch.object(resources.time, "sleep"), redirect_stdout(io.StringIO()):
            resources.cleanup(args, self.path, state)
            first_count = len(calls)
            resources.cleanup(args, self.path, state)
        self.assertTrue(state["Cleaned"])
        self.assertFalse(existing)
        self.assertFalse(sessions)
        self.assertFalse(any("delete" in call for call in calls[first_count:]))
        verbs = [call[:2] for call in calls]
        self.assertLess(verbs.index(["harness", "delete"]), verbs.index(["instance", "delete"]))
        self.assertLess(verbs.index(["instance", "delete"]), verbs.index(["tool", "delete"]))
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
