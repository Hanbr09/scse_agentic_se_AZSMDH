"""Regression cases for publication failure and simulator boundaries."""

from contextlib import nullcontext
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from artifact_io import read_json, write_json, write_text
import main
import verify_integration as verifier


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "ROOT", tmp_path)
    write_text(tmp_path / "brief.txt", "Synthetic publication fixture, not model evidence.")
    write_json(tmp_path / "artifacts/integration_latest.json",
               {"status": "passed", "run_directory": "previous"})
    write_text(tmp_path / "generated/navigation_logic_revised.py", "previous code\n")
    for name in main.REPORT_FILES:
        write_json(tmp_path / "artifacts" / name, {"old": name})
    return tmp_path


def published_bytes(root):
    paths = [root / "artifacts/integration_latest.json", root / "generated/navigation_logic_revised.py",
             *(root / "artifacts" / name for name in main.REPORT_FILES)]
    return {path: path.read_bytes() for path in paths}


@pytest.mark.parametrize("error", [RuntimeError("fixture rejection"), KeyboardInterrupt()])
def test_failed_attempt_keeps_all_published_files(project, monkeypatch, error):
    before = published_bytes(project)
    monkeypatch.setattr(main.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0))
    def fail(*args):
        raise error
    monkeypatch.setattr(main, "run_round", fail)
    model = SimpleNamespace(model="offline fixture", bind_original_agents=nullcontext)
    with pytest.raises(type(error)):
        main.run_pipeline(project / "attempt", model)
    assert published_bytes(project) == before
    assert read_json(project / "artifacts/integration_last_attempt.json")["status"] == "error"


def test_failed_legacy_suite_keeps_accepted_pointer(project, monkeypatch):
    before = published_bytes(project)
    monkeypatch.setattr(main.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=1))
    model = SimpleNamespace(model="offline fixture", bind_original_agents=nullcontext)
    with pytest.raises(RuntimeError, match="regression"):
        main.run_pipeline(project / "attempt", model)
    assert published_bytes(project) == before


def make_completed_run(root, status="passed", changed=True):
    folder = root / "candidate"
    write_json(folder / "run.json", {"status": status, "revision_changed_source": changed})
    write_text(folder / "round_1/navigation_logic.py", "new fixture code\n")
    for name in main.REPORT_FILES:
        write_json(folder / "round_1" / name, {"new": name})
    return folder


@pytest.mark.parametrize("status,changed", [("error", True), ("needs_revision", True), ("passed", False)])
def test_rejected_result_is_not_published(project, status, changed):
    before = published_bytes(project)
    with pytest.raises(ValueError, match="passed"):
        main.publish_result(make_completed_run(project, status, changed))
    assert published_bytes(project) == before


def test_completed_result_publishes_code_reports_and_pointer(project):
    folder = make_completed_run(project)
    main.publish_result(folder)
    assert read_json(project / "artifacts/integration_latest.json")["run_directory"] == "candidate"
    assert (project / "generated/navigation_logic_revised.py").read_text() == "new fixture code\n"
    for name in main.REPORT_FILES:
        assert read_json(project / "artifacts" / name) == {"new": name}


def test_missing_candidate_report_leaves_everything_unchanged(project):
    folder = make_completed_run(project)
    (folder / "round_1/test_report.json").unlink()
    before = published_bytes(project)
    with pytest.raises(FileNotFoundError):
        main.publish_result(folder)
    assert published_bytes(project) == before


def test_publication_write_failure_restores_previous_bytes(project, monkeypatch):
    folder = make_completed_run(project)
    before = published_bytes(project)
    original = main.write_text
    failed = False
    def fail_once(path, content):
        nonlocal failed
        if not failed and path == project / "artifacts/benchmark_review.json":
            failed = True
            raise OSError("Synthetic disk failure")
        return original(path, content)
    monkeypatch.setattr(main, "write_text", fail_once)
    with pytest.raises(OSError, match="Synthetic"):
        main.publish_result(folder)
    assert published_bytes(project) == before


def test_model_cleanup_failure_prevents_publication(monkeypatch, tmp_path):
    import sys
    monkeypatch.setattr(sys, "argv", ["main.py", "--allow-model", "--output", str(tmp_path)])
    monkeypatch.setattr(main, "run_pipeline", lambda *a: {"status": "passed"})
    class Model:
        def close(self):
            raise RuntimeError("Synthetic unload failure")
    monkeypatch.setattr(main, "LocalModel", lambda *a, **k: Model())
    published = []
    monkeypatch.setattr(main, "publish_result", published.append)
    with pytest.raises(RuntimeError, match="unload"):
        main.main()
    assert published == []


