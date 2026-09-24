from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from artifact_io import read_json, write_text
import run_bug_check
from tests.test_plan_and_develop import CODE


class BugCheckTests(unittest.TestCase):
    def test_only_left_fallback_is_changed(self):
        faulty, old_return = run_bug_check.wrong_left_fallback(CODE)
        self.assertEqual(old_return, 'return "LEFT"')
        self.assertIn('elif not left_blocked:\n        return "RIGHT"', faulty)
        self.assertEqual(faulty.split("def decide_next_move")[1], CODE.split("def decide_next_move")[1])

    def test_failed_test_process_still_restores_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            path = base / "generated" / "navigation_logic.py"
            write_text(path, CODE)
            original = path.read_bytes()
            with patch.object(run_bug_check, "BASE_DIR", base), patch.object(run_bug_check, "test_once",
                    side_effect=[({"exit_code": 0}, "OK"), RuntimeError("test process failed")]):
                with self.assertRaisesRegex(RuntimeError, "test process failed"):
                    run_bug_check.main()
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(read_json(base / "artifacts/bug_check.json")["status"], "failed")


if __name__ == "__main__":
    unittest.main()
