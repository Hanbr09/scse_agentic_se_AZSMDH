"""Measure all four teacher worlds in isolated, sequential subprocesses."""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys

from artifact_io import read_json, write_json
from developer_agent import load_navigation


ROOT = Path(__file__).resolve().parent
WORLDS = ("world_easy.yaml", "world_medium.yaml", "world_hard.yaml", "world_custom.yaml")


def validate_world_report(report):
    if not isinstance(report, dict):
        raise ValueError("World report must be an object.")
    for key in ("reached_goal", "collision_or_done", "efficiency_passed"):
        if type(report.get(key)) is not bool:
            raise ValueError(f"{key} must be a boolean.")
    for key in ("steps_taken", "max_steps_allowed", "efficient_step_limit", "history_length"):
        if type(report.get(key)) is not int:
            raise ValueError(f"{key} must be an integer.")
    steps = report["steps_taken"]
    if not 1 <= steps <= 300 or report["history_length"] != steps:
        raise ValueError("Invalid measured step count.")
    if report["max_steps_allowed"] != 300 or report["efficient_step_limit"] != 200:
        raise ValueError("Teacher benchmark limits must remain 300 and 200.")
    expected = ("failed" if not report["reached_goal"] else
                "efficient" if steps <= 200 else "acceptable_but_inefficient")
    if report.get("efficiency_status") != expected or report["efficiency_passed"] != (expected == "efficient"):
        raise ValueError("Efficiency does not match the measured result.")
    pose = report.get("final_pose")
    if (not isinstance(pose, list) or len(pose) != 3
            or any(type(value) not in (int, float) or not math.isfinite(value) for value in pose)):
        raise ValueError("Invalid final pose.")
    return report


def run_world(world, code, output_dir, *, timeout=90, interactive=False):
    world = Path(world).resolve()
    if not world.is_file():
        raise FileNotFoundError(world)
    load_navigation(code)
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    workspace = output_dir / "work"
    (workspace / "generated").mkdir(parents=True)
    (workspace / "irsim_worlds").mkdir()
    shutil.copyfile(ROOT / "test_irsim_with_agent.py", workspace / "test_irsim_with_agent.py")
    shutil.copyfile(world, workspace / "irsim_worlds" / world.name)
    (workspace / "generated/__init__.py").write_text("", encoding="utf-8")
    (workspace / "generated/navigation_logic.py").write_text(code, encoding="utf-8", newline="\n")
    command = [sys.executable, "-B", str(ROOT / "irsim_capture.py"),
               "--script", str(workspace / "test_irsim_with_agent.py"),
               "--world", str(workspace / "irsim_worlds" / world.name),
               "--capture", str(output_dir)]
    if interactive:
        command.append("--interactive")
    environment = dict(os.environ, PYTHONUTF8="1", OMP_NUM_THREADS="2",
                       OPENBLAS_NUM_THREADS="2", MKL_NUM_THREADS="2")
    if not interactive:
        environment["MPLBACKEND"] = "Agg"
    with (output_dir / "process.log").open("w", encoding="utf-8") as log:
        process = subprocess.run(command, cwd=workspace, env=environment,
                                 stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
    if process.returncode:
        raise RuntimeError(f"{world.name} exited {process.returncode}; see {output_dir / 'process.log'}")
    report = validate_world_report(read_json(workspace / "artifacts/irsim_report.json"))
    capture = read_json(output_dir / "trajectory.json")
    report.update({
        "world": world.name,
        "collision_before_cleanup": capture["collision_before_cleanup"],
        "done_before_cleanup": capture["done_before_cleanup"],
        "navigation_sha256": hashlib.sha256(code.encode("utf-8")).hexdigest(),
        "world_sha256": hashlib.sha256(world.read_text(encoding="utf-8").encode("utf-8")).hexdigest(),
    })
    write_json(output_dir / "report.json", report)
    return report


def summarize(results):
    if not results or len({r["world"] for r in results}) != len(results):
        raise ValueError("Need nonempty, uniquely named world results.")
    for result in results:
        validate_world_report(result)
    total = len(results)
    reached = sum(r["reached_goal"] for r in results)
    efficient = sum(r["efficiency_passed"] for r in results)
    return {
        "total_worlds": total, "goals_reached": reached, "success_rate": reached / total,
        "efficient_worlds": efficient, "inefficient_success_worlds": reached - efficient,
        "failed_worlds": total - reached, "efficiency_rate": efficient / total,
        "average_steps_taken": sum(r["steps_taken"] for r in results) / total,
        "results": results,
    }


def run_benchmark(code, output_dir, *, timeout=90, interactive=False, logger=None):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for name in WORLDS:
        if logger:
            logger.info("IR-SIM starting %s", name)
        result = run_world(ROOT / "irsim_worlds" / name, code, output_dir / Path(name).stem,
                           timeout=timeout, interactive=interactive)
        results.append(result)
        write_json(output_dir / "completed_worlds.json", results)
        if logger:
            logger.info("IR-SIM %s: goal=%s steps=%s efficiency=%s", name,
                        result["reached_goal"], result["steps_taken"], result["efficiency_status"])
    report = summarize(results)
    write_json(output_dir / "irsim_benchmark_report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--code", type=Path, default=ROOT / "generated/navigation_logic.py")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--interactive", action="store_true")
    args = parser.parse_args()
    result = run_benchmark(args.code.read_text(encoding="utf-8"), args.output,
                           interactive=args.interactive)
    print(json.dumps({k: v for k, v in result.items() if k != "results"}, indent=2))
    return 0 if result["success_rate"] == 1 else 2


if __name__ == "__main__":
    raise SystemExit(main())
