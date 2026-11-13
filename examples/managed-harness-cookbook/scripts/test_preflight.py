import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("preflight.sh")


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.bin = Path(self.directory.name)
        self.calls = self.bin / "calls"
        (self.bin / "python3").symlink_to(sys.executable)
        self.command("agr", 'printf "%s\\n" "$*" >> "$PREFLIGHT_CALLS"\n'
                     'if [ "$1" = version ]; then echo \'{"Status":"succeeded","Data":{"Channel":"preview"}}\'; fi')
        self.command("curl")
        self.env = {**os.environ, "PATH": str(self.bin), "PREFLIGHT_CALLS": str(self.calls),
                    "AGR_REGION": "ap-chongqing", "AGR_ROLE_ARN": "qcs::cam::uin/100000000001:roleName/demo",
                    "HARNESS_SUBNET_ID": "subnet-demo", "HARNESS_SECURITY_GROUP_ID": "sg-demo",
                    "TOKENHUB_API_KEY_ID": "ak-demo", "HARNESS_NAME_SUFFIX": "demo"}

    def command(self, name, body="exit 0"):
        path = self.bin / name
        path.write_text("#!/bin/sh\n" + body + "\n")
        path.chmod(0o700)

    def run_preflight(self, scenario="connect"):
        return subprocess.run(["/bin/bash", str(SCRIPT), scenario], env=self.env, text=True, capture_output=True)

    def test_missing_node_and_npx_warns_and_still_runs_doctor(self):
        result = self.run_preflight()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("optional acpx", result.stderr)
        self.assertIn("doctor --region ap-chongqing -o text", self.calls.read_text())

    def test_old_node_warns_without_blocking_other_connections(self):
        self.command("node", "exit 1")
        self.command("npx")
        result = self.run_preflight()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Node.js 22.13", result.stderr)

    def test_supported_node_and_npx_need_no_warning(self):
        self.command("node")
        self.command("npx")
        result = self.run_preflight()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")

    def test_missing_curl_still_blocks_connect(self):
        (self.bin / "curl").unlink()
        result = self.run_preflight()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing for connect: curl", result.stderr)
        self.assertNotIn("doctor", self.calls.read_text())

    def test_missing_required_value_still_blocks_connect(self):
        self.env.pop("AGR_ROLE_ARN")
        result = self.run_preflight()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("AGR_ROLE_ARN", result.stderr)
        self.assertFalse(self.calls.exists())


if __name__ == "__main__":
    unittest.main()
