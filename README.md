# Robot Navigation Agent Pipeline

Group AZSMDH

This project uses three Qwen agents to turn a robot navigation brief into
working Python decision logic. The Analyst describes what the robot must
achieve, the Planner decides how it should respond, and the Developer writes
the navigation function. Each stage receives only the previous stage's
validated artifact, rather than its conversation history.

```text
brief.txt
    -> Analyst   -> artifacts/requirements.json
    -> Planner   -> artifacts/plan.json
    -> Developer -> generated/navigation_logic.py
```

The Testing extension reruns all three agents on real inputs and adds a
public sensor-state interface. It preserves this group's original
`choose_action` implementation and seven-rule plan structure, rather than
replacing them with a different navigation design. Earlier structured results
are archived in `artifacts/baseline/`; the original brief and preliminary
plain-text replies remain available.

The current submission passes 76 unittest methods on Python 3.10.11 and 3.12.0.
Eight of those methods cover the full 64-state navigation matrix. The deliberate
wrong-turn experiment produced six assertion failures; restoration returned
the suite to passing. The three agent outputs have matching real Qwen records.
See `artifacts/testing_audit.json` for the checks and linked logs.

## Try the saved result

The submitted result can be inspected and tested without installing Ollama
or downloading a model. The commands below use Python 3.10 on Windows; with
another supported Python version, replace `py -3.10` with that interpreter.

```powershell
git clone https://github.com/Hanbr09/scse_agentic_se_AZSMDH.git
cd scse_agentic_se_AZSMDH
py -3.10 -B verify_pipeline.py
py -3.10 -B demo_navigation.py --front-blocked --goal AHEAD
py -3.10 -B -m unittest discover -v
```

For an existing clone, run `git pull` inside the project instead of cloning
again. The example above prints `Action: LEFT`: the goal is ahead, but that
path is blocked, so the saved plan chooses the first safe fallback.

Two other examples:

```powershell
py -3.10 -B demo_navigation.py --goal RIGHT
py -3.10 -B demo_navigation.py --front-blocked --left-blocked --right-blocked
```

These print `Action: RIGHT` and `Action: STOP`. Leaving out `--goal` means
that goal-direction information is unavailable.

## How the decision works

Programs now call `decide_next_move(state)`. The state is a dictionary with
six boolean fields, matching the teacher's example:

```python
state = {
    "front_blocked": True,
    "left_blocked": False,
    "right_blocked": False,
    "goal_ahead": True,
    "goal_on_left": False,
    "goal_on_right": False,
}
```

This example returns LEFT. All three goal flags being false represents
unavailable goal information. If several goal flags are true, the adapter
uses the first clear indicated goal in ahead-left-right order. That tie-break
is an explicit group decision for an otherwise unspecified sensor combination.

Internally, the unchanged helper
`choose_action(front_blocked, left_blocked, right_blocked, goal_direction=None)`
returns `FORWARD`, `LEFT`, `RIGHT`, or `STOP`. Other programs do not call it
directly. The obstacle inputs must be
booleans; `True` means blocked. The optional goal value is `AHEAD`, `LEFT`,
`RIGHT`, or `None`.

The saved plan prefers a safe goal direction. If that direction is blocked,
or goal information is absent, it checks front, left, then right. It stops
when all three directions are blocked. This fallback order was chosen at
the planning stage; it is not an extra requirement attributed to the brief.
The function decides one move at a time. It does not claim to find an entire
route, detect arrival at a destination, or control a physical robot. Missing
keys or non-boolean sensor values are outside the stated input contract.

## Two testing levels

The three root-level scripts `test_analyst.py`, `test_planner.py`, and
`test_developer.py` run the actual agents through their normal runners.
They read the original brief, the accepted requirements, and the accepted
plan respectively. Each agent's own validator accepts or rejects its reply.
Successful artifacts are saved and displayed; failed replies remain in the
raw exchange folders without replacing accepted files.

`test_generated_navigation_logic.py` is a separate, offline behavior test.
An explicit table describes eight obstacle patterns for each of eight
goal-flag patterns: all 64 combinations. Expected actions are not obtained
from the generated code. The tests also check the teacher's example, input
preservation, and decisions after sensor values change.

The PDF uses both `artifacts/navigation_logic.py` and
`generated/navigation_logic.py`. The generated path is the canonical file
used by the tests. The artifacts path and legacy root path contain identical
copies, and verification rejects mismatched copies.

