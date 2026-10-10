"""Offline contract checks; model replies in this file are explicit fixtures."""

from contextlib import contextmanager
import copy
import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from artifact_io import read_json
import analyst_agent
import benchmark_irsim
import developer_agent
import integration_model
import main
import planner_agent
import reviewer_agent
import reviewer_benchmark_agent as benchmark_reviewer
import runner
import test_agent as agent
import verify_integration


ROOT = Path(__file__).resolve().parents[1]
CODE = (ROOT / "generated/navigation_logic.py").read_text(encoding="utf-8")
PLAN = read_json(ROOT / "artifacts/plan.json")
REQUIREMENTS = read_json(ROOT / "artifacts/requirements.json")
TEST_CODE = """import pytest
from generated.navigation_logic import decide_next_move
from runner import scenario_cases

@pytest.mark.parametrize("state, expected", scenario_cases())
def test_navigation(state, expected):
    before = state.copy()
    actual = decide_next_move(state)
    assert actual == expected
    assert actual in ("FORWARD", "LEFT", "RIGHT", "STOP")
    assert state == before
"""


def world(name="world_easy.yaml", goal=True, steps=150, collision=False):
    status = "failed" if not goal else "efficient" if steps <= 200 else "acceptable_but_inefficient"
    return {"world": name, "reached_goal": goal, "collision_or_done": collision,
            "steps_taken": steps, "max_steps_allowed": 300, "efficient_step_limit": 200,
            "efficiency_status": status, "efficiency_passed": status == "efficient",
            "history_length": steps, "final_pose": [8.0, 1.0, 0.0],
            "collision_before_cleanup": collision}


def benchmark():
    return benchmark_irsim.summarize([world(name) for name in benchmark_irsim.WORLDS])


def logical_reply(revision=False):
    return {"issue": "Fixture issue.", "likely_cause": "Fixture cause.",
            "recommendation": "Fixture recommendation.", "needs_revision": revision}


def test_cases_cover_six_booleans_once():
    cases = runner.scenario_cases()
    assert len(cases) == 64
    assert len({tuple(state.values()) for state, _ in cases}) == 64
    assert all(type(value) is bool for state, _ in cases for value in state.values())


def test_original_simulation_passes():
    report = runner.run_simulation(CODE)
    assert (report["passed"], report["failed"], report["success_rate"]) == (64, 0, 1.0)


def test_changed_clear_left_action_is_detected():
    mutant = CODE.replace("elif not left_blocked:\n        return 'LEFT'",
                          "elif not left_blocked:\n        return 'RIGHT'")
    assert mutant != CODE
    assert runner.run_simulation(mutant)["failed"] > 0


def test_simulation_collects_runtime_errors():
    broken = CODE.replace('state["front_blocked"]', 'state["missing"]')
    result = runner.run_simulation(broken)
    assert result["failed"] == 64
    assert all("KeyError" in row["error"] for row in result["results"])


def test_simulation_writes_report(tmp_path):
    output = tmp_path / "simulation.json"
    assert runner.run_simulation(CODE, output) == read_json(output)


def test_valid_generated_tests():
    assert agent.validate_test_code(TEST_CODE) == TEST_CODE


def test_generated_safety_assertions_are_allowed():
    code = TEST_CODE + """
    if actual == "FORWARD":
        assert not state["front_blocked"]
    elif actual == "LEFT":
        assert not state["left_blocked"]
    elif actual == "RIGHT":
        assert not state["right_blocked"]
    else:
        assert state["front_blocked"] and state["left_blocked"] and state["right_blocked"]
"""
    assert agent.validate_test_code(code) == code


def test_generated_test_cannot_modify_sensors():
    with pytest.raises(ValueError):
        agent.validate_test_code(TEST_CODE + '    state["front_blocked"] = False\n')


@pytest.mark.parametrize("code", [
    "", "   ", "```python\n" + TEST_CODE + "\n```",
    TEST_CODE + "\nimport os\n",
    TEST_CODE.replace("actual = decide_next_move(state)", "actual = eval('1')"),
    TEST_CODE.replace("actual = decide_next_move(state)", "actual = pytest.skip()"),
    TEST_CODE.replace("state, expected", "state"),
    TEST_CODE.replace("scenario_cases()", "[]", 1),
    TEST_CODE.replace("before = state.copy()", "state = {}"),
    TEST_CODE.replace("before = state.copy()", "return"),
    TEST_CODE.replace("assert actual == expected", "pass"),
    TEST_CODE.replace("import pytest", "import pytest as safe"),
    TEST_CODE.replace("actual = decide_next_move(state)", "actual = state.clear()"),
    TEST_CODE + "\npytest.main()\n",
])
def test_unsafe_or_incomplete_test_code_is_rejected(code):
    with pytest.raises(ValueError):
        agent.validate_test_code(code)


