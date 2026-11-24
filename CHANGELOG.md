# Changelog

## 0.6.0 — 2026-11-23 (tag v0.6.0 at 446b65c)

BACKLOG L39-L55, approved by the supervisor on 2026-11-23 ("Approved for v0.6: every item marked Rec, as worded,
with these edits and choices"), one commit per item or approved pair, and L56 (below; approved 2026-11-23, added
on 2026-11-24). Known-answer tests in
`kit_tests/test_v06_rules.py`: of the 49 tests for L39-L55, 42 fail or error on b361f81 (the v0.6-dev commit before them);
the other 7 are L50's refusal cases, which pass on both (they guard the widening). Not done (waits): the
`--venv` option of L43.

- Setup: `new_project.py` creates `data/` and `inputs/` in every project (L41); the per-project `.venv` is the
  documented interpreter, printed with its pip command (L43, reduced form); it says that `cpu_working_threads`
  and `memory_max_gb` in `docs/COMPUTE.md` have no default and must be set (L39, L54).
- Rules: new kit rule **G27** (a group statistic takes only estimates that exist at that sample size; L40,
  the cold-pressor project's approved wording); project rules now start at G28. G2 names a default run and the
  full suite (L55). G15 accepts the template's approval box ticked and dated (L48). G22 names
  `cpu_working_threads`, `memory_max_gb` and the pre-batch check (L39, L54, L44). G23: the orchestrator's
  derived numbers come from `eegharness.numbers` or are marked `(hand count, not derived)` (L51).
- Audit rounds (L45, L47) in `/onboard`, `/assignment` and `/apply-pipeline`: fixes labelled code/test or
  wording; a wording-only failure gets one round limited to the named lines, outside the two-round limit; an
  auditor's suggested wording is held to G7/G26 and a failure on it is an auditor error; every round counts
  toward a hard limit of 4 per step, then stop and ask the supervisor; cost per round from running totals
  (`log_cost.py --rounds`), cost figures never from adding up rows. The 05_audit fix table has a Kind column.
- `/onboard` step 0 runs the new `tools/check_inputs.py` (shipped in `.harness/tools/`): no start while
  `inputs/` holds a template placeholder `<...>` or a person's words reported without a verbatim quote (L42,
  L46).
- `eegharness.sources`: the box `Approved by <name>: [x]   Date: YYYY-MM-DD` is a record; ticked without a
  date it is reported as `undated_approval` (L48).
