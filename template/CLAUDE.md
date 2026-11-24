# {{PROJECT}} — Project instructions for Claude

Built with harness v{{HARNESS_VERSION}} (`.harness/VERSION`). An EEG research pipeline
for the recordings in `data/raw/` and the request in `inputs/`. Results go to the
person who requested the study and into an academic write-up. **Correctness of the evaluation
always outranks speed or headline accuracy.** Treat any surprising gain as a bug until a
synthetic test and the methods audit say otherwise.

## How this project is built: from scratch, paradigm unknown at the start

Nothing in this file says what kind of EEG study this is. The agents find out, decide,
justify every decision in writing, and own their mistakes: when something turns out
wrong, they find it, fix it, and record what happened (`agent_runs/<run>/log.md`,
`docs/DECISIONS.md`).

What the agents know about the data comes from two files only:

| File | Written by | Contains |
|---|---|---|
| `docs/DATA_PROFILE.md` / `.json` | the profiler script (`.harness/tools/run_profile.py`) | what was **measured**: formats, sampling rates, channels, event codes, counts, intervals, transitions, folder and file-name structure |
| `docs/PARADIGM.md` | paradigm-analyst, approved by the supervisor | what it **means**: paradigm family, events, classes, analysis unit, timing, metrics, typical mistakes, and what is still unknown |

Never assume a property of the data that is in neither file. If you need one, measure it
with project code and add it to the record, or ask (see "When you don't know").

Inputs given to this project (`inputs/`): the request and notes of the person who asked for the study (the requester), and any
papers named there. Use them; cite them (G6).

## When you don't know

- Recognize what the evidence supports, and stop where it ends. Write **UNKNOWN —
  needs a human** instead of forcing a fit: an unexplained event code, a paradigm
  that matches no family you can justify, a contradiction between the notes and the data.
- **Investigate before you ask (G16).** Before a question goes to the supervisor, search, in
  this order: (1) every input in full, including appendices, supplementary material,
  tables and figure captions; (2) every document in the data folder (through
  `.harness/tools/read_document.py`, which refuses recordings) and in `inputs/` (lab logs,
  READMEs, protocol sheets); (3) the documentation the inputs
  point to (a named public dataset's description, a device or software manual, a cited
  paper); (4) a measurement with project code. Record what each source said, including
  "searched, not found".
- Only facts that none of these sources answers are questions for the supervisor (what a
  code means when nothing written says it, how the experiment was run). Ask them once,
  grouped, in the handoff file, each with the sources you checked, what you measured and
  the options you see.
- Every contact with the supervisor (a question, an approval, a request to run something) is
  logged in the run's `human_contacts.md` (G16). The agent proposes the category;
  the supervisor confirms it.
- If you recognize these recordings as a specific public dataset, say so in your handoff
  ("contamination flag") and do not use what you remember about it; work only from
  the files, the inputs and sources you open.

## General rules (method-agnostic)

The methods-auditor checks every change against these by number. They say *what must be
true*, not *how*: choosing how is the agents' job.

**G1. No information from evaluation data reaches training.** Anything fitted or chosen
from data (filters, spatial filters, scalers, feature selection, hyperparameters,
thresholds, early stopping, normalization statistics) uses training data only. Every
evaluation protocol states in writing what counts as an unseen sample, and argues why
test samples share no information with training samples (consider time overlap, shared
trials or blocks, shared sessions, shared participants). The auditor rejects a protocol
without that argument.

**G2. Known-answer tests.** Every new reader, estimator, feature, model or preprocessing
step ships with a synthetic test in `tests/` whose correct answer is known in advance
(a planted signal is recovered where it was planted; a file written and read back gives
the same values; a known filter response is preserved). `pytest tests/` (the default run,
which leaves out tests marked `slow`) runs on CPU in about a minute with no real data; the full
suite, `pytest tests/ -m ""`, runs before every freeze and commit and in the auditor's check (L55). A test for a fix or for an index layout (reshape,
flatten, coefficient slicing, adjacency, channel order) must fail on the plausible buggy
variant (wrong axis, contiguous instead of strided, crossing a trial, a fit that sees
the test data, a no-op), and the test file shows that it does.

