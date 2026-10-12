# Saved Results

[Project overview](../README.md) | [Integration guide](../docs/INTEGRATION.md)

## Current integration result

The accepted run is `20261010T131220778018Z`, recorded on 10 October 2026.
The reports below describe its revised round, not a new run performed when
opening this repository.

| File | Contents |
| --- | --- |
| [integration_latest.json](integration_latest.json) | Pointer to the accepted run |
| [integration_audit.json](integration_audit.json) | Saved-evidence audit result |
| [test_report.json](test_report.json) | Generated test results and negative control |
| [simulation_report.json](simulation_report.json) | Decisions for all 64 sensor states |
| [simulation_review.json](simulation_review.json) | Review of the logical simulation |
| [irsim_benchmark_report.json](irsim_benchmark_report.json) | Measured results for all four worlds |
| [benchmark_review.json](benchmark_review.json) | Benchmark review and measured flags |
| [integration_visual_checks.json](integration_visual_checks.json) | Recorded visual checks |

Later implementation fixes are listed separately in
[maintenance/source_changes.json](maintenance/source_changes.json).
The historical run and its snapshots remain unchanged. New execution attempts
write `integration_last_attempt.json`; only an accepted publication replaces
`integration_latest.json`. See the [maintenance notes](../docs/maintenance-20261013.txt).

## The complete run

Start with the [trace](integration_runs/20261010T131220778018Z/trace.log) for
the sequence of executed stages, or the [run manifest](integration_runs/20261010T131220778018Z/run.json)
for the saved status. The [initial round](integration_runs/20261010T131220778018Z/round_0/)
and [revised round](integration_runs/20261010T131220778018Z/round_1/) each contain
the exact model exchanges, navigation module, generated tests, reviews and
four simulation workspaces. Each workspace retains its measured positions,
report, plot and animation.

The `mutation_control` folders deliberately test a wrong STOP-only policy.
Their 56 assertion failures per round are expected evidence that the tests
detect incorrect actions. The actual policy passed all 64 cases per round.

Source snapshots and simulation workspace copies are kept because
`verify_integration.py` checks their contents against the executed results.
Seven failed development runs and a preliminary baseline are archived outside
the working repository and remain in Git history at commit `4a2df3c`.
Only the accepted integration run is included in the current checkout.

## Earlier stages

[testing_audit.json](testing_audit.json) and
[navigation_verification.json](navigation_verification.json) summarize the
earlier Testing-stage checks. The accepted requirements, plan and original
code remain in this directory with their Analyst, Planner and Developer
exchange folders. `baseline`, `execution`, `testing_runs`, `testing_offline`
and `bug_checks` retain the evidence referenced by those earlier audits.

Historical audit records preserve the paths used when they were recorded.
Their explanatory documents now live in [docs/history](../docs/history/TESTING_README.md),
and the teacher PDFs are in [docs/instructions](../docs/instructions/).

New local benchmarks belong in `local_benchmarks/`. Both that directory and
new integration run folders are ignored by Git until deliberately reviewed;
do not replace the submitted evidence with an unfinished experiment.