- The methods-auditor's hook allows `python -m eegharness.outputs check` and `python -m eegharness.sources
  check` (read only; no `--record`, no redirect) (L50).
- New `eegharness.compute`: limits of `docs/COMPUTE.md`; the thread check used by
  `eegpipe.settings.validate` (n_jobs or torch threads above `cpu_working_threads`, -1, or the value unset
  are refused; L39); `temps` and `templog` (CPU package and GPU temperature once a minute next to a job
  table; L39); `precheck --parts B --peak-gb G` before each batch: memory_max_gb set, B x peak within it,
  enough available memory, `data/raw` resolves with every profiled file (L54, L44).
- Profiler: `DATA_PROFILE` records where `data/raw` is stored (resolved path, mount point, filesystem,
  device, removable, under /media) (L44; `eegprofile/storage.py`).
- `eegpipe.runner.stage` (L49): every attempt is recorded before its job starts; a part left `running` by a
  killed stage becomes `interrupted`, counts in `n_attempts` and toward `retry.max_attempts`; `n_interrupted`
  in `part_status.json` and `index.csv`. Projects get it when they re-vendor `eegpipe/`.
- `eegharness.outputs check --paths-file F` (one folder per line, spaces kept) and `--record OUT` (the
  result in a versioned folder with provenance and compute time) (L52).
- `eegharness.numbers` (L53): tab-separated files, `glob` selections over many files, `json` fields, `scale`
  (factor or divisor: seconds to hours) and `all_equal`; every file read recorded with its SHA-256. Existing
  specs are unchanged.
- Template `tests/conftest.py` (L55): a `slow` marker, left out of `pytest tests/`, run with `-m ""`. New
  projects only (`--update` keeps an existing conftest).
- Plan audit (L56, approved by the supervisor on 2026-11-23, added to 0.6.0 on 2026-11-24): "Every quantity a plan's
  gate or decision rule uses must be named with the code path and output field that records it; the plan
  auditor checks that the field exists." New plan-template section "Gate and rule inputs"; new
  `tools/check_plan_fields.py` (shipped in `.harness/tools/`; MISSING when the named code does not write the
  field, NEW for code the plan adds, a failure with `--final` in the change audit; `--output` checks a real
  output); the methods-auditor runs it (its hook allows it); rows in the plan-audit, apply-pipeline and change
  audit templates. Known-answer tests `test_v06_rules.py::test_l56_*` (4), failing on 7ad1c35.
- Evaluator tool, not a template rule (commit 61005fc, made from the evaluation session on 2026-11-23): `run_cost.py`
  reports the waits between jobs per phase (gaps of at least `--min-wait-h` hours, default 1, in the union of
  the job intervals, with their suspended part; not compute time), for runs stopped and restarted across
  days (imagined-speech-eeg B_loro batch 01, stopped twice for low memory). Known-answer test
  `kit_tests/test_run_cost.py::test_waits_between_jobs_known_answer`, failing on b361f81.
- Checks on the final 0.6.0 code, commit 25e942c, with no other session using the tree (2026-11-23, 22:32-22:37
  UTC): kit suite 559 passed, 1 skipped, 1 xfailed in 4 min 49 s (kit venv, torch CPU; tree clean before and
  after); `check_install.py` ready in the kit venv (smoke subset 200 passed; it includes the worked example,
  which matches its pinned outputs) and in a fresh venv from `requirements.txt` without torch (195 passed,
  5 skipped; torch WARN). This commit changes only this file and README.md.
- Changed earlier tests to the approved behaviour: `test_eegharness_v05_lessons.py` (the ticked, dated box
  is no longer reported, L48), `test_kit.py` and `test_v05_rules.py` (G1-G27, project rules from G28, L40).

## Unreleased before 0.6.0 (after 0.5.0)

- New `run_cost.py` (evaluator-side, like `cost_report.py`): the cost of a finished run in a versioned
  folder with provenance: agent cost in USD from the headless invocations' cumulative `total_cost_usd`,
  tokens from the transcripts (`cost_report.report`), and CPU and GPU wall time per phase from the job
  wrappers' run logs, minus the laptop's suspend intervals (`journalctl` excerpt). Known-answer tests
  `kit_tests/test_run_cost.py` on the real log formats and job names of ssvep-apply.

## 0.5.0 — 2026-11-15 (tag v0.5.0 at 67defdb)

Lessons L37 and L38 from cold-pressor onboarding, the approved rule wordings (G15, G10, G16, G22, new G26,
Data handling, the workflow skills, the paradigm-analyst), and the release files
(install check, worked example, README). Known-answer tests in
`kit_tests/test_eegharness_v05_lessons.py`, `kit_tests/test_v05_rules.py`, `kit_tests/test_worked_example.py`
and `kit_tests/test_check_install.py`.

- Rules: **G15 amended** (L38, approved by the supervisor on 2026-11-16, applied from v0.5 on, no fixes to
  past commits): an orchestrator's or a human's instruction is quoted in the committed file that relies
  on it; a contact number, a name with a date or an `agent_runs/` path is never the only citation;
  `python -m eegharness.sources check` passes before a commit.
- Rules approved by the supervisor on 2026-11-16 ("Approved, all seven as worded"), with known-answer tests
  in `kit_tests/test_v05_rules.py` that fail on 03c00f6:
  - G22 (L37): every measurement and reporting output records its compute time; the auditor runs
    `python -m eegharness.outputs check` on the outputs a result cites (results check).
  - onboard, assignment, apply-pipeline (L29): run each agent in the foreground and wait for its handoff.
  - G10 (L32): a frozen check states its decision rule, sidedness and the consequence of each outcome;
    otherwise it is descriptive and gates nothing.
  - Data handling (L33): committed files never quote or paraphrase a participant's free text or form
    details; the paradigm-analyst and the auditor check it.
  - New **G26 Evidence must be able to fail** (L34, from cold-pressor's project rule G26): a decision
    citing a test claims exactly what the test asserts; auditor item 9 and an audit-template row. Project
    rules now start at G27; cold-pressor's own G26 becomes the kit's when it moves to 0.5.
  - G16 (L35): only an explicit answer is logged as an answer; placeholders and defaults are "no answer".
  - paradigm-analyst (L36): Edit for `docs/PARADIGM.md` only (guard), no Write once that file is committed;
    new `tools/check_frozen_text.py` (shipped in `.harness/tools/`): a file may only gain lines after a
    committed version; the onboard skill runs it after every revision.
- `eegharness.outputs` (L37): `ComputeTimer`, `record_compute_time`, `record_no_compute`,
  `check_compute_time` and `python -m eegharness.outputs check`. `compute_time` in `provenance.json`:
  wall s, CPU s (process and finished children), device, UTC end; null with `compute_time_reason` when
  nothing is computed; never written by default, recorded once. Recorded by `eegpipe.runner.methods`
  (each stage part; device from the networks settings, else cpu), `eegpipe.runner.select`,
  `eegpipe.runner.collect`, `eegharness.numbers derive` and `eegharness.compare_runs`.
- New `eegharness.sources` (L38): `python -m eegharness.sources check` reports, in git-tracked files
  (vendored `eegpipe/`, `eegharness/` and git's own files skipped):
  - any `agent_runs/` reference;
  - a paragraph citing a human contact without quoting it (at least 3 quoted words or a `>` block quote);
  - a paragraph attributing something to a configured name with an ISO date within 60 characters,
    unquoted; the names come only from the project's local `.claude/harness.json` (`sources.names`,
    none by default) or `--name`; an approval line "Approved by <name>, <date>[, <what>]" is exempt;
  - a names list in a committed `.claude/harness.json`.
- `new_project.py --update` keeps the `sources` section of a project's `.claude/harness.json`.
- New `check_install.py`: Python, the required packages against `requirements.txt`, git; optional
  torch (and its device), `pdftotext`, `claude`; then a smoke subset of `kit_tests` with the worked
  example (about 1 min; `--quick` skips it).
- New worked example `examples/ssvep_synthetic/run_example.py`: a synthetic 5-class SSVEP study run
  through settings → select and freeze → stage → collect → numbers with a cited `results.md`, on CPU in
  about 30 s; outputs pinned (`kit_tests/golden/worked_example_ssvep.json`).
- README: install, quickstart, measured costs (ssvep-apply), limitations, the names list.
- Versions: `VERSION`, `eegpipe` and `eegharness` 0.5.0.
- Still known broken: the `unit_label` case of 0.4.0 (below), unchanged.

## 0.4.1 — 2026-11-10 (tag v0.4.1 at 3233ff4)

MAS's P20 within-subject network protocol in `eegpipe` (the supervisor's decisions 2026-11-10; ssvep-apply D-008/D-009).
Every ported piece is checked bit for bit against MAS's own code, copied verbatim into
`kit_tests/mas_p20_reference.py` from mas-ssvep-eeg-xai @ f725369 (`kit_tests/test_eegpipe_v041_p20.py`).

- New `eegpipe.network_windows`:
  - `iir_network_input`: MAS's broadband filter (Butterworth band-pass and 60 Hz notch, `filtfilt(b, a)` with
    SciPy's default padding) on the continuous record, no resampling. Equal to MAS's `broadband_filter`.
    The leakage gate between units uses the cascade's effective span (impulse response below `span_tol`,
    doubled). If the gate fails, the record is filtered unit by unit.
  - 1 s windows every 0.25 s inside each trial, carrying the trial id (13 in a 4 s trial; MAS has 17 in its
    5 s stimulus).
  - Folds: StratifiedGroupKFold(5, shuffle) over the windows grouped by trial, with no trial on both sides.
  - Fold seed = seed base + fold, for the model, the DataLoader, the augmentation and the inner validation
    split (MAS `nn_sweep` l.117).
  - Trial probability = mean of its windows' probabilities.
  - `EEGNetSSVEP`: exact port of MAS (2,349 parameters at 7 x 256, the same weights and outputs as MAS for
    the same seed).
  - `MasAugmentedDataset`: exact port of MAS `SSVEPAugmentedDataset`.
- `networks.fit_network` takes `augmentation.kind` "mas_p10". With the P20 trainer settings it equals MAS's
  `fit_network` exactly on CPU: split, normalisation, best epoch, losses, predictions.
- The runner runs a network part under P20 when `networks.windows.enabled`:
  - `network_input.kind` "iir_ba";
  - a `results.json["network_protocol"]` section, with a window-folds hash per seed;
  - window BA and accuracy in `pooled.csv`;
  - fold seed, training and validation accuracy and best epoch in `per_fold.csv`;
  - the network input filtering and gate in `gates.csv`.

  The part keeps the study's `epochs_sha256` and `folds_sha256`, so the stage runner's identity check across
  parts is unchanged.
- Settings rules:
  - windows need `networks.cv.scheme` "window_grouped" and `label_scheme` "unit_label";
  - seed bases closer than `networks.cv.n_splits` are refused, because they share fold seeds (G18);
  - an `iir_ba` input must not resample;
  - a `mas_p10` augmentation must name all of its values.
- The ssvep profile now holds MAS's P20 values: windows, grouped folds, no class weights, unweighted
  validation loss, augmentation ON (mas_p10), EEGNetSSVEP with kernel fs // 2, the iir_ba network input, and
  seed bases 20261107, 20262107, 20263107. Correction: 0.4.0 cited `training.py::fit_network` but used whole
  trials, the study folds and augmentation OFF, which matches no MAS network result.
- Correction to `networks.AugmentedDataset` (docstring): it is not MAS's augmentation (order, mixup lambda,
  shift rounding). The P300 golden outputs are unchanged.
- Positive control (the supervisor 2026-11-10): planted SSVEP at the five study frequencies reaches trial BA
  >= 0.9 with both networks under P20, and noise stays near chance.
- `eegharness` 0.4.1: version number only.

## 0.4.0 — 2026-11-09 (tag v0.4.0 at f6c238c; P300 Stage-2 ended and its suite ran once, spec §0 D3)

Applies the supervisor's pipeline to any EEG study (spec: `docs/v0.4_spec_draft.md`, decisions §0).

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
- Real identifiers in tests (P300 Stage-2 lesson: a pre-declared check parsed `^(\S+): pooled BA` and
  failed on the real F1 id, which has a space): `kit_tests/test_real_identifiers.py` runs the kit's
  matchers on `f1/raw/Shrinkage-LDA lsqr`, `f1/fbcsp+fbcca/...`, data part `Sub-01/Session 1` and files
  such as `Training 5 - F.ebr` and `Training 7, repeat - F.ebr` (runner end to end, selection, stage
  slugs, fold keys). `eegharness.folds` keys now accept real file and method names (spaces, hyphens,
  `+`, `,`, parentheses); they still refuse path separators, `:*?"<>|`, control characters and a
  leading `.` or space (the old pattern refused `Training 5 - F.ebr` and accepted `.hidden`). G12 and the
  synthetic-tester require real identifiers in fixtures for every parser and matcher.
