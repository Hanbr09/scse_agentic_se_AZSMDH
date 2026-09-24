"""Check the saved requirements, plan and navigation code without a model."""

import hashlib
from pathlib import Path

from analyst_agent import MODEL, SYSTEM_PROMPT as ANALYST_PROMPT, validate_requirements
from artifact_io import parse_json, read_json, write_json
from developer_agent import SYSTEM_PROMPT as DEVELOPER_PROMPT, check_navigation, validate_code
from planner_agent import SYSTEM_PROMPT as PLANNER_PROMPT, validate_plan


BASE_DIR = Path(__file__).resolve().parent


def matching_exchange(folder, expected_input, expected_output, *, json_output, prompt, text_input=False):
    for path in sorted(folder.glob("*.json"), reverse=True):
        record = read_json(path)
        request, response = record.get("request", {}), record.get("response", {})
        messages = request.get("messages", [])
        if len(messages) != 2 or [m.get("role") for m in messages] != ["system", "user"]:
            continue
        if messages[0].get("content") != prompt or request.get("model") != MODEL:
            continue
        try:
            supplied = messages[1]["content"] if text_input else parse_json(messages[1]["content"])
            received = response["message"]["content"]
            if json_output:
                received = parse_json(received)
            else:
                received = received.replace("\r\n", "\n").replace("\r", "\n")
        except (KeyError, TypeError, ValueError):
            continue
        if supplied == expected_input and received == expected_output and response.get("done") is True:
            if response.get("done_reason") == "length":
                continue
            options = request.get("options", {})
            if (options != {"temperature": 0, "num_gpu": 0, "num_thread": 2, "num_ctx": 2048, "num_predict": 768}
                    or request.get("keep_alive") != 0 or request.get("stream") is not False):
                raise ValueError("Recorded model request does not use the approved CPU settings.")
            return {"file": path.name, "model": request.get("model"), "eval_count": response.get("eval_count")}
    raise ValueError(f"No complete model exchange matches the artifacts in {folder.name}.")


def verify(base_dir=BASE_DIR):
    base_dir = Path(base_dir)
    paths = [base_dir / "artifacts" / "requirements.json", base_dir / "artifacts" / "plan.json",
             base_dir / "generated" / "navigation_logic.py"]
    requirements = validate_requirements(read_json(paths[0]))
    plan = validate_plan(read_json(paths[1]))
    code = paths[2].read_text(encoding="utf-8")
    validate_code(code, plan)
    for mirror in (base_dir / "navigation_logic.py", base_dir / "artifacts" / "navigation_logic.py"):
        if mirror.read_text(encoding="utf-8") != code:
            raise ValueError("The generated artifact and compatibility copies differ.")
        paths.append(mirror)
    cases = check_navigation(code, plan)
    brief = (base_dir / "brief.txt").read_text(encoding="utf-8-sig")
    paths.append(base_dir / "brief.txt")
    evidence = {
        "analyst": matching_exchange(base_dir / "artifacts" / "analyst_runs", brief, requirements,
                                     json_output=True, prompt=ANALYST_PROMPT, text_input=True),
        "planner": matching_exchange(base_dir / "artifacts" / "planner_runs", requirements, plan,
                                     json_output=True, prompt=PLANNER_PROMPT),
        "developer": matching_exchange(base_dir / "artifacts" / "developer_runs", plan, code,
                                       json_output=False, prompt=DEVELOPER_PROMPT),
    }
    report = {
        "status": "passed",
        "scenario_count": len(cases),
        "scope": "All 8 obstacle patterns times 8 goal-flag patterns, including the original 32 single-goal/unknown states.",
        "multiple_goal_policy": "Prefer the first clear indicated goal: ahead, left, then right.",
        "limitations": ["Not a physical robot or route simulation", "Missing or non-boolean sensor fields are outside the input contract"],
        "previous_logic_retained": True,
        "hash_convention": "UTF-8 text with CRLF/CR normalized to LF; no other content changes.",
        "sha256_utf8_lf": {
            p.relative_to(base_dir).as_posix(): hashlib.sha256(p.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
            for p in paths
        },
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
