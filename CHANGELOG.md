# Changelog

## 0.4.0 — unreleased (tag after the P300 Stage-2 run ends and its suite has run once; spec §0 D3)

Applies Sebastian's pipeline to any EEG study (spec: `docs/v0.4_spec_draft.md`, decisions §0).

- New vendored package `eegpipe` (ported from the P300 project's `p300/ssvep-methods`, code
  @ cd5db15, tests @ d833264, and from mas-ssvep-eeg-xai v1.0.4 @ f725369), generalised to k
  classes (D5) with 5-class known-answer tests:
  `filtering`, `gates` (span and window gates between exchangeable units, unit-wise fallback),
  `epochs` (adapter event table -> retained epochs), `dataset`, `folds` (the P300 dealing,
  bitwise; optional class balance), `cca`, `classical` (10-model suite, strict parameter
  tables), `evaluate` (k-class metrics, per-stratum permutation tests for unit-target and
  unit-label schemes, restricted draws so every training fold keeps every class),
  `networks` (EEGNet, ShallowConvNet, the trainer; same-class mixup and shift added),
  `network_input`, `phase`, `connectivity` (declared two-class contrast; `nbs.pair_by`),
  `graphstats` (BH-FDR, NBS), `graph` (edge-gated GNN), `paired` (exact Wilcoxon / Pratt, sign
  test, HL bootstrap, Holm, verdicts), `settings` (validator, profiles `erp` and `ssvep`),
  `runner` (part runner, label-free selection, frozen stage runner with retry and provenance
  rules, confirmatory collect), `ssvep` (continuous filter banks with an IIR span gate, FBCCA,
  FBCSP, CCNN, DualBranchFusionCNN with channels by name).
- Rules G24 (the library is configured, never edited) and G25 (confirmatory runs only from a
  frozen commit); the guard protects `eegpipe/` like `eegharness/`; `new_project.py` vendors it.
- New `/apply-pipeline` skill and `agent_runs/_templates/apply_pipeline/`; PARADIGM.md gains
  "Pipeline settings this study needs"; plan-audit and audit templates gain G24/G25 rows.
- Gaps found by the ssvep-apply plan audit, fixed with known-answer tests that fail on df717c2
  (`kit_tests/test_eegpipe_v04_gaps.py`): FBCSP has its own bank (`ssvep.filterbank.fbcsp_bank`; the
  union input holds both banks, `f1.fbcca.n_bands`, checked by the validator); FBCCA references
  combine several response multiples (e.g. [1, 2] for on-off and checkerboard runs) and drop
  harmonics at or above Nyquist; the ssvep profile's F1 primary is the cited flagship
  `fbcsp+fbcca`; the network input window may start after the event; `cv_network` reports
  `train_ba` on the un-augmented training fold (G18). Found by the ssvep-apply development run:
  `fbcsp+fbcca` registers the SSVEP steps in a spawned worker (it failed with `permutation.n_jobs` > 1).
- Network parts record torch's version and build (`build`: "cuda X.Y" or "cpu", `cuda_available`) in
  `results.json["torch_environment"]`; a configured CUDA device without CUDA still stops the part (no CPU fallback).
- Two lessons from the P300 Stage-2 run (2026-11-09), fixed with known-answer tests that fail on 01d9573
  (`kit_tests/test_eegpipe_stage2_lessons.py`): a file with 0 used epochs (every epoch rejected) no
  longer stops the per-file permutation step (a unit with no retained epoch takes any shuffled target)
  and gets a `per_file_tests.csv` row with status `no_used_epochs`, BA NaN, entering Holm as p = 1 with
  the family kept at every file (P300 D-018); a file whose used epochs miss a class (BA NaN) is
  `missing_class`, also entered as p = 1 (P300 DEV-2), and `permutation_p` refuses a NaN observed value
  instead of returning the minimum p. The file count comes from the assembled files (`n_files`,
  `evaluate.n_strata`), never max(file_idx) + 1, and the null's width is checked (files + pooled
  column; one column per stratum in `per_stratum_tests`). New columns: `status`, `n_used_epochs`,
  `perm_p_entering_holm`, `holm_m`; `per_file.csv` has a row (n = 0) for an empty file.
- Kit tests: 402 passed (1 CUDA test skipped on CPU); torch, scipy and scikit-learn join the kit
  test environment. `eegharness` 0.4.0: version number only.

## 0.3.1 — 2026-11-06

