"""
skill-data-analysis: sandboxed data analysis and chart generation skill.

Authentication is auto-detected by ``ags_client.SandboxSession``:

  * ``TENCENTCLOUD_SECRET_ID`` / ``TENCENTCLOUD_SECRET_KEY`` set → AKSK mode.
  * Otherwise ``E2B_API_KEY`` / ``E2B_DOMAIN`` must be set → APIKey mode.

Demonstrates:
  1. Uploading a CSV dataset into the sandbox
  2. Running pandas aggregation and matplotlib chart generation inside the sandbox
  3. Downloading the generated PNG chart back locally
  4. Returning summary statistics + chart path to an Agent

Skills exposed:
  - analyse_csv(csv_text, group_by, value_col, chart_path)
"""

import json
import logging
import textwrap

from ags_client import SandboxSession

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Skill: analyse_csv
# ---------------------------------------------------------------------------

def analyse_csv(
    csv_text: str,
    group_by: str,
    value_col: str,
    chart_path: str = "chart.png",
) -> dict:
    """Upload *csv_text*, compute grouped sum/mean/count of *value_col* by
    *group_by*, generate a matplotlib bar chart, download it to *chart_path*.

    The sandbox lifecycle is managed by ``SandboxSession``; the underlying
    credential mode (AKSK vs APIKey) is auto-detected at runtime.
    """
    log.info("analyse_csv: group_by=%s value_col=%s", group_by, value_col)

    analysis_code = textwrap.dedent(f"""
        import json
        import pandas as pd
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        df = pd.read_csv("/tmp/input.csv")
        grouped = df.groupby({group_by!r})[{value_col!r}].agg(["sum", "mean", "count"])
        grouped.columns = ["sum", "mean", "count"]
        grouped = grouped.sort_values("sum", ascending=False)

        summary = grouped.reset_index().to_dict(orient="records")
        print(json.dumps(summary))

        fig, ax = plt.subplots(figsize=(8, 5))
        ax.bar(grouped.index.astype(str), grouped["sum"], color="steelblue")
        ax.set_title(f"Sum of {value_col!r} by {group_by!r}")
        ax.set_xlabel({group_by!r})
        ax.set_ylabel(f"Sum of {value_col!r}")
        plt.xticks(rotation=30, ha="right")
        plt.tight_layout()
        plt.savefig("/tmp/chart.png", dpi=150)
        plt.close()
        print("chart saved")
    """)

    with SandboxSession() as sbx:
        sbx.files.write("/tmp/input.csv", csv_text)
        log.info("Uploaded %d bytes to /tmp/input.csv", len(csv_text))

        lines: list[str] = []
        execution = sbx.run_code(
            analysis_code,
            on_stdout=lambda msg: lines.append(msg.line),
        )
        error = execution.error.value if execution.error else None

        summary = []
        if not error and lines:
            try:
                summary = json.loads(lines[0])
            except json.JSONDecodeError:
                log.warning("Could not parse summary JSON from stdout")

        if not error:
            try:
                chart_bytes: bytes = sbx.files.read("/tmp/chart.png", format="bytes")
                with open(chart_path, "wb") as f:
                    f.write(chart_bytes)
                log.info("Chart saved to %s (%d bytes)", chart_path, len(chart_bytes))
            except Exception as exc:
                log.error("Chart download failed: %s", exc)
                error = str(exc)

    log.info("analyse_csv: done, error=%s", error)
    return {
        "summary": summary,
        "chart_path": chart_path if not error else None,
        "stdout": lines,
        "error": error,
    }


# ---------------------------------------------------------------------------
# Entry point — demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sample_csv = """category,region,revenue,units
Electronics,North,15000,120
Electronics,South,9800,80
Clothing,North,7200,200
Clothing,South,6100,180
Books,North,3400,340
Books,South,2900,290
Home,North,8800,90
Home,South,7100,75
"""
    log.info("=== Demo: analyse_csv ===")
    result = analyse_csv(
        csv_text=sample_csv,
        group_by="category",
        value_col="revenue",
        chart_path="revenue_by_category.png",
    )
    print("\n=== Skill Result: analyse_csv ===")
    print(json.dumps(result, indent=2, ensure_ascii=False))
