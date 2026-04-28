"""
skill-file-ops-extended: filesystem operations missing from ``skill-file-sandbox``.

``skill-file-sandbox`` covers upload / transform / download.  This skill adds
the individual primitives the e2e suite exercises under "File Operations" in
``e2e/basic/sandbox_operations_test.go``:

  * file existence check
  * directory creation (mkdir -p semantics)
  * file / directory removal
  * detailed directory listing (name + type + size where available)
  * file rename / move

Skills exposed:
  - file_exists(path)
  - make_dir(path)
  - remove_path(path)
  - list_dir_detailed(path)
  - rename_path(src, dst)
  - run_batch(ops)              # execute a list of ops in ONE sandbox
"""

import json
import logging
from typing import Any

from ags_client import SandboxSession

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers operating on an open Sandbox
# ---------------------------------------------------------------------------

def _exists(sbx, path: str) -> bool:
    """Check if ``path`` exists inside the sandbox.

    Tries ``sbx.files.exists`` first; falls back to an in-sandbox ``test -e``
    if the SDK does not expose that method.
    """
    fn = getattr(sbx.files, "exists", None)
    if fn is not None:
        return bool(fn(path))
    # Fallback via command
    r = sbx.commands.run(f"test -e {_shell_quote(path)}")
    return int(getattr(r, "exit_code", 1)) == 0


def _mkdir(sbx, path: str) -> None:
    fn = getattr(sbx.files, "make_dir", None) or getattr(sbx.files, "makedir", None)
    if fn is not None:
        fn(path)
        return
    sbx.commands.run(f"mkdir -p {_shell_quote(path)}")


def _remove(sbx, path: str) -> None:
    fn = getattr(sbx.files, "remove", None)
    if fn is not None:
        fn(path)
        return
    sbx.commands.run(f"rm -rf {_shell_quote(path)}")


def _rename(sbx, src: str, dst: str) -> None:
    fn = getattr(sbx.files, "rename", None)
    if fn is not None:
        fn(src, dst)
        return
    sbx.commands.run(f"mv {_shell_quote(src)} {_shell_quote(dst)}")


def _list_detailed(sbx, path: str) -> list[dict]:
    """Return a list of ``{name, type, size}`` for each entry in ``path``.

    ``type`` is one of ``"file"`` / ``"dir"`` / ``"other"``. We prefer the SDK's
    ``files.list`` when it returns rich objects; otherwise we shell out to
    ``stat`` so the result shape is the same.
    """
    fn = getattr(sbx.files, "list", None)
    if fn is not None:
        try:
            entries = fn(path)
        except Exception:  # noqa: BLE001
            entries = None
        if entries:
            out: list[dict] = []
            for e in entries:
                name = getattr(e, "name", None) or (e if isinstance(e, str) else None)
                kind = getattr(e, "type", None) or ""
                size = getattr(e, "size", None)
                out.append({
                    "name": name,
                    "type": str(kind).lower() or "unknown",
                    "size": size,
                })
            return out

    # Fallback: use stat for each entry in path.
    r = sbx.commands.run(
        f"ls -A1 {_shell_quote(path)} 2>/dev/null",
    )
    names = [ln for ln in str(getattr(r, "stdout", "")).splitlines() if ln]
    out = []
    for n in names:
        full = f"{path.rstrip('/')}/{n}"
        r2 = sbx.commands.run(
            f"stat -c '%F|%s' {_shell_quote(full)}",
        )
        raw = str(getattr(r2, "stdout", "")).strip()
        kind_raw, _, size_raw = raw.partition("|")
        if "directory" in kind_raw:
            kind = "dir"
        elif "regular" in kind_raw:
            kind = "file"
        else:
            kind = "other"
        try:
            size = int(size_raw) if size_raw else None
        except ValueError:
            size = None
        out.append({"name": n, "type": kind, "size": size})
    return out


def _shell_quote(s: str) -> str:
    """Minimal POSIX single-quote shell escape suitable for path arguments."""
    return "'" + s.replace("'", "'\"'\"'") + "'"


# ---------------------------------------------------------------------------
# Skills — each opens a fresh sandbox
# ---------------------------------------------------------------------------

def file_exists(path: str) -> dict:
    """Return ``{path, exists}``."""
    with SandboxSession() as sbx:
        return {"path": path, "exists": _exists(sbx, path)}


