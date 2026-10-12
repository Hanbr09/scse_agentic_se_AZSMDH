# Robot Navigation Agent Pipeline

Group AZSMDH

This project turns a robot navigation brief into requirements, a plan and
Python decision logic, then tests that logic in a sensor-state simulation
and four IR-SIM worlds. Qwen agents generate and review the artifacts;
executable tests and simulation measurements determine whether they pass.

The current stage is **Integration and Simulation**. The earlier Requirements
Engineering, Plan and Develop, and Testing work is retained in this repository.

## Start here

You can verify the submitted results without Ollama or a downloaded model.
From the repository folder on Windows, create an environment and install
the dependencies:

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-integration.txt
```

Then check the saved evidence and run the offline tests:

```powershell
.\.venv\Scripts\python.exe -B verify_integration.py
.\.venv\Scripts\python.exe -B verify_pipeline.py
.\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider --import-mode=importlib integration_tests
.\.venv\Scripts\python.exe -B -m unittest discover -q
```

The integration audit checks the saved model exchanges, their inputs, source
snapshots, generated tests and simulation reports. It does not call a model
or repeat the four routes. The two test commands now cover 101 integration checks
and 76 earlier unittest methods.

The [13 October maintenance notes](docs/maintenance-20261013.txt) describe
publication-failure protection and simulator boundary fixes. The original
run evidence is unchanged; the audit explicitly identifies later source changes.

## Explore the result

The [evidence index](artifacts/README.md) links to the reports and recorded
runs. Both the original and revised navigation code reached all four goals:

| World | Steps | Recorded revised run |
| --- | ---: | --- |
| Easy | 150 | [Animation](artifacts/integration_runs/20261010T131220778018Z/round_1/worlds/world_easy/simulation.gif) |
| Medium | 148 | [Animation](artifacts/integration_runs/20261010T131220778018Z/round_1/worlds/world_medium/simulation.gif) |
| Hard | 187 | [Animation](artifacts/integration_runs/20261010T131220778018Z/round_1/worlds/world_hard/simulation.gif) |
| Custom | 193 | [Animation](artifacts/integration_runs/20261010T131220778018Z/round_1/worlds/world_custom/simulation.gif) |

Each round passed 64 model-generated test cases and an independent simulation
of all 64 boolean sensor states. A deliberately incorrect STOP-only control
failed 56 assertions in each round, as expected. Those failures show that the
tests detect bad behavior; they are not failures of the submitted policy.

To repeat the four routes with the saved revised code, without using a model:

```powershell
.\.venv\Scripts\python.exe -B benchmark_irsim.py --code generated/navigation_logic_revised.py --output artifacts/local_benchmarks/my_benchmark
```

Use a fresh output directory each time. Local benchmark folders are ignored
by Git so they do not replace or crowd the submitted evidence. These results
describe the supplied worlds, not every possible map or a physical robot.

## Generate a new run

[The integration guide](docs/INTEGRATION.md) explains the full workflow,
resource checks and interactive simulation options. On the Windows/NVIDIA
machine used for the recorded run, the managed entry point is:

```powershell
.\.venv\Scripts\python.exe -B run_integration.py --allow-model --backend vulkan
```

This command makes real requests to an already-downloaded `qwen2.5:3b`
model in Ollama. It starts a temporary local service, checks GPU loading,
limits CPU math to two threads and closes its own service on completion or
failure. The Vulkan device index is machine-specific; read the guide before
running it elsewhere. No model training or cloud API is involved.

`main.py` orchestrates the agents, tests, simulations, reviews and revision
round. A new run may update the current result files. Its raw run folder is
kept locally and ignored by Git until explicitly reviewed for publication;
only the accepted recorded run is included by default.

## Where things are

| Location | Purpose |
| --- | --- |
| `main.py`, `run_integration.py` | Pipeline orchestration and managed model execution |
| Root agent and runner scripts | Required entry points from the project stages |
| `generated/` | Accepted original and revised navigation code |
| `irsim_worlds/` | The four supplied simulation maps |
| `tests/`, `integration_tests/` | Offline regression and integration checks |
| [artifacts/](artifacts/README.md) | Accepted outputs and verification evidence |
| [docs/INTEGRATION.md](docs/INTEGRATION.md) | Current workflow, results and limitations |
| [docs/history/](docs/history/TESTING_README.md) | Earlier stage explanations and usage |
| [docs/instructions/](docs/instructions/) | Unmodified teacher instruction PDFs |

The root Python files remain in their original locations to preserve the
teacher's entry points and earlier-stage interfaces. Successful run folders
also retain input snapshots and isolated simulation workspaces because the
audit verifies them against the reported results.

Seven failed development attempts and a duplicate preliminary baseline were
moved to a local archive outside the repository working tree during cleanup.
They also remain in Git history at commit `4a2df3c`. The accepted run's raw
exchanges and evidence were not changed. Historical audit records retain
their original document paths; the documents now live under `docs/`.

## Submission

The project continues in the original group repository:
[Hanbr09/scse_agentic_se_AZSMDH](https://github.com/Hanbr09/scse_agentic_se_AZSMDH).
One group member must submit the repository link through the course system.
Uploading to GitHub does not itself complete that separate submission.