- G11/G23 slipped again in the P300 results step (derived numbers in uncommitted /tmp scripts): new
  `eegharness.numbers` (standard library only). Each derived number (value, pp, difference, pp
  difference, ratio, percent, count, sum, mean, SD, median, min, max) is declared under a stable key in
  a committed spec (`configs/numbers/<run>.json`; `derive` refuses an uncommitted or modified spec and
  any table outside the project), written to a versioned folder (`numbers.json` with the spec's and
  each table's SHA-256, `numbers.csv`), and cited as `<text> [num:key]`; `check` verifies every
  citation. Rows are selected by exact identifiers; exactly one row per single value; NaN refuses
  unless dropped explicitly (counted). The results-analyst, the 06_results template, G23, the
  auditor's results check and the 05_audit template use it; the guard lets the auditor run
  `numbers check` (not `derive`). Tests: `kit_tests/test_eegharness_numbers.py`.
- P300 golden regression (spec §4, D3), after the P300 Stage-2 run ended: `kit_tests/golden/make_p300_goldens.py`
  runs the frozen P300 code (a read-only `git archive` export of `d833264`) on a fixed synthetic P300 study (3 files,
  one filtered block by block, artifact rejections) with the P300 Stage-2 settings, one BLAS/OpenMP and one torch
  thread (two runs give identical files); `kit_tests/test_eegpipe_p300_golden.py` (18 tests) requires eegpipe to
  reproduce every output bit for bit: epochs, counts and gates, the network input (and its refusal on the fallback
  file), session and folds, out-of-fold predictions of the baseline and all 20 F1 methods (both QDA fail alike),
  permutation draws, null and per-file tests, phase epochs and the F3 classifiers, condition-level connectivity,
  EEGNet, ShallowConvNet and the GNN on CPU, BH-FDR and NBS, and the paired statistics. The P300 suite at `d833264`
  ran once on a scratch export: 391 passed.
- Found by the golden: with rejection on, the runner checked shuffled unit targets against the codes of the
  RETAINED epochs and refused a study whenever the screen had removed every epoch of a code from a unit; P300
  checks against each block's codes before rejection. New `evaluate.unit_code_sets_of_events` (the adapter's full
  event table), used by the runner; known-answer test `test_runner_shuffle_check_uses_codes_before_rejection`
  (fails on f11889a).
- KNOWN BROKEN in 0.4.0: under `label_scheme` `unit_label` (SSVEP trials), a unit whose epochs are all
  rejected stops the methods runner (`IndexError` in the runner's unit labels for fold balancing;
  `evaluate.unit_values` refuses it next). Not fixed in 0.4.0 (decision 2026-11-09); the failing case is
  the strict xfail `test_unit_label_unit_with_every_epoch_rejected_runs` in
  `kit_tests/test_eegpipe_stage2_lessons.py` (a fix makes it XPASS, which fails the suite until the
  marker is removed).
- Kit tests: 452 passed, 1 xfailed (known broken, above), 1 CUDA test skipped on CPU; torch, scipy and scikit-learn join the kit
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
  go to the supervisor; resumable folds), G23 (derivations through committed, tested tools; no
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
  proposes the category, the supervisor confirms); measurement requests and a frozen,
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
