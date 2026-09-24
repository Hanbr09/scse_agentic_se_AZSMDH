# Testing the navigation handoffs

## Continuing the existing implementation

The starting revision is 8a5bd4884e9c12d7e0f6a81b43b2274a124e2644.
That version uses seven ordered decisions and a four-argument choose_action
function. The Testing stage keeps that helper's syntax tree unchanged.
A new decide_next_move(state) translates the six dictionary fields into
the helper's arguments. All external examples and behavioral tests call
only this public entrypoint.

There is no goal-direction value when all goal flags are false. Multiple
flags are handled deterministically by considering clear indicated goals
ahead, left, then right. The original brief does not specify this tie-break;
it is recorded here so ambiguous states have a testable interpretation.

## What each test establishes

The three real-agent scripts share the normal runners instead of bypassing
validation or manufacturing accepted replies. The Analyst starts with the
original brief. Planner and Developer each receive only the previous
validated artifact as the user message. The Developer's system prompt also
contains this group's original helper and the new adapter contract.
Every completed reply is retained before acceptance checks.

The behavioral suite uses a fixed action table, independent of the model's
implementation and the validator's oracle. Eight tests each cover eight
obstacle combinations, giving all 64 combinations of the six boolean fields.
Separate cases cover the teacher's example and changing sensor values.
Each matrix case also checks that the caller's dictionary is not modified.
The unittest method count is therefore different from the scenario count.

The intentional bug changes only the clear-left fallback to return RIGHT.
The experiment first checks an unmodified baseline, then checks the faulty
file, then restores the exact original bytes and checks again. An assertion
about the action must fail during the faulty run; a parsing/import failure
does not count as detecting this bug. The test expectations stay unchanged
throughout this experiment.

## Model output review

The first new Planner response described the fallback as proceeding without
turning, although its rule list allowed turns. A schema-constrained strategy
sentence now states the retained policy unambiguously. Its structured rules
still remain the group's original seven condition/action pairs.

The first Developer response omitted the original helper and treated state
as a sliced sequence rather than a dictionary. Validation rejected it before
execution or replacement. The prompt was clarified to require the complete
module and dictionary-key access. These earlier replies remain in the run
folders; they are not presented as accepted final results.

## Evidence and limits

The accepted Testing session is recorded on September 24, 2026. Analyst,
Planner and Developer completed sequentially with qwen2.5:3b on CPU using two
threads. The service was closed after both the rejected and accepted sessions.
Python 3.10.11 and 3.12.0 each passed 76 test methods: 66 infrastructure tests
and 10 behavioral methods. Eight of the behavioral methods contain the 64
matrix states. The deliberate LEFT-to-RIGHT bug caused six failing subcases.
The original bytes were restored and all behavior tests passed again.

Raw records are organized by purpose:

- `artifacts/analyst_runs/`, `planner_runs/`, `developer_runs/`: actual model exchanges.
- `artifacts/testing_runs/`: real-agent script output, server logs and cleanup status.
- `artifacts/testing_offline/`: full offline test output on both Python versions.
- `artifacts/bug_checks/`: before, faulty, and restored behavior-test output.
- `artifacts/testing_audit.json`: source revision, required-file hashes and final checks.

The final navigation verification matches the brief, requirements, plan,
and code to their recorded real Qwen exchanges. It checks CPU-only request
options and all 64 sensor states. Generated code has identical copies in
generated/, artifacts/, and the legacy root location because the PDF uses
two different output paths and older project tools used the root path.

Offline regression tests use clearly identified synthetic fixtures and do
not count as model runs. Testing results apply to complete dictionaries of
six booleans. They do not establish physical-robot behavior, whole-route
completion, malformed sensor support, classroom attendance or Moodle submission.
Detecting one intentional error is evidence of useful tests, not proof that
all possible software defects have been eliminated.
