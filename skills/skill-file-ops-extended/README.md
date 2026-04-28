# Skill: File Ops (Extended)

This example complements `skill-file-sandbox` (upload / transform / download) with the **individual filesystem primitives** the e2e suite tests under "File Operations" in `e2e/basic/sandbox_operations_test.go`: existence check, directory creation, removal, rename, and detailed listing.

Each skill opens a fresh sandbox per call, so they compose cleanly with an Agent's tool-call loop. For multi-op workflows where it is wasteful to spin up a sandbox per step, use `run_batch` to execute a list of ops in a single session.

## What this example demonstrates

- **`file_exists(path)`** — check if `path` exists
- **`make_dir(path)`** — `mkdir -p` semantics
- **`remove_path(path)`** — recursive removal (file or directory)
- **`list_dir_detailed(path)`** — list entries with `{name, type, size}`
- **`rename_path(src, dst)`** — move / rename
- **`run_batch(ops)`** — run several ops in one sandbox; supports `exists` / `mkdir` / `remove` / `list` / `rename` / `write` / `read`

Where the e2b SDK does not expose a method (e.g. older versions without `files.exists`), the skill transparently falls back to an in-sandbox shell command.

## Prerequisites

- Python 3.13 (managed by `uv`)
- `uv` installed
- Either an AGS API key **or** Tencent Cloud AKSK credentials

## Required environment variables

```bash
# Option A — APIKey mode
export E2B_API_KEY="your_ags_api_key"
export E2B_DOMAIN="ap-guangzhou.tencentags.com"
```

```bash
# Option B — AKSK mode
export TENCENTCLOUD_SECRET_ID="your_secret_id"
export TENCENTCLOUD_SECRET_KEY="your_secret_key"
export TENCENTCLOUD_REGION="ap-guangzhou"
```

## Install and run

```bash
make setup
make run
```

## Expected output

```
=== Skill Result: file_exists (before) ===
{"path": "/tmp/agsskill_demo", "exists": false}

=== Skill Result: run_batch ===
{
  "results": [
    {"i": 0, "op": "mkdir",  "created": true},
    {"i": 1, "op": "write",  "written": true},
    {"i": 2, "op": "list",   "entries": [{"name": "hello.txt", "type": "file", "size": 3}]},
    {"i": 3, "op": "read",   "content": "hi\n"},
    {"i": 4, "op": "rename", "ok": true},
    {"i": 5, "op": "list",   "entries": [{"name": "hi.txt", "type": "file", "size": 3}]},
    {"i": 6, "op": "remove", "removed": true},
    {"i": 7, "op": "exists", "exists": false}
  ],
  "ok": true
}
```

## Common failure modes

| Symptom | Likely cause |
|---|---|
| `KeyError: 'E2B_API_KEY'` | Environment variable not exported |
| Sandbox creation timeout | Wrong `E2B_DOMAIN` for your region |
| `TencentCloudSDKException` on credential check | Invalid or missing `TENCENTCLOUD_SECRET_ID` / `SECRET_KEY` |
| `PermissionError` on `remove_path` | Path owned by another user; re-run as root or use a writeable path |

## Skill interface

```python
file_exists(path: str) -> dict
make_dir(path: str) -> dict
remove_path(path: str) -> dict
list_dir_detailed(path: str = "/tmp") -> dict
rename_path(src: str, dst: str) -> dict
run_batch(ops: list[dict]) -> dict
```
