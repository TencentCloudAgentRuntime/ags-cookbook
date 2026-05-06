"""
skill-data-pipeline: multi-context data-analysis pipeline in a single sandbox.

Mirrors the ``examples/data-analysis`` cookbook example: a three-stage pipeline
where each stage runs in an isolated Python context (variables do not leak)
but all stages share the sandbox filesystem, so artefacts (CSV, JSON, PNG)
written by stage N are available to stage N+1.

Each stage is described as::

    {"name": "load",      "code": "...", "writes": ["/tmp/raw.parquet"]}
    {"name": "transform", "code": "...", "writes": ["/tmp/clean.parquet"]}
    {"name": "chart",     "code": "...", "writes": ["/tmp/chart.png"]}

``writes`` is purely declarative metadata captured in the result; the skill
does not enforce it (the stage code is responsible for actually writing).

Skills exposed:
  - run_pipeline(stages, downloads=None, tool_name="code-interpreter-v1")
"""

import json
import logging
import os

from ags_client import SandboxSession

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)


def _execute_stage(sbx, ctx, code: str, stage_name: str) -> dict:
    """Run a single code string in ``ctx``; collect stdout / error summary."""
    lines: list[str] = []
    execution = sbx.run_code(
        code,
        context=ctx,
        on_stdout=lambda msg, n=stage_name: lines.append(f"[{n}] {str(getattr(msg,'line',msg))}"),
    )
    error = execution.error.value if execution.error else None
    texts = [r.text for r in execution.results if hasattr(r, "text")]
    return {"stdout": lines, "text_results": texts, "error": error}


# ---------------------------------------------------------------------------
# Skill: run_pipeline
# ---------------------------------------------------------------------------

def run_pipeline(
    stages: list[dict],
    downloads: list[str] | None = None,
    tool_name: str = "code-interpreter-v1",
    timeout: str = "10m",
) -> dict:
    """Run ``stages`` sequentially in one sandbox; download listed artefacts.

    For each stage we create a **fresh code context** so Python-level state
    is isolated between stages; the underlying filesystem is shared so files
    flow between them.  If any stage's ``code`` raises, subsequent stages are
    skipped and the pipeline is reported as failed.

    Args:
        stages: list of ``{name, code, writes?}`` dicts.
        downloads: after all stages complete, read these sandbox paths back as
                   bytes and record ``size`` / local ``saved_to`` path.
        tool_name: AGS sandbox tool to use.
        timeout: session timeout.

    Returns:
        ``{"stages": [...], "downloads": [...], "ok": bool}``.
    """
    log.info("run_pipeline: %d stages (downloads=%d)", len(stages), len(downloads or []))
    stage_results: list[dict] = []
    artefacts: list[dict] = []
    ok = True

    with SandboxSession(tool_name=tool_name, timeout=timeout) as sbx:
        for i, stage in enumerate(stages):
            name = stage.get("name") or f"stage-{i}"
            code = stage.get("code", "")
            writes = stage.get("writes") or []

            if not ok:
                stage_results.append({"i": i, "name": name, "skipped": True})
                continue

            log.info("run_pipeline: stage %d (%s) starting", i, name)
            ctx = sbx.create_code_context()
            outcome = _execute_stage(sbx, ctx, code, name)
            stage_results.append({
                "i": i,
                "name": name,
                "writes": writes,
                **outcome,
            })
            if outcome["error"] is not None:
                ok = False

        # Download declared artefacts even if one stage failed — earlier
        # intermediates may still be useful for debugging.
        for path in downloads or []:
            try:
                data: bytes = sbx.files.read(path, format="bytes")
                local = os.path.basename(path) or "artifact.bin"
                with open(local, "wb") as f:
                    f.write(data)
                artefacts.append({
                    "remote": path, "saved_to": local, "size": len(data), "error": None,
                })
            except Exception as e:  # noqa: BLE001
                artefacts.append({
                    "remote": path, "saved_to": None, "size": 0, "error": str(e),
                })

    return {"stages": stage_results, "downloads": artefacts, "ok": ok}


# ---------------------------------------------------------------------------
# Entry point — demo a 3-stage pipeline
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    log.info("=== Demo: 3-stage data pipeline ===")

    stage_load = {
        "name": "load",
        "writes": ["/tmp/raw.csv"],
        "code": (
            "import csv\n"
            "rows = [\n"
            "    {'category': 'Electronics', 'region': 'N', 'revenue': 15000},\n"
            "    {'category': 'Electronics', 'region': 'S', 'revenue': 9800},\n"
            "    {'category': 'Clothing',    'region': 'N', 'revenue': 7200},\n"
            "    {'category': 'Clothing',    'region': 'S', 'revenue': 6100},\n"
            "    {'category': 'Books',       'region': 'N', 'revenue': 3400},\n"
            "    {'category': 'Books',       'region': 'S', 'revenue': 2900},\n"
            "]\n"
            "with open('/tmp/raw.csv','w',newline='') as f:\n"
            "    w = csv.DictWriter(f, fieldnames=['category','region','revenue'])\n"
            "    w.writeheader(); w.writerows(rows)\n"
            "print(f'wrote {len(rows)} rows')\n"
        ),
    }
    stage_transform = {
        "name": "transform",
        "writes": ["/tmp/summary.json"],
        "code": (
            "import csv, json\n"
            "agg = {}\n"
            "for row in csv.DictReader(open('/tmp/raw.csv')):\n"
            "    agg[row['category']] = agg.get(row['category'], 0) + int(row['revenue'])\n"
            "summary = sorted(agg.items(), key=lambda kv: -kv[1])\n"
            "open('/tmp/summary.json','w').write(json.dumps(summary, indent=2))\n"
            "print(f'top category: {summary[0]}')\n"
        ),
    }
    stage_chart = {
        "name": "chart",
        "writes": ["/tmp/chart.png"],
        "code": (
            "import json, matplotlib\n"
            "matplotlib.use('Agg')\n"
            "import matplotlib.pyplot as plt\n"
            "data = json.load(open('/tmp/summary.json'))\n"
            "cats, values = zip(*data)\n"
            "plt.figure(figsize=(6,4))\n"
            "plt.bar(cats, values, color='steelblue')\n"
            "plt.title('Revenue by category')\n"
            "plt.tight_layout()\n"
            "plt.savefig('/tmp/chart.png', dpi=120)\n"
            "print('saved chart')\n"
        ),
    }

    result = run_pipeline(
        [stage_load, stage_transform, stage_chart],
        downloads=["/tmp/summary.json", "/tmp/chart.png"],
    )
    print("\n=== Skill Result: run_pipeline ===")
    print(json.dumps(result, indent=2, ensure_ascii=False))
