"""Offline fixtures exercise validation and isolation, not Qwen performance."""

from contextlib import redirect_stdout
from copy import deepcopy
import io
from itertools import permutations
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import analyst_agent
import artifact_io
import developer_agent as developer
import planner_agent as planner
import run_developer
import run_planner
import verify_pipeline


PROJECT = Path(__file__).resolve().parents[1]
REQUIREMENTS = {
    "goal": "Navigate toward the goal safely.",
    "allowed_actions": ["FORWARD", "LEFT", "RIGHT", "STOP"],
    "safe_stop": True, "avoid_obstacles": True,
}
PLAN = {
    "strategy": "Prefer a safe goal direction; otherwise choose front, left, right, or stop.",
    "decisions": [{"condition": name, "action": action} for name, action in planner.RULE_ACTIONS.items()],
    "stop_condition": "all_blocked",
}
# This is explicitly test code, never a substitute for navigation_logic.py.
CODE = '''def choose_action(front_blocked, left_blocked, right_blocked, goal_direction=None):
    if goal_direction == "AHEAD" and not front_blocked:
        return "FORWARD"
    if goal_direction == "LEFT" and not left_blocked:
        return "LEFT"
    if goal_direction == "RIGHT" and not right_blocked:
        return "RIGHT"
    if not front_blocked:
        return "FORWARD"
    if not left_blocked:
        return "LEFT"
    if not right_blocked:
        return "RIGHT"
    return "STOP"
'''


class PlanTests(unittest.TestCase):
    def test_valid_plan_is_returned_without_rewriting(self):
        plan = deepcopy(PLAN)
        self.assertIs(planner.validate_plan(plan), plan)
        self.assertEqual(plan, PLAN)

    def test_all_six_fallback_orders_are_design_choices(self):
        for order in permutations(PLAN["decisions"][3:6]):
            plan = deepcopy(PLAN)
            plan["decisions"][3:6] = list(order)
            self.assertIs(planner.validate_plan(plan), plan)

    def test_rejects_wrong_types_and_keys(self):
        values = [None, [], "{}", {}, dict(PLAN, extra=True)]
        values.extend({k: v for k, v in PLAN.items() if k != missing} for missing in PLAN)
        for value in values:
            with self.subTest(value=value), self.assertRaises(ValueError):
                planner.validate_plan(value)

    def test_rejects_bad_strategy(self):
        for value in (None, True, [], "", "  ", "x" * 1001):
            with self.subTest(value=value), self.assertRaises(ValueError):
                planner.validate_plan(dict(PLAN, strategy=value))

    def test_rejects_invalid_rules(self):
        for rule in (None, [], {}, {"condition": []}, {"condition": "front_clear", "action": "LEFT"},
                     {"condition": "front_clear", "action": []}, {"condition": "unknown", "action": "STOP"},
                     {"condition": "all_blocked", "action": "BACKWARD"}):
            plan = deepcopy(PLAN)
            plan["decisions"][0] = rule
            with self.subTest(rule=rule), self.assertRaises(ValueError):
                planner.validate_plan(plan)

    def test_rejects_bad_rule_list(self):
        for value in (None, {}, [], PLAN["decisions"][:-1], PLAN["decisions"] * 2):
            with self.subTest(value=value), self.assertRaises(ValueError):
                planner.validate_plan(dict(PLAN, decisions=value))

    def test_rejects_duplicate_rules_and_unsafe_order(self):
        duplicate = deepcopy(PLAN)
        duplicate["decisions"][1] = duplicate["decisions"][0]
        unsafe = deepcopy(PLAN)
        unsafe["decisions"][0], unsafe["decisions"][3] = unsafe["decisions"][3], unsafe["decisions"][0]
        for plan in (duplicate, unsafe, dict(PLAN, stop_condition="goal_reached")):
            with self.subTest(plan=plan), self.assertRaises(ValueError):
                planner.validate_plan(plan)

    def test_planner_sends_only_validated_requirements(self):
        with patch.object(planner, "ask_qwen", return_value=json.dumps(PLAN)) as ask:
            self.assertEqual(planner.run_planner(REQUIREMENTS), PLAN)
        self.assertEqual(json.loads(ask.call_args.args[1]), REQUIREMENTS)
        self.assertIs(ask.call_args.kwargs["response_schema"], planner.PLAN_SCHEMA)
        self.assertNotIn("brief", json.loads(ask.call_args.args[1]))

    def test_invalid_input_does_not_reach_model(self):
        with patch.object(planner, "ask_qwen") as ask:
            with self.assertRaises(ValueError):
                planner.run_planner(dict(REQUIREMENTS, conversation="private prior messages"))
            ask.assert_not_called()

    def test_invalid_response_is_not_repaired_or_retried(self):
        for text in ("```json\n{}\n```", "{}", "not JSON", '{"strategy":"x","strategy":"y"}'):
            with self.subTest(text=text), patch.object(planner, "ask_qwen", return_value=text) as ask:
                with self.assertRaises(ValueError):
                    planner.run_planner(REQUIREMENTS)
                self.assertEqual(ask.call_count, 1)


