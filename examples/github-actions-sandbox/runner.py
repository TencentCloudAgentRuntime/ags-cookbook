from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import shlex
import tarfile
import time
from typing import Any, Callable, Iterable


REMOTE_ARCHIVE = "/tmp/ags-workspace.tar.gz"
REMOTE_WORKSPACE = "/tmp/ags-workspace"
REMOTE_ARTIFACT = "/tmp/ags-artifacts.tar.gz"
REMOTE_EXIT_CODE = "/tmp/ags-workload-exit-code"
DEFAULT_EXCLUDES = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}


def should_exclude(relative_path: Path, extra_excludes: set[str]) -> bool:
    parts = relative_path.parts
    if any(part in DEFAULT_EXCLUDES or part in extra_excludes for part in parts):
        return True
    return any(
        part == ".env" or (part.startswith(".env.") and part != ".env.example")
        for part in parts
    )


def build_workspace_archive(
    workspace: Path, excludes: Iterable[str] = (), *, output_dir: Path | None = None
) -> bytes:
    workspace = workspace.resolve()
    if not workspace.is_dir():
        raise ValueError(f"workspace is not a directory: {workspace}")
    output_dir = output_dir.resolve() if output_dir is not None else None
    if output_dir == workspace:
        raise ValueError("output directory must differ from workspace")

    extra_excludes = set(excludes)

    def excluded(path: Path) -> bool:
        return should_exclude(path.relative_to(workspace), extra_excludes) or (
            output_dir is not None
            and output_dir.is_relative_to(workspace)
            and path.resolve().is_relative_to(output_dir)
        )

    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for directory, dirs, files in os.walk(workspace, followlinks=False):
            root = Path(directory)
            dirs[:] = sorted(name for name in dirs if not excluded(root / name))
            for name in sorted(dirs + files):
                path = root / name
                if not excluded(path):
                    archive.add(path, arcname=path.relative_to(workspace).as_posix(), recursive=False)
    return buffer.getvalue()


def validate_artifact_path(value: str) -> str:
    path = PurePosixPath(value)
    if path.is_absolute() or not value or ".." in path.parts:
        raise ValueError("artifact path must be a non-empty relative path without '..'")
    return path.as_posix()


