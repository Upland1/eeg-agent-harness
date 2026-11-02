---
name: onboard
description: First run of every project. Profiles the recordings with the harness script, gets a reader plugin built if a format is unreadable, and has the paradigm-analyst write docs/PARADIGM.md for Sebastian's approval.
disable-model-invocation: true
---
You are the orchestrator of the onboarding run (`agent_runs/README.md`,
"Onboarding"). Update the run's `log.md` after every step. Do not interpret
the data yourself; the profiler measures and the paradigm-analyst interprets.

1. **Set up.** Create `agent_runs/<YYYY-MM-DD>_onboarding/` and copy the files
   of `agent_runs/_templates/onboarding/` except `PARADIGM.md`, plus
   `agent_runs/_templates/log.md`. Fill
   `00_assignment.md`: list every file in `inputs/` and quote the
   professor's request from it verbatim. Status: READY.
2. **Profile.** Run
   `python .harness/tools/run_profile.py --data data/raw --out docs/DATA_PROFILE`
   (add `--plugin readers/<name>.py` for every plugin in `readers/`). Summarize
   the console line and the Overview table in `01_profile.md`: files,
   profiled, no reader, errors, formats.
3. **Reader (only if files have no reader or reader errors).** Write the
   problem in `01_profile.md` (extensions, counts, error messages), then ask
   the pipeline-engineer for a reader plugin (naming the onboarding run) and
   the synthetic-tester for its round-trip test, then the methods-auditor
   for an audit of the plugin. Rerun step 2 with the plugin. After two
   failed rounds, stop and report.
4. **Paradigm.** Ask the paradigm-analyst for `docs/PARADIGM.md`, naming
   the onboarding run.
5. **STOP for Sebastian.** Show the paradigm family with its evidence, the
   UNKNOWN items and the questions only a human can answer. Sebastian
   answers in `02_paradigm_review.md` and ticks
   "Approved by Sebastian: [x]" in `docs/PARADIGM.md`. If his answers
   change claims, ask the paradigm-analyst for a revision (`## Revision N`).
6. **Close.** Log the outcome. Assignments (`/assignment`) may start only
   when `docs/PARADIGM.md` is approved.

If an agent sets Status: BLOCKED, stop and report why.
