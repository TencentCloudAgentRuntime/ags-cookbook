import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parent.parent


class EndpointCleanupTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / "scripts").mkdir()
        shutil.copyfile(ROOT / "scripts/resources.py", self.root / "scripts/resources.py")
        shutil.copyfile(ROOT / "Makefile", self.root / "Makefile")
        self.bin = self.root / "bin"
        self.bin.mkdir()
        (self.bin / "python3").symlink_to(sys.executable)
        self.remote = self.root / "remote"
        self.trace = self.root / "trace.jsonl"
        self.config = self.root / "cli-endpoint"
        self.state = self.root / ".state/simple.json"
        self.make = shutil.which("make")
        self.assertIsNotNone(self.make, "make is required to test the cleanup target")
        self.env = {**os.environ, "PATH": str(self.bin), "AGR_REGION": "ap-chongqing",
                    "FAKE_ROOT": str(self.root)}
        self.env.pop("AGR_CLOUD_ENDPOINT", None)
        agr = self.bin / "agr"
        agr.write_text("#!" + sys.executable + "\n" + '''import json, os, pathlib, sys
args = sys.argv[1:]
root = pathlib.Path(os.environ["FAKE_ROOT"])
endpoint = os.environ.get("AGR_CLOUD_ENDPOINT") or ((root / "cli-endpoint").read_text() if (root / "cli-endpoint").exists() else "default.example.test")
if "--cloud-endpoint" in args:
    endpoint = args[args.index("--cloud-endpoint") + 1]
with (root / "trace.jsonl").open("a") as stream:
    stream.write(json.dumps({"Command": args[:2], "Args": args, "Endpoint": endpoint,
                             "EnvLoaded": os.environ.get("CLEANUP_ENV_LOADED")}) + "\\n")
if args[:2] == ["config", "show"]:
    data = {} if os.environ.get("FAKE_BAD_CONFIG") else {"Values": {"cloud_endpoint": {"Value": endpoint}}}
    print(json.dumps({"Status": "succeeded", "Data": data}))
    sys.exit(0)
remote = root / "remote"
if args[:2] == ["model-provider", "create"]:
    remote.write_text(endpoint)
    print(json.dumps({"Status": "succeeded", "Data": {"ModelProvider": {"ModelProviderId": "mp-owned"}}}))
    sys.exit(0)
if not remote.exists() or remote.read_text() != endpoint:
    print(json.dumps({"Status": "failed", "Failure": {"Code": "ResourceNotFound.ModelProviderNotFound", "Kind": "not_found"}}))
    sys.exit(1)
if args[:2] == ["model-provider", "delete"]:
    remote.unlink()
print(json.dumps({"Status": "succeeded", "Data": {}}))
''')
        agr.chmod(0o700)

    def run_helper(self, *args):
        return subprocess.run([sys.executable, str(self.root / "scripts/resources.py"), *args],
                              cwd=self.root, env=self.env, text=True, capture_output=True)

    def create(self, endpoint="fixture.example.test"):
        self.env["AGR_CLOUD_ENDPOINT"] = endpoint
        result = self.run_helper("create", "simple", "model-provider", "--name", "review")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.state.read_text())["CloudEndpoint"], endpoint)
        created = json.loads(self.trace.read_text().splitlines()[-1])
        self.assertEqual(created["Command"], ["model-provider", "create"])
        self.assertIn("--cloud-endpoint", created["Args"])
        self.env.pop("AGR_CLOUD_ENDPOINT")

    def cleanup(self, entry):
        if entry == "direct":
            return self.run_helper("cleanup", "simple", "--yes")
        return subprocess.run([self.make, "cleanup", "SCENARIO=simple"], cwd=self.root,
                              env=self.env, text=True, capture_output=True)

    def assert_cleaned_at(self, endpoint, entry):
        before = len(self.trace.read_text().splitlines())
        result = self.cleanup(entry)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.remote.exists(), "Cleanup reported success but left the original resource")
        state = json.loads(self.state.read_text())
        self.assertTrue(state["Cleaned"])
        self.assertEqual(state["CloudEndpoint"], endpoint)
        calls = [json.loads(line) for line in self.trace.read_text().splitlines()[before:]]
        self.assertIn(["model-provider", "delete"], [call["Command"] for call in calls])
        for call in calls:
            self.assertEqual(call["Endpoint"], endpoint)
            self.assertIn("--cloud-endpoint", call["Args"])
        result = self.cleanup(entry)
        self.assertEqual(result.returncode, 0, result.stderr)
        return calls

    def test_direct_cleanup_keeps_the_creation_endpoint_in_a_fresh_terminal(self):
        self.create()
        self.assert_cleaned_at("fixture.example.test", "direct")

    def test_make_cleanup_loads_env_and_keeps_the_creation_endpoint(self):
        self.create()
        (self.root / ".env").write_text("AGR_CLOUD_ENDPOINT=fixture.example.test\nCLEANUP_ENV_LOADED=1\n")
        calls = self.assert_cleaned_at("fixture.example.test", "make")
        self.assertTrue(all(call["EnvLoaded"] == "1" for call in calls))

    def test_both_cleanup_entries_ignore_later_cli_config_and_env_changes(self):
        for entry in ("direct", "make"):
            with self.subTest(entry=entry):
                self.config.write_text("original.example.test")
                result = self.run_helper("create", "simple", "model-provider", "--name", "review")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.config.write_text("different.example.test")
                (self.root / ".env").write_text("AGR_CLOUD_ENDPOINT=other.example.test\n")
                self.assert_cleaned_at("original.example.test", entry)

    def test_both_cleanup_entries_preserve_legacy_state_without_guessing(self):
        self.create()
        state = json.loads(self.state.read_text())
        state.pop("CloudEndpoint", None)
        self.state.write_text(json.dumps(state))
        original = self.state.read_bytes()
        before = self.trace.read_bytes()
        for entry in ("direct", "make"):
            with self.subTest(entry=entry):
                result = self.cleanup(entry)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("CloudEndpoint", result.stderr)
                self.assertEqual(self.state.read_bytes(), original)
                self.assertEqual(self.trace.read_bytes(), before)
                self.assertTrue(self.remote.exists())

    def test_default_endpoint_is_recorded_before_cli_config_changes(self):
        result = self.run_helper("create", "simple", "model-provider", "--name", "review")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.config.write_text("different.example.test")
        self.assert_cleaned_at("default.example.test", "direct")

    def test_create_stops_if_effective_endpoint_is_unknown(self):
        self.env["FAKE_BAD_CONFIG"] = "1"
        result = self.run_helper("create", "simple", "model-provider", "--name", "review")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cloud_endpoint", result.stderr)
        self.assertFalse(self.state.exists())
        self.assertFalse(self.remote.exists())
        calls = [json.loads(line)["Command"] for line in self.trace.read_text().splitlines()]
        self.assertEqual(calls, [["config", "show"]])


if __name__ == "__main__":
    unittest.main()
