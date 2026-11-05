# Changelog

## 0.2.0 — 2026-11-?? (frozen for evaluation round 2)

From the first project's lessons L1–L25 (general ones only).

- Rules: G9–G11 ported from the first project; new G12 (known-answer tests before
  the first real-data run, false-positive-rate test on noise for every test
  statistic), G13 (exchangeability unit; nulls can draw the observed labelling),
  G14 (quality, rejection and label claims per participant and session, with
  comparison set and absolute measures), G15 (committed files cite only committed
  things), G16 (use every written source before asking a human).
- Workflow: plan audit (`02b_plan_audit.md`) by the methods-auditor before approval;
  one batched approval per stop; human-contact log `human_contacts.md` (agent
  proposes the category, Sebastian confirms); measurement requests and a frozen,
  per-participant label sanity check in onboarding; approved docs committed at
  approval; short CPU runs by the orchestrator; rejection section required in results.
- Agents: methods-auditor gets a read-only shell; paradigm-analyst reads documents
  in the data folder and documentation the inputs point to, verifies input identity,
  writes measurement requests; tester builds its own config, uses realistic inputs,
  adds false-positive-rate tests; engineer runs on real data only after tests pass;
  no un-awaited background work.
- Tools: `eegharness` package vendored into each project (`new_output_dir`:
  versioned output folders with provenance; `compare_runs` regression check);
  profiler lists written documents in the data folder as documents, not as files
  without a reader.
- Hooks: guard tokenizes shell commands (the first project's 9 false blocks pass,
  real violations still block, also inside `bash -c` and heredocs run by a shell);
  `log_cost.py` logs tokens and wall time per agent call and per orchestrator
  session, in both arms.
- `new_project.py`: vendors `eegharness/`, adds `tests/conftest.py`, commits the
  project skeleton (with `inputs/`) so agents start from a clean tree.
- Not in 0.2: release gate for numbers shown outside the project (needs a
  number-tracing tool).

## 0.1.0 — 2026-11-02

First version, derived from the P300 project setup of 2026-11-01 with all
paradigm content removed.

- General rules G1–G8; "When you don't know" (UNKNOWN, questions only a human
  can answer, contamination flags).
- Six agents: paradigm-analyst (new), literature-scout, pipeline-engineer,
  synthetic-tester, methods-auditor, results-analyst; all read
  `docs/DATA_PROFILE.md` and `docs/PARADIGM.md` instead of fixed data facts.
- Skills: `onboard` (new), `assignment` (requires an approved PARADIGM.md),
  `cite-sources`.
- Deterministic profiler with a reader registry (MNE formats + per-project plugins).
- Guard hook: recordings read-only, `.harness/` frozen, git safety, auditor
  read-only, evaluation material and blocklist out of reach; control mode.
- `new_project.py`: harness and control arms, frozen-version check for evaluations.
- `kit_tests/`: 14 known-answer tests (profiler, guard, project creation, run isolation, paradigm neutrality).
