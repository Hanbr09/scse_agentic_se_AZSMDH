"""Read the validated requirements and save a Qwen-generated plan."""

import argparse
from pathlib import Path

from artifact_io import read_json, write_json
from planner_agent import run_planner


BASE_DIR = Path(__file__).resolve().parent


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-model", action="store_true", help="Allow one local CPU model request.")
    args = parser.parse_args(argv)
    if not args.allow_model:
        print("No model was started. Real inference requires the --allow-model flag.")
        return 1
    try:
        requirement = read_json(BASE_DIR / "artifacts" / "requirements.json")
        plan = run_planner(requirement, trace_dir=BASE_DIR / "artifacts" / "planner_runs")
        write_json(BASE_DIR / "artifacts" / "plan.json", plan)
        print("Validated Qwen plan saved to artifacts/plan.json")
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Could not finish: {error}")
        return 1
    except KeyboardInterrupt:
        print("Request cancelled. The previous plan was kept.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
