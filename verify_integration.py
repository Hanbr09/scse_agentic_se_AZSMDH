"""Audit a saved integration run without starting a model or simulator."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

from analyst_agent import validate_requirements
from artifact_io import parse_json, read_json
from benchmark_irsim import WORLDS, summarize, validate_world_report
from developer_agent import ORIGINAL_CODE, validate_code
from planner_agent import validate_plan
from reviewer_agent import validate_review
from reviewer_benchmark_agent import BOOL_KEYS, KEYS, build_deterministic_review
from runner import run_simulation
from test_agent import validate_test_code


ROOT = Path(__file__).resolve().parent


def require(condition, message):
    if not condition:
        raise ValueError(message)


def text_hash(path):
    # Git may change checkout line endings; compare the same UTF-8/LF text.
    return hashlib.sha256(Path(path).read_text(encoding="utf-8").encode("utf-8")).hexdigest()


def code_hash(code):
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def exchange(folder, stage, expected_input):
    paths = list((folder / "exchanges" / stage).glob("*.json"))
    require(len(paths) == 1, f"{stage}: expected exactly one recorded exchange")
    record = read_json(paths[0])
    request, response = record["request"], record["response"]
    require("error" not in record and response["done"] is True
            and response["done_reason"] == "stop", f"{stage}: incomplete response")
    require(request["model"] == response["model"] == "qwen2.5:3b", "Wrong model")
    require(request["options"] == {"temperature": 0, "seed": 48391, "num_gpu": 99,
                                   "num_thread": 2, "num_ctx": 8192, "num_predict": 2048},
            "Unexpected recorded model settings")
    messages = request["messages"]
    require(len(messages) == 2 and messages[0]["role"] == "system"
            and messages[1]["role"] == "user", "Unexpected conversation structure")
    actual_input = messages[1]["content"]
    if not isinstance(expected_input, str):
        actual_input = parse_json(actual_input)
    require(actual_input == expected_input, f"{stage}: upstream input does not match")
    models = record["loaded_models"]["models"]
    require(any(m["name"] == request["model"] and m["size"] > 0
                and m["size_vram"] >= m["size"] * 0.99 for m in models), "GPU evidence missing")
    for key in ("hardware_before", "hardware_after"):
        require(record[key]["ram_gib"] >= 1.25 and record[key]["gpu_c"] < 80,
                "Recorded hardware limit exceeded")
    require(response["eval_count"] > 0 and response["prompt_eval_count"] > 0,
            "Model token counts missing")
    return response["message"]["content"]


def verify_pytest(folder, tests, code, report):
    for name, key in (("pytest", "normal"), ("mutation_control", "mutation_control")):
        saved = read_json(folder / name / "result.json")
        require(saved == report[key], "Pytest summary differs from recorded result")
        suites = list(ET.parse(folder / name / "results.xml").getroot().iter("testsuite"))
        for count in ("tests", "failures", "errors", "skipped"):
            require(saved[count] == sum(int(s.get(count, 0)) for s in suites),
                    "Pytest summary differs from JUnit XML")
        require((folder / name / "test_navigation.py").read_text(encoding="utf-8") == tests,
                "Different generated tests were executed")
        expected_code = code if name == "pytest" else "def decide_next_move(state):\n    return 'STOP'\n"
        require((folder / name / "generated/navigation_logic.py").read_text(encoding="utf-8") == expected_code,
                "Different navigation was tested")
    require(report["normal"] == {"tests": 64, "failures": 0, "errors": 0,
                                  "skipped": 0, "returncode": 0, "passed": True}, "Tests did not pass")
    mutation = report["mutation_control"]
    require(mutation["tests"] == 64 and mutation["failures"] > 0 and mutation["errors"] == 0
            and mutation["skipped"] == 0 and mutation["returncode"] == 1
            and report["mutation_detected"] is True and report["passed"] is True,
            "Wrong-action control was not detected")


def verify_worlds(folder, code, benchmark):
    results = []
    for name in WORLDS:
        directory = folder / "worlds" / Path(name).stem
        report = validate_world_report(read_json(directory / "report.json"))
        original = read_json(directory / "work/artifacts/irsim_report.json")
        require(all(report[k] == v for k, v in original.items()), "Teacher report changed")
        require(report["world"] == name and report["navigation_sha256"] == code_hash(code),
                "World was run with a different navigation source")
        require(report["world_sha256"] == text_hash(ROOT / "irsim_worlds" / name), "World hash differs")
        require(text_hash(directory / "work/irsim_worlds" / name) == report["world_sha256"],
                "Simulation used a changed world")
        require(text_hash(directory / "work/test_irsim_with_agent.py") == text_hash(ROOT / "test_irsim_with_agent.py"),
                "Simulation used a changed teacher script")
        require(text_hash(directory / "work/generated/navigation_logic.py") == code_hash(code),
                "Simulation workspace navigation differs")
        trace = read_json(directory / "trajectory.json")
        require(len(trace["poses"]) == report["steps_taken"] + 1
                and trace["poses"][-1] == report["final_pose"], "Trajectory differs from report")
        require(trace["collision_before_cleanup"] == report["collision_before_cleanup"]
                and trace["done_before_cleanup"] == report["done_before_cleanup"], "Cleanup capture differs")
        distance = math.dist(trace["poses"][-1][:2], trace["goal"][:2])
        require(report["reached_goal"] == (distance < 0.4), "Goal flag differs from measured distance")
        require((directory / "trajectory.png").stat().st_size > 1000
                and (directory / "simulation.gif").stat().st_size > 1000, "Visual evidence missing")
        results.append(report)
    require(benchmark == summarize(results), "Benchmark does not match individual worlds")
    require(read_json(folder / "worlds/irsim_benchmark_report.json") == benchmark, "World aggregate differs")
    require(read_json(folder / "worlds/completed_worlds.json") == results, "Incomplete world sequence")


def verify(output):
    output = Path(output).resolve()
    provenance = read_json(ROOT / "artifacts/integration_starter.json")
    for relative, expected in provenance["files"].items():
        require(text_hash(ROOT / relative) == expected, f"Teacher file changed: {relative}")
    for relative, expected in provenance["previous_source_files"].items():
        require(text_hash(ROOT / relative) == expected, f"Previous source changed: {relative}")
    for name, digest in read_json(output / "source_hashes.json").items():
        require(text_hash(ROOT / name) == digest and text_hash(output / ("source_" + name)) == digest,
                f"Source has changed since this run: {name}")
    brief = (output / "brief.txt").read_text(encoding="utf-8")
    require(brief == (ROOT / "brief.txt").read_text(encoding="utf-8-sig"), "Brief changed")
    previous = None
    rounds = []
    for number in range(2):
        folder = output / f"round_{number}"
        requirements = validate_requirements(read_json(folder / "requirements.json"))
        plan = validate_plan(read_json(folder / "plan.json"))
        code = validate_code((folder / "navigation_logic.py").read_text(encoding="utf-8"), plan)
        require(parse_json(exchange(folder, "analyst", brief)) == requirements, "Requirements not model output")
        require(parse_json(exchange(folder, "planner", requirements)) == plan, "Plan not model output")
        if previous is None:
            require(exchange(folder, "developer", plan) == code, "Navigation not model output")
        else:
            payload = {"original_code": previous["code"], "requirements": requirements, "plan": plan,
                       "review_notes": {"simulation": previous["simulation_review"],
                                        "benchmark": previous["benchmark_review"]},
                       "benchmark_report": previous["benchmark"]}
            reply = parse_json(exchange(folder, "developer_revision", payload))
            require(set(reply) == {"code"}
                    and ORIGINAL_CODE.rstrip() + "\n\n" + reply["code"] == code,
                    "Revision does not preserve the helper and verbatim model adapter")
            require(code != previous["code"], "Revision did not change source")
        tests = validate_test_code((folder / "test_navigation.py").read_text(encoding="utf-8"))
        require(parse_json(exchange(folder, "test_agent", {"brief": brief, "requirements": requirements,
                                                         "plan": plan, "navigation_code": code})) == {"code": tests},
                "Tests not model output")
        testing = read_json(folder / "test_report.json")
        verify_pytest(folder, tests, code, testing)
        simulation = read_json(folder / "simulation_report.json")
        require(simulation == run_simulation(code) and simulation["passed"] == 64,
                "Simulation is not reproducible")
        simulation_review = validate_review(read_json(folder / "simulation_review.json"))
        payload = {k: v for k, v in simulation.items() if k != "results"}
        payload["failed_scenarios"] = [r for r in simulation["results"] if not r["passed"]]
        require(parse_json(exchange(folder, "reviewer", payload)) == simulation_review
                and simulation_review["needs_revision"] is False, "Logical review inconsistent")
        benchmark = read_json(folder / "irsim_benchmark_report.json")
        verify_worlds(folder, code, benchmark)
        measured = build_deterministic_review(benchmark)
        benchmark_review = validate_review(read_json(folder / "benchmark_review.json"), KEYS)
        require(all(benchmark_review[k] == measured[k] for k in BOOL_KEYS)
                and benchmark_review["needs_revision"] is False, "Benchmark verdict inconsistent")
        require(parse_json(exchange(folder, "benchmark_reviewer", {
            "benchmark": benchmark, "measured_verdict": measured})) == benchmark_review, "Review not model output")
        previous = {"round": number, "code": code, "requirements": requirements, "plan": plan,
                    "testing": testing, "simulation": simulation, "simulation_review": simulation_review,
                    "benchmark": benchmark, "benchmark_review": benchmark_review,
                    "navigation_sha256": code_hash(code), "passed": True}
        require(read_json(folder / "round_result.json") == previous, "Round summary differs")
        rounds.append({"round": number, "passed": True, "navigation_sha256": code_hash(code),
                       "scenario_passes": 64, "goals_reached": benchmark["goals_reached"],
                       "average_steps": benchmark["average_steps_taken"]})
    summary = read_json(output / "run.json")
    require(summary["status"] == "passed" and summary["revision_changed_source"] is True
            and summary["rounds"] == rounds, "Run summary inconsistent")
    runtime = read_json(output / "runtime/status.json")
    require(runtime["status"] == "finished" and runtime["returncode"] == 0
            and all(runtime["cleanup"].values()), "Run or cleanup did not finish")
    for line in (output / "runtime/hardware.jsonl").read_text(encoding="utf-8").splitlines():
        sample = parse_json(line)
        require(sample["ram_gib"] >= 1.25 and sample["gpu_c"] < 80, "Hardware limit exceeded")
    legacy = (output / "legacy_tests.log").read_text(encoding="utf-8")
    require("Ran 76 tests" in legacy and "\nOK\n" in legacy, "Previous tests did not pass")
    require((ROOT / "generated/navigation_logic_revised.py").read_text(encoding="utf-8") == previous["code"],
            "Published revision differs")
    for filename in ("simulation_report.json", "irsim_benchmark_report.json", "simulation_review.json",
                     "benchmark_review.json", "test_report.json"):
        require(read_json(ROOT / "artifacts" / filename) == read_json(output / "round_1" / filename),
                f"Latest report differs: {filename}")
    return {"status": "passed", "rounds": 2, "model_exchanges": 12,
            "generated_tests_per_round": 64, "logical_states_per_round": 64,
            "worlds_per_round": 4, "mean_steps": rounds[-1]["average_steps"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path)
    args = parser.parse_args()
    output = args.run or ROOT / read_json(ROOT / "artifacts/integration_latest.json")["run_directory"]
    print(json.dumps(verify(output), indent=2))


if __name__ == "__main__":
    main()
