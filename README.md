# Robot Navigation Requirements Analyst

Group: AZSMDH. Submission repository name: `scse_agentic_se_AZSMDH`.

This project converts a robot navigation brief into requirements using Qwen.
It covers requirements analysis, not robot movement or a simulator.

`brief_to_req.py` is the initial plain-text exercise. `analyst_agent.py`
contains `run_analyst(brief_text)` and `validate_requirements(result)`.
`run_analyst.py` reads the brief and saves validated model output in
`artifacts/requirements.json`.

## Current status

On September 21, 2026, Qwen generated both `robot_requirements.txt` and
`artifacts/requirements.json`. The three plain-text runs were identical,
but contained two interpretation errors discussed in [observations.md](observations.md).
The final structured response passed validation and was saved without changing
its values. All 26 offline tests also passed; these are separate from the
real model runs. Test fixtures were not used as submission results.

The real run used CPU inference with two threads. Each response unloaded
the model, and the temporary server was stopped after verification.

## Offline checks

With Python 3.10 or newer, run from this project folder:

```powershell
py -3.10 -B -m unittest discover -s tests -v
```

These checks use only the standard library. They do not install software,
connect to Ollama, start a model, or use a GPU.

## Real model runs

Do not run this section until the machine and model runtime have been
approved for use. Even CPU inference consumes memory and can create load.
The scripts request CPU-only inference with two threads and request model
unloading after each response. They do not start the Ollama service, install
models, retry failed requests, or create a background service. These settings
reduce resource use; they do not guarantee system stability.

Use an existing suitable Python environment or create a project environment:

```powershell
py -3.10 -m venv .venv
& "./.venv/Scripts/python.exe" -m pip install -r requirements.txt
```

An installed Ollama application and an already-downloaded Qwen model are
also required. The default model is `qwen2.5:3b`; `OLLAMA_MODEL` can select
another installed Qwen model. Do not copy a `.venv` folder between computers.

When ready, run `./start_ollama_cpu.ps1` in a separate PowerShell terminal.
This explicitly disables CUDA and Vulkan for that server. Keep the terminal
open while making requests, then press Ctrl+C there to stop the server.
Do not start a second server if another Ollama instance is using port 11434.

The entry points require explicit permission via `--allow-model`:

```powershell
& "./.venv/Scripts/python.exe" brief_to_req.py --allow-model --runs 3
& "./.venv/Scripts/python.exe" run_analyst.py --allow-model
```

The first command makes three requests sequentially, records the actual
responses in `robot_requirements.txt`, and reports whether their text is
identical. Inspect the responses for meaning as well: identical wording alone
does not establish correct requirements.

The second command makes one request and saves only a result that passes
validation. Invalid JSON, missing or extra keys, invalid actions, and unsafe
boolean values are rejected rather than silently repaired. The `goal` text
must still be reviewed for fidelity to the brief; type checks cannot prove
its meaning is correct.

## Submission

The submission repository must be named `scse_agentic_se_AZSMDH`.
Include the three Python files,
`brief.txt`, the genuine `robot_requirements.txt`, and the genuine
`artifacts/requirements.json`, together with the supporting files.

The supplied instructions say to submit only the repository link to Moodle
by September 23, midnight. Check Moodle for the precise deadline and time zone.
