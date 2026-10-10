# Integration and Simulation

The navigation policy from the Testing stage is now part of one runnable
pipeline. It produces tests, checks the sensor decisions, drives the robot
through four IR-SIM worlds, and asks Qwen to review the measured results.
The revision round repeats every stage, including both reviews and all four
worlds. Earlier project files and their recorded results remain available.

## Run the saved code

From the repository directory, install the integration dependencies:

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-integration.txt
.\.venv\Scripts\python.exe -B runner.py
.\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider --import-mode=importlib integration_tests
.\.venv\Scripts\python.exe -B -m unittest discover -q
.\.venv\Scripts\python.exe -B verify_integration.py
```

These commands do not call a language model. The existing
`verify_pipeline.py` still checks the earlier Testing-stage evidence.
The new run is recorded separately in `artifacts/integration_latest.json`.
`verify_integration.py` checks the recorded model replies, inputs between
agents, executed test files, JUnit results, all four simulation workspaces,
review flags and source hashes. It also confirms that the teacher's files
and the earlier Python files (apart from the extended Developer) are intact.

To repeat the four measured routes using the saved navigation code:

```powershell
.\.venv\Scripts\python.exe -B benchmark_irsim.py --code generated/navigation_logic_revised.py --output artifacts/my_benchmark
```

Use a new output directory for each run. Each world keeps its original report,
console log, measured positions, trajectory image and animation. A world that
does not reach its goal remains a failure; the benchmark never drops it from
the denominator.

For an interactive window on Windows, activate the environment and run the
teacher's Python script directly:

```powershell
.\.venv\Scripts\python.exe test_irsim_with_agent.py irsim_worlds/world_easy.yaml
```

Repeat with `world_medium.yaml`, `world_hard.yaml` and `world_custom.yaml`.
On Linux, the original `run_visual.sh` is also available. The PDF calls the
third file `world_difficult.yaml`; the supplied repository calls it
`world_hard.yaml`. The contents and filename from the repository are retained.
The teacher script loads the original saved policy. To watch the revision
instead, add `--interactive` to the benchmark command above; it uses an
isolated copy of the same teacher script with the selected code.

## Run the agents

The model stages require Ollama with `qwen2.5:3b` already downloaded.
No training or external API is involved. On this Windows/NVIDIA machine:

```powershell
.\.venv\Scripts\python.exe -B run_integration.py --allow-model --backend vulkan
```

The wrapper starts a private local service on port 11522. Vulkan device 1 is
the NVIDIA GPU on this machine; another machine may need a different index
or the default `--backend auto`. Requests verify GPU loading, limit CPU math
to two threads, and keep at most one model loaded. The earlier Analyst and
Planner files are unchanged: the integration entry point temporarily gives
them this local transport and restores their original bindings afterwards.

Startup requires 4.5 GiB of available RAM and 4500 MiB of free GPU memory.
The run stops if RAM falls below 1.25 GiB or GPU temperature reaches 80 C.
Between requests, temperatures of 72 C or more trigger a cooling wait.
The wrapper closes only its own worker and model service on completion or
failure. These checks reduce load; they cannot guarantee hardware stability.

An externally managed local service can instead be used with:

```powershell
.\.venv\Scripts\python.exe -B main.py --allow-model --base-url http://127.0.0.1:11434
```

## What a run contains

`main.py` reads the original brief and calls the Analyst, Planner, Developer,
Test Agent, logical simulation, simulation reviewer, IR-SIM benchmark and
benchmark reviewer in order. It records each step in `trace.log`.
The second round uses `run_developer_revision()` with the previous code,
both reviews, the measured benchmark, requirements and plan.
The model returns the revised adapter only. The application combines that
verbatim response with the preserved `choose_action` helper to form the new
module. The code is rejected if its behavior or interface violates the
previous stage's contract. Model replies are not manually fixed.

The generated pytest file uses an independent table of all 64 boolean sensor
states. Tests check the action and preserve the input dictionary. The same
tests also run against a separate, deliberately wrong STOP-only module.
This demonstrates that they can fail on incorrect navigation; the actual
navigation file is never replaced by the faulty control.

Reviewers return structured JSON. Logical results determine whether the
simulation needs revision. Benchmark measurements determine the safety,
goal-completion and efficiency flags; a model cannot change a failed flag to
passed. Missing or inconsistent measurements are not accepted as success.

The supplied simulation script and four worlds are unchanged. A small
observer captures plots and collision status before IR-SIM closes the scene.
It does not change actions, velocities, obstacles, goal tolerance or physics.
Automated runs use a noninteractive plotting backend. Their GIFs show the
actual sampled simulation frames, not an illustrative path.

## Results and limits

The accepted run on 10 October 2026 is
[`20261010T131220778018Z`](artifacts/integration_runs/20261010T131220778018Z/trace.log).
It contains twelve real `qwen2.5:3b` exchanges with full GPU loading recorded.
Both the initial and revised code reached all four goals with the same results:

| World | Steps | Result |
| --- | ---: | --- |
| [Easy animation](artifacts/integration_runs/20261010T131220778018Z/round_1/worlds/world_easy/simulation.gif) | 150 | Reached |
| [Medium animation](artifacts/integration_runs/20261010T131220778018Z/round_1/worlds/world_medium/simulation.gif) | 148 | Reached |
| [Hard animation](artifacts/integration_runs/20261010T131220778018Z/round_1/worlds/world_hard/simulation.gif) | 187 | Reached |
| [Custom animation](artifacts/integration_runs/20261010T131220778018Z/round_1/worlds/world_custom/simulation.gif) | 193 | Reached |

The mean was 169.5 steps. Every run was below the supplied 200-step efficiency
limit; the hard limit remains 300. No collision was observed in these runs.
Since the measured policy already works in these worlds, the requested code
revision is a readability change, not a claimed repair of an unseen failure.
The revised adapter uses `selected_goal` for its local bearing; the original
helper is unchanged. Fresh tests and all four fresh simulations passed before
the revised module was saved as `generated/navigation_logic_revised.py`.

Each round passed 64 generated pytest cases and the independent 64-state
logical simulation. The STOP-only control produced 56 expected assertion
failures in each round. The project also passed its 76 previous unittest
methods and 73 new offline integration checks on Python 3.10.11.
The saved-evidence audit passed, and the temporary model service was stopped.

Raw model exchanges, rejected attempts and source snapshots stay with their
run folders. Failed requests do not replace accepted results. These four
worlds do not establish correctness for every possible map or a physical robot.
Earlier attempts exposed model output-format and helper-retention errors;
those rejected replies remain recorded, rather than being presented as passes.

The new work uses the
[Integration and Simulation starter](https://github.com/prabhatram/project_integration_and_simulation)
and remains in this original AZSMDH repository.