**G3. Report per participant and session, with the data source.** Never only a pooled
mean. State which files, which preprocessing and which protocol produced each number.
Use metrics that stay honest when classes are imbalanced, and state chance level.

**G4. Honest statistics.** Significance by procedures whose assumptions hold for this
data; state the unit of resampling; report inconclusive results as inconclusive.

**G5. Explicit parameters.** Every threshold, window and setting is set explicitly and
recorded in the config or the run's plan; never inherited silently from a default.

**G6. Cite every source.** Follow `.claude/skills/cite-sources/SKILL.md`. Every decision,
formula, parameter and borrowed pattern carries `[n]` → a numbered `## Sources` list;
own choices are `[own]` with a reason.

**G7. Numbers come from runs.** Every number in a write-up comes verbatim from a logged
run (command, commit, output file). Nothing estimated or retyped.

**G8. Decisions are written down.** Each design decision goes into `docs/DECISIONS.md`:
the question, the options considered, the choice, the evidence, and the sources.

**G9. Outputs are never overwritten.** Every script that writes results creates a new
folder `<out>/<UTC time>_<commit>[_dirty]/` with `provenance.json` (command, commit,
dirty flag, versions, SHA-256 of inputs), using `eegharness.outputs.new_output_dir`
(`eegharness/`). Superseded outputs are kept; the run log says which output a
reported number comes from. *Incident: evaluation round 1, a gate's first output was
overwritten and survived only in a transcript (harness lesson L1).*

**G10. Checks are frozen before they see real data.** Any gate, screening rule, quality
check, threshold or selection rule is fixed and committed (code and threshold) before it
runs on real recordings. A change after that is a deviation, recorded with the output
that had been seen. A frozen check states its decision rule (statistic, resampling unit, α, windows), its sidedness with a reason, and what each outcome changes in the plan; a check without them is descriptive and gates nothing. *Incident: evaluation round 1, a statistic was changed after seeing
one file's output (L2); a control was frozen as "report only", with no rule (L32).*

**G11. Derived numbers come from scripts too.** Differences, ratios, p-values, means and
any other number derived from results are computed by a committed script and written to
a logged output; nothing is calculated inside a write-up, and evidence scripts are never
left in a scratchpad. Extends G7. *Incident: evaluation round 1, reports traced only part
of their sampled numbers, mostly values computed in markdown (L3, L4).*

**G12. Test a measurement before it measures.** Every new measurement, estimator,
screening statistic or test statistic ships with known-answer tests (G2) that pass
**before** its first run on real data, on realistic inputs (e.g. block-updated
timestamps, uneven intervals, missing events) and with the study's real identifiers:
method ids, part and file names as written, with their spaces, slashes and hyphens
(`f1/raw/Shrinkage-LDA lsqr`, `Training 5 - F.edf`), for every parser and matcher. Every
test statistic also gets a false-positive-rate test: on pure noise with no effect, it
rejects at about its nominal rate, within a binomial tolerance stated in the test. *Incident: a survey script and a
rate estimator gave wrong numbers on real data before any test existed (L5, L6, L17); a
pre-declared check parsed `^(\S+): pooled BA` and failed on the real F1 id, which has a space,
because its tests used a made-up id (L30).*

