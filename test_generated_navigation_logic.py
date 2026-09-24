"""Known-state behavior tests expanded from the teacher's six-boolean example."""

from itertools import product
from pathlib import Path
import unittest

from developer_agent import load_navigation


BASE_DIR = Path(__file__).resolve().parent
BLOCKED_PATTERNS = tuple(product((False, True), repeat=3))
# Columns follow 000, 001, 010, 011, 100, 101, 110, 111 (front, left, right).
# These expected actions are written independently of the generated implementation.
EXPECTED = {
    "":    ("FORWARD", "FORWARD", "FORWARD", "FORWARD", "LEFT",  "LEFT", "RIGHT", "STOP"),
    "A":   ("FORWARD", "FORWARD", "FORWARD", "FORWARD", "LEFT",  "LEFT", "RIGHT", "STOP"),
    "L":   ("LEFT",    "LEFT",    "FORWARD", "FORWARD", "LEFT",  "LEFT", "RIGHT", "STOP"),
    "R":   ("RIGHT",   "FORWARD", "RIGHT",   "FORWARD", "RIGHT", "LEFT", "RIGHT", "STOP"),
    "AL":  ("FORWARD", "FORWARD", "FORWARD", "FORWARD", "LEFT",  "LEFT", "RIGHT", "STOP"),
    "AR":  ("FORWARD", "FORWARD", "FORWARD", "FORWARD", "RIGHT", "LEFT", "RIGHT", "STOP"),
    "LR":  ("LEFT",    "LEFT",    "RIGHT",   "FORWARD", "LEFT",  "LEFT", "RIGHT", "STOP"),
    "ALR": ("FORWARD", "FORWARD", "FORWARD", "FORWARD", "LEFT",  "LEFT", "RIGHT", "STOP"),
}


def make_state(blocked, goals):
    return {
        "front_blocked": blocked[0], "left_blocked": blocked[1], "right_blocked": blocked[2],
        "goal_ahead": "A" in goals, "goal_on_left": "L" in goals, "goal_on_right": "R" in goals,
    }


class NavigationMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        code = (BASE_DIR / "generated" / "navigation_logic.py").read_text(encoding="utf-8")
        cls.decide_next_move = staticmethod(load_navigation(code))

    def check_group(self, goals):
        for blocked, expected in zip(BLOCKED_PATTERNS, EXPECTED[goals]):
            with self.subTest(goals=goals or "unknown", blocked=blocked):
                state = make_state(blocked, goals)
                before = state.copy()
                action = self.decide_next_move(state)
                self.assertIn(action, ("FORWARD", "LEFT", "RIGHT", "STOP"))
                self.assertEqual(action, expected)
                self.assertEqual(state, before, "The caller's state was changed.")
                if action != "STOP":
                    self.assertFalse(dict(zip(("FORWARD", "LEFT", "RIGHT"), blocked))[action])

    def test_unknown_goal(self):
        self.check_group("")

    def test_goal_ahead(self):
        self.check_group("A")

    def test_goal_left(self):
        self.check_group("L")

    def test_goal_right(self):
        self.check_group("R")

    def test_goals_ahead_and_left(self):
        self.check_group("AL")

    def test_goals_ahead_and_right(self):
        self.check_group("AR")

    def test_goals_left_and_right(self):
        self.check_group("LR")

    def test_all_goal_flags(self):
        self.check_group("ALR")

    def test_teacher_example(self):
        self.assertEqual(self.decide_next_move(make_state((False, False, False), "A")), "FORWARD")

    def test_updated_sensor_state_is_not_cached(self):
        state = make_state((False, False, False), "L")
        self.assertEqual(self.decide_next_move(state), "LEFT")
        state["left_blocked"] = True
        self.assertEqual(self.decide_next_move(state), "FORWARD")
        state["front_blocked"] = True
        state["right_blocked"] = True
        self.assertEqual(self.decide_next_move(state), "STOP")


if __name__ == "__main__":
    unittest.main(verbosity=2)
