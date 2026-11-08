# eeg-harness

A multi-agent harness that takes an EEG study it has never seen (recordings,
the professor's notes, papers) and builds the analysis pipeline from scratch:
it measures the data, works out the paradigm, asks only what a human must
answer, then plans, implements, tests, audits and reports.

**Private. Never push this repository anywhere public** (it contains the agent
files). Projects made from it keep these files out of their own git history.

## Layout

| Path | What |
|---|---|
| `VERSION` | harness version; every project records the version that built it |
| `template/` | copied into each project: `CLAUDE.md` (general rules G1–G25), `.claude/` (6 agents; skills `onboard`, `assignment`, `apply-pipeline`, `cite-sources` and the method checklists `deep-learning`, `connectivity`, `compute-jobs`; guard, test and cost hooks), `agent_runs/` (handoff contract and templates, including the plan audit and the human-contact log), `tests/conftest.py`, `docs/COMPUTE.md` (per-job CPU/GPU limits, set by Sebastian) |
| `tools/` | deterministic tools: the dataset profiler `run_profile.py` and its reader registry (`eegprofile/`), copied to `<project>/.harness/tools/`; the `eegharness` package (versioned output folders with provenance, `compare_runs` regression check; core: grouped `splits` with a leakage check, unit-level `permutation`, `chance` levels; optional for deep learning: `seeds`, resumable `folds`; numpy only, torch never required), **vendored** as committed code to `<project>/eegharness/`; the `eegpipe` package (Sebastian's pipeline: classical suite and baseline, EEGNet/ShallowConvNet with the trainer, phase features, condition-level connectivity with debiased wPLI, BH-FDR and NBS, the edge-gated GNN, grouped folds with leakage gates, the settings validator and profiles, the dev → freeze → confirm runner, paired statistics, and the SSVEP option FBCCA, FBCSP, CCNN, DualBranchFusionCNN; numpy, scipy, scikit-learn; torch for the networks), **vendored** to `<project>/eegpipe/` and protected by the guard (G24) |
| `new_project.py` | creates or updates a project (harness arm or control arm) |
| `cost_report.py` | tokens and time of a finished project (either arm) from its transcripts, run by the evaluator after the run |
| `kit_tests/` | known-answer tests for the tools, the guard and project creation |

Nothing in `template/` names a paradigm or a lab format; `kit_tests/test_kit.py`
checks that.

## How a project runs

1. `python new_project.py <dir> --name <name>` and put the recordings in
   `<dir>/data/raw/`, the professor's material in `<dir>/inputs/`.
2. Open Claude Code in `<dir>` and run `/onboard`:
   - the **profiler** (a script) measures formats, sampling rates, channels, event
     codes, counts, intervals, transitions and the folder and file-name structure;
   - if a format has no reader, the **pipeline-engineer** writes a reader plugin
     in `readers/` with a round-trip test, and the profiler runs again;
   - the **paradigm-analyst** writes `docs/PARADIGM.md`: paradigm family, events,
     classes, analysis unit, expected signal, metrics, typical mistakes, UNKNOWNs;
   - the paradigm-analyst's measurement requests and frozen label sanity check are
     built, tested and run, and PARADIGM is revised with their outputs;
   - Sebastian answers, in one message, the questions only a human can answer
     (after the agents searched every written source, G16) and approves; the
     approved docs are committed.
3. `/assignment` for each request: scout → plan → plan audit → approval → engineer →
   tester → auditor → real runs (short ones by the orchestrator, long or GPU ones by
   Sebastian) → results.
4. `/apply-pipeline` to apply Sebastian's pipeline (`eegpipe`, v0.4): adapter
   (`adapter.py`: recording → event table) → settings (`configs/pipeline.json` from the
   `erp` or `ssvep` profile, every value with its source, `eegpipe.settings.validate`) →
   plan → plan audit → approval → gates and smoke → development run → freeze
   (`eegpipe.runner.select`, approval) → confirmatory stage (`eegpipe.runner.stage`, frozen
   commit, resumable, retry rule, provenance checks) → statistics (`eegpipe.runner.collect`:
   exact Wilcoxon or Pratt, sign test, Hodges-Lehmann with bootstrap interval, Holm) →
   results (G24, G25).

Every run logs tokens and time per agent (`cost.jsonl`) and every human contact with its
category (`human_contacts.md`: approval / human-only fact / should-have-found, confirmed
by Sebastian).

## Readers

Standard formats go through MNE (`.edf .bdf .gdf .vhdr .fif .set .cnt .mff .nxe`).
Any other format needs a plugin: a `.py` file with `EXTENSIONS` and
`read(path) -> Recording` (`tools/eegprofile/recording.py`), plus its test. Plugins
are written per project by the agents, not shipped in the kit, so that every
project builds its reader from scratch.

## Versions and evaluation

- Change the kit only between evaluation rounds. Each change: update `VERSION`
  and `CHANGELOG.md`, run `kit_tests`, commit, tag `v<version>`.
- `new_project.py --eval-dir <eval>` refuses an untagged or dirty kit, makes the
  evaluation folder unreachable for the agents (permission deny rules + guard
  hook + the blocklist read by the hook), and copies a case's `inputs/`.
- `<eval>/blocklist.json`: `"terms"` (strings blocked anywhere in a tool call) and, from
  v0.3.1, `"dirs"` (absolute folders or files treated like the evaluation folder: nothing
  inside them is reachable, and no search or listing may start in a folder that contains
  one, e.g. the shared data folder above `data/raw`).
- `--control` makes the control arm: the same inputs and protections, no harness.

## Reproducing a frozen version

Evaluation projects are built from the tagged commit, never from `main`: `main` may
carry later commits (documentation, validation reports) and `new_project.py --eval-dir`
refuses any checkout that is not exactly a clean tag. Use a detached worktree at the tag:

```bash
cd <kit repository>
git fetch --tags                                    # if working from a fresh clone
git worktree add --detach <worktree dir> v<version>          # e.g. v0.3.0
python <worktree dir>/new_project.py <project dir> --name <name> \
    --eval-dir <eval dir> [--case <eval dir>/cases/<case>] [--control]
cat <project dir>/.harness/build.json               # must show "git": "v<version>", "dirty": false
git worktree remove <worktree dir>                  # after all projects of the round are built
```

`.harness/build.json` in each project records the kit version it was built from; cite
that file, not the state of `main`. Tested on 2026-11-05 with `v0.2.0` (`011a8b4`).

## Tests

```bash
python -m pytest kit_tests -q -p no:cacheprovider
```

The full suite needs numpy, scipy, scikit-learn, mne and pytest (`requirements.txt`),
`pdftotext`, and torch (CPU build) for the network tests; with them only the CUDA test is skipped
on a machine without a GPU (v0.2.0: 190 passed; v0.3.0: 211; v0.3.1: 249; v0.4.0: 392 passed, 1
skipped without CUDA). Keep the virtual environment
outside the repository (e.g. `~/.venvs/eeg-harness-kit`).

## Release and privacy

This repository is private. Public release must come from a clean export; the private
history contains unredacted transcripts (commit `6c3d48c`, `docs/validation/v0.2.0_e2e/`,
redacted in the following commit but still in history). Export the tagged tree
(`git archive v<version>`) plus the redacted `docs/validation/`, never push this history
to a public remote.
