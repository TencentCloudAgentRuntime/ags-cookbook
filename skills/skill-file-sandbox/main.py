"""
skill-file-sandbox: sandbox filesystem I/O skill.

Authentication is auto-detected by ``ags_client.SandboxSession``:

  * ``TENCENTCLOUD_SECRET_ID`` / ``TENCENTCLOUD_SECRET_KEY`` set → AKSK mode.
  * Otherwise ``E2B_API_KEY`` / ``E2B_DOMAIN`` must be set → APIKey mode.

Demonstrates:
  1. Uploading text content into the sandbox filesystem
  2. Running a transform inside the sandbox that reads and writes files
  3. Downloading the result file back to the local host
  4. Listing sandbox directory contents

Skills exposed:
  - upload_and_run(local_text, remote_path, transform_code, result_path)
  - list_sandbox_dir(path)
"""

import json
import logging

from ags_client import SandboxSession

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Skill 1: upload_and_run
# ---------------------------------------------------------------------------

def upload_and_run(
    local_text: str,
    remote_path: str,
    transform_code: str,
    result_path: str,
) -> dict:
    """Upload *local_text* to *remote_path* inside a sandbox, execute
    *transform_code* (which reads *remote_path* and writes *result_path*),
    then download and return the result file content.

    The sandbox lifecycle is managed by ``SandboxSession``; the underlying
    credential mode (AKSK vs APIKey) is auto-detected at runtime.
    """
    log.info("upload_and_run: starting sandbox…")
    with SandboxSession() as sbx:
        sbx.files.write(remote_path, local_text)
        log.info("uploaded %d bytes → %s", len(local_text), remote_path)

        lines: list[str] = []
        execution = sbx.run_code(
            transform_code,
            on_stdout=lambda msg: lines.append(msg.line),
        )
        error = execution.error.value if execution.error else None
        if error:
            log.error("transform failed: %s", error)

        result_content: str | None = None
        if not error:
            try:
                result_content = sbx.files.read(result_path)
                log.info("downloaded %d bytes ← %s", len(result_content), result_path)
            except Exception as exc:
                log.error("download failed: %s", exc)
                error = str(exc)

    log.info("upload_and_run: sandbox stopped.")
    return {
        "uploaded": remote_path,
        "stdout": lines,
        "result_content": result_content,
        "error": error,
    }


# ---------------------------------------------------------------------------
# Skill 2: list_sandbox_dir
# ---------------------------------------------------------------------------

def list_sandbox_dir(path: str = "/tmp") -> dict:
    """Return the directory listing of *path* inside a fresh sandbox."""
    log.info("list_sandbox_dir: path=%s", path)
    code = (
        f"import os, json\n"
        f"entries = os.listdir({path!r})\n"
        f"print(json.dumps(sorted(entries)))"
    )
    with SandboxSession() as sbx:
        execution = sbx.run_code(code)
        raw = execution.logs.stdout
        entries = json.loads(raw[0]) if raw else []
        error = execution.error.value if execution.error else None

    log.info("list_sandbox_dir: found %d entries, error=%s", len(entries), error)
    return {"path": path, "entries": entries, "error": error}


# ---------------------------------------------------------------------------
# Entry point — demo both skills
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    log.info("=== Demo 1: upload_and_run ===")
    sample_csv = "name,score\nAlice,88\nBob,72\nCharlie,95\n"
    transform = (
        "import csv, json\n"
        "rows = list(csv.DictReader(open('/tmp/scores.csv')))\n"
        "rows.sort(key=lambda r: -int(r['score']))\n"
        "open('/tmp/ranked.json', 'w').write(json.dumps(rows, indent=2))\n"
        "print(f'sorted {len(rows)} rows')"
    )
    result1 = upload_and_run(
        local_text=sample_csv,
        remote_path="/tmp/scores.csv",
        transform_code=transform,
        result_path="/tmp/ranked.json",
    )
    print("\n=== Skill Result: upload_and_run ===")
    print(json.dumps(result1, indent=2, ensure_ascii=False))

    log.info("=== Demo 2: list_sandbox_dir ===")
    result2 = list_sandbox_dir("/tmp")
    print("\n=== Skill Result: list_sandbox_dir ===")
    print(json.dumps(result2, indent=2, ensure_ascii=False))
