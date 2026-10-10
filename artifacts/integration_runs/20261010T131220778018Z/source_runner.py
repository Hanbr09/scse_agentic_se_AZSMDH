"""Check every six-boolean sensor state against an independent action table."""

import argparse
from itertools import product
from pathlib import Path

from artifact_io import write_json
from developer_agent import load_navigation


ROOT = Path(__file__).resolve().parent
KEYS = ("front_blocked", "left_blocked", "right_blocked",
        "goal_ahead", "goal_on_left", "goal_on_right")
# Columns are the eight front/left/right obstacle patterns in binary order.
EXPECTED = {
    "": ("FORWARD", "FORWARD", "FORWARD", "FORWARD", "LEFT", "LEFT", "RIGHT", "STOP"),
    "A": ("FORWARD", "FORWARD", "FORWARD", "FORWARD", "LEFT", "LEFT", "RIGHT", "STOP"),
    "L": ("LEFT", "LEFT", "FORWARD", "FORWARD", "LEFT", "LEFT", "RIGHT", "STOP"),
    "R": ("RIGHT", "FORWARD", "RIGHT", "FORWARD", "RIGHT", "LEFT", "RIGHT", "STOP"),
    "AL": ("FORWARD", "FORWARD", "FORWARD", "FORWARD", "LEFT", "LEFT", "RIGHT", "STOP"),
    "AR": ("FORWARD", "FORWARD", "FORWARD", "FORWARD", "RIGHT", "LEFT", "RIGHT", "STOP"),
    "LR": ("LEFT", "LEFT", "RIGHT", "FORWARD", "LEFT", "LEFT", "RIGHT", "STOP"),
    "ALR": ("FORWARD", "FORWARD", "FORWARD", "FORWARD", "LEFT", "LEFT", "RIGHT", "STOP"),
}


def scenario_cases():
    cases = []
    for goals, actions in EXPECTED.items():
        for blocked, action in zip(product((False, True), repeat=3), actions):
            values = blocked + tuple(letter in goals for letter in "ALR")
            cases.append((dict(zip(KEYS, values)), action))
    return cases


def run_simulation(code, output_path=None):
    decide = load_navigation(code)
    results = []
    for number, (state, expected) in enumerate(scenario_cases(), 1):
        supplied = state.copy()
        actual, error = None, None
        try:
            actual = decide(supplied)
            if not isinstance(actual, str):
                raise ValueError("Action must be a string.")
            if supplied != state:
                raise ValueError("Navigation changed the caller's state.")
        except Exception as failure:
            error = f"{type(failure).__name__}: {failure}"
            actual = actual if isinstance(actual, str) else None
        results.append({"id": number, "state": state, "expected": expected,
                        "actual": actual, "passed": error is None and actual == expected,
                        "error": error})
    passed = sum(result["passed"] for result in results)
    report = {"total_scenarios": len(results), "passed": passed,
              "failed": len(results) - passed, "success_rate": passed / len(results),
              "scope": "All 64 combinations; not a physical route guarantee.",
              "results": results}
    if output_path is not None:
        write_json(output_path, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--code", type=Path, default=ROOT / "generated/navigation_logic.py")
    parser.add_argument("--report", type=Path, default=ROOT / "artifacts/simulation_report.json")
    args = parser.parse_args()
    report = run_simulation(args.code.read_text(encoding="utf-8"), args.report)
    print(f"Navigation scenarios: {report['passed']}/{report['total_scenarios']} passed.")
    return int(report["failed"] != 0)


if __name__ == "__main__":
    raise SystemExit(main())