**G13. State the exchangeability unit.** Every evaluation and every resampling procedure
(permutation, bootstrap, cross-validation) names its exchangeable unit (epoch, trial,
block, session, participant) and argues it from event timing versus epoch length (do
segments overlap or share a trial or block?). Permutation nulls draw from the full set
of labellings, the observed one included (p = (1 + #{null ≥ observed}) / (1 + n)).
*Incident: an approved plan contained a null that could not draw the observed
labelling; it was anti-conservative and caught only after it was built (L9, L17, L21).*

**G14. Quality claims are per unit, comparative and absolute.** Data-quality, rejection
and label-sanity claims are reported per participant and session (a pooled pass can hide
a reversed participant), state their comparison set (which other participants or
sessions), and give absolute as well as relative measures. Check the same participant's
other sessions before calling an effect session-specific. Every run reports its
rejection rate per criterion; a high rate is an anomaly to diagnose before interpreting
results. *Incident: a pooled label check passed with one participant reversed; a
"bad session" claim rested on a relative measure only (L15, L18, L19).*

**G15. Committed files cite committed things.** Committed code, decisions and docs never
reference uncommitted files (`agent_runs/`, scratchpads, local notes). They cite commit
hashes and committed or reproducible output paths. A source that is an orchestrator's or a
human's instruction is quoted, in its own words, in the committed file that relies on it; a
contact number, a name with a date, or an `agent_runs/` path is never the only citation.
`python -m eegharness.sources check` passes before a commit (the names it looks for are in the
project's local `.claude/harness.json`, `sources.names`; an approval line in the form "Approved
by <name>, <date>[, <what>]", or the template's box ticked and dated, "Approved by <name>: [x]
Date: YYYY-MM-DD", is a record, not a citation; a ticked box needs its date). *Incident: audits found committed
decisions pointing at local run files (L22); a committed paradigm cited the supervisor's decisions by
contact number only, and settings by name and date only (L38).*

**G16. Use every written source before asking a human.** Before any question goes to
the supervisor, the agents check, and record what each said ("searched, not found" included):
(a) every input in full, including appendices, supplementary material, tables and figure
captions; (b) every document in the data folder that is not a recording (lab logs,
READMEs, protocol sheets, spreadsheets), read through
`.harness/tools/read_document.py`; (c) the documentation the inputs point to (a named
dataset's description, a device or software manual, a cited paper); (d) a measurement
with project code. A question goes to the supervisor only if none of these answers it, and it
lists the sources checked. Every human contact (question, approval, request) is logged
in the run's `human_contacts.md` as **approval**, **human-only fact** or
**should-have-found** (the answer was in a source in reach); the agent proposes the
category and the supervisor confirms it. Only an explicit answer is logged as an answer; template text, placeholders or suggested defaults are logged as 'no answer', and the agent asks once more, grouped. *Incident: in onboarding, several questions sent to
the supervisor were answered by the input paper's appendix, the public documentation the
paper names, or the lab log in the data folder (L25); bracketed defaults in a reply were
logged as answers (L35).*

Rules G17–G23 make G1, G4 and G7 concrete for neural networks, connectivity and long
jobs. When a plan uses one of these methods, every agent working on it reads the matching
checklist: `.claude/skills/deep-learning/SKILL.md`, `.claude/skills/connectivity/SKILL.md`,
`.claude/skills/compute-jobs/SKILL.md`.

**G17. Training and preprocessing stay inside the training data.** Extends G1.
(a) Early-stopping and validation splits are drawn from the training fold, grouped by the
G13 unit, never from the test fold or a held-out participant. (b) Normalization statistics
come from the training fold, or are computed per sample with no statistics across samples
(the plan says which). (c) Augmentation runs on the fly on training samples only and never
mixes classes. (d) Hyperparameters, architecture, epochs and checkpoints are chosen on inner
validation, never on test results. (e) Any transform applied to a test sample must be
computable without that sample's label (e.g. never subtract the mean response of the test
trial's own class). (f) Unsupervised test-time normalization (statistics from unlabeled test
data) is allowed only when the method name and the write-up say so and state where the
statistics came from (whole session = offline upper bound; first K units = online).
(g) When participants are pooled, group ids are unique across participants, all share one
channel set chosen by name, and nothing from the held-out participant reaches any fit.
(h) Operations over consecutive samples (smoothing, context windows, sequence models) never
cross a unit boundary, and samples are ordered by recording time. (i) Defaults inherited
from ported or library code (priors, augmentation, label smoothing, segment lengths,
class weights) are listed in the plan and set explicitly; a default that contradicts the
plan is a FAIL. *Incidents: early stopping on the test fold, augmentation and transductive
normalization in an earlier study; a preprocessing step that needed the test label
and inherited defaults contradicting the plan, caught by plan audit (L28).*

**G18. Seeds and spread.** Every stochastic model is seeded per fold and repeat before it is
built (data loaders included), with the seed scheme in the plan
(`eegharness.seeds`). Every reported number of a stochastic model is the mean and SD over
at least 3 seeds (more if the plan says so), per participant, with each seed's value saved.
A/B comparisons use the same seeds and folds (paired). A difference smaller than the seed
spread is reported as "no difference shown". Final training accuracy on un-augmented
training data is reported next to test accuracy, and the parameter count next to the
architecture. Device and nondeterminism settings are recorded in `provenance.json`.
*Incident: in an earlier study two runs of the same network command differed by several
points; a network sweep ran one seed.*

**G19. Significance budget, and development data stay out of the confirmatory test.**
Before results, the plan states the comparisons that may be called significant: the
primary configurations (a fixed, committed set), the test and its unit (G13), α and the
family-wise correction (e.g. Holm). Every configuration tried counts against the budget
(architectures, variants, sweeps, epochs, seeds chosen). Data used to develop, tune or
debug (participants, sessions or runs) never enter the confirmatory test; the plan names
both sets. Anything outside the budget is reported as exploratory and never marked
significant. Accuracy is compared with a chance level for the actual number of test
trials (`eegharness.chance`), not only 1/k. *Incident: plan audit of a methods port found
the development session re-entering the confirmatory test and no fixed family of primary
configurations (L28).*

**G20. Connectivity estimators and their statistics.** (a) Every connectivity estimator has
a known-answer test on independent noise that reports its bias at the sample size used;
conditions are compared at matched sample sizes or estimated once per condition over
concatenated data, never by averaging per-segment estimates of a biased estimator.
(b) Phase is taken by a method valid for the segment length, with an edge-immunity test.
(c) Stimulus versus baseline uses the same band and estimator. (d) Permutations exchange
whole units (G13) with the observed group sizes; the number of permutations can resolve α;
a result that crosses α between permutation counts is inconclusive. (e) Global,
edge-wise (FDR) and component-wise (NBS) criteria are reported separately, each fixed
before results (G10); a threshold sweep is a sensitivity analysis, not a selection.
(f) Directed measures are symmetrized (estimate and null) before undirected statistics.
(g) Missing channels are embedded by name as NaN before averaging across participants.
(h) Subgroups (e.g. responders) are defined independently of the measure tested.
*Incident: an earlier study averaged biased per-window coherence, took Hilbert phase on
short windows, permuted windows instead of trials, and merged two criteria into one flag.*

**G21. Filter continuous data, then cut; metadata from the file.** Filter continuous
recordings before cutting segments; segments within the filter's ringing time of a
discontinuity or artifact are discarded or flagged. Sampling rate, channel names and units
come from the file header, never from a constant; channels are selected by name, never by
position. Extends G5. *Incident: an earlier study filtered each short window and assumed
a sampling rate that was not the recorded one.*

**G22. Long and GPU jobs.** Every job in a plan states its device, expected runtime, seeds
and output folder. The limits per job are in `docs/COMPUTE.md` (set by the supervisor). The
orchestrator runs a job itself, after the audit PASS, only if it fits the CPU or GPU limit
there **and** a committed smoke test (synthetic data or one fold, under 5 minutes, CPU)
has passed through the same entry point. Longer work is split into resumable parts (per
fold, seed or session) that each fit the limit; a part that cannot fit, and anything on
remote hardware, goes to the supervisor as exact commands with expected runtime and the
outputs to return. Long jobs
save each fold with its configuration (`eegharness.folds`); a rerun with a different
configuration on the same folder is refused. Runtime and device are reported per job.
`docs/COMPUTE.md` also sets `cpu_working_threads` (threads per job of a long run, enforced by
`eegpipe.settings.validate`; L39) and `memory_max_gb` (memory the jobs may use together): the plan
states each part's peak memory from the development run, a batch of b parts runs only if b × peak
fits, and before each batch `python -m eegharness.compute precheck` confirms available memory and
that `data/raw` resolves with every profiled file (L54, L44).
Every measurement and reporting output records its compute time (`record_compute_time`; no computation: null with a reason); the auditor runs `python -m eegharness.outputs check` on the outputs a result cites. *Incident: an audit found the runtimes of the measurement outputs unmeasured (L37).*

**G23. Derivations go through committed, tested tools.** Any number derived for a handoff
or write-up (difference, ratio, mean, interval, p-value, count) comes from a committed
tool with a test before it enters the handoff; no scratch scripts, no inline arithmetic.
A handoff that cites a path outside the repository cannot be READY. The tool is
`eegharness.numbers`: each number is declared under a stable key in a committed spec
(`configs/numbers/<run>.json`), derived into a versioned folder, and cited in the report as
`<text> [num:key]`; `python -m eegharness.numbers check` verifies every citation. The auditor
checks both in a results check. A number the orchestrator derives from outputs for `log.md` or
for the supervisor comes from `eegharness.numbers` or a committed tool. Otherwise it is sent marked
`(hand count, not derived)` with the tool gap named, and it is never corrected by another hand count
(L51). Extends G11. *Incident: the results-analyst computed write-up
numbers with scratch scripts in a temporary folder although G11 existed (L27).*

**G24. The pipeline library is configured, never edited.** `eegpipe/` (the supervisor's pipeline:
classical suite, EEGNet/ShallowConvNet and their trainer, phase features and connectivity
with debiased wPLI, FDR and NBS, the edge-gated GNN, grouped folds with leakage gates, the
stage runner and paired statistics, and a frequency-tagging option) is vendored code like
`eegharness/`. A project changes what it does only through `configs/pipeline.json`, every
value with its source (`eegpipe.settings`). A study that needs something the library does not
do adds a NEW project module with its own tests (G2, G12) and a DECISIONS.md entry naming the
gap; it never patches, copies-and-edits or monkeypatches `eegpipe`. *Incident: an earlier study
re-implemented its methods per script, and two versions of one estimator drifted apart.*

**G25. Confirmatory runs only from a frozen commit.** The data used to develop, tune or debug
(named in the settings, G19) are separated before any confirmatory number exists; the
confirmatory selection is label-free and seeded (`eegpipe.runner.select`), committed with the
settings (the freeze, approved by the supervisor); `eegpipe.runner.stage` refuses a dirty tree,
checks HEAD and the tree before and after every job, and refuses outputs whose commit,
settings hash or epochs/folds hashes disagree; `eegpipe.runner.collect` refuses an incomplete
root unless the analysis is stamped INTERIM. Nothing computed before the freeze is reported as
confirmatory. The auditor checks the freeze commit, the selection and every refusal in the log.
*Incident: in a methods port the development session re-entered the confirmatory test, and a
part was nearly rerun at a different commit (L28; methods-port audit C4).*

**G26. Evidence must be able to fail.** Evidence for a design decision is a check that would have come out differently if the decision were wrong; a decision that cites a test states exactly what the test asserts (the alternatives it rules out and the limits it checks) and nothing beyond; the auditor compares the entry with the test's assertions. *Incident: a decision claimed filter limits and
alternatives its test did not check; three audit rounds to make the entry and the test agree (L34).*

**G27. A group statistic takes only estimates that exist at that sample size.** Extends G20 (a). A per-participant (or per-unit) estimate enters a group statistic only if its estimator is defined and non-degenerate at that unit's sample size; the minimum is derived from the estimator and tested (a test at the minimum and one below it), and inclusion is decided by the estimator's own criterion, never by another method's validity flag. Every unit left out is listed with its reason in that runner's output. *Incident: a connectivity group step selected participants by a classifier's
validity flag and left out one whose estimate was a structural zero at one trial, with no reason row (L40).*

**Rules grow from experience.** When a test or the auditor catches a new kind of mistake,
the orchestrator writes up the incident and proposes a new rule (G28, G29, …). The supervisor
approves it before it is added here, with a one-line reference to the incident. Rules
that apply to any EEG study are also proposed to the harness (next version, never the
running one).

## Data handling

- Recordings live in `data/raw/` (git-ignored, read-only). Agents may **read** them
  through project code; never modify, copy elsewhere, upload or commit them.
- Processed arrays, models and reports are generated, git-ignored, and rebuilt by script,
  each run into a new versioned folder (G9).
- Shared tools are vendored, committed code in `eegharness/`: versioned output folders
  and provenance (`outputs`), regression checks (`python -m eegharness.compare_runs`),
  grouped splits with a leakage check (`splits`), unit-level permutation tests
  (`permutation`), chance levels (`chance`), seeding (`seeds`), resumable folds
  (`folds`) and derived report numbers with stable keys (`python -m eegharness.numbers`, G23). torch is never required by `eegharness`. Project code imports only committed
  files, never `.harness/`.
- the supervisor's pipeline is vendored, committed code in `eegpipe/` (G24): configured in
  `configs/pipeline.json` (`eegpipe.settings`; one profile per design family), read through the
  project's `adapter.py` (recording -> event table), run with `eegpipe.runner` (G25). It needs
  numpy, scipy and scikit-learn; torch only for the networks and the GNN.
- Committed files never quote or paraphrase a participant's own answers, comments or free text, or personal details from forms; protocol facts from such documents are stated in the agent's own words, without per-participant content; the paradigm-analyst and the auditor check it. *Incident: a draft commit quoted a filled protocol form, and a paradigm
  description paraphrased one participant's sensations (L33).*
- Jobs run under the limits in `docs/COMPUTE.md` (G22); longer or remote jobs are listed in
  the plan's "Runs" section for the supervisor.

## Never do

- Never push, force-push or rewrite git history. Never commit to `main`.
- Never commit data, `CLAUDE.md`, `.claude/`, `.harness/` or `agent_runs/`, and never
  mention Claude in commit messages or committed files.
- Never loosen a test tolerance without saying so explicitly in the handoff.
- Never edit files in `reports/`, `.harness/`, `eegharness/` or `eegpipe/` by hand.
- Never start background work (background shells, detached jobs) that you do not wait for
  and collect before you finish.
- Never look for answer keys, evaluation material or other projects' results outside this
  folder.

## Deliverable conventions

- Individual files, never zip archives; every changed file labelled **NEW** or
  **MODIFIED** with its repo path.
- Minimal diffs; no unrelated refactoring.
- Write-ups in a concise academic-paper tone, numbers verbatim from outputs.
- One step at a time; no unrequested work.

## Multi-agent workflow

1. **Onboarding first** (`/onboard`): profiler → reader plugin if a format is unreadable →
   paradigm-analyst writes `docs/PARADIGM.md` (with a frozen label sanity check) →
   the supervisor approves → approved docs are committed.
2. **Then one run per assignment** (`/assignment`): 00_assignment → 01_brief → 02_plan →
   02b_plan_audit → [the supervisor approves] → 03_changes → 04_tests → 05_audit →
   runs (G22) → 06_results → results check (G23, in 05_audit).
3. **Applying the supervisor's pipeline** (`/apply-pipeline`, G24, G25): adapter → settings →
   02_plan → 02b_plan_audit → [the supervisor approves] → gates and smoke → development run →
   freeze [the supervisor approves] → confirmatory stage → statistics → 06_results → results check.

Every run keeps `log.md` (one row per agent call, with tokens and time),
`human_contacts.md` (G16) and `cost.jsonl` (written by a hook).

Agents hand work to each other through `agent_runs/<YYYY-MM-DD>_<slug>/` following
`agent_runs/README.md`. Subagents don't see the conversation; everything they need is in
their input handoff file, `docs/DATA_PROFILE.md`, `docs/PARADIGM.md` or this document.
Each agent writes only its own handoff file. Before marking a handoff `READY`, run the
`cite-sources` checklist (G6).
