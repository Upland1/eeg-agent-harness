# {{PROJECT}} — Project instructions for Claude

Built with harness v{{HARNESS_VERSION}} (`.harness/VERSION`). An EEG research pipeline
for the recordings in `data/raw/` and the request in `inputs/`. Results go to the
supervising professor and into an academic write-up. **Correctness of the evaluation
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
| `docs/PARADIGM.md` | paradigm-analyst, approved by Sebastian | what it **means**: paradigm family, events, classes, analysis unit, timing, metrics, typical mistakes, and what is still unknown |

Never assume a property of the data that is in neither file. If you need one, measure it
with project code and add it to the record, or ask (see "When you don't know").

Inputs given to this project (`inputs/`): the professor's request and notes, and any
papers named there. Use them; cite them (G6).

## When you don't know

- Recognize what the evidence supports, and stop where it ends. Write **UNKNOWN —
  needs a human** instead of forcing a fit: an unexplained event code, a paradigm
  that matches no family you can justify, a contradiction between the notes and the data.
- **Investigate before you ask (G16).** Before a question goes to Sebastian, search, in
  this order: (1) every input in full, including appendices, supplementary material,
  tables and figure captions; (2) every document in the data folder and in `inputs/`
  (lab logs, READMEs, protocol sheets, file headers); (3) the documentation the inputs
  point to (a named public dataset's description, a device or software manual, a cited
  paper); (4) a measurement with project code. Record what each source said, including
  "searched, not found".
- Only facts that none of these sources answers are questions for Sebastian (what a
  code means when nothing written says it, how the experiment was run). Ask them once,
  grouped, in the handoff file, each with the sources you checked, what you measured and
  the options you see.
- Every contact with Sebastian (a question, an approval, a request to run something) is
  logged in the run's `human_contacts.md` (G16). The agent proposes the category;
  Sebastian confirms it.
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
the same values; a known filter response is preserved). `pytest tests/` runs on CPU in
about a minute with no real data.

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
that had been seen. *Incident: evaluation round 1, a statistic was changed after seeing
one file's output (L2).*

**G11. Derived numbers come from scripts too.** Differences, ratios, p-values, means and
any other number derived from results are computed by a committed script and written to
a logged output; nothing is calculated inside a write-up, and evidence scripts are never
left in a scratchpad. Extends G7. *Incident: evaluation round 1, reports traced only part
of their sampled numbers, mostly values computed in markdown (L3, L4).*

**G12. Test a measurement before it measures.** Every new measurement, estimator,
screening statistic or test statistic ships with known-answer tests (G2) that pass
**before** its first run on real data, on realistic inputs (e.g. block-updated
timestamps, uneven intervals, missing events). Every test statistic also gets a
false-positive-rate test: on pure noise with no effect, it rejects at about its nominal
rate, within a binomial tolerance stated in the test. *Incident: a survey script and a
rate estimator gave wrong numbers on real data before any test existed (L5, L6, L17).*

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
hashes and committed or reproducible output paths. *Incident: audits found committed
decisions pointing at local run files (L22).*

**G16. Use every written source before asking a human.** See "When you don't know":
inputs in full, documents in the data folder, documentation the inputs point to, and
measurement come first; each question lists the sources checked and what they said.
Every human contact is logged in `human_contacts.md` as *approval*, *human-only fact*,
or *should-have-found* (the answer was in a written source in reach). *Incident: in
onboarding, several questions sent to Sebastian were answered by the input paper's
appendix, the public documentation the paper names, or the lab log in the data folder
(L25).*

**Rules grow from experience.** When a test or the auditor catches a new kind of mistake,
the orchestrator writes up the incident and proposes a new rule (G17, G18, …). Sebastian
approves it before it is added here, with a one-line reference to the incident. Rules
that apply to any EEG study are also proposed to the harness (next version, never the
running one).

## Data handling

- Recordings live in `data/raw/` (git-ignored, read-only). Agents may **read** them
  through project code; never modify, copy elsewhere, upload or commit them.
- Processed arrays, models and reports are generated, git-ignored, and rebuilt by script,
  each run into a new versioned folder (G9).
- Shared tools are vendored, committed code in `eegharness/` (versioned output
  folders and provenance, `python -m eegharness.compare_runs` for regression checks).
  Project code imports only committed files, never `.harness/`.
- Long runs (more than about 10 minutes, or anything on GPU) are listed in the plan's
  "What Sebastian will run" section; Sebastian runs them locally or on Colab.

## Never do

- Never push, force-push or rewrite git history. Never commit to `main`.
- Never commit data, `CLAUDE.md`, `.claude/`, `.harness/` or `agent_runs/`, and never
  mention Claude in commit messages or committed files.
- Never loosen a test tolerance without saying so explicitly in the handoff.
- Never edit files in `reports/`, `.harness/` or `eegharness/` by hand.
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
   Sebastian approves → approved docs are committed.
2. **Then one run per assignment** (`/assignment`): 00_assignment → 01_brief → 02_plan →
   02b_plan_audit → [Sebastian approves] → 03_changes → 04_tests → 05_audit →
   [Sebastian runs long jobs] → 06_results.

Every run keeps `log.md` (one row per agent call, with tokens and time),
`human_contacts.md` (G16) and `cost.jsonl` (written by a hook).

Agents hand work to each other through `agent_runs/<YYYY-MM-DD>_<slug>/` following
`agent_runs/README.md`. Subagents don't see the conversation; everything they need is in
their input handoff file, `docs/DATA_PROFILE.md`, `docs/PARADIGM.md` or this document.
Each agent writes only its own handoff file. Before marking a handoff `READY`, run the
`cite-sources` checklist (G6).