class CodeTests(unittest.TestCase):
    def test_valid_code_is_unchanged_and_all_combinations_checked(self):
        self.assertIs(developer.validate_code(CODE, PLAN), CODE)
        cases = developer.check_navigation(CODE, PLAN)
        self.assertEqual(len(cases), 32)
        self.assertTrue(all(case["actual"] == case["expected"] for case in cases))
        self.assertEqual(sum(case["actual"] == "STOP" for case in cases), 4)

    def test_actual_optional_argument(self):
        choose = developer.load_navigation(CODE)
        self.assertEqual(choose(True, False, False), "LEFT")
        self.assertEqual(choose(True, True, True), "STOP")
        self.assertEqual(choose(False, False, False, "RIGHT"), "RIGHT")

    def test_rejects_bad_code_and_signature(self):
        samples = (None, "", "x" * 12001, "```python\n" + CODE + "```",
                   CODE.replace("choose_action", "move"), CODE.replace("goal_direction=None", "goal_direction='AHEAD'"),
                   CODE.replace("front_blocked,", "front_blocked: bool,"), "def choose_action(:\n    pass",
                   CODE + "\nx = 'FORWARD'\n", CODE + "\ndef extra():\n    return 'STOP'\n")
        for code in samples:
            with self.subTest(code=repr(code)[:100]), self.assertRaises(ValueError):
                developer.validate_code(code, PLAN)

    def test_dangerous_features_are_rejected_before_execution(self):
        bodies = ("import os", "return open('should_not_exist.txt', 'w')", "while True:\n        pass",
                  "return __import__('os').system('echo unsafe')", "return front_blocked.__class__",
                  "return choose_action(front_blocked, left_blocked, right_blocked)",
                  "def inner():\n        return 'STOP'", "return [x for x in []]")
        for body in bodies:
            code = CODE.splitlines()[0] + "\n    " + body + "\n"
            with self.subTest(body=body), self.assertRaises(ValueError):
                developer.load_navigation(code)

    def test_rejects_unsafe_or_incomplete_behavior(self):
        wrong = (
            CODE.replace('if not front_blocked:', 'if front_blocked:'),
            CODE.replace('return "STOP"', 'return "FORWARD"'),
            CODE.replace('return "LEFT"', 'return "STOP"'),
            CODE.replace('return "RIGHT"', 'return "BACKWARD"'),
            CODE.splitlines()[0] + '\n    return "STOP"\n',
            CODE.splitlines()[0] + '\n    return missing_variable\n',
        )
        for code in wrong:
            with self.subTest(code=code), self.assertRaises(ValueError):
                developer.validate_code(code, PLAN)

    def test_safe_code_must_also_follow_plan_fallback_order(self):
        plan = deepcopy(PLAN)
        plan["decisions"][3], plan["decisions"][4] = plan["decisions"][4], plan["decisions"][3]
        with self.assertRaisesRegex(ValueError, "disagrees with the plan"):
            developer.validate_code(CODE, plan)

    def test_developer_sends_only_plan_and_keeps_model_text(self):
        with patch.object(developer, "ask_qwen", return_value=CODE) as ask:
            self.assertEqual(developer.run_developer(PLAN), CODE)
        self.assertEqual(json.loads(ask.call_args.args[1]), PLAN)
        self.assertNotIn("allowed_actions", json.loads(ask.call_args.args[1]))

    def test_bad_plan_does_not_reach_developer_model(self):
        with patch.object(developer, "ask_qwen") as ask:
            with self.assertRaises(ValueError):
                developer.run_developer({})
            ask.assert_not_called()


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def invoke(self, module, args):
        with patch.object(module, "BASE_DIR", self.folder), redirect_stdout(io.StringIO()):
            return module.main(args)

    def test_both_runners_require_permission(self):
        for module, name in ((run_planner, "run_planner"), (run_developer, "run_developer")):
            with patch.object(module, name) as run:
                self.assertEqual(self.invoke(module, []), 1)
                run.assert_not_called()
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_missing_input_prevents_model_request(self):
        for module, name in ((run_planner, "run_planner"), (run_developer, "run_developer")):
            with patch.object(module, name) as run:
                self.assertEqual(self.invoke(module, ["--allow-model"]), 1)
                run.assert_not_called()

    def test_mocked_pipeline_saves_fixture_code_unchanged(self):
        artifact_io.write_json(self.folder / "artifacts" / "requirements.json", REQUIREMENTS)
        with patch.object(planner, "ask_qwen", return_value=json.dumps(PLAN)):
            self.assertEqual(self.invoke(run_planner, ["--allow-model"]), 0)
        with patch.object(developer, "ask_qwen", return_value=CODE):
            self.assertEqual(self.invoke(run_developer, ["--allow-model"]), 0)
        self.assertEqual((self.folder / "navigation_logic.py").read_text(encoding="utf-8"), CODE)
        for stage, supplied, response in (("planner", REQUIREMENTS, json.dumps(PLAN)), ("developer", PLAN, CODE)):
            artifact_io.write_json(self.folder / "artifacts" / (stage + "_runs") / "test_fixture.json", {
                "test_fixture": True,
                "request": {"model": "offline-fixture", "options": {"num_gpu": 0, "num_thread": 2}, "keep_alive": 0,
                            "messages": [{"role": "system", "content": "Offline fixture"},
                                         {"role": "user", "content": json.dumps(supplied)}]},
                "response": {"done": True, "done_reason": "stop", "message": {"content": response}},
            })
        self.assertEqual(verify_pipeline.verify(self.folder)["scenario_count"], 32)

    def test_verification_requires_matching_raw_model_evidence(self):
        artifact_io.write_json(self.folder / "artifacts" / "requirements.json", REQUIREMENTS)
        artifact_io.write_json(self.folder / "artifacts" / "plan.json", PLAN)
        artifact_io.write_text(self.folder / "navigation_logic.py", CODE)
        with self.assertRaisesRegex(ValueError, "No complete model exchange"):
            verify_pipeline.verify(self.folder)
        self.assertFalse((self.folder / "artifacts" / "navigation_verification.json").exists())

    def test_modified_code_no_longer_matches_evidence(self):
        self.test_mocked_pipeline_saves_fixture_code_unchanged()
        artifact_io.write_text(self.folder / "navigation_logic.py", CODE + "\n# manually changed\n")
        with self.assertRaisesRegex(ValueError, "No complete model exchange"):
            verify_pipeline.verify(self.folder)

    def test_bad_plan_preserves_existing_plan(self):
        artifact_io.write_json(self.folder / "artifacts" / "requirements.json", REQUIREMENTS)
        output = self.folder / "artifacts" / "plan.json"
        artifact_io.write_text(output, "previous plan")
        with patch.object(planner, "ask_qwen", return_value="{}"):
            self.assertEqual(self.invoke(run_planner, ["--allow-model"]), 1)
        self.assertEqual(output.read_text(), "previous plan")

    def test_bad_code_preserves_existing_code(self):
        artifact_io.write_json(self.folder / "artifacts" / "plan.json", PLAN)
        output = self.folder / "navigation_logic.py"
        artifact_io.write_text(output, "previous code")
        with patch.object(developer, "ask_qwen", return_value="import os"):
            self.assertEqual(self.invoke(run_developer, ["--allow-model"]), 1)
        self.assertEqual(output.read_text(), "previous code")

    def test_serialization_failure_preserves_previous_file(self):
        output = self.folder / "result.json"
        output.write_text("old", encoding="utf-8")
        with self.assertRaises(ValueError):
            artifact_io.write_json(output, {"bad": float("nan")})
        self.assertEqual(output.read_text(), "old")

    def test_replace_failure_preserves_previous_file_and_removes_temp(self):
        output = self.folder / "result.txt"
        output.write_text("old", encoding="utf-8")
        with patch.object(Path, "replace", side_effect=OSError("disk error")):
            with self.assertRaises(OSError):
                artifact_io.write_text(output, "new")
        self.assertEqual(output.read_text(), "old")
        self.assertEqual(list(self.folder.glob("*.tmp")), [])

    def test_rejects_duplicate_json_keys_and_non_json_constants(self):
        for text in ('{"a":1,"a":2}', '{"x":NaN}', '{"x":Infinity}'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                artifact_io.parse_json(text)

    def test_raw_exchange_is_recorded_before_truncation_rejection(self):
        response = {"message": {"content": "unfinished"}, "done_reason": "length"}
        client = Mock()
        client.chat.return_value = response
        sdk = SimpleNamespace(Client=Mock(return_value=client))
        with patch.dict(sys.modules, {"ollama": sdk}):
            with self.assertRaisesRegex(RuntimeError, "output limit"):
                analyst_agent.ask_qwen("test prompt", "test data", trace_dir=self.folder)
        trace = artifact_io.read_json(next(self.folder.glob("*.json")))
        self.assertEqual(trace["response"], response)
        self.assertEqual(trace["request"]["options"]["num_gpu"], 0)
        self.assertEqual(trace["request"]["options"]["num_thread"], 2)
        self.assertEqual(client.chat.call_count, 1)

    def test_json_schema_passed_to_local_model(self):
        client = Mock()
        client.chat.return_value = {"message": {"content": json.dumps(PLAN)}}
        sdk = SimpleNamespace(Client=Mock(return_value=client))
        with patch.dict(sys.modules, {"ollama": sdk}):
            analyst_agent.ask_qwen("role", "data", response_schema=planner.PLAN_SCHEMA)
        self.assertIs(client.chat.call_args.kwargs["format"], planner.PLAN_SCHEMA)
        self.assertEqual(client.chat.call_args.kwargs["keep_alive"], 0)

    def test_entry_points_work_from_another_directory_without_model(self):
        for name in ("run_planner.py", "run_developer.py"):
            completed = subprocess.run([sys.executable, "-B", str(PROJECT / name)],
                                       cwd=self.folder, capture_output=True, text=True, timeout=10)
            self.assertEqual(completed.returncode, 1, completed.stderr)
            self.assertIn("No model was started", completed.stdout)

    def test_import_has_no_model_side_effect(self):
        command = "import sys, planner_agent, developer_agent, run_planner, run_developer; print('ollama' in sys.modules)"
        result = subprocess.run([sys.executable, "-B", "-c", command], cwd=PROJECT,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "False")


if __name__ == "__main__":
    unittest.main()
