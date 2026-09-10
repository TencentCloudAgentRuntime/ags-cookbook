#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path

from runner import run_in_sandbox


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description="Run a checked-out GitHub repository in a fresh AGS sandbox."
    )
    value.add_argument(
        "--workspace",
        type=Path,
        default=Path(os.getenv("GITHUB_WORKSPACE", ".")),
        help="Local checkout to upload (default: GITHUB_WORKSPACE or current directory).",
    )
    value.add_argument(
        "--command",
        default=os.getenv("SANDBOX_COMMAND", "python workload/ci_task.py"),
        help="Shell command to run inside the sandbox.",
    )
    value.add_argument(
        "--artifact-path",
        default=os.getenv("SANDBOX_ARTIFACT_PATH", "workload/output"),
        help="Relative sandbox workspace path to download as an archive.",
    )
    value.add_argument(
        "--output-dir",
        type=Path,
        default=Path(os.getenv("AGS_RESULT_DIR", "ags-results")),
        help="Local directory for the run report and artifact archive.",
    )
    value.add_argument(
        "--template",
        default=os.getenv("AGS_SANDBOX_TEMPLATE", "code-interpreter-v1"),
    )
    value.add_argument(
        "--sandbox-timeout",
        type=int,
        default=int(os.getenv("AGS_SANDBOX_TIMEOUT", "900")),
    )
    value.add_argument(
        "--command-timeout",
        type=int,
        default=int(os.getenv("AGS_COMMAND_TIMEOUT", "600")),
    )
    value.add_argument(
        "--env",
        action="append",
        default=[],
        metavar="NAME",
        help="Explicitly forward one existing environment variable; repeat as needed.",
    )
    value.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="NAME",
        help="Exclude a file or directory name from the uploaded checkout.",
    )
    return value


def main() -> int:
    args = parser().parse_args()
    return run_in_sandbox(
        workspace=args.workspace,
        command=args.command,
        artifact_path=args.artifact_path,
        output_dir=args.output_dir,
        template=args.template,
        sandbox_timeout=args.sandbox_timeout,
        command_timeout=args.command_timeout,
        env_names=args.env,
        excludes=args.exclude,
    )


if __name__ == "__main__":
    raise SystemExit(main())
