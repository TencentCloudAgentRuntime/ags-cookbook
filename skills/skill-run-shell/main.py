"""
skill-run-shell: bash command execution inside an AGS sandbox.

Wraps the e2b ``sandbox.commands.run()`` API so an Agent can invoke shell
commands as a first-class tool.  Returns ``stdout``, ``stderr`` and ``exit_code``
in a structured dict — all three are valuable for agentic error recovery.

Authentication is auto-detected by ``ags_client.SandboxSession``:

  * ``TENCENTCLOUD_SECRET_ID`` / ``TENCENTCLOUD_SECRET_KEY`` set → AKSK mode.
  * Otherwise ``E2B_API_KEY`` / ``E2B_DOMAIN`` must be set → APIKey mode.

Skills exposed:
  - run_shell(cmd, cwd=None, envs=None, timeout=60)
  - run_shell_many(cmds)
"""

import json
import logging

from ags_client import SandboxSession

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)


def _run_one(sbx, cmd: str, cwd: str | None, envs: dict | None, timeout: int) -> dict:
    """Run a single command inside ``sbx`` and collect the canonical result shape."""
    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []

    # e2b Sandbox's Commands.run API accepts on_stdout / on_stderr callbacks and
    # returns an object with .exit_code / .stdout / .stderr.  We collect via
    # callbacks so the result dict keeps both "merged" strings and "chunks".
    result = sbx.commands.run(
        cmd,
        cwd=cwd,
        envs=envs,
        timeout=timeout,
        on_stdout=lambda data: stdout_chunks.append(str(data)),
        on_stderr=lambda data: stderr_chunks.append(str(data)),
    )

    # Some SDK versions return .stdout as a string already containing the full
    # output; prefer that when present.
    stdout_full = getattr(result, "stdout", None)
    if stdout_full is None:
        stdout_full = "".join(stdout_chunks)
    stderr_full = getattr(result, "stderr", None)
    if stderr_full is None:
        stderr_full = "".join(stderr_chunks)

    return {
        "cmd": cmd,
        "exit_code": int(getattr(result, "exit_code", 0)),
        "stdout": stdout_full,
        "stderr": stderr_full,
    }


# ---------------------------------------------------------------------------
# Skill 1: run_shell
# ---------------------------------------------------------------------------

def run_shell(
    cmd: str,
    cwd: str | None = None,
    envs: dict | None = None,
    timeout: int = 60,
) -> dict:
    """Execute a bash ``cmd`` inside a fresh sandbox, return exit code and streams.

    Args:
        cmd: Shell command line.  Passed to the sandbox's default bash.
        cwd: Working directory inside the sandbox; ``None`` uses the SDK default.
        envs: Extra environment variables injected for this command only.
        timeout: Seconds before the command is killed.

    Returns:
        ``{"cmd", "exit_code", "stdout", "stderr"}``.  A non-zero ``exit_code``
        is a *normal* result — the caller decides what to do with it.
    """
    log.info("run_shell: %r (cwd=%s, timeout=%ss)", cmd, cwd, timeout)
    with SandboxSession() as sbx:
        return _run_one(sbx, cmd, cwd, envs, timeout)


# ---------------------------------------------------------------------------
# Skill 2: run_shell_many
# ---------------------------------------------------------------------------

def run_shell_many(cmds: list[str], timeout: int = 60) -> dict:
    """Run multiple commands sequentially inside ONE sandbox, return list of results.

    Stops iterating as soon as ``exit_code != 0`` and reports which index failed.
    """
    log.info("run_shell_many: %d commands", len(cmds))
    results: list[dict] = []
    with SandboxSession() as sbx:
        for i, cmd in enumerate(cmds):
            r = _run_one(sbx, cmd, None, None, timeout)
            results.append(r)
            if r["exit_code"] != 0:
                log.info("run_shell_many: stopped at index %d (exit=%d)",
                         i, r["exit_code"])
                return {"results": results, "failed_at": i, "ok": False}
    return {"results": results, "failed_at": -1, "ok": True}


# ---------------------------------------------------------------------------
# Entry point — demo both skills
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    log.info("=== Demo 1: run_shell (simple echo) ===")
    r1 = run_shell("echo hello && echo boom >&2 && exit 3")
    print("\n=== Skill Result: run_shell ===")
    print(json.dumps(r1, indent=2, ensure_ascii=False))

    log.info("=== Demo 2: run_shell (pipeline + cwd) ===")
    r2 = run_shell(
        "printf 'a\\nb\\nc\\n' | sort -r | head -n2",
        cwd="/tmp",
    )
    print("\n=== Skill Result: run_shell (pipe) ===")
    print(json.dumps(r2, indent=2, ensure_ascii=False))

    log.info("=== Demo 3: run_shell_many ===")
    r3 = run_shell_many([
        "echo step-1",
        "ls /tmp | head -n3",
        "false",              # will fail with exit=1; 4th step should not run
        "echo should-not-run",
    ])
    print("\n=== Skill Result: run_shell_many ===")
    print(json.dumps(r3, indent=2, ensure_ascii=False))
