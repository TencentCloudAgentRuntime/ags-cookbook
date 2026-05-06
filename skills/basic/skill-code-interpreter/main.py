"""
skill-code-interpreter: sandboxed code execution skill.

Authentication is auto-detected by ``ags_client.SandboxSession``:

  * ``TENCENTCLOUD_SECRET_ID`` / ``TENCENTCLOUD_SECRET_KEY`` set → AKSK mode
    (sandbox lifecycle managed via the Tencent Cloud AGS control plane).
  * Otherwise ``E2B_API_KEY`` / ``E2B_DOMAIN`` must be set → APIKey mode
    (sandbox created directly via ``e2b-code-interpreter``).

Demonstrates:
  1. Single-shot code execution in the sandbox
  2. Multi-context isolation — two independent contexts inside ONE sandbox
     share the filesystem but have separate Python states
  3. Structured result returned to an Agent

Skills exposed:
  - run_code(code)                    execute a snippet, return stdout/error
  - run_code_multi_context(snippets)  run N snippets in N isolated contexts
"""

import json
import logging

from ags_client import SandboxSession

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Skill 1: run_code
# ---------------------------------------------------------------------------

def run_code(code: str) -> dict:
    """Execute *code* in a fresh AGS sandbox and return stdout / error.

    The sandbox is acquired and released by ``SandboxSession``; the underlying
    credential mode (AKSK vs APIKey) is auto-detected at runtime.
    """
    log.info("run_code: starting sandbox…")
    with SandboxSession() as sbx:
        lines: list[str] = []
        execution = sbx.run_code(
            code,
            on_stdout=lambda msg: lines.append(msg.line),
        )
        result = {
            "stdout": lines,
            "text_results": [r.text for r in execution.results if hasattr(r, "text")],
            "error": execution.error.value if execution.error else None,
        }
    log.info("run_code: sandbox stopped.")
    return result


# ---------------------------------------------------------------------------
# Skill 2: run_code_multi_context
# ---------------------------------------------------------------------------

def run_code_multi_context(snippets: list[str]) -> dict:
    """Run each snippet in its own isolated context inside ONE sandbox.

    Contexts share the sandbox filesystem but have completely separate Python
    interpreter states — variables in context N are not visible in context M.
    """
    log.info("run_code_multi_context: starting sandbox for %d contexts…", len(snippets))
    results = []

    with SandboxSession() as sbx:
        for idx, code in enumerate(snippets):
            ctx = sbx.create_code_context()
            lines: list[str] = []
            execution = sbx.run_code(
                code,
                context=ctx,
                on_stdout=lambda msg, i=idx: lines.append(f"[ctx{i}] {msg.line}"),
            )
            results.append({
                "context_index": idx,
                "stdout": lines,
                "error": execution.error.value if execution.error else None,
            })
            log.info("context %d done, error=%s", idx, execution.error)

    log.info("run_code_multi_context: sandbox stopped.")
    return {"contexts": results}


# ---------------------------------------------------------------------------
# Entry point — demo both skills
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    log.info("=== Demo 1: run_code ===")
    out1 = run_code(
        "import sys\nresult = 2 ** 10\nprint(f'2^10 = {result}')\nprint(f'Python {sys.version}')"
    )
    print("\n=== Skill Result: run_code ===")
    print(json.dumps(out1, indent=2, ensure_ascii=False))

    log.info("=== Demo 2: run_code_multi_context ===")
    snippet_a = "secret = 'context-A-only'\nprint(f'ctx A secret: {secret}')"
    snippet_b = (
        "try:\n"
        "    print(secret)\n"
        "except NameError:\n"
        "    print('ctx B: secret is NOT visible — isolation confirmed')"
    )
    out2 = run_code_multi_context([snippet_a, snippet_b])
    print("\n=== Skill Result: run_code_multi_context ===")
    print(json.dumps(out2, indent=2, ensure_ascii=False))
