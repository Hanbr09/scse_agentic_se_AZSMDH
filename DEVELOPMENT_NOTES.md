# Planning and Development Notes

This is the historical record of the September 23 stage. The Testing extension
is documented in TESTING_NOTES.md; the former artifacts are in artifacts/baseline/.

## From requirements to a decision policy

The original brief describes a robot with three obstacle signals and
optional goal-direction information. Its structured requirements retain
four permitted actions and the two safety flags. We kept that existing
artifact rather than writing a different set of requirements for this stage.

The Planner receives only the four-field requirements object. Its system
prompt defines the interface and the decision vocabulary, while its user
message contains the artifact. Neither the original Analyst conversation
nor its preliminary plain-text replies are sent downstream.

The plan has three fields: `strategy`, `decisions`, and `stop_condition`.
Each decision has a `condition` and an `action`. Named conditions make the
guards explicit and allow the program to check their meaning, rather than
accepting arbitrary sentences such as "move if appropriate."

There are three safe-goal rules, three clear-direction fallback rules,
and one all-blocked stop rule. Validation checks the condition/action
pairs, uniqueness, and ordering. All safe-goal rules must precede fallback
rules, and stopping is last. The Planner may choose any ordering of the
three fallback directions. For this run it chose front, left, then right.
That choice resolves an unspecified case in the brief; it is a design
decision, not a claim that the customer mandated a particular order.

The Developer receives only the validated plan. The function signature and
the meaning of the condition names are defined in its system prompt. It
produces ordinary Python source, not a JSON object containing executable
text and not a Markdown code block.

## Validating generated code

Syntax alone is insufficient. Before loading generated code, the validator
uses Python's AST to require one function with the agreed signature and a
small, bounded set of decision-logic constructs. It rejects imports, calls,
loops, decorators, attribute access, and top-level execution. This is a
deliberately narrow interface for this exercise, not a general-purpose
sandbox for arbitrary Python programs.

The accepted function is then checked over all eight obstacle combinations
and all four goal values (`None`, `AHEAD`, `LEFT`, `RIGHT`). The checks verify
the allowed action, obstacle avoidance, safe-goal preference, stopping only
when blocked on all three sides, and agreement with the selected plan.
The eight cases with no goal are also called with the optional argument
omitted. Unexpected return values or exceptions cause rejection.

The code is saved only after those checks pass. File replacement is atomic,
so a rejected response or a write failure does not overwrite the previous
artifact. There is no fallback that substitutes hand-written navigation
code for a failed model response.

## Recorded run

On September 23, 2026, `qwen2.5:3b` generated the plan and then the code in
two sequential requests. Both were accepted on their first attempt. The
runtime used Python 3.10.11, Ollama 0.34.2, and the `ollama` Python package
0.6.2. Inference used two CPU threads, no GPU layers, a 2048-token context,
temperature 0, and a 768-token output limit. The model unloaded after each
request and the temporary server was stopped after verification.

The raw exchanges are in `artifacts/planner_runs` and
`artifacts/developer_runs`. Each records the actual prompts, options, model
reply, and response metadata. `artifacts/execution/20260923-142409` contains
the original server logs and the runtime summary. Startup warnings about
no usable GPU are expected for this intentionally CPU-only run; the log
confirms CPU inference and two inference threads.

`verify_pipeline.py` checks that the plan equals a recorded JSON response,
the code equals a recorded text response, and each user message contains
exactly its preceding artifact. The verification report includes the file
hashes and the outcomes of all 32 navigation scenarios. Text hashes normalize
line endings to LF so Windows and other Git checkouts agree. These consistency
checks make accidental manual changes visible; the model text was not
rewritten after generation.

The 58 offline tests exercise program behavior with explicitly identified
fixtures. They are separate from the two genuine Qwen requests and the
32-case check of the actual generated function. Results do not establish
performance on a physical robot, route completion, or support for input
types outside the documented interface.

## Source and continuity

The teacher repository was cloned and its history was merged into the
existing group project before completing the starter files:

- Requirements Engineering baseline: `cd69057`.
- Plan and Develop source: `prabhatram/scse_plan_and_develop`, commit
  `8d73372049699eda1814cb87b88cd5c4fa186853`.
- `SCSE '26 - Project Instructions - Plan and Develop.pdf` is unchanged.
- `brief.txt`, `robot_requirements.txt`, `artifacts/requirements.json`, and
  `observations.md` retain their earlier content.

The shared Qwen helper was extended to record exchanges, reject truncated
output, and impose an output limit. The Analyst interface and the earlier
results remain intact. The imported macOS `.DS_Store` metadata is excluded
because it is not part of the coursework.