def make_dir(path: str) -> dict:
    """Create ``path`` (and parents). Returns ``{path, created}``."""
    with SandboxSession() as sbx:
        _mkdir(sbx, path)
        return {"path": path, "created": _exists(sbx, path)}


def remove_path(path: str) -> dict:
    """Remove ``path`` (file or directory recursively). Returns ``{path, removed}``."""
    with SandboxSession() as sbx:
        _remove(sbx, path)
        return {"path": path, "removed": not _exists(sbx, path)}


def list_dir_detailed(path: str = "/tmp") -> dict:
    """Return ``{path, entries: [{name,type,size}, ...], count}``."""
    with SandboxSession() as sbx:
        entries = _list_detailed(sbx, path)
        return {"path": path, "entries": entries, "count": len(entries)}


def rename_path(src: str, dst: str) -> dict:
    """Rename / move ``src`` → ``dst``.  Returns ``{src, dst, ok}``."""
    with SandboxSession() as sbx:
        _rename(sbx, src, dst)
        return {"src": src, "dst": dst, "ok": _exists(sbx, dst)}


# ---------------------------------------------------------------------------
# Skill: run_batch — run N ops inside ONE sandbox
# ---------------------------------------------------------------------------

_BATCH_OPS: dict[str, Any] = {
    "exists":      lambda sbx, args: {"exists": _exists(sbx, args["path"])},
    "mkdir":       lambda sbx, args: (_mkdir(sbx, args["path"]) or {"created": _exists(sbx, args["path"])}),
    "remove":      lambda sbx, args: (_remove(sbx, args["path"]) or {"removed": not _exists(sbx, args["path"])}),
    "list":        lambda sbx, args: {"entries": _list_detailed(sbx, args["path"])},
    "rename":      lambda sbx, args: (_rename(sbx, args["src"], args["dst"]) or {"ok": _exists(sbx, args["dst"])}),
    "write":       lambda sbx, args: (sbx.files.write(args["path"], args["content"]) or {"written": True}),
    "read":        lambda sbx, args: {"content": sbx.files.read(args["path"])},
}


def run_batch(ops: list[dict]) -> dict:
    """Execute a list of filesystem ops in a single sandbox session.

    Each op is ``{"op": <name>, ...args}``; supported ops are ``exists``,
    ``mkdir``, ``remove``, ``list``, ``rename``, ``write``, ``read``.

    Returns ``{"results": [...], "ok": <bool>}`` — any exception for an op is
    captured as ``{"error": str}`` on that entry but does NOT abort the batch.
    """
    log.info("run_batch: %d ops", len(ops))
    results: list[dict] = []
    with SandboxSession() as sbx:
        for i, op in enumerate(ops):
            name = op.get("op")
            handler = _BATCH_OPS.get(name)
            if handler is None:
                results.append({"i": i, "op": name, "error": "unknown op"})
                continue
            try:
                outcome = handler(sbx, op) or {}
                results.append({"i": i, "op": name, **outcome})
            except Exception as e:  # noqa: BLE001
                results.append({"i": i, "op": name, "error": str(e)})
    ok = not any("error" in r for r in results)
    return {"results": results, "ok": ok}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    log.info("=== Demo: file_exists / make_dir / list_dir_detailed / remove_path ===")
    target_dir = "/tmp/agsskill_demo"

    # Exists check (should be False).
    r1 = file_exists(target_dir)
    print("\n=== Skill Result: file_exists (before) ===")
    print(json.dumps(r1, indent=2, ensure_ascii=False))

    # Batch: mkdir, write, list, read, rename, list, remove.
    r2 = run_batch([
        {"op": "mkdir", "path": target_dir},
        {"op": "write", "path": f"{target_dir}/hello.txt", "content": "hi\n"},
        {"op": "list",  "path": target_dir},
        {"op": "read",  "path": f"{target_dir}/hello.txt"},
        {"op": "rename", "src": f"{target_dir}/hello.txt", "dst": f"{target_dir}/hi.txt"},
        {"op": "list",  "path": target_dir},
        {"op": "remove", "path": target_dir},
        {"op": "exists", "path": target_dir},
    ])
    print("\n=== Skill Result: run_batch ===")
    print(json.dumps(r2, indent=2, ensure_ascii=False, default=str))