- Guard: `blocklist.json` may list `"dirs"`, absolute folders or files treated like the
  evaluation folder. A path inside one is blocked, and so is any search or listing (grep -r,
  rg, find, tree, du, ls with or without -R, the Grep and Glob tools) whose resolved starting
  folder contains one, including a search with no folder operand run from such a folder.
  Closes the gap where `grep -r x data/raw/..` read every sibling of the recordings' folder.
  Known-answer tests: `kit_tests/test_guard_blocked_dirs.py` (38), including the v0.3.0
  behaviour as the buggy variant.
- Compute limits template: 120 min per CPU and per GPU job; longer work split into resumable
  parts that each fit the limit (G22 text and the `compute-jobs` checklist updated).
- `eegharness` 0.3.1: version number only (it follows the kit); no code change.

## 0.3.0 — 2026-11-06

Support for pipelines with classical ML, neural networks, phase connectivity with
permutation/FDR/NBS statistics, and graph neural networks. Spec: `docs/v0.3_spec_draft.md`
(sources: an earlier SSVEP study's rules and pitfalls, lessons L27–L28).

- Rules: G2 amended (a test for a fix or index layout fails on the plausible buggy
  variant); new G17 (training and preprocessing inside the training data; test transforms
  computable without test labels; inherited defaults listed and set — L28), G18 (seeds,
  at least 3, spread, paired A/B, train accuracy, device provenance), G19 (significance
  budget: fixed primary configurations, test, alpha, family-wise correction; development
  data kept out of the confirmatory test — L28), G20 (connectivity estimators and their
  statistics), G21 (filter continuous data, metadata from the file, channels by name),
  G22 (long and GPU jobs: limits per project in `docs/COMPUTE.md`; the orchestrator runs
  CPU and local GPU jobs within them after a committed smoke test; longer or remote jobs
  go to Sebastian; resumable folds), G23 (derivations through committed, tested tools; no
  READY handoff citing a path outside the repository — L27).
- Method checklists (skills) `deep-learning`, `connectivity`, `compute-jobs`, read by the
  agents when a plan uses those methods; no new agents.
- Workflow: plan template gains training/defaults, significance-budget and "Runs" sections;
  plan-audit and audit templates gain G17–G23 rows; the methods-auditor adds a results check
  (`## Results check` in `05_audit.md`) after `06_results.md`; results template reports seed
  spread and primary vs exploratory comparisons.
- Tools (`eegharness` 0.3.0): `splits` (unique group ids across participants, grouped and
  stratified k-fold, leave-one-group-out, grouped inner validation, `check_no_leak`),
  `permutation` (unit-level permutation keeping units whole and group sizes, observed
  labelling in the null), `chance` (exact binomial chance level) — core, numpy only;
  `seeds` (fold seeds, seeding with optional torch, seed summary) and `folds` (resumable
  fold store refusing a changed configuration) — torch optional; provenance records
  torch's device and determinism settings when torch is imported.
- Tests: 211 kit tests, including a false-positive-rate test showing unit-level permutation
  at the nominal rate and window-level permutation inflated on clustered data.

## 0.2.0 — 2026-11-05 (frozen for evaluation round 2)

From the first project's lessons L1–L26 (general ones only).

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
  without a reader; `read_document.py` prints them (.txt .md .pdf .docx .odt .rtf
  .csv .xlsx …) and refuses recordings; it is the paradigm-analyst's only shell
  command, and its Read/Grep tools open nothing under `data/`.
- Hooks: guard tokenizes shell commands (the first project's 9 false blocks pass,
  real violations still block, also inside `bash -c` and heredocs run by a shell);
  `log_cost.py` logs tokens and wall time per agent call and per orchestrator
  session (harness arm). `cost_report.py` (kit) computes the same numbers for any
  project, both arms, from its transcripts after the run; the control arm gets no
  cost hook, so its setup and behaviour do not change.
- Guard resolves every path before checking it (L26): relative paths, `..`, `cd`,
  symlinks, quotes, globs, `~`, variables set in the command, `--option=path`, and
  string literals in heredocs and `-c` code, for shell commands and file tools, in
  both arms. Recursive tools aimed at a folder containing the evaluation folder are
  blocked. Round 1 had let `cat ../../<eval folder>/...` through from inside a project.
- `new_project.py`: vendors `eegharness/`, adds `tests/conftest.py`, commits the
  project skeleton (with `inputs/`) so agents start from a clean tree.
- End-to-end check (2026-11-05): `/onboard` headless on a synthetic 3-participant
  auditory oddball, scratch project only. Reached the approval stop with one human
  contact; the analyst read the lab-log .docx through `read_document.py` and asked
  nothing it answered. Two defects found and fixed before release: the cost
  summary counted resumed agents once per round (now once per agent), and the
  auditor's read-only `sed -n <lines>p` was blocked (now allowed).
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
