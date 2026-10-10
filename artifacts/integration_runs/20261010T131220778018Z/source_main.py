"""Run the AZSMDH agents, tests, simulation, reviews and revision in sequence."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import shutil
import subprocess
import sys

from analyst_agent import run_analyst
from artifact_io import write_json, write_text
from benchmark_irsim import run_benchmark
from developer_agent import run_developer, run_developer_revision
from integration_model import LocalModel
from planner_agent import run_planner
from reviewer_agent import run_reviewer
from reviewer_benchmark_agent import run_benchmark_reviewer
from runner import run_simulation
from test_agent import execute_tests, run_test_agent


ROOT = Path(__file__).resolve().parent


def make_logger(output):
    logger = logging.getLogger("integration." + output.name)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    for handler in (logging.FileHandler(output / "trace.log", encoding="utf-8"), logging.StreamHandler(sys.stdout)):
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger


def check_generated_tests(tests, code, output):
    normal = execute_tests(tests, code, output / "pytest")
    # Execute the same tests against a deliberately wrong module in a separate directory.
    mutant = "def decide_next_move(state):\n    return 'STOP'\n"
    mutation = execute_tests(tests, mutant, output / "mutation_control")
    return {"normal": normal, "mutation_control": mutation,
            "mutation_detected": mutation["tests"] == 64 and mutation["failures"] > 0 and mutation["errors"] == 0,
            "passed": normal["passed"] and mutation["tests"] == 64
                      and mutation["failures"] > 0 and mutation["errors"] == 0}


def run_round(number, output, brief, previous, model, logger):
    folder = output / f"round_{number}"
    folder.mkdir()
    logger.info("Analyst Agent: reading brief.txt")
    requirements = run_analyst(brief, trace_dir=folder / "exchanges/analyst")
    write_json(folder / "requirements.json", requirements)
    logger.info("Analyst Agent created round_%s/requirements.json", number)
    plan = run_planner(requirements, trace_dir=folder / "exchanges/planner")
    write_json(folder / "plan.json", plan)
    logger.info("Planner Agent created round_%s/plan.json", number)
    if previous is None:
        code = run_developer(plan, trace_dir=folder / "exchanges/developer")
    else:
        code = run_developer_revision(
            previous["code"], {"simulation": previous["simulation_review"],
                               "benchmark": previous["benchmark_review"]},
            previous["benchmark"], requirements, plan,
            trace_dir=folder / "exchanges/developer_revision")
    write_text(folder / "navigation_logic.py", code)
    logger.info("Developer Agent created round_%s/navigation_logic.py%s", number,
                " (revision)" if previous else "")
    tests = run_test_agent(requirements, plan, code, brief, ask=model.ask,
                           trace_dir=folder / "exchanges/test_agent")
    write_text(folder / "test_navigation.py", tests)
    logger.info("Test Agent created round_%s/test_navigation.py", number)
    testing = check_generated_tests(tests, code, folder)
    write_json(folder / "test_report.json", testing)
    logger.info("Generated tests: %s; wrong-action control detected: %s",
                testing["normal"], testing["mutation_detected"])
    simulation = run_simulation(code, folder / "simulation_report.json")
    logger.info("Simulation: %s/%s scenarios passed", simulation["passed"], simulation["total_scenarios"])
    simulation_review = run_reviewer(simulation, ask=model.ask,
                                     trace_dir=folder / "exchanges/reviewer")
    write_json(folder / "simulation_review.json", simulation_review)
    logger.info("Reviewer Agent created simulation_review.json; needs_revision=%s",
                simulation_review["needs_revision"])
    benchmark = run_benchmark(code, folder / "worlds", logger=logger)
    write_json(folder / "irsim_benchmark_report.json", benchmark)
    logger.info("Benchmark: %s/%s goals reached", benchmark["goals_reached"], benchmark["total_worlds"])
    benchmark_review = run_benchmark_reviewer(benchmark, ask=model.ask,
                                             trace_dir=folder / "exchanges/benchmark_reviewer")
    write_json(folder / "benchmark_review.json", benchmark_review)
    logger.info("Benchmark Reviewer created benchmark_review.json; needs_revision=%s",
                benchmark_review["needs_revision"])
    result = {
        "round": number, "code": code, "requirements": requirements, "plan": plan,
        "testing": testing, "simulation": simulation, "simulation_review": simulation_review,
        "benchmark": benchmark, "benchmark_review": benchmark_review,
        "navigation_sha256": hashlib.sha256(code.encode("utf-8")).hexdigest(),
        "passed": testing["passed"] and simulation["failed"] == 0
                  and not simulation_review["needs_revision"] and not benchmark_review["needs_revision"],
    }
    write_json(folder / "round_result.json", result)
    return result


def run_pipeline(output, model):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    if (output / "trace.log").exists() or (output / "round_0").exists():
        raise FileExistsError("Use a new output directory; earlier evidence is not overwritten.")
    logger = make_logger(output)
    started = datetime.now(timezone.utc).isoformat()
    summary = {"started_at": started, "status": "running", "model": model.model, "rounds": []}
    try:
        brief = (ROOT / "brief.txt").read_text(encoding="utf-8-sig")
        write_text(output / "brief.txt", brief)
        logger.info("Loaded the original brief.")
        sources = {}
        for source in sorted(ROOT.glob("*.py")):
            source_text = source.read_text(encoding="utf-8")
            sources[source.name] = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
            write_text(output / ("source_" + source.name), source_text)
        write_json(output / "source_hashes.json", sources)
        summary["text_hash_convention"] = "UTF-8 with LF line endings"
        with (output / "legacy_tests.log").open("w", encoding="utf-8") as stream:
            legacy = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-q"],
                                    cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, timeout=90)
        if legacy.returncode:
            raise RuntimeError("The previous-stage regression tests failed; see legacy_tests.log.")
        logger.info("Previous-stage regression tests passed.")
        previous = None
        with model.bind_original_agents():
            for number in range(2):
                result = run_round(number, output, brief, previous, model, logger)
                summary["rounds"].append({
                    "round": number, "passed": result["passed"],
                    "navigation_sha256": result["navigation_sha256"],
                    "scenario_passes": result["simulation"]["passed"],
                    "goals_reached": result["benchmark"]["goals_reached"],
                    "average_steps": result["benchmark"]["average_steps_taken"],
                })
                previous = result
        summary["status"] = "passed" if previous["passed"] else "needs_revision"
        summary["revision_changed_source"] = summary["rounds"][0]["navigation_sha256"] != summary["rounds"][1]["navigation_sha256"]
        if not summary["revision_changed_source"]:
            summary["status"] = "needs_revision"
            summary["note"] = "The revision was identical; no revised source was demonstrated."
        if summary["status"] == "passed":
            write_text(ROOT / "generated/navigation_logic_revised.py", previous["code"])
            for filename in ("simulation_report.json", "irsim_benchmark_report.json",
                             "simulation_review.json", "benchmark_review.json", "test_report.json"):
                shutil.copyfile(output / "round_1" / filename, ROOT / "artifacts" / filename)
        logger.info("Pipeline finished: %s", summary["status"])
        return summary
    except Exception as error:
        summary["status"] = "error"
        summary["error"] = f"{type(error).__name__}: {error}"
        logger.exception("Pipeline stopped; rejected outputs remain in the run folder.")
        raise
    finally:
        summary["finished_at"] = datetime.now(timezone.utc).isoformat()
        write_json(output / "run.json", summary)
        write_json(ROOT / "artifacts/integration_latest.json",
                   {"run_directory": output.relative_to(ROOT).as_posix()
                    if output.is_relative_to(ROOT) else str(output), **summary})
        for handler in list(logger.handlers):
            handler.close()
            logger.removeHandler(handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-model", action="store_true")
    parser.add_argument("--base-url", default="http://127.0.0.1:11522")
    parser.add_argument("--model", default="qwen2.5:3b")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--cpu", action="store_true")
    parser.add_argument("--no-hardware-guard", action="store_true",
                        help="For externally managed non-NVIDIA hosts only.")
    args = parser.parse_args()
    if not args.allow_model:
        parser.error("Real model calls require --allow-model and a running local service.")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = args.output or ROOT / "artifacts/integration_runs" / stamp
    model = LocalModel(args.base_url, args.model, num_gpu=0 if args.cpu else 99,
                       guard=not args.no_hardware_guard)
    try:
        result = run_pipeline(output, model)
        print(json.dumps(result, indent=2))
        return 0 if result["status"] == "passed" else 2
    finally:
        model.close()


if __name__ == "__main__":
    raise SystemExit(main())
