"""Check the saved requirements, plan and navigation code without a model."""

import hashlib
from pathlib import Path

from analyst_agent import validate_requirements
from artifact_io import parse_json, read_json, write_json
from developer_agent import check_navigation
from planner_agent import validate_plan


BASE_DIR = Path(__file__).resolve().parent


def matching_exchange(folder, expected_input, expected_output, *, json_output):
    for path in sorted(folder.glob("*.json"), reverse=True):
        record = read_json(path)
        request, response = record.get("request", {}), record.get("response", {})
        messages = request.get("messages", [])
        if len(messages) != 2 or [m.get("role") for m in messages] != ["system", "user"]:
            continue
        try:
            supplied = parse_json(messages[1]["content"])
            received = response["message"]["content"]
            if json_output:
                received = parse_json(received)
        except (KeyError, TypeError, ValueError):
            continue
        if supplied == expected_input and received == expected_output and response.get("done") is True:
            if response.get("done_reason") == "length":
                continue
            options = request.get("options", {})
            if options.get("num_gpu") != 0 or options.get("num_thread") != 2 or request.get("keep_alive") != 0:
                raise ValueError("Recorded model request does not use the approved CPU settings.")
            return {"file": path.name, "model": request.get("model"), "eval_count": response.get("eval_count")}
    raise ValueError(f"No complete model exchange matches the artifacts in {folder.name}.")


def verify(base_dir=BASE_DIR):
    base_dir = Path(base_dir)
    paths = [base_dir / "artifacts" / "requirements.json", base_dir / "artifacts" / "plan.json", base_dir / "navigation_logic.py"]
    requirements = validate_requirements(read_json(paths[0]))
    plan = validate_plan(read_json(paths[1]))
    code = paths[2].read_text(encoding="utf-8")
    cases = check_navigation(code, plan)
    evidence = {
        "planner": matching_exchange(base_dir / "artifacts" / "planner_runs", requirements, plan, json_output=True),
        "developer": matching_exchange(base_dir / "artifacts" / "developer_runs", plan, code, json_output=False),
    }
    report = {
        "status": "passed",
        "scenario_count": len(cases),
        "scope": "All 8 boolean obstacle combinations times 4 supported goal values; not a physical robot or route simulation.",
        "sha256": {p.relative_to(base_dir).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        "model_evidence": evidence,
        "cases": cases,
    }
    write_json(base_dir / "artifacts" / "navigation_verification.json", report)
    return report


def main():
    try:
        report = verify()
        print(f"PASS: {report['scenario_count']} navigation scenarios; artifacts also match their recorded model exchanges.")
        print("Saved artifacts/navigation_verification.json. No model was called.")
        return 0
    except (OSError, ValueError) as error:
        print(f"Verification failed: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