def test_test_agent_payload_contains_all_inputs(tmp_path):
    ask = Mock(return_value=json.dumps({"code": TEST_CODE}))
    assert agent.run_test_agent(REQUIREMENTS, PLAN, CODE, "The original brief.",
                                ask=ask, trace_dir=tmp_path) == TEST_CODE
    payload = json.loads(ask.call_args.args[1])
    assert payload == {"brief": "The original brief.", "requirements": REQUIREMENTS,
                       "plan": PLAN, "navigation_code": CODE}


def test_real_pytest_runner_and_mutation_control(tmp_path):
    result = main.check_generated_tests(TEST_CODE, CODE, tmp_path)
    assert result["passed"]
    assert result["normal"]["tests"] == 64
    assert result["mutation_control"]["failures"] > 0
    assert result["mutation_control"]["errors"] == 0


@pytest.mark.parametrize("steps,goal,status", [
    (200, True, "efficient"), (201, True, "acceptable_but_inefficient"),
    (300, True, "acceptable_but_inefficient"), (300, False, "failed"),
])
def test_efficiency_boundaries(steps, goal, status):
    result = world(goal=goal, steps=steps)
    assert benchmark_irsim.validate_world_report(result)["efficiency_status"] == status


@pytest.mark.parametrize("key,value", [
    ("reached_goal", 1), ("steps_taken", True), ("steps_taken", 301),
    ("max_steps_allowed", 500), ("efficient_step_limit", 250),
    ("efficiency_status", "efficient-but-slow"), ("final_pose", [float("nan"), 0, 0]),
    ("efficiency_passed", False),
])
def test_bad_world_measurements_rejected(key, value):
    report = world()
    report[key] = value
    with pytest.raises(ValueError):
        benchmark_irsim.validate_world_report(report)


def test_benchmark_aggregation_uses_all_worlds():
    results = [world("world_easy.yaml", steps=100), world("world_medium.yaml", steps=200),
               world("world_hard.yaml", steps=250), world("world_custom.yaml", goal=False, steps=300)]
    report = benchmark_irsim.summarize(results)
    assert report["success_rate"] == 0.75
    assert report["efficiency_rate"] == 0.5
    assert report["average_steps_taken"] == 212.5
    assert report["inefficient_success_worlds"] == 1 and report["failed_worlds"] == 1


def test_empty_and_duplicate_benchmarks_rejected():
    for results in ([], [world(), world()]):
        with pytest.raises(ValueError):
            benchmark_irsim.summarize(results)


def test_logical_reviewer_pass(tmp_path):
    ask = Mock(return_value=json.dumps(logical_reply()))
    review = reviewer_agent.run_reviewer(runner.run_simulation(CODE), ask=ask, trace_dir=tmp_path)
    assert review["needs_revision"] is False


def test_logical_reviewer_cannot_overrule_measurements(tmp_path):
    ask = Mock(return_value=json.dumps(logical_reply(True)))
    with pytest.raises(ValueError):
        reviewer_agent.run_reviewer(runner.run_simulation(CODE), ask=ask, trace_dir=tmp_path)


def test_forged_simulation_rows_rejected_before_model(tmp_path):
    ask = Mock()
    report = runner.run_simulation(CODE)
    report["results"][0]["actual"] = "STOP"
    with pytest.raises(ValueError):
        reviewer_agent.run_reviewer(report, ask=ask, trace_dir=tmp_path)
    ask.assert_not_called()


@pytest.mark.parametrize("change", [
    {"needs_revision": "false"}, {"needs_revision": 0}, {"issue": ""},
    {"unexpected": "field"}, {"recommendation": None},
])
def test_review_schema_rejects_invalid_fields(change):
    result = {**logical_reply(), **change}
    with pytest.raises(ValueError):
        reviewer_agent.validate_review(result)


def test_benchmark_reviewer_pass():
    report = benchmark_reviewer.build_deterministic_review(benchmark())
    assert all(report[key] for key in ("safety_passed", "goal_completion_passed", "efficiency_passed"))
    assert not report["needs_revision"]


def test_failed_goal_requires_revision_and_efficiency_failure():
    reports = [world(name) for name in benchmark_irsim.WORLDS]
    reports[-1] = world(benchmark_irsim.WORLDS[-1], goal=False, steps=300)
    review = benchmark_reviewer.build_deterministic_review(benchmark_irsim.summarize(reports))
    assert review["safety_passed"]
    assert not review["goal_completion_passed"] and not review["efficiency_passed"]
    assert review["needs_revision"]


