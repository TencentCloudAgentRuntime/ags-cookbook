"""
skill-run-shell-stream: bash command execution with streaming output.

Unlike :mod:`skill-run-shell` which collects the full output and returns it
at the end, this skill invokes a caller-supplied callback for each chunk of
stdout / stderr as it arrives.  This matches the ``ExecCommandStream`` flow
used by the e2e test framework and lets an Agent surface long-running progress
to the user in real time.

Skills exposed:
  - run_shell_stream(cmd, on_chunk, cwd=None, envs=None, timeout=300)
  - run_shell_collect_chunks(cmd, cwd=None, envs=None, timeout=300)
    — a convenience wrapper that buffers chunks and returns them in the result
"""

import json
import logging
import sys
import time
from typing import Callable

from ags_client import SandboxSession

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)


# Chunk schema mirrors the Go e2e framework's StreamChunk: {"type", "data"}.
Chunk = dict  # {"type": "stdout"|"stderr", "data": str, "t": float}


def _build_callbacks(on_chunk: Callable[[Chunk], None]):
    """Return (on_stdout, on_stderr) e2b callbacks that forward to ``on_chunk``."""
    t0 = time.time()

    def _on_stdout(data):
        on_chunk({"type": "stdout", "data": str(data), "t": time.time() - t0})

    def _on_stderr(data):
        on_chunk({"type": "stderr", "data": str(data), "t": time.time() - t0})

    return _on_stdout, _on_stderr


# ---------------------------------------------------------------------------
# Skill 1: run_shell_stream
# ---------------------------------------------------------------------------

def run_shell_stream(
    cmd: str,
    on_chunk: Callable[[Chunk], None],
    cwd: str | None = None,
    envs: dict | None = None,
    timeout: int = 300,
) -> dict:
    """Run ``cmd`` with real-time streaming; invoke ``on_chunk`` for each chunk.

    ``on_chunk`` receives dicts of the form::

        {"type": "stdout" | "stderr", "data": <str>, "t": <seconds since start>}

    Returns the final ``{"cmd", "exit_code", "duration_s"}``.  The full output
    text is NOT in the return value — callers that need it should buffer from
    the callback (see :func:`run_shell_collect_chunks` for an example).
    """
    log.info("run_shell_stream: %r (timeout=%ss)", cmd, timeout)
    started = time.time()

    with SandboxSession() as sbx:
        on_stdout, on_stderr = _build_callbacks(on_chunk)
        result = sbx.commands.run(
            cmd,
            cwd=cwd,
            envs=envs,
            timeout=timeout,
            on_stdout=on_stdout,
            on_stderr=on_stderr,
        )

    return {
        "cmd": cmd,
        "exit_code": int(getattr(result, "exit_code", 0)),
        "duration_s": round(time.time() - started, 3),
    }


# ---------------------------------------------------------------------------
# Skill 2: run_shell_collect_chunks — returns chunks for non-streaming callers
# ---------------------------------------------------------------------------

def run_shell_collect_chunks(
    cmd: str,
    cwd: str | None = None,
    envs: dict | None = None,
    timeout: int = 300,
) -> dict:
    """Like :func:`run_shell_stream` but buffers chunks and returns them.

    The buffered representation preserves chunk boundaries and timing so the
    Agent can replay the stream or verify that output arrived incrementally
    (e.g. by checking that at least two different ``t`` values are present).
    """
    buffer: list[Chunk] = []
    meta = run_shell_stream(
        cmd,
        on_chunk=buffer.append,
        cwd=cwd,
        envs=envs,
        timeout=timeout,
    )
    meta["chunks"] = buffer
    meta["chunk_count"] = len(buffer)
    meta["distinct_seconds"] = len({int(c["t"]) for c in buffer})
    return meta


# ---------------------------------------------------------------------------
# Entry point — demo both flavours
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # -- Demo 1: streaming to stdout in real time -------------------------
    log.info("=== Demo 1: run_shell_stream (progressive) ===")
    # This classic bash loop prints one line every second; the callback
    # will fire ~5 times, not once at the end.
    long_cmd = "for i in 1 2 3 4 5; do echo tick $i; sleep 1; done"

    def _print_chunk(c):
        # Write directly so we can see streaming interactively.
        stream = sys.stdout if c["type"] == "stdout" else sys.stderr
        stream.write(f"[{c['type']}@{c['t']:.1f}s] {c['data']}")
        stream.flush()

    meta = run_shell_stream(long_cmd, on_chunk=_print_chunk, timeout=30)
    print("\n=== Skill Result: run_shell_stream ===")
    print(json.dumps(meta, indent=2, ensure_ascii=False))

    # -- Demo 2: collected chunks ----------------------------------------
    log.info("=== Demo 2: run_shell_collect_chunks (buffered) ===")
    r = run_shell_collect_chunks(
        "for i in 1 2 3; do echo out-$i; echo err-$i >&2; sleep 1; done",
        timeout=30,
    )
    # Trim the chunks for display — in a real run they'd all be present.
    display = dict(r)
    display["chunks"] = r["chunks"][:4] + (["…"] if len(r["chunks"]) > 4 else [])
    print("\n=== Skill Result: run_shell_collect_chunks (truncated) ===")
    print(json.dumps(display, indent=2, ensure_ascii=False, default=str))
