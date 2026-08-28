import importlib.util
import unittest
from pathlib import Path
from unittest import mock


EXAMPLE_ROOT = Path(__file__).resolve().parents[1]
SETUP_HELPER_PATH = (
    EXAMPLE_ROOT
    / "overlay"
    / "OSWorld"
    / "desktop_env"
    / "providers"
    / "ags"
    / "sandbox_setup.py"
)


def load_setup_module():
    spec = importlib.util.spec_from_file_location("ags_osworld_sandbox_setup", SETUP_HELPER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self.payload = payload
        self.text = text

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class SandboxSetupTest(unittest.TestCase):
    def setUp(self):
        self.module = load_setup_module()

    def test_execute_shell_accepts_zero_returncode(self):
        response = FakeResponse(
            payload={"status": "success", "returncode": 0, "output": "ready", "error": ""}
        )
        with mock.patch.object(self.module.requests, "post", return_value=response) as post:
            result = self.module.execute_shell(
                "http://localhost:15000/setup/execute",
                "true",
                label="preflight",
            )

        self.assertEqual(result["output"], "ready")
        self.assertEqual(post.call_args.kwargs["json"], {"command": "true", "shell": True})

    def test_execute_shell_rejects_nonzero_returncode_even_on_http_200(self):
        response = FakeResponse(
            payload={"status": "success", "returncode": 127, "output": "", "error": "not found"}
        )
        with mock.patch.object(self.module.requests, "post", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "returncode=127"):
                self.module.execute_shell(
                    "http://localhost:15000/setup/execute",
                    "missing-command",
                    label="install wrapper",
                )

    def test_execute_shell_rejects_missing_returncode(self):
        response = FakeResponse(payload={"status": "success", "output": "ambiguous"})
        with mock.patch.object(self.module.requests, "post", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "returncode=None"):
                self.module.execute_shell(
                    "http://localhost:15000/setup/execute",
                    "true",
                    label="preflight",
                )

    def test_upload_file_rejects_http_error(self):
        response = FakeResponse(status_code=404, text="missing route")
        with mock.patch.object(self.module.requests, "post", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "HTTP 404"):
                self.module.upload_file(
                    "http://localhost:15000/setup/upload",
                    "/tmp/proxy.py",
                    "proxy.py",
                    b"content",
                )


if __name__ == "__main__":
    unittest.main()
