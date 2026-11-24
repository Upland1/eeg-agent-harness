---
name: apply-pipeline
description: Applies the supervisor's pipeline (eegpipe) to this study - adapter, settings from PARADIGM.md, plan, audit, development run, freeze, confirmatory stage, paired statistics, results - through agent_runs/ handoff files (G24, G25). Requires an approved docs/PARADIGM.md and a tested reader (run /onboard first).
disable-model-invocation: true
---
Run "apply the pipeline" for the request in the arguments, through the handoff contract in
`agent_runs/README.md` and the templates in `agent_runs/_templates/apply_pipeline/`. You are
the orchestrator. Update `log.md` after every agent call; log every contact with the supervisor in
`human_contacts.md` (G16) before sending it. Cite the source of every choice (G6).

**Agents.** Run each agent in the foreground and wait for its handoff before the next step or the end of the turn; a subagent still running when the turn ends is stopped.

**Audit rounds (L45, L47).** The auditor labels each required fix *code/test* or *wording*. A
failure whose fixes are all wording gets one fix round, limited to the named lines and checked by
diff. That round does not count toward the two-round limit. The run log records each round's tokens
and wall time as differences of running totals. Cost figures come only from `cost_report.py`,
`run_cost.py` or the `log_cost.py` summary, never from adding up rows. A suggested wording in a
required fix is held to G7/G26: any number in it is quoted from printed output with its line, or it
gives none. A failure on text the auditor proposed is recorded as an auditor error and is not
counted as a round against the agent. An auditor error is not counted against the agent, but every
round counts toward a hard limit of 4 rounds per step, whoever caused the failure; at the limit,
stop and ask the supervisor. Per-round figures: `python .claude/hooks/log_cost.py --rounds
agent_runs/<run>` (differences of the running totals); the kit's `cost_report.py` and `run_cost.py`
give the reported totals after the run.

**What is fixed and what is decided here.** The methods are the supervisor's, vendored in
`eegpipe/` (G24): never edited, never re-implemented. What this run decides, and justifies, is
how they meet THIS study: the adapter (recording -> events -> labels and units), every
setting in `configs/pipeline.json` with its source, the families and primaries, the
development data, the confirmatory selection rule and the statistics budget (G19).
Read `eegpipe/__init__.py`, `eegpipe/settings.py`, `eegpipe/runner/__init__.py` (adapter
contract) and the module of every family the plan enables before writing anything.

**Preconditions.** `docs/PARADIGM.md` has "Approved by the supervisor: [x]" and a section "Pipeline
settings this study needs" (classes, exchangeable unit, label rule, timing and windows,
frequencies or bands, contrast for connectivity, development data, participants reported
separately), and the reader has passing tests. Otherwise stop and say what is missing.

A. **Adapter** (pipeline-engineer -> synthetic-tester). `adapter.py` at the project root with
   `dataset_parts`, `read`, `events` (and `condition_of`, `eligible` if needed), returning the
   event table of `eegpipe.epochs` (onset, unit, label, unit_start, unit_end, code; one
   `unit_target` per unit when labels come from a per-unit target). Tests: a synthetic
   recording through the REAL reader gives the planted events; the label rule of PARADIGM is
   reproduced exactly; units never cross; unit ids unique across files; fs and channel names
   from the header (G21). Handoffs `03_changes.md`, `04_tests.md`.

B. **Settings.** Start from the profile that matches the PARADIGM design family
   (`eegpipe.settings.from_profile`) and replace every paradigm value by the PARADIGM one;
   `sources` gives each key's source; `eegpipe.settings.validate(cfg)` must pass; the
   unconfirmed profile defaults it returns go into the plan, each confirmed or changed with a
   reason (G17 i). Paste `eegpipe.settings.table(cfg)` into the plan.

C. **Plan** (pipeline-engineer, `02_plan.md` + the section of
   `_templates/apply_pipeline/02_plan_pipeline.md`): families enabled; one primary per family;
   comparator; development data (named); confirmatory selection rule (label-free, seeded);
   Holm family = the primaries; parts and expected runtime of each (G22: CPU and GPU parts
   within `docs/COMPUTE.md`, longer ones as exact commands); what is exploratory.

D. **Plan audit** (methods-auditor, `02b_plan_audit.md` with the rows of
   `_templates/apply_pipeline/02b_audit_rows.md`): G1-G27; every profile default confirmed;
   unit and strata argued (G13); development and confirmatory data disjoint (G19); label
   scheme matches PARADIGM. FAIL -> back to C ("Audit rounds" above). **STOP: the supervisor approves the plan and the
   settings.**

E. **Gates and smoke** (orchestrator): the part runner on the development data part
   (`python -m eegpipe.runner.methods --config <dev part config> --out outputs/dev`), CPU
   parts first, then one GPU part with `max_epochs` reduced in a smoke copy of the settings;
   any failing window gate stops the run (G1). Report gates and timings.

F. **Development run** (orchestrator, within COMPUTE.md): every enabled part on the development
   data only; numbers are labelled "development" in every handoff; fixes are logged; nothing
   from here is ever reported as confirmatory.

G. **Freeze.** `python -m eegpipe.runner.select --config configs/pipeline.json --out
   configs/selection`; set `stage.selection_output` to that folder and `stage.name` to
   "confirmation"; commit settings, selection and code on the run branch.
   **STOP: the supervisor approves the freeze** (commit hash, selection, parts plan from
   `eegpipe.runner.stage --dry-run`).

H. **Confirmatory stage** (orchestrator runs the parts within COMPUTE.md, in the background,
   waiting for each to finish; the supervisor runs the rest as exact commands):
   `python -m eegpipe.runner.stage --config configs/pipeline.json --out outputs/stage2
   --parts cpu` then `--parts gpu`. Never edit tracked files while it runs. A provenance stop
   goes to the supervisor with the log; rerun only with `--rerun-after-provenance` after his
   decision (logged).

I. **Statistics** (results-analyst): `python -m eegpipe.runner.collect --stage <root> --out
   outputs/stage2_stats`; an incomplete root only with `--interim` and the stamp in every
   table. Every number in a handoff comes from these outputs (G7, G11, G23).

J. **Results** (results-analyst `06_results.md` with `_templates/apply_pipeline/06_results_pipeline.md`;
   methods-auditor results check in `05_audit.md`): per-participant tables (G3), seed spread
   (G18), the paired tests with path, HL and interval, Holm and verdict, failures and pending
   parts, exploratory results apart, and the comparison the supervisor asked for in the request.

Close: summary in `log.md` (tokens, time, contacts, what was caught) and a one-message report
to the supervisor with the verdicts and the output paths.
