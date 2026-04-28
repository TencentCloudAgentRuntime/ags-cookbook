"""
skill-multi-lang-exec: multi-language code execution via AIO sandbox uvicorn.

AIO sandbox images bundle a uvicorn server on port 49999 that exposes
``/execute`` as an NDJSON stream.  Each request carries ``{"code", "language"}``
and the response body is a sequence of lines like::

    {"type": "stdout", "text": "…"}
    {"type": "result", "text": "…"}
    {"type": "error",  "name": "NameError", "value": "name 'x' is not defined"}

Languages verified by the e2e suite (``aio/aio_dataplane_test.go``):
``python`` / ``javascript`` / ``bash`` / ``r`` / ``java``.

This skill makes one HTTP round-trip per invocation and parses the NDJSON
payload into a structured dict.  The browser / code sandboxes (``code-interpreter-v1``,
``browser-v1``) do NOT have this endpoint — use the ``aio-v1`` tool image.

Skills exposed:
  - run_code(code, language="python")
  - run_many(snippets)
  - get_host_info()
"""

import json
import logging
from typing import Iterable

import httpx

from ags_client import BrowserSandboxSession, build_port_url

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

# uvicorn listens on port 49999 in AIO images.
_UVICORN_PORT = 49999
# default AIO tool
_DEFAULT_TOOL = "aio-v1"


def _parse_ndjson(text: str) -> dict:
    """Parse the uvicorn /execute NDJSON response into a structured dict."""
    stdout_parts: list[str] = []
    result_parts: list[str] = []
    error: dict | None = None

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = obj.get("type")
        if kind == "stdout":
            stdout_parts.append(obj.get("text", ""))
        elif kind == "result":
            result_parts.append(obj.get("text", ""))
        elif kind == "error":
            error = {
                "name": obj.get("name", ""),
                "value": obj.get("value", ""),
                "traceback": obj.get("traceback", ""),
            }
    return {
        "stdout": "".join(stdout_parts),
        "result": "".join(result_parts),
        "error": error,
    }


# ---------------------------------------------------------------------------
# Internal: open an AIO sandbox, POST /execute, return parsed result
# ---------------------------------------------------------------------------

def _execute(
    code: str,
    language: str,
    tool_name: str,
    timeout: str,
) -> dict:
    # ``BrowserSandboxSession`` is only misleading in name — it is the generic
    # "start a sandbox, return (instance_id, token, region)" session helper.
    # Reusing it avoids duplicating control-plane logic.
    with BrowserSandboxSession(tool_name=tool_name, timeout=timeout) as (instance_id, token, region):
        url = build_port_url(instance_id, _UVICORN_PORT, "/execute")
        headers = {"X-Access-Token": token, "Content-Type": "application/json"}
        payload = {"code": code, "language": language}
        log.info("POST %s (language=%s, code_len=%d)", url, language, len(code))
        with httpx.Client(timeout=120.0, verify=True) as client:
            resp = client.post(url, headers=headers, json=payload)
        body = resp.text
        parsed = _parse_ndjson(body)
        return {
            "instance_id": instance_id,
            "language": language,
            "status_code": resp.status_code,
            **parsed,
        }


# ---------------------------------------------------------------------------
# Skill 1: run_code
# ---------------------------------------------------------------------------

def run_code(
    code: str,
    language: str = "python",
    tool_name: str = _DEFAULT_TOOL,
    timeout: str = "10m",
) -> dict:
    """Execute ``code`` in ``language`` inside an AIO sandbox.

    ``language`` ∈ ``{"python", "javascript", "bash", "r", "java"}`` (validated
    by the server).  Returns ``{stdout, result, error, language, instance_id,
    status_code}`` where ``error`` is ``None`` on success.
    """
    return _execute(code, language, tool_name, timeout)


# ---------------------------------------------------------------------------
# Skill 2: run_many — run a series of snippets in the SAME sandbox
# ---------------------------------------------------------------------------

def run_many(
    snippets: list[dict],
    tool_name: str = _DEFAULT_TOOL,
    timeout: str = "10m",
) -> dict:
    """Run several ``{code, language}`` snippets sequentially in ONE sandbox.

    Returns ``{"results": [...], "ok": <bool>}``.  Execution continues on
    errors; per-snippet errors are captured in the result entry.

    Note: each call hits uvicorn ``/execute`` which is a stateless NDJSON
    endpoint — this skill does NOT preserve language-level state between
    snippets.  For Python state persistence, use :mod:`skill-code-repl`.
    """
    results: list[dict] = []
    with BrowserSandboxSession(tool_name=tool_name, timeout=timeout) as (instance_id, token, region):
        url = build_port_url(instance_id, _UVICORN_PORT, "/execute")
        headers = {"X-Access-Token": token, "Content-Type": "application/json"}
        with httpx.Client(timeout=120.0) as client:
            for i, snip in enumerate(snippets):
                code = snip.get("code", "")
                language = snip.get("language", "python")
                try:
                    resp = client.post(url, headers=headers, json={"code": code, "language": language})
                    parsed = _parse_ndjson(resp.text)
                    results.append({
                        "i": i,
                        "language": language,
                        "status_code": resp.status_code,
                        **parsed,
                    })
                except Exception as e:  # noqa: BLE001
                    results.append({"i": i, "language": language, "error": {"name": "TransportError", "value": str(e)}})
    ok = all(r.get("error") in (None, {}) for r in results)
    return {"instance_id": instance_id, "results": results, "ok": ok}


# ---------------------------------------------------------------------------
# Skill 3: get_host_info — introspect where /execute lives
# ---------------------------------------------------------------------------

def get_host_info(tool_name: str = _DEFAULT_TOOL, timeout: str = "10m") -> dict:
    """Return the AIO sandbox's uvicorn /execute URL and auxiliary port hints.

    Useful for Agents that want to fan out custom requests (multi-language
    tests, benchmarking) without re-opening a session per call.  The session
    is NOT closed here — the caller takes ownership via the returned
    ``_session_keepalive``.
    """
    session = BrowserSandboxSession(tool_name=tool_name, timeout=timeout)
    instance_id, token, region = session.__enter__()
    return {
        "instance_id": instance_id,
        "access_token": token,
        "region": region,
        "uvicorn_execute": build_port_url(instance_id, _UVICORN_PORT, "/execute"),
        "uvicorn_health": build_port_url(instance_id, _UVICORN_PORT, "/health"),
        "nginx_health": build_port_url(instance_id, 9000, "/health"),
        "novnc_url": build_port_url(instance_id, 9000, "/novnc/"),
        "vscode_url": build_port_url(instance_id, 9000, "/vscode/"),
        "_session_keepalive": session,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    log.info("=== Demo: run_code across 5 languages ===")
    # Snippets cherry-picked from e2e/aio/aio_dataplane_test.go so outputs are
    # comparable to the canonical test expectations.
    demos = [
        ("python",     "print('hello from python'); print(sum(range(101)))"),
        ("javascript", "console.log('hello from js'); console.log([1,2,3].reduce((a,b)=>a+b))"),
        ("bash",       "echo hello from bash; echo $((3*4))"),
        ("r",          'cat("hello from r\\n"); cat(sum(1:10))'),
        ("java",       'public class S { public static void main(String[] a){ System.out.println("hello from java"); } }'),
    ]
    for lang, code in demos:
        r = run_code(code, language=lang)
        print(f"\n=== Skill Result: run_code ({lang}) ===")
        print(json.dumps(r, indent=2, ensure_ascii=False))