def test_cleanup_does_not_hide_observed_collision():
    report = benchmark()
    report["results"][0]["collision_before_cleanup"] = True
    review = benchmark_reviewer.build_deterministic_review(report)
    assert not review["safety_passed"] and review["needs_revision"]


@pytest.mark.parametrize("report", [None, {}, {"results": []}, {"success_rate": 1.0}])
def test_missing_benchmark_fields_fail_closed(report):
    review = benchmark_reviewer.build_deterministic_review(report)
    assert review["needs_revision"]
    assert not review["safety_passed"]


def test_inconsistent_benchmark_totals_fail_closed():
    report = benchmark()
    report["average_steps_taken"] = 0
    assert benchmark_reviewer.build_deterministic_review(report)["needs_revision"]


def test_benchmark_model_cannot_override_flags(tmp_path):
    review = benchmark_reviewer.build_deterministic_review(benchmark())
    review["safety_passed"] = False
    with pytest.raises(ValueError):
        benchmark_reviewer.run_benchmark_reviewer(benchmark(),
                                                  ask=Mock(return_value=json.dumps(review)),
                                                  trace_dir=tmp_path)


def test_revision_has_all_context_and_preserves_original_helper(tmp_path):
    revised = CODE.replace("    goal_direction", "    selected_goal").replace(
        "right_blocked, goal_direction)", "right_blocked, selected_goal)")
    adapter = "def decide_next_move" + revised.split("def decide_next_move", 1)[1]
    revised = developer_agent.ORIGINAL_CODE.rstrip() + "\n\n" + adapter
    # Only the adapter's local name changes; the first helper remains byte-for-byte intact.
    with patch.object(developer_agent, "ask_qwen", return_value=json.dumps({"code": adapter})) as ask:
        result = developer_agent.run_developer_revision(
            CODE, {"issue": "none"}, benchmark(), REQUIREMENTS, PLAN, trace_dir=tmp_path)
    assert result == revised
    assert runner.run_simulation(result)["passed"] == 64
    assert set(json.loads(ask.call_args.args[1])) == {
        "original_code", "review_notes", "benchmark_report", "requirements", "plan"}
    assert ask.call_args.kwargs["response_schema"] == developer_agent.REVISION_SCHEMA


@pytest.mark.parametrize("reply", ["```python\n" + CODE + "\n```",
                                  json.dumps({"code": CODE, "extra": "text"}),
                                  json.dumps({"code": CODE}),
                                  json.dumps({"code": ""}),
                                  json.dumps({"code": 123}),
                                  json.dumps({"code": "def decide_next_move(:"}),
                                  json.dumps({"code": "```python\n" + CODE + "\n```"})])
def test_revision_rejects_wrapped_or_extra_output(reply, tmp_path):
    with patch.object(developer_agent, "ask_qwen", return_value=reply), pytest.raises(ValueError):
        developer_agent.run_developer_revision(CODE, {}, benchmark(), REQUIREMENTS, PLAN, trace_dir=tmp_path)


def test_transport_binding_is_restored_on_failure():
    model = integration_model.LocalModel.__new__(integration_model.LocalModel)
    before = [module.ask_qwen for module in (analyst_agent, planner_agent, developer_agent)]
    with pytest.raises(RuntimeError), model.bind_original_agents():
        assert analyst_agent.ask_qwen == model.ask
        raise RuntimeError("Fixture failure")
    assert before == [module.ask_qwen for module in (analyst_agent, planner_agent, developer_agent)]


def test_hardware_hard_stop():
    with patch.object(integration_model, "hardware_sample", return_value={"ram_gib": 1, "gpu_c": 50}):
        with pytest.raises(RuntimeError):
            integration_model.wait_until_cool()


def test_hardware_temperature_stop():
    with patch.object(integration_model, "hardware_sample", return_value={"ram_gib": 5, "gpu_c": 80}):
        with pytest.raises(RuntimeError):
            integration_model.wait_until_cool()


def test_hardware_cooldown_waits():
    with patch.object(integration_model, "hardware_sample", side_effect=[
            {"ram_gib": 5, "gpu_c": 73}, {"ram_gib": 5, "gpu_c": 65}]), \
            patch.object(integration_model.time, "sleep") as sleep:
        assert integration_model.wait_until_cool()["gpu_c"] == 65
        sleep.assert_called_once_with(5)


