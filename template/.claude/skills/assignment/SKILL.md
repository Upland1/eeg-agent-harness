---
name: assignment
description: Runs one professor assignment through the agent pipeline (scout, plan, plan audit, approval, engineer, tester, auditor, real runs, analyst) using agent_runs/ handoff files. Requires an approved docs/PARADIGM.md (run /onboard first).
disable-model-invocation: true
---
Run the assignment given in the arguments (a run folder, or a request to
start one) through the handoff contract in `agent_runs/README.md`. You are
the orchestrator. Update `log.md` after every agent call (agent, date,
outcome, audit round, sources cited, tokens and wall time from
`cost.jsonl`, what was caught).

**Precondition.** `docs/PARADIGM.md` exists and has
"Approved by Sebastian: [x]". Otherwise stop and say to run `/onboard`.

**Cite the source of every solution** (G6). Whenever you propose or report a
solution (in `02_plan.md`, in a STOP message, in the close summary), name
what it came from: a numbered source in `01_brief.md` (`[n]`, with authors
and year), a CLAUDE.md rule (G1–G16, G17+), an audit finding (`02b_plan_audit.md`
or `05_audit.md` round and item), `docs/PARADIGM.md` or `docs/DATA_PROFILE.md`
(section and value), the code it follows (`path:line`), or Sebastian's
request. If a choice rests only on your own reasoning, mark it `[own]` with
the reason. Never cite from memory something nobody opened.

**Contacts with Sebastian** (G16). Before any question: inputs in full,
documents in the data folder, documentation the inputs point to, a
measurement. Log every contact in `human_contacts.md` before sending it,
with the sources checked and a proposed category; Sebastian confirms it.
Batch: one message per STOP, everything he must decide in it.

1. **Set up.** If the run folder does not exist, create
   `agent_runs/<YYYY-MM-DD>_<slug>/`, copy the `*.md` files from
   `_templates/` (not the `onboarding/` folder), and fill `00_assignment.md`
   with the request verbatim. If it exists, use its `00_assignment.md` as is;
   it must be `Status: READY`. `git status` must be clean; if approved docs
   are uncommitted, commit them first (on a branch, by explicit path).
2. **Brief.** If the request involves a method the project has not used yet
   (always true for the first assignment), ask the literature-scout for
   `01_brief.md`. Otherwise note "skipped" in the log.
3. **Plan.** Write `02_plan.md` yourself after reading the brief, the
   paradigm, the profile and the code it touches. Name the branch and its
   base (`main` unless the plan explains why). Fill the "Source" column for
   every row, the G1 unseen-sample argument and the G13 exchangeability unit
   for any evaluation or resampling, the checks frozen before real data
   (G10, G12, G14), the tests with known answers (with a false-positive-rate
   test for every test statistic), and "What Sebastian will run" with
   runtimes.
4. **Plan audit.** Ask the methods-auditor for `02b_plan_audit.md`, naming
   the run folder. On FAIL, revise the plan (`## Revision N` at its end) and
   ask for the next round. After two failed rounds, stop and show Sebastian
   both files.
5. **STOP for approval (one message).** Show the plan, the plan-audit
   verdict and its non-blocking notes, and every decision Sebastian must
   make. Continue only when `02_plan.md` has "Approved by Sebastian: [x]" and
   "Status: READY".
6. **Implement.** Ask the pipeline-engineer, naming the run folder.
7. **Test.** Ask the synthetic-tester, naming the run folder.
8. **Audit.** Ask the methods-auditor, naming the run folder.
   - FAIL: send the engineer back with `05_audit.md` (fix round), then tester
     and auditor again. After two failed rounds set the run BLOCKED and stop.
   - A mistake that fits no G rule: write the incident in `log.md` and
     propose a new rule (G17, …) to Sebastian. Do not add it yourself.
9. **Real runs.** Commands from "What Sebastian will run" that take under
   about 10 minutes on CPU, you run yourself after the audit PASS, and log.
   Longer or GPU runs: show Sebastian the exact commands and wait until he
   drops the outputs in the run folder. Every output is a versioned folder
   (G9). If an earlier run of the same pipeline exists, run
   `python -m eegharness.compare_runs --a <old> --b <new> --out <run folder>/regression`
   and log its exit status.
10. **Results.** Ask the results-analyst for `06_results.md`.
11. **Close.** Summarize for Sebastian: branch, commit, test and audit
    verdicts, the main numbers per participant, the source behind each
    solution, the totals from `cost.jsonl`, the contacts per category from
    `human_contacts.md`, and that merging and pushing are his to do.

At every step, if an agent sets Status: BLOCKED, stop and report why.
