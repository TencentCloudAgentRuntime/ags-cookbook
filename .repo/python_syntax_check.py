#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import py_compile
import sys

ROOT = Path(__file__).resolve().parent.parent
EXCLUDE_PARTS = {'.git', '.venv', '__pycache__', 'reports'}
EXCLUDE_PREFIXES = [ROOT / 'examples' / 'osworld-ags' / 'osworld']

files = []
for path in ROOT.rglob('*.py'):
    if any(part in EXCLUDE_PARTS for part in path.parts):
        continue
    if any(path.is_relative_to(prefix) for prefix in EXCLUDE_PREFIXES if prefix.exists()):
        continue
    files.append(path)

errors = []
for path in sorted(files):
    try:
        py_compile.compile(str(path), doraise=True)
    except py_compile.PyCompileError as exc:
        errors.append(f"{path.relative_to(ROOT)}: {exc.msg}")

if errors:
    print('Python syntax check failed:\n')
    for err in errors:
        print(f'- {err}')
    sys.exit(1)

print(f'Python syntax check passed for {len(files)} files.')
