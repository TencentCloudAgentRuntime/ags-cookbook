from __future__ import annotations

import hashlib
import json
from pathlib import Path
import platform


root = Path.cwd()
readme = root / "README.md"
if not readme.is_file():
    raise SystemExit("README.md was not uploaded with the checkout")

output = Path(__file__).resolve().parent / "output"
output.mkdir(parents=True, exist_ok=True)
result = {
    "message": "GitHub checkout executed inside an isolated AGS sandbox",
    "python": platform.python_version(),
    "readme_sha256": hashlib.sha256(readme.read_bytes()).hexdigest(),
}
(output / "result.json").write_text(
    json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
print(json.dumps(result, sort_keys=True))
