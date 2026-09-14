from __future__ import annotations

import io
from contextlib import redirect_stderr, redirect_stdout
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from runner import (
    REMOTE_EXIT_CODE,
    REMOTE_ARCHIVE,
    REMOTE_ARTIFACT,
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

    def exists(self, path: str) -> bool:
        return True

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
            if "on_stdout" in kwargs:
                kwargs["on_stdout"]("workload output\n")
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
    def test_candidate_evaluation_reports_success_failure_and_import_error(self) -> None:
        workload = Path(__file__).parent / "workload"
        for source, expected_code, field in (
            # Never read the replaceable user candidate into a host-side test.
            ("def unique_in_order(values): return list(dict.fromkeys(values))\n", 0, None),
            ("def unique_in_order(values): return []\n", 1, "failures"),
            ("raise RuntimeError('candidate import failed')\n", 1, "errors"),
        ):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                candidate = root / "candidate.py"
                candidate.write_text(source)
                completed = subprocess.run(
                    [sys.executable, str(workload / "ci_task.py"), "--candidate", str(candidate), "--output-dir", str(root / "output")],
                    capture_output=True, text=True,
                )
                self.assertEqual(completed.returncode, expected_code, completed.stderr)
                report = json.loads((root / "output/result.json").read_text())
                self.assertEqual(report["tests"], 5)
                if field:
                    self.assertGreater(report[field], 0)
                else:
                    self.assertEqual(report["status"], "passed")
                import xml.etree.ElementTree as ET
                xml = ET.parse(root / "output/junit.xml").getroot()
                self.assertEqual(len(xml.findall("testcase")), 5)
                self.assertEqual(int(xml.attrib["failures"]), report["failures"])
                self.assertEqual(int(xml.attrib["errors"]), report["errors"])

    def test_local_evaluation_tests_do_not_execute_replaceable_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            example = Path(__file__).parent
            (root / "workload").mkdir()
            for name in ("test_runner.py", "runner.py", "workload/ci_task.py"):
                shutil.copyfile(example / name, root / name)
            marker = root / "candidate-executed"
            (root / "workload/candidate.py").write_text(
                f"from pathlib import Path\nPath({str(marker)!r}).touch()\n"
                "raise RuntimeError('replaceable candidate must not run on host')\n"
            )
            completed = subprocess.run(
                [sys.executable, "-m", "unittest",
                 "test_runner.RunnerTests.test_candidate_evaluation_reports_success_failure_and_import_error"],
                cwd=root, capture_output=True, text=True, timeout=30,
            )
            self.assertFalse(marker.exists(), "local tests executed the replaceable candidate")
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_reused_output_removes_only_owned_files(self) -> None:
        for failure in ("missing", "download", "create"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.assertEqual(self.invoke(root, FakeSandbox()), 0)
                output = root / "ags-results"
                (output / "keep.txt").write_text("user file")
                sandbox = FakeSandbox()
                if failure == "missing":
                    with patch.object(sandbox.files, "exists", return_value=False):
                        self.assertEqual(self.invoke(root, sandbox), 0)
                elif failure == "download":
                    original_read = sandbox.files.read
                    def read(path, **kwargs):
                        if path == REMOTE_ARTIFACT:
                            raise ConnectionError("download interrupted")
                        return original_read(path, **kwargs)
                    with patch.object(sandbox.files, "read", side_effect=read):
                        self.assertEqual(self.invoke(root, sandbox), 2)
                else:
                    with patch("runner.build_workspace_archive", side_effect=OSError("archive failed")):
                        self.assertEqual(self.invoke(root, sandbox), 2)
                self.assertFalse((output / "artifacts.tar.gz").exists())
                self.assertEqual((output / "keep.txt").read_text(), "user file")
                report = json.loads((output / "run-report.json").read_text())
                self.assertNotIn("artifact_archive", report)

    def test_partial_logs_survive_command_failure_without_duplication(self) -> None:
        for failure in (None, TimeoutError("timed out"), ConnectionError("disconnected")):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                sandbox = FakeSandbox()
                stdout, stderr = io.StringIO(), io.StringIO()
                def run(command, **kwargs):
                    if command.startswith("bash -lc"):
                        kwargs["on_stdout"]("partial progress\n")
                        kwargs["on_stderr"]("partial diagnostic\n")
                        self.assertIn("partial progress", stdout.getvalue())
                        self.assertIn("partial diagnostic", stderr.getvalue())
                        if failure:
                            raise failure
                        return Result(stdout="partial progress\n", stderr="partial diagnostic\n")
                    return Result()
                with patch.object(sandbox.commands, "run", side_effect=run), redirect_stdout(stdout), redirect_stderr(stderr):
                    self.assertEqual(self.invoke(Path(directory), sandbox), 2 if failure else 0)
                self.assertEqual(stdout.getvalue().count("partial progress"), 1)
                self.assertEqual(stderr.getvalue().count("partial diagnostic"), 1)
                self.assertTrue(sandbox.killed)

    def invoke(self, root: Path, sandbox: FakeSandbox, output: Path | None = None) -> int:
        return run_in_sandbox(
            workspace=root,
            command="true",
            artifact_path="output",
            output_dir=output if output is not None else root / "ags-results",
            template="test",
            sandbox_timeout=60,
            command_timeout=30,
            sandbox_factory=lambda **kwargs: sandbox,
        )

    def test_artifact_read_failure_is_not_success(self) -> None:
        for workload_code in (0, 7):
            with self.subTest(workload_code=workload_code), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                sandbox = FakeSandbox(workload_code)
                original_read = sandbox.files.read

                def read(path, **kwargs):
                    if path == REMOTE_ARTIFACT:
                        raise ConnectionError("synthetic download failure")
                    return original_read(path, **kwargs)

                with patch.object(sandbox.files, "read", side_effect=read), patch.dict(
                    os.environ, {"GITHUB_OUTPUT": str(root / "github-output")}
                ):
                    code = self.invoke(root, sandbox)
                report = json.loads((root / "ags-results/run-report.json").read_text())
                self.assertEqual(code, 2)
                self.assertEqual(report["status"], "infrastructure_error")
                self.assertEqual(report["exit_code"], 2)
                self.assertEqual(report["workload_exit_code"], workload_code)
                self.assertEqual(report["error_type"], "ConnectionError")
                self.assertEqual(report["cleanup"], "killed")
                self.assertTrue(sandbox.killed)
                self.assertIn("exit-code=2\n", (root / "github-output").read_text())

    def test_existing_artifact_packaging_failure_is_fatal(self) -> None:
        failures = (
            ConnectionError("synthetic command transport failure"),
            Result(1, stderr="tar: file changed as we read it"),
            Result(2, stderr="tar: write error: No space left on device"),
            Result(2, stderr="tar: output: Cannot open: Permission denied"),
        )
        for failure in failures:
            with self.subTest(failure=type(failure).__name__), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                sandbox = FakeSandbox()
                original_run = sandbox.commands.run

                def run(command, **kwargs):
                    if command.startswith("tar -czf"):
                        if isinstance(failure, Exception):
                            raise failure
                        return failure
                    return original_run(command, **kwargs)

                stderr = io.StringIO()
                with patch.object(sandbox.commands, "run", side_effect=run), \
                        patch.object(sandbox.files, "exists", return_value=True) as exists, \
                        patch.object(sandbox.files, "read", wraps=sandbox.files.read) as read, \
                        redirect_stderr(stderr):
                    code = self.invoke(root, sandbox)
                report = json.loads((root / "ags-results/run-report.json").read_text())
                exists.assert_called_once_with("/tmp/ags-workspace/output")
                self.assertTrue(sandbox.killed)
                self.assertEqual(code, 2)
                self.assertEqual(report["exit_code"], 2)
                self.assertEqual(report["workload_exit_code"], 0)
                self.assertEqual(report["status"], "infrastructure_error")
                self.assertNotIn("artifact_warning", report)
                self.assertNotIn("artifact_archive", report)
                self.assertFalse(any(c.args[0] == REMOTE_ARTIFACT for c in read.call_args_list))
                if isinstance(failure, Result):
                    self.assertIn(failure.stderr, stderr.getvalue())

    def test_missing_artifact_skips_tar_and_preserves_workload_result(self) -> None:
        for workload_code in (0, 7):
            with self.subTest(workload_code=workload_code), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                sandbox = FakeSandbox(workload_code)
                with patch.object(sandbox.files, "exists", return_value=False), \
                        patch.object(sandbox.files, "read", wraps=sandbox.files.read) as read:
                    code = self.invoke(root, sandbox)
                report = json.loads((root / "ags-results/run-report.json").read_text())
                self.assertEqual(code, workload_code)
                self.assertEqual(report["workload_exit_code"], workload_code)
                self.assertEqual(report["status"], "succeeded" if workload_code == 0 else "workload_failed")
                self.assertIn("artifact_warning", report)
                self.assertNotIn("error", report)
                self.assertFalse(any(cmd.startswith("tar -czf") for cmd, _ in sandbox.commands.calls))
                self.assertFalse(any(c.args[0] == REMOTE_ARTIFACT for c in read.call_args_list))
                self.assertTrue(sandbox.killed)

    def test_artifact_existence_check_failure_is_fatal(self) -> None:
        for failure in (PermissionError("access denied"), ConnectionError("disconnected")):
            with self.subTest(failure=type(failure).__name__), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                sandbox = FakeSandbox()
                with patch.object(sandbox.files, "exists", side_effect=failure):
                    code = self.invoke(root, sandbox)
                report = json.loads((root / "ags-results/run-report.json").read_text())
                self.assertEqual(code, 2)
                self.assertEqual(report["status"], "infrastructure_error")
                self.assertNotIn("artifact_warning", report)
                self.assertTrue(sandbox.killed)

    def test_repeated_runs_exclude_only_the_actual_output_subtree(self) -> None:
        for relative in (Path("ags-results"), Path("nested/custom-results")):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                sibling = root / "source" / relative.name
                sibling.mkdir(parents=True)
                (sibling / "keep.txt").write_text("keep this source")
                output = root / relative
                self.assertEqual(self.invoke(root, FakeSandbox(), output), 0)
                second = FakeSandbox()
                self.assertEqual(self.invoke(root, second, output), 0)
                with tarfile.open(fileobj=io.BytesIO(second.files.writes[REMOTE_ARCHIVE]), mode="r:gz") as archive:
                    names = archive.getnames()
                self.assertFalse(any(Path(n).is_relative_to(relative) for n in names))
                self.assertIn((sibling / "keep.txt").relative_to(root).as_posix(), names)

    def test_output_outside_workspace_does_not_exclude_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "source"
            workspace.mkdir()
            (workspace / "keep.txt").write_text("keep")
            for output in (root / "results", root):
                with tarfile.open(fileobj=io.BytesIO(build_workspace_archive(workspace, output_dir=output)), mode="r:gz") as archive:
                    self.assertIn("keep.txt", archive.getnames())

    def test_output_equal_to_workspace_is_rejected_before_creation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for output in (root, root / "nested/.."):
                with self.subTest(output=output), self.assertRaisesRegex(ValueError, "must differ"):
                    self.invoke(root, FakeSandbox(), output)

    def test_make_passes_literal_commands_and_paths_to_python(self) -> None:
        example = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sentinel = root / "host-executed"
            # Stand in for uv so the real Make recipe reaches the real CLI parser
            # without creating a sandbox or executing any workload.
            uv = root / "uv"
            uv.write_text(
                f"#!{sys.executable}\n"
                "import json, sys\n"
                f"sys.path.insert(0, {str(example)!r})\n"
                "from main import parser\n"
                "args = parser().parse_args(sys.argv[4:])\n"
                "print('CAPTURE=' + json.dumps(vars(args), default=str))\n"
            )
            uv.chmod(0o700)
            commands = [
                'python -c "print(1)"',
                'printf \'%s\\n\' "$VALUE" | tee output.txt',
                f'echo `touch {sentinel}`',
                f'echo $(touch {sentinel})',
                f'echo $(shell touch {sentinel})',
                "printf 'first\\n'\nprintf 'second\\n'",
            ]
            env = {"PATH": str(root) + os.pathsep + os.defpath}
            for command in commands:
                for source in ("argument", "environment"):
                    with self.subTest(command=command, source=source):
                        args = ["make", "--no-print-directory", "run"]
                        run_env = dict(env)
                        if source == "argument":
                            args.append("COMMAND=" + command)
                        else:
                            run_env["COMMAND"] = command
                        workspace = 'folder with "quotes" and $literal'
                        args += ["WORKSPACE=" + workspace, "OUTPUT_DIR=custom results", "ARTIFACT_PATH=output files"]
                        result = subprocess.run(args, cwd=example, env=run_env, text=True, capture_output=True)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        captured = json.loads(next(line.removeprefix("CAPTURE=") for line in result.stdout.splitlines() if line.startswith("CAPTURE=")))
                        self.assertEqual(captured["command"], command)
                        self.assertEqual(captured["workspace"], workspace)
                        self.assertEqual(captured["output_dir"], "custom results")
                        self.assertEqual(captured["artifact_path"], "output files")
                        self.assertFalse(sentinel.exists(), "command executed on host")

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