@pytest.mark.parametrize("deferred", [False, True])
def test_entrypoint_publishes_only_after_cleanup(monkeypatch, tmp_path, deferred):
    import sys
    args = ["main.py", "--allow-model", "--output", str(tmp_path)]
    if deferred:
        args.append("--defer-publication")
    monkeypatch.setattr(sys, "argv", args)
    events = []
    monkeypatch.setattr(main, "run_pipeline", lambda *a: {"status": "passed"})
    monkeypatch.setattr(main, "LocalModel",
                        lambda *a, **k: SimpleNamespace(close=lambda: events.append("closed")))
    monkeypatch.setattr(main, "publish_result", lambda *a: events.append("published"))
    assert main.main() == 0
    assert events == (["closed"] if deferred else ["closed", "published"])


def trajectory(stopped=False, distance=0.4):
    pose = [distance, 0.0, 0.0]
    report = {"steps_taken": 1, "final_pose": pose, "reached_goal": distance <= 0.4,
              "collision_before_cleanup": False, "done_before_cleanup": False}
    trace = {"poses": [pose] if stopped else [[0.5, 0.0, 0.0], pose],
             "goal": [0.0, 0.0], "collision_before_cleanup": False, "done_before_cleanup": False}
    action = "STOP" if stopped else "FORWARD"
    console = f"Step 1: state={{}} action={action} velocity=[0 0]\n"
    if stopped:
        console += "Agent returned STOP.\n"
    return trace, report, console


@pytest.mark.parametrize("distance", [0.399999, 0.4, 0.400001])
def test_goal_boundary_matches_teacher(distance):
    verifier.verify_trajectory(*trajectory(distance=distance))


def test_stop_has_no_extra_physics_step():
    trace, report, console = trajectory(stopped=True, distance=4.0)
    trace["physical_steps"] = 0
    verifier.verify_trajectory(trace, report, console)


@pytest.mark.parametrize("fault", ["count", "goal", "console", "stop_marker", "physical_steps"])
def test_inconsistent_trajectory_is_still_rejected(fault):
    trace, report, console = trajectory()
    if fault == "count":
        trace["poses"].pop(0)
    elif fault == "goal":
        report["reached_goal"] = False
    elif fault == "console":
        console = console.replace("Step 1:", "Step 2:")
    elif fault == "stop_marker":
        console += "Agent returned STOP.\n"
    else:
        trace["physical_steps"] = 0
    with pytest.raises(ValueError):
        verifier.verify_trajectory(trace, report, console)


def source_fixture(root, monkeypatch):
    monkeypatch.setattr(verifier, "ROOT", root)
    folder = root / "saved"
    write_text(root / "main.py", "old source\n")
    write_text(folder / "source_main.py", "old source\n")
    old_hash = verifier.text_hash(root / "main.py")
    write_json(folder / "source_hashes.json", {"main.py": old_hash})
    return folder, old_hash


def test_unchanged_sources_need_no_amendment(tmp_path, monkeypatch):
    folder, _ = source_fixture(tmp_path, monkeypatch)
    assert verifier.verify_sources(folder) == []


def test_recorded_source_snapshot_cannot_be_rewritten(tmp_path, monkeypatch):
    folder, _ = source_fixture(tmp_path, monkeypatch)
    write_text(folder / "source_main.py", "changed snapshot\n")
    with pytest.raises(ValueError, match="snapshot changed"):
        verifier.verify_sources(folder)


@pytest.mark.parametrize("fault", [None, "wrong_run", "wrong_before", "wrong_after", "extra_file"])
def test_live_fix_requires_exact_and_run_scoped_amendment(tmp_path, monkeypatch, fault):
    folder, old_hash = source_fixture(tmp_path, monkeypatch)
    write_text(tmp_path / "main.py", "fixed source\n")
    amendment = {"run_directory": "saved", "files": {
        "main.py": {"before": old_hash, "after": verifier.text_hash(tmp_path / "main.py")}}}
    if fault == "wrong_run":
        amendment["run_directory"] = "unrelated"
    elif fault == "wrong_before":
        amendment["files"]["main.py"]["before"] = "0" * 64
    elif fault == "wrong_after":
        amendment["files"]["main.py"]["after"] = "0" * 64
    elif fault == "extra_file":
        amendment["files"]["unrelated.py"] = copy.deepcopy(amendment["files"]["main.py"])
    write_json(tmp_path / "artifacts/maintenance/source_changes.json", amendment)
    if fault:
        with pytest.raises(ValueError):
            verifier.verify_sources(folder)
    else:
        assert verifier.verify_sources(folder) == ["main.py"]
