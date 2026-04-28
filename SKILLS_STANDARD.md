# AGS Skills Integration Standard

This document defines the **canonical standard** for adding Skills-based examples to the AGS Cookbook.
All new Skills examples **must** follow these conventions.

---

## 1. What is a Skill?

A **Skill** is a plain Python callable that an Agent registers as a named tool.
The callable receives structured arguments from an Agent's tool-call payload,
performs work (optionally inside an AGS sandbox), and returns a JSON-serialisable `dict`.

```
Agent  ──tool-call──▶  Skill function  ──sandboxed execution──▶  AGS
                                    ◀──structured result──────────
```

---

## 2. Mandatory dependencies

Every Skills example **must** declare exactly these two runtime dependencies
(minimum versions may be updated as the ecosystem evolves):

| Package | Minimum version | Purpose |
|---|---|---|
| `e2b-code-interpreter` | `>=2.4.1` | Sandboxed code execution inside AGS |
| `tencentcloud-sdk-python` | `>=3.0.0` | Tencent Cloud control-plane calls |

Additional libraries may be added as needed, but these two are non-negotiable.

---

## 3. Python version

All Skills examples **must** target **Python 3.13**:

```toml
# pyproject.toml
[project]
requires-python = ">=3.13"
```

`uv` is used to manage the interpreter and virtual environment.
The project must not assume a system Python.

---

## 4. Dependency management with `uv`

- Use `pyproject.toml` + `uv.lock` for all dependency declarations.
- Do **not** use `requirements.txt` or bare `pip`.
- `Makefile` targets must use `uv sync` / `uv run`:

```makefile
.PHONY: setup run

setup:
	uv sync

run:
	uv run main.py
```

---

## 5. Project layout

Each Skills example lives under `examples/<skill-name>/` and must contain:

```
examples/<skill-name>/
├── main.py            # entry point; each skill is a plain callable
├── pyproject.toml     # project metadata and dependencies
├── uv.lock            # committed lockfile
├── Makefile           # at minimum: setup + run targets
├── .env.example       # placeholder env vars; never commit real secrets
├── README.md          # English; see §6
└── README_zh.md       # Chinese translation (mandatory for Skills examples)
```

---

## 6. README requirements

`README.md` **must be written in English**.
`README_zh.md` is **mandatory** for all Skills examples.

Each README must cover all seven sections in this order:

1. **What the example demonstrates** — one-paragraph summary
2. **Prerequisites** — Python version, `uv`, any external tools
3. **Required environment variables** — table or fenced block
4. **Install steps** — `make setup` (or equivalent)
5. **Run command** — `make run` (or equivalent)
6. **Expected output or artifacts** — exact or representative output
7. **Common failure modes** — at least the three canonical failure modes below

### Canonical failure modes (include all three)

| Symptom | Likely cause |
|---|---|
| `KeyError: 'E2B_API_KEY'` | Environment variable not exported |
| Sandbox creation timeout | Wrong `E2B_DOMAIN` for your region |
| `TencentCloudSDKException` on credential check | Invalid or missing `TENCENTCLOUD_SECRET_ID` / `SECRET_KEY` |

---

## 7. Environment variables

### AGS sandbox (required)

```bash
export E2B_API_KEY="your_ags_api_key"
export E2B_DOMAIN="ap-guangzhou.tencentags.com"   # region-specific
```

### Tencent Cloud control-plane (required when using tencentcloud-sdk-python)

```bash
export TENCENTCLOUD_SECRET_ID="your_secret_id"
export TENCENTCLOUD_SECRET_KEY="your_secret_key"
export TENCENTCLOUD_REGION="ap-guangzhou"
```

Rules:
- All secrets are read from environment variables. **Never hard-code credentials.**
- Provide `.env.example` with placeholder values only.
- Load `.env` via shell `export` or a loader such as `python-dotenv` — never committed.

---

## 8. Skill interface contract

```python
def skill_name(arg1: SomeType, arg2: SomeType) -> dict:
    """One-line docstring describing what the skill does."""
    ...
    return {
        "field": value,   # must be JSON-serialisable
    }
```

- Each skill is a **pure function** with respect to secrets (reads from env, not parameters).
- The return value **must** be JSON-serialisable.
- Use `logging` (not `print`) for diagnostic output inside the skill body.
- `print` is acceptable only in the `__main__` block for human-readable final output.

---

## 9. Logging

```python
import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)
```

- Use `log.info` for progress milestones (sandbox created, skill invoked, sandbox closed).
- Use `log.error` for recoverable errors; let unrecoverable errors propagate as exceptions.

---

## 10. Commit and PR conventions

Inherited from [CONTRIBUTING.md](./CONTRIBUTING.md); Skills-specific additions:

- Commit prefix: `feat(skills):` for new skills, `fix(skills):` for corrections
- PR **must** update `examples/README.md` (example list table) and root `README.md` (example overview table)
- English and Chinese READMEs must be updated together in the same commit
- The `uv.lock` file **must** be committed alongside `pyproject.toml`

---

## 11. Reference example

`examples/skills-hello-world` is the canonical reference that implements every rule in this document.
Use it as the starting template for new Skills examples.

```bash
make example-setup EXAMPLE=skills-hello-world
make example-run   EXAMPLE=skills-hello-world
```
