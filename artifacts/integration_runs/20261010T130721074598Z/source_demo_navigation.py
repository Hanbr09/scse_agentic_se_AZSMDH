"""Try one decision using the saved, validated navigation code; no model needed."""

import argparse
from pathlib import Path

from artifact_io import read_json
from developer_agent import load_navigation, validate_code


BASE_DIR = Path(__file__).resolve().parent


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--front-blocked", action="store_true")
    parser.add_argument("--left-blocked", action="store_true")
    parser.add_argument("--right-blocked", action="store_true")
    parser.add_argument("--goal", choices=("AHEAD", "LEFT", "RIGHT"), default=None)
    args = parser.parse_args(argv)
    try:
        code = (BASE_DIR / "generated" / "navigation_logic.py").read_text(encoding="utf-8")
        validate_code(code, read_json(BASE_DIR / "artifacts" / "plan.json"))
        state = {
            "front_blocked": args.front_blocked, "left_blocked": args.left_blocked,
            "right_blocked": args.right_blocked, "goal_ahead": args.goal == "AHEAD",
            "goal_on_left": args.goal == "LEFT", "goal_on_right": args.goal == "RIGHT",
        }
        action = load_navigation(code)(state)
        print(f"Action: {action}")
        return 0
    except (OSError, ValueError) as error:
        print(f"Could not run the example: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
