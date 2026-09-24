"""Read the brief, run the analyst, and save validated JSON."""

import argparse
import json
from pathlib import Path

from analyst_agent import run_analyst
from artifact_io import write_json


BASE_DIR = Path(__file__).resolve().parent


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-model", action="store_true", help="Allow one local CPU model request.")
    args = parser.parse_args(argv)
    if not args.allow_model:
        print("No model was started. Real inference requires the --allow-model flag.")
        return 1

    try:
        brief_text = (BASE_DIR / "brief.txt").read_text(encoding="utf-8-sig")
        requirements = run_analyst(brief_text, trace_dir=BASE_DIR / "artifacts" / "analyst_runs")
        output_path = BASE_DIR / "artifacts" / "requirements.json"
        write_json(output_path, requirements)
        print("Validated Qwen requirements saved to artifacts/requirements.json")
        print(json.dumps(requirements, indent=2, ensure_ascii=False))
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Could not finish: {error}")
        return 1
    except KeyboardInterrupt:
        print("Request cancelled.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
