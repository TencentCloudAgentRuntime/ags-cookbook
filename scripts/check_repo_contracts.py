#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES_DIR = ROOT / "examples"
EXAMPLE_DIRS = sorted([p for p in EXAMPLES_DIR.iterdir() if p.is_dir()])

errors: list[str] = []


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def require_contains(path: Path, needle: str, label: str) -> None:
    text = read(path)
    if needle not in text:
        errors.append(f"{path.relative_to(ROOT)} missing {label}: {needle}")


root_readmes = [ROOT / "README.md", ROOT / "README_zh.md", ROOT / "examples" / "README.md"]
for example_dir in EXAMPLE_DIRS:
    name = example_dir.name
    for doc in root_readmes:
        require_contains(doc, f"`{name}`", f"example reference for {name}")

for example_dir in EXAMPLE_DIRS:
    name = example_dir.name
    readme = example_dir / "README.md"
    makefile = example_dir / "Makefile"
    if not readme.exists():
        errors.append(f"{example_dir.relative_to(ROOT)} missing README.md")
        continue
    if not makefile.exists():
        errors.append(f"{example_dir.relative_to(ROOT)} missing Makefile")
        continue

    readme_text = read(readme)
    make_text = read(makefile)

    if not re.search(r"(?m)^run:", make_text):
        errors.append(f"{makefile.relative_to(ROOT)} missing run target")
    if "make run" not in readme_text:
        errors.append(f"{readme.relative_to(ROOT)} should mention make run")

    if re.search(r"(?m)^setup:\s*$", make_text) and "make setup" not in readme_text:
        errors.append(f"{readme.relative_to(ROOT)} should mention make setup because Makefile provides setup")

    pyproject = example_dir / "pyproject.toml"
    uv_lock = example_dir / "uv.lock"
    if pyproject.exists() and not uv_lock.exists():
        errors.append(f"{example_dir.relative_to(ROOT)} has pyproject.toml but no uv.lock")

    if name == "osworld-ags" and "osworld/.venv" not in readme_text:
        errors.append(f"{readme.relative_to(ROOT)} should document isolated osworld/.venv usage")

if errors:
    print("Repository contract check failed:\n")
    for item in errors:
        print(f"- {item}")
    sys.exit(1)

print(f"Repository contract check passed for {len(EXAMPLE_DIRS)} examples.")
