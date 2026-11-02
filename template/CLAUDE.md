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
- Only facts that cannot be measured or found in the literature are questions for
  Sebastian (what a code means when nothing in the data or notes says it, how the
  experiment was run). Ask them once, grouped, in the handoff file, with what you
  measured and the options you see.
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

**Rules grow from experience.** When a test or the auditor catches a new kind of mistake,
the orchestrator writes up the incident and proposes a new rule (G9, G10, …). Sebastian
approves it before it is added here, with a one-line reference to the incident. Rules
that apply to any EEG study are also proposed to the harness (next version, never the
running one).

## Data handling

- Recordings live in `data/raw/` (git-ignored, read-only). Agents may **read** them
  through project code; never modify, copy elsewhere, upload or commit them.
- Processed arrays, models and reports are generated, git-ignored, and rebuilt by script.
- Long runs (more than about 10 minutes, or anything on GPU) are listed in the plan's
  "What Sebastian will run" section; Sebastian runs them locally or on Colab.

## Never do

- Never push, force-push or rewrite git history. Never commit to `main`.
- Never commit data, `CLAUDE.md`, `.claude/`, `.harness/` or `agent_runs/`, and never
  mention Claude in commit messages or committed files.
- Never loosen a test tolerance without saying so explicitly in the handoff.
- Never edit files in `reports/` or `.harness/` by hand.
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
   paradigm-analyst writes `docs/PARADIGM.md` → Sebastian approves.
2. **Then one run per assignment** (`/assignment`): 00_assignment → 01_brief → 02_plan →
   [Sebastian approves] → 03_changes → 04_tests → 05_audit → [Sebastian runs long jobs]
   → 06_results.

Agents hand work to each other through `agent_runs/<YYYY-MM-DD>_<slug>/` following
`agent_runs/README.md`. Subagents don't see the conversation; everything they need is in
their input handoff file, `docs/DATA_PROFILE.md`, `docs/PARADIGM.md` or this document.
Each agent writes only its own handoff file. Before marking a handoff `READY`, run the
`cite-sources` checklist (G6).
