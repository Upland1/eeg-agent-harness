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
| `template/` | copied into each project: `CLAUDE.md` (general rules G1–G8), `.claude/` (6 agents, skills `onboard`, `assignment`, `cite-sources`, guard and test hooks), `agent_runs/` (handoff contract and templates) |
| `tools/` | deterministic tools, copied to `<project>/.harness/tools/`: the dataset profiler `run_profile.py` and its reader registry (`eegprofile/`) |
| `new_project.py` | creates or updates a project (harness arm or control arm) |
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
   - Sebastian answers the questions only a human can answer and approves.
3. `/assignment` for each request: scout → plan → approval → engineer → tester →
   auditor → Sebastian's long runs → results.

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
- `--control` makes the control arm: the same inputs and protections, no harness.

## Tests

```bash
python -m pytest kit_tests -q
```