To demonstrate that the tests detect an actual wrong action:

```powershell
py -3.10 -B run_bug_check.py
```

The script requires a passing baseline, changes the original helper's clear-left
fallback from LEFT to RIGHT, and reruns the behavior suite. An action assertion
must fail. It restores the original file in a `finally` block, then requires
the tests to pass again and the original bytes to match. Logs and before/after
hashes are saved under `artifacts/bug_checks/`, with the latest summary in
`artifacts/bug_check.json`. Submitted code is restored, not deliberately faulty.

## Generate new artifacts

This section makes real model requests. It requires an installed Ollama
application and an already-downloaded `qwen2.5:3b` model. Run only on a
machine approved for local inference. The scripts do not download models,
start inference on import, or retry failed requests automatically.

Create a Python environment in this project, rather than copying someone
else's environment:

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

The Windows helper below manages a temporary local service and invokes the
three smoke-test scripts in order:

```powershell
.\.venv\Scripts\python.exe run_smoke_tests.py --allow-model
py -3.10 -B -m unittest discover -v
py -3.10 -B run_bug_check.py
```

The helper refuses to start when another model service exists or less than
4.5 GiB RAM is available. It uses only CPU inference with two threads,
unloads the model between requests, and closes only its own service on
completion or failure. There are no GPU requests or model downloads.
Resource limits reduce load but cannot guarantee every machine's stability.

Stop if a command reports failure. Raw replies remain in `artifacts/analyst_runs`,
`artifacts/planner_runs`, and `artifacts/developer_runs`, including rejected
replies. `artifacts/testing_runs/` contains the displayed outputs and cleanup
records. To rerun just one stage, add `--only analyst`, `--only planner`, or
`--only developer`. Any changed upstream artifact requires downstream stages
to be rerun, followed by verification and the bug check.

The earlier plain-text Requirements Engineering exercise is separate from this
Testing run. Its existing `robot_requirements.txt` is preserved; repeating it
is optional and needs a running, approved local service:

```powershell
.\.venv\Scripts\python.exe brief_to_req.py --allow-model --runs 3
```

Individual `test_*.py --allow-model` smoke scripts also require an already
running local service. Prefer the managed helper. The legacy
`start_ollama_cpu.ps1` remains available for manual service operation.

## Project files

- `brief_to_req.py`, `analyst_agent.py`, `run_analyst.py`: the earlier
  Requirements Engineering work. [observations.md](observations.md) retains
  the discussion of the initial plain-text replies and their limitations.
- `planner_agent.py`, `run_planner.py`: plan generation and validation.
- `developer_agent.py`, `run_developer.py`: code generation, restricted
  syntax checks, and navigation behavior checks.
- `generated/navigation_logic.py`: unedited, accepted Qwen code and its two compatibility copies.
- `verify_pipeline.py`, `demo_navigation.py`: offline verification and a
  small command-line example using the saved result.
- `test_analyst.py`, `test_planner.py`, `test_developer.py`: explicit real-agent smoke entrypoints.
- `test_generated_navigation_logic.py`: independent expected-action matrix.
- `run_bug_check.py`: deliberate wrong-action exercise with guaranteed restoration on handled failures.
- `artifacts/`: current results, raw exchanges, baseline snapshots, verification and test logs.
- `tests/`: standard-library regression tests. Mocked replies are explicitly test fixtures.

[DEVELOPMENT_NOTES.md](DEVELOPMENT_NOTES.md) explains the plan format,
validation boundaries and the previous-stage run. [TESTING_NOTES.md](TESTING_NOTES.md)
explains the Testing work. Both teacher instruction PDFs are included unchanged.

## Submission

This repository combines the earlier Requirements Engineering project with
the [Plan and Develop starter](https://github.com/prabhatram/scse_plan_and_develop)
and the [Testing starter](https://github.com/prabhatram/scse-26-project-testing).
Its name remains `scse_agentic_se_AZSMDH`, as required. One group member
submits only this repository link to Moodle:

[Hanbr09/scse_agentic_se_AZSMDH](https://github.com/Hanbr09/scse_agentic_se_AZSMDH)

The Testing announcement says September 25 at midnight. Check the exact
closing time and course time zone in Moodle. The PDF also requires working
physically with group members; code checks cannot verify attendance.
