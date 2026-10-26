r"""运行 Day10 离线规则验收，输出 JUnit、逐案例诊断和独立统计。

    .\.venv\Scripts\python.exe examples/day10_evaluate.py
    .\.venv\Scripts\python.exe examples/day10_evaluate.py --layer e2e

不会调用真实模型。Mock 故意说错被拦截属于规则测试成功，不是真实模型错误率。
"""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4
import xml.etree.ElementTree as ET


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--layer", choices=["all", "fixed", "e2e"], default="all")
    parser.add_argument("--case", choices=[f"R{index:02}" for index in range(1, 16)])
    parser.add_argument("--output", type=Path, help="新建的输出目录；不覆盖已有目录")
    args = parser.parse_args(argv)
    if args.layer == "e2e" and args.case and args.case not in {f"R{index:02}" for index in range(1, 6)}:
        parser.error("端到端层仅覆盖 R01～R05")
    project = Path(__file__).resolve().parents[1]
    output = (args.output or project / "data" / "reports" / "day10-rules" / uuid4().hex[:12]).resolve()
    output.mkdir(parents=True, exist_ok=False)
    xml_path = output / "junit.xml"
    command = [sys.executable, "-m", "pytest", "tests/test_day10_cases.py", "-q",
               f"--junitxml={xml_path}", "-o", "junit_family=xunit1"]
    selection = {
        "fixed": "test_fixed_evidence_cases",
        "e2e": "test_end_to_end_retrieval_cases",
    }.get(args.layer)
    if args.case:
        selection = f"({selection}) and {args.case}" if selection else args.case
    if selection:
        command += ["-k", selection]
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    completed = subprocess.run(command, cwd=project, env=environment,
                               capture_output=True, text=True, encoding="utf-8")
    print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="", file=sys.stderr)
    runs = []
    counts = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}
    if xml_path.exists():
        root = ET.parse(xml_path).getroot()
        for test in root.iter("testcase"):
            state = ("failed" if test.find("failure") is not None else
                     "errors" if test.find("error") is not None else
                     "skipped" if test.find("skipped") is not None else "passed")
            counts[state] += 1
            properties = {item.get("name"): item.get("value") for item in test.findall("properties/property")}
            if properties.get("case_id"):
                diagnostics = json.loads(properties.pop("diagnostics", "{}"))
                runs.append({**properties, "test_outcome": state, "diagnostics": diagnostics})
    summary = {
        "evaluation_kind": "mock_rule_tests",
        "pytest_exit_code": completed.returncode,
        "rule_tests": counts,
        "fixed_case_runs": sum(run.get("layer") == "fixed" for run in runs),
        "end_to_end_case_runs": sum(run.get("layer") == "e2e" for run in runs),
        "covered_parent_case_ids": sorted({run["case_id"] for run in runs}),
        "fixture_reviews_are_not_human_acceptance": True,
        "real_model_quality": {"status": "not_measured", "model_calls": 0, "error_rate": None},
    }
    (output / "cases.json").write_text(json.dumps(runs, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output_directory": str(output), **summary}, ensure_ascii=False, indent=2))
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
