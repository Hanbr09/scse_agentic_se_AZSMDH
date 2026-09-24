"""Temporarily introduce one wrong fallback action, test it, and restore the file."""

import ast
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import subprocess
import sys

from artifact_io import write_json, write_text


BASE_DIR = Path(__file__).resolve().parent


def wrong_left_fallback(code):
    tree = ast.parse(code)
    original = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "choose_action")
    for node in ast.walk(original):
        if (isinstance(node, ast.If) and isinstance(node.test, ast.UnaryOp)
                and isinstance(node.test.op, ast.Not) and isinstance(node.test.operand, ast.Name)
                and node.test.operand.id == "left_blocked"):
            statement = node.body[0]
            if not isinstance(statement, ast.Return) or not isinstance(statement.value, ast.Constant) or statement.value.value != "LEFT":
                continue
            lines = code.splitlines(keepends=True)
            start = sum(map(len, lines[:statement.lineno - 1])) + statement.col_offset
            end = sum(map(len, lines[:statement.end_lineno - 1])) + statement.end_col_offset
            return code[:start] + 'return "RIGHT"' + code[end:], code[start:end]
    raise ValueError("The original LEFT fallback was not found; nothing was changed.")


def test_once(folder, label):
    result = subprocess.run([sys.executable, "-B", str(BASE_DIR / "test_generated_navigation_logic.py")],
                            cwd=BASE_DIR, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=30)
    output = result.stdout + result.stderr
    log = folder / (label + ".log")
    write_text(log, output)
    return {"exit_code": result.returncode, "log": log.relative_to(BASE_DIR).as_posix()}, output


def main():
    source_path = BASE_DIR / "generated" / "navigation_logic.py"
    original = source_path.read_bytes()
    folder = BASE_DIR / "artifacts" / "bug_checks" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    report = {"status": "failed", "created_utc": datetime.now(timezone.utc).isoformat(),
              "source": "generated/navigation_logic.py",
              "before_sha256": hashlib.sha256(original).hexdigest()}
    try:
        report["before"], _ = test_once(folder, "before")
        if report["before"]["exit_code"] != 0:
            raise RuntimeError("The baseline failed. The file has not been changed.")
        faulty, old_return = wrong_left_fallback(original.decode("utf-8"))
        report["change"] = {"location": "choose_action: clear-left fallback",
                            "before": old_return, "after": 'return "RIGHT"'}
        try:
            write_text(source_path, faulty)
            report["faulty_sha256"] = hashlib.sha256(source_path.read_bytes()).hexdigest()
            report["with_bug"], output = test_once(folder, "with_bug")
            if (report["with_bug"]["exit_code"] == 0 or "AssertionError" not in output
                    or "FAIL: test_unknown_goal" not in output):
                raise RuntimeError("The wrong fallback was not caught by an action assertion.")
        finally:
            source_path.write_bytes(original)
        report["after_restore"], _ = test_once(folder, "after_restore")
        report["after_sha256"] = hashlib.sha256(source_path.read_bytes()).hexdigest()
        if source_path.read_bytes() != original or report["after_restore"]["exit_code"] != 0:
            raise RuntimeError("The original code was not restored successfully.")
        report["status"] = "passed"
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        write_json(folder / "result.json", report)
        write_json(BASE_DIR / "artifacts" / "bug_check.json", report)
    print("PASS: the incorrect LEFT fallback was detected, then the original code passed again.")
    print("Records: " + folder.relative_to(BASE_DIR).as_posix())


if __name__ == "__main__":
    main()
