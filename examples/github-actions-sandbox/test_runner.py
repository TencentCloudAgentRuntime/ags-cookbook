from __future__ import annotations

import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
import unittest

from runner import (
    REMOTE_EXIT_CODE,
    build_workspace_archive,
    run_in_sandbox,
    validate_artifact_path,
)


class Result:
    def __init__(self, exit_code: int = 0, stdout: str = "", stderr: str = ""):
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr


class FakeFiles:
    def __init__(self, workload_exit_code: int = 0):
        self.writes: dict[str, bytes] = {}
        self.workload_exit_code = workload_exit_code

    def write(self, path: str, content: bytes) -> None:
        self.writes[path] = content

    def read(self, path: str, format: str = "text") -> bytes | str:
        if path == REMOTE_EXIT_CODE:
            return str(self.workload_exit_code)
        del format
        return b"fake-artifact"


class FakeCommands:
    def __init__(self, workload_exit_code: int = 0):
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.workload_exit_code = workload_exit_code

    def run(self, command: str, **kwargs: object) -> Result:
        self.calls.append((command, kwargs))
        if command.startswith("bash -lc"):
            return Result(stdout="workload output\n")
        return Result()


class FakeSandbox:
    sandbox_id = "sandbox-test-123"

    def __init__(self, workload_exit_code: int = 0):
        self.files = FakeFiles(workload_exit_code)
        self.commands = FakeCommands(workload_exit_code)
        self.killed = False

    def kill(self) -> None:
        self.killed = True


class CleanupFailingSandbox(FakeSandbox):
    def kill(self) -> None:
        raise RuntimeError("cleanup unavailable")


class RunnerTests(unittest.TestCase):
    def test_archive_excludes_git_and_dotenv_but_keeps_example(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".git").mkdir()
            (root / ".git" / "config").write_text("secret", encoding="utf-8")
            (root / ".env").write_text("SECRET=value", encoding="utf-8")
            (root / ".env.local").write_text("SECRET=value", encoding="utf-8")
            (root / ".env.example").write_text("SECRET=", encoding="utf-8")
            (root / "main.py").write_text("print('ok')", encoding="utf-8")

            payload = build_workspace_archive(root)
            with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
                names = set(archive.getnames())

            self.assertIn("main.py", names)
            self.assertIn(".env.example", names)
            self.assertNotIn(".env", names)
            self.assertNotIn(".env.local", names)
            self.assertFalse(any(name.startswith(".git") for name in names))

    def test_rejects_unsafe_artifact_paths(self) -> None:
        for value in ("", "/tmp/output", "../output", "a/../../output"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_artifact_path(value)

    def test_success_writes_report_downloads_artifact_and_kills(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            output = root / "result"
            workspace.mkdir()
            (workspace / "README.md").write_text("demo", encoding="utf-8")
            sandbox = FakeSandbox()

            exit_code = run_in_sandbox(
                workspace=workspace,
                command="python task.py",
                artifact_path="output",
                output_dir=output,
                template="code-interpreter-v1",
                sandbox_timeout=60,
                command_timeout=30,
                sandbox_factory=lambda **kwargs: sandbox,
            )

            self.assertEqual(exit_code, 0)
            self.assertTrue(sandbox.killed)
            self.assertEqual((output / "artifacts.tar.gz").read_bytes(), b"fake-artifact")
            report = json.loads((output / "run-report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "succeeded")
            self.assertEqual(report["cleanup"], "killed")
            self.assertEqual(report["sandbox_id"], "sandbox-test-123")
            self.assertNotIn("python task.py", json.dumps(report))

    def test_only_explicit_environment_is_forwarded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            workspace.mkdir()
            (workspace / "file").write_text("x", encoding="utf-8")
            sandbox = FakeSandbox()
            os.environ["SAFE_TEST_VALUE"] = "forward-me"
            self.addCleanup(os.environ.pop, "SAFE_TEST_VALUE", None)

            run_in_sandbox(
                workspace=workspace,
                command="true",
                artifact_path="output",
                output_dir=root / "result",
                template="test",
                sandbox_timeout=60,
                command_timeout=30,
                env_names=["SAFE_TEST_VALUE"],
                sandbox_factory=lambda **kwargs: sandbox,
            )

            workload_call = next(
                call for call in sandbox.commands.calls if call[0].startswith("bash -lc")
            )
            self.assertEqual(workload_call[1]["envs"], {"SAFE_TEST_VALUE": "forward-me"})

    def test_workload_failure_is_propagated_and_cleaned_up(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            output = root / "result"
            workspace.mkdir()
            (workspace / "file").write_text("x", encoding="utf-8")
            sandbox = FakeSandbox(workload_exit_code=7)

            exit_code = run_in_sandbox(
                workspace=workspace,
                command="exit 7",
                artifact_path="output",
                output_dir=output,
                template="test",
                sandbox_timeout=60,
                command_timeout=30,
                sandbox_factory=lambda **kwargs: sandbox,
            )

            report = json.loads((output / "run-report.json").read_text(encoding="utf-8"))
            self.assertEqual(exit_code, 7)
            self.assertEqual(report["status"], "workload_failed")
            self.assertEqual(report["exit_code"], 7)
            self.assertEqual(report["cleanup"], "killed")
            self.assertTrue(sandbox.killed)

    def test_cleanup_failure_fails_the_wrapper(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            output = root / "result"
            workspace.mkdir()
            (workspace / "file").write_text("x", encoding="utf-8")
            sandbox = CleanupFailingSandbox()

            exit_code = run_in_sandbox(
                workspace=workspace,
                command="true",
                artifact_path="output",
                output_dir=output,
                template="test",
                sandbox_timeout=60,
                command_timeout=30,
                sandbox_factory=lambda **kwargs: sandbox,
            )

            report = json.loads((output / "run-report.json").read_text(encoding="utf-8"))
            self.assertEqual(exit_code, 2)
            self.assertEqual(report["status"], "cleanup_failed")
            self.assertEqual(report["cleanup"], "failed")
            self.assertEqual(report["workload_exit_code"], 0)


if __name__ == "__main__":
    unittest.main()
