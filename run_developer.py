"""Read the plan and save Qwen code only after all navigation checks pass."""

import argparse
from pathlib import Path

from artifact_io import read_json, write_text
from developer_agent import run_developer


BASE_DIR = Path(__file__).resolve().parent


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-model", action="store_true", help="Allow one local CPU model request.")
    args = parser.parse_args(argv)
    if not args.allow_model:
        print("No model was started. Real inference requires the --allow-model flag.")
        return 1
    try:
        plan = read_json(BASE_DIR / "artifacts" / "plan.json")
        code = run_developer(plan, trace_dir=BASE_DIR / "artifacts" / "developer_runs")
        write_text(BASE_DIR / "navigation_logic.py", code)
        print("Qwen code passed all 32 navigation scenarios and was saved to navigation_logic.py")
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Could not finish: {error}")
        return 1
    except KeyboardInterrupt:
        print("Request cancelled. The previous navigation code was kept.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
