---
name: assignment
description: Runs one professor assignment through the agent pipeline (scout, plan, approval, engineer, tester, auditor, human benchmark, analyst) using agent_runs/ handoff files. Requires an approved docs/PARADIGM.md (run /onboard first).
disable-model-invocation: true
---
Run the assignment given in the arguments (a run folder, or a request to
start one) through the handoff contract in `agent_runs/README.md`. You are
the orchestrator. Update `log.md` after every step (agent, date, outcome,
audit round, sources cited, what was caught).

**Precondition.** `docs/PARADIGM.md` exists and has
"Approved by Sebastian: [x]". Otherwise stop and say to run `/onboard`.

**Cite the source of every solution** (G6). Whenever you propose or report a
solution (in `02_plan.md`, in a STOP message, in the close summary), name
what it came from: a numbered source in `01_brief.md` (`[n]`, with authors
and year), a CLAUDE.md rule (G1–G8, G9+), an audit finding (`05_audit.md`
round and item), `docs/PARADIGM.md` or `docs/DATA_PROFILE.md` (section and
value), the code it follows (`path:line`), or Sebastian's request. If a
choice rests only on your own reasoning, mark it `[own]` with the reason.
Never cite from memory something nobody opened.

1. **Set up.** If the run folder does not exist, create
   `agent_runs/<YYYY-MM-DD>_<slug>/`, copy the `*.md` files from
   `_templates/` (not the `onboarding/` folder), and fill `00_assignment.md`
   with the request verbatim. If it exists, use its `00_assignment.md` as is;
   it must be `Status: READY`.
2. **Brief.** If the request involves a method the project has not used yet
   (always true for the first assignment), ask the literature-scout for
   `01_brief.md`. Otherwise note "skipped" in the log.
3. **Plan.** Write `02_plan.md` yourself after reading the brief, the
   paradigm, the profile and the code it touches. Name the branch and its
   base (`main` unless the plan explains why). Fill the "Source" column for
   every row, the G1 unseen-sample argument for any evaluation protocol, the
   tests with known answers, and "What Sebastian will run" with runtimes.
   **STOP** and tell Sebastian the plan is ready. Continue only when it has
   "Approved by Sebastian: [x]" and "Status: READY".
4. **Implement.** Ask the pipeline-engineer, naming the run folder.
5. **Test.** Ask the synthetic-tester, naming the run folder.
6. **Audit.** Ask the methods-auditor, naming the run folder.
   - FAIL: send the engineer back with `05_audit.md` (fix round), then tester
     and auditor again. After two failed rounds set the run BLOCKED and stop.
   - A mistake that fits no G rule: write the incident in `log.md` and
     propose a new rule (G9, …) to Sebastian. Do not add it yourself.
7. **STOP for the real run.** Show Sebastian the exact commands from the
   plan's "What Sebastian will run" and wait until he drops the outputs in
   the run folder. Never run them yourself.
8. **Results.** Ask the results-analyst for `06_results.md`.
9. **Close.** Summarize for Sebastian: branch, commit, test and audit
   verdicts, the main numbers per participant, the source behind each
   solution, and that merging and pushing are his to do.

At every step, if an agent sets Status: BLOCKED, stop and report why.
