"""Evaluate a replaceable candidate inside AGS, returning JSON and JUnit reports."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET


CASES = (
    ("empty", [], []),
    ("duplicates", [3, 1, 3, 2, 1], [3, 1, 2]),
    ("already_unique", [1, 2, 3], [1, 2, 3]),
    ("negative_values", [-1, 0, -1, 2], [-1, 0, 2]),
    ("strings", ["b", "a", "b"], ["b", "a"]),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, default=Path(__file__).with_name("candidate.py"))
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).with_name("output"))
    args = parser.parse_args()

    def check(values, expected):
        spec = importlib.util.spec_from_file_location("candidate", args.candidate)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        actual = module.unique_in_order(values)
        if actual != expected:
            raise AssertionError(f"expected {expected!r}, got {actual!r}")

    suite = unittest.TestSuite(
        unittest.FunctionTestCase(lambda v=values, e=expected: check(v, e), description=name)
        for name, values, expected in CASES
    )
    print("Evaluating candidate code inside the sandbox...", flush=True)
    result = unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(suite)
    report = {
        "tests": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "status": "passed" if result.wasSuccessful() else "failed",
    }
    xml = ET.Element("testsuite", name="candidate", **{k: str(report[k]) for k in ("tests", "failures", "errors")})
    problems = {test.shortDescription(): (kind, detail) for kind, items in
                (("failure", result.failures), ("error", result.errors)) for test, detail in items}
    for name, _, _ in CASES:
        case = ET.SubElement(xml, "testcase", classname="candidate", name=name)
        if name in problems:
            kind, detail = problems[name]
            ET.SubElement(case, kind).text = detail
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    ET.ElementTree(xml).write(args.output_dir / "junit.xml", encoding="utf-8", xml_declaration=True)
    print(json.dumps(report), flush=True)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
