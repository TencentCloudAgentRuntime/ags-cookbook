"""
skill-code-repl: persistent Python REPL contexts inside a sandbox.

The existing :mod:`skill-code-interpreter` creates a fresh sandbox per call, so
variables do not survive between Agent tool calls.  This skill exposes a
**persistent context** abstraction: the first call to :func:`create_repl`
starts a sandbox, creates a code context, and caches both in process-local
registries.  Subsequent :func:`run_in_repl` calls reuse the same sandbox +
context, so ``x = 1`` in call N is still visible in call N+1.

Lifecycle sketch::

    repl_id = create_repl()["repl_id"]
    run_in_repl(repl_id, "a = 10")["text_results"]
    run_in_repl(repl_id, "print(a + 1)")["stdout"]   # → ["11\n"]
    close_repl(repl_id)

Process-local caching means REPLs are NOT persisted across Python processes —
this is appropriate for a single long-lived Agent process.  For multi-process
deployments, bring your own shared registry (e.g. Redis) keyed on ``repl_id``.

Skills exposed:
  - create_repl(timeout="30m")
  - run_in_repl(repl_id, code, on_stdout=None)
  - close_repl(repl_id)
  - list_repls()
"""

import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from ags_client import SandboxSession

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)


@dataclass
class _Repl:
    repl_id: str
    session: SandboxSession
    sandbox: Any
    context: Any
    turn: int = 0


# process-local registry
_REPLS: dict[str, _Repl] = {}


# ---------------------------------------------------------------------------
# Skill: create_repl
# ---------------------------------------------------------------------------

def create_repl(timeout: str = "30m") -> dict:
    """Start a sandbox and a fresh code context; return a repl id for reuse.

    The sandbox is **not** released at return — it stays alive until
    :func:`close_repl` is called.  The default ``timeout`` is longer than
    other skills because REPLs are meant to span many tool calls.
    """
    repl_id = f"repl-{uuid.uuid4().hex[:12]}"
    session = SandboxSession(timeout=timeout)
    sandbox = session.__enter__()  # manually open so we can hold it open
    try:
        context = sandbox.create_code_context()
    except Exception:
        # make sure we do not leak the sandbox if context creation fails
        session.__exit__(None, None, None)
        raise

    _REPLS[repl_id] = _Repl(
        repl_id=repl_id,
        session=session,
        sandbox=sandbox,
        context=context,
    )
    log.info("create_repl: %s (active=%d)", repl_id, len(_REPLS))
    return {"repl_id": repl_id, "timeout": timeout}


# ---------------------------------------------------------------------------
# Skill: run_in_repl
# ---------------------------------------------------------------------------

def run_in_repl(
    repl_id: str,
    code: str,
    on_stdout: Callable[[str], None] | None = None,
) -> dict:
    """Execute ``code`` inside the cached context identified by ``repl_id``.

    ``on_stdout`` (if provided) is called with each raw line; a local buffer
    is always returned in the result.
    """
    repl = _REPLS.get(repl_id)
    if repl is None:
        return {"repl_id": repl_id, "error": f"unknown repl_id: {repl_id}"}

    lines: list[str] = []

    def _cb(msg):
        line = str(getattr(msg, "line", msg))
        lines.append(line)
        if on_stdout is not None:
            on_stdout(line)

    repl.turn += 1
    execution = repl.sandbox.run_code(
        code,
        context=repl.context,
        on_stdout=_cb,
    )
    error = execution.error.value if execution.error else None

    return {
        "repl_id": repl_id,
        "turn": repl.turn,
        "stdout": lines,
        "text_results": [r.text for r in execution.results if hasattr(r, "text")],
        "error": error,
    }


# ---------------------------------------------------------------------------
# Skill: close_repl
# ---------------------------------------------------------------------------

def close_repl(repl_id: str) -> dict:
    """Release the sandbox backing ``repl_id``.  Idempotent."""
    repl = _REPLS.pop(repl_id, None)
    if repl is None:
        return {"repl_id": repl_id, "closed": False, "reason": "unknown repl_id"}

    try:
        repl.session.__exit__(None, None, None)
    except Exception as e:  # noqa: BLE001
        log.error("close_repl: session exit failed: %s", e)
        return {"repl_id": repl_id, "closed": False, "reason": str(e), "turns": repl.turn}

    log.info("close_repl: %s (active=%d)", repl_id, len(_REPLS))
    return {"repl_id": repl_id, "closed": True, "turns": repl.turn}


# ---------------------------------------------------------------------------
# Skill: list_repls
# ---------------------------------------------------------------------------

def list_repls() -> dict:
    """Return the ids + turn counts of every live REPL in this process."""
    return {
        "repls": [{"repl_id": r.repl_id, "turns": r.turn} for r in _REPLS.values()],
        "count": len(_REPLS),
    }


# ---------------------------------------------------------------------------
# Entry point — demo persistent state across turns
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    log.info("=== Demo: persistent REPL ===")
    repl = create_repl()
    rid = repl["repl_id"]
    print("\n=== Skill Result: create_repl ===")
    print(json.dumps(repl, indent=2, ensure_ascii=False))

    try:
        # Turn 1: define a variable.
        r1 = run_in_repl(rid, "import math\nx = 7\nprint(f'x={x}')")
        print("\n=== Skill Result: run_in_repl (turn 1) ===")
        print(json.dumps(r1, indent=2, ensure_ascii=False))

        # Turn 2: reuse x from turn 1 — proving the context persists.
        r2 = run_in_repl(rid, "y = math.factorial(x)\nprint(f'{x}! = {y}')")
        print("\n=== Skill Result: run_in_repl (turn 2) ===")
        print(json.dumps(r2, indent=2, ensure_ascii=False))

        # Turn 3: show currently defined user names.
        r3 = run_in_repl(
            rid,
            "names = [k for k in dir() if not k.startswith('_') and k not in ('In','Out','get_ipython','exit','quit')]\nprint(sorted(names))",
        )
        print("\n=== Skill Result: run_in_repl (turn 3) ===")
        print(json.dumps(r3, indent=2, ensure_ascii=False))

        print("\n=== Skill Result: list_repls ===")
        print(json.dumps(list_repls(), indent=2, ensure_ascii=False))
    finally:
        closed = close_repl(rid)
        print("\n=== Skill Result: close_repl ===")
        print(json.dumps(closed, indent=2, ensure_ascii=False))