def test_remote_model_endpoints_are_rejected():
    with pytest.raises(ValueError):
        integration_model.LocalModel("https://example.com")


def test_round_calls_stages_in_order_and_passes_review_to_revision(tmp_path):
    events = []
    logical = runner.run_simulation(CODE)
    bench = benchmark()
    review = logical_reply()
    measured = benchmark_reviewer.build_deterministic_review(bench)
    model, logger = Mock(), Mock()
    testing = {"passed": True, "normal": {"tests": 64}, "mutation_detected": True}

    def stage(name, result):
        def call(*args, **kwargs):
            events.append(name)
            return result
        return call

    with patch.object(main, "run_analyst", side_effect=stage("analyst", REQUIREMENTS)), \
            patch.object(main, "run_planner", side_effect=stage("planner", PLAN)), \
            patch.object(main, "run_developer", side_effect=stage("developer", CODE)), \
            patch.object(main, "run_developer_revision", side_effect=stage("revision", CODE)) as revision, \
            patch.object(main, "run_test_agent", side_effect=stage("test_agent", TEST_CODE)), \
            patch.object(main, "check_generated_tests", side_effect=stage("pytest", testing)), \
            patch.object(main, "run_simulation", side_effect=stage("simulation", logical)), \
            patch.object(main, "run_reviewer", side_effect=stage("reviewer", review)), \
            patch.object(main, "run_benchmark", side_effect=stage("benchmark", bench)), \
            patch.object(main, "run_benchmark_reviewer", side_effect=stage("benchmark_reviewer", measured)):
        initial = main.run_round(0, tmp_path, "brief", None, model, logger)
        repeated = main.run_round(1, tmp_path, "brief", initial, model, logger)
    tail = ["test_agent", "pytest", "simulation", "reviewer", "benchmark", "benchmark_reviewer"]
    assert events == ["analyst", "planner", "developer", *tail, "analyst", "planner", "revision", *tail]
    assert initial["passed"] and repeated["passed"]
    assert revision.call_args.args[0] == CODE
    assert revision.call_args.args[1] == {"simulation": review, "benchmark": measured}
    assert revision.call_args.args[2] == bench


def test_failed_generated_tests_prevent_round_acceptance(tmp_path):
    with patch.object(main, "run_analyst", return_value=REQUIREMENTS), \
            patch.object(main, "run_planner", return_value=PLAN), \
            patch.object(main, "run_developer", return_value=CODE), \
            patch.object(main, "run_test_agent", return_value=TEST_CODE), \
            patch.object(main, "check_generated_tests", return_value={
                "passed": False, "normal": {"tests": 64}, "mutation_detected": False}), \
            patch.object(main, "run_simulation", return_value=runner.run_simulation(CODE)), \
            patch.object(main, "run_reviewer", return_value=logical_reply()), \
            patch.object(main, "run_benchmark", return_value=benchmark()), \
            patch.object(main, "run_benchmark_reviewer", return_value=benchmark_reviewer.build_deterministic_review(benchmark())):
        result = main.run_round(0, tmp_path, "brief", None, Mock(), Mock())
    assert result["passed"] is False


def test_evidence_text_hash_is_line_ending_independent(tmp_path):
    unix, windows = tmp_path / "unix.py", tmp_path / "windows.py"
    unix.write_bytes(b"a = 1\nb = 2\n")
    windows.write_bytes(b"a = 1\r\nb = 2\r\n")
    assert verify_integration.text_hash(unix) == verify_integration.text_hash(windows)


def test_evidence_audit_rejects_an_incomplete_exchange(tmp_path):
    from artifact_io import write_json
    write_json(tmp_path / "exchanges/analyst/fixture.json", {
        "request": {}, "response": {"done": False, "done_reason": "length"}})
    with pytest.raises(ValueError, match="incomplete response"):
        verify_integration.exchange(tmp_path, "analyst", "fixture")


def test_evidence_audit_checks_junit_and_executed_source(tmp_path):
    result = main.check_generated_tests(TEST_CODE, CODE, tmp_path)
    verify_integration.verify_pytest(tmp_path, TEST_CODE, CODE, result)
    edited = copy.deepcopy(result)
    edited["normal"]["tests"] = 65
    with pytest.raises(ValueError, match="recorded result"):
        verify_integration.verify_pytest(tmp_path, TEST_CODE, CODE, edited)
    (tmp_path / "pytest/generated/navigation_logic.py").write_text("pass\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Different navigation"):
        verify_integration.verify_pytest(tmp_path, TEST_CODE, CODE, result)