def forwarded_environment(names: Iterable[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for name in names:
        if not name or "=" in name:
            raise ValueError(f"invalid environment variable name: {name!r}")
        if name not in os.environ:
            raise ValueError(f"environment variable is not set: {name}")
        values[name] = os.environ[name]
    return values


def _run_allow_failure(commands: Any, command: str, **kwargs: Any) -> Any:
    try:
        return commands.run(command, **kwargs)
    except Exception as exc:
        if hasattr(exc, "exit_code"):
            return exc
        raise


def _print_command_output(result: Any) -> None:
    stdout = str(getattr(result, "stdout", "") or "")
    stderr = str(getattr(result, "stderr", "") or "")
    if stdout:
        print(stdout, end="" if stdout.endswith("\n") else "\n")
    if stderr:
        print(stderr, end="" if stderr.endswith("\n") else "\n", file=os.sys.stderr)


def _write_github_outputs(sandbox_id: str, exit_code: int, output_dir: Path) -> None:
    github_output = os.getenv("GITHUB_OUTPUT")
    if not github_output:
        return
    with Path(github_output).open("a", encoding="utf-8") as output:
        output.write(f"sandbox-id={sandbox_id}\n")
        output.write(f"exit-code={exit_code}\n")
        output.write(f"result-dir={output_dir}\n")


def run_in_sandbox(
    *,
    workspace: Path,
    command: str,
    artifact_path: str,
    output_dir: Path,
    template: str,
    sandbox_timeout: int,
    command_timeout: int,
    env_names: Iterable[str] = (),
    excludes: Iterable[str] = (),
    sandbox_factory: Callable[..., Any] | None = None,
) -> int:
    """Upload a checkout, run one command in a fresh AGS sandbox, and collect results."""
    if not command.strip():
        raise ValueError("command must not be empty")
    artifact_path = validate_artifact_path(artifact_path)
    envs = forwarded_environment(env_names)
    workspace = workspace.resolve()
    output_dir = output_dir.resolve()
    if output_dir == workspace:
        raise ValueError("output directory must differ from workspace")
    output_dir.mkdir(parents=True, exist_ok=True)

    if sandbox_factory is None:
        from e2b import Sandbox

        sandbox_factory = Sandbox.create

    started_at = time.time()
    command_digest = hashlib.sha256(command.encode("utf-8")).hexdigest()
    report: dict[str, Any] = {
        "schema_version": 1,
        "status": "infrastructure_error",
        "template": template,
        "command_sha256": command_digest,
        "forwarded_environment_names": sorted(envs),
        "artifact_path": artifact_path,
        "sandbox_id": None,
        "exit_code": 2,
        "workload_exit_code": None,
        "cleanup": "not_created",
    }
    sandbox = None
    return_code = 2

    try:
        archive = build_workspace_archive(workspace, excludes, output_dir=output_dir)
        report["workspace_archive_bytes"] = len(archive)

        print(f"Creating AGS sandbox from template {template!r}...")
        sandbox = sandbox_factory(template=template, timeout=sandbox_timeout)
        report["sandbox_id"] = sandbox.sandbox_id
        report["cleanup"] = "pending"
        print(f"Sandbox created: {sandbox.sandbox_id}")

        sandbox.files.write(REMOTE_ARCHIVE, archive)
        setup = _run_allow_failure(
            sandbox.commands,
            f"mkdir -p {shlex.quote(REMOTE_WORKSPACE)} && "
            f"tar -xzf {shlex.quote(REMOTE_ARCHIVE)} -C {shlex.quote(REMOTE_WORKSPACE)}",
            timeout=command_timeout,
        )
        if int(getattr(setup, "exit_code", 1)) != 0:
            _print_command_output(setup)
            raise RuntimeError("failed to extract the workspace archive in the sandbox")

        print(f"Running workload in {REMOTE_WORKSPACE}...")
        workload_command = shlex.join(["bash", "-lc", command])
        wrapper_command = (
            "set +e\n"
            f"{workload_command}\n"
            "ags_workload_exit_code=$?\n"
            f"printf '%s\\n' \"$ags_workload_exit_code\" > {shlex.quote(REMOTE_EXIT_CODE)}\n"
            "exit 0"
        )
        result = _run_allow_failure(
            sandbox.commands,
            shlex.join(["bash", "-lc", wrapper_command]),
            cwd=REMOTE_WORKSPACE,
            envs=envs,
            timeout=command_timeout,
        )
        _print_command_output(result)
        if int(getattr(result, "exit_code", 1)) != 0:
            raise RuntimeError("workload wrapper did not complete")
        exit_code = int(str(sandbox.files.read(REMOTE_EXIT_CODE)).strip())
        report["workload_exit_code"] = exit_code
        return_code = exit_code
        report["exit_code"] = exit_code
        report["status"] = "succeeded" if exit_code == 0 else "workload_failed"

        # SDK exists() returns False only for NOT_FOUND; permission and transport
        # errors must reach the infrastructure-error handler below.
        remote_artifact_path = str(PurePosixPath(REMOTE_WORKSPACE) / artifact_path)
        if sandbox.files.exists(remote_artifact_path):
            artifact_command = (
                f"tar -czf {shlex.quote(REMOTE_ARTIFACT)} "
                f"-C {shlex.quote(REMOTE_WORKSPACE)} -- {shlex.quote(artifact_path)}"
            )
            artifact_result = _run_allow_failure(
                sandbox.commands, artifact_command, timeout=command_timeout
            )
            if int(getattr(artifact_result, "exit_code", 1)) != 0:
                _print_command_output(artifact_result)
                raise RuntimeError("failed to package sandbox artifacts")
            artifact_bytes = sandbox.files.read(REMOTE_ARTIFACT, format="bytes")
            if isinstance(artifact_bytes, str):
                artifact_bytes = artifact_bytes.encode("utf-8")
            artifact_file = output_dir / "artifacts.tar.gz"
            artifact_file.write_bytes(artifact_bytes)
            report["artifact_archive"] = artifact_file.name
            report["artifact_archive_bytes"] = len(artifact_bytes)
            print(f"Downloaded sandbox artifacts to {artifact_file}")
        else:
            report["artifact_warning"] = f"artifact path not collected: {artifact_path}"
            print(report["artifact_warning"], file=os.sys.stderr)

    except Exception as exc:
        return_code = 2
        report["exit_code"] = 2
        report["status"] = "infrastructure_error"
        report["error_type"] = type(exc).__name__
        report["error"] = str(exc)
        print(f"AGS sandbox infrastructure error: {exc}", file=os.sys.stderr)
    finally:
        if sandbox is not None:
            try:
                sandbox.kill()
                report["cleanup"] = "killed"
                print(f"Sandbox cleaned up: {sandbox.sandbox_id}")
            except Exception as exc:
                report["cleanup"] = "failed"
                report["cleanup_error"] = str(exc)
                report["status"] = "cleanup_failed"
                report["exit_code"] = 2
                return_code = 2
                print(f"Sandbox cleanup failed: {exc}", file=os.sys.stderr)

        report["duration_seconds"] = round(time.time() - started_at, 3)
        report_file = output_dir / "run-report.json"
        report_file.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        _write_github_outputs(
            str(report.get("sandbox_id") or ""), int(report["exit_code"]), output_dir
        )
        print(f"Run report written to {report_file}")
    return return_code
