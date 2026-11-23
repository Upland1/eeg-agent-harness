---
name: onboard
description: First run of every project. Profiles the recordings with the harness script, gets a reader plugin built if a format is unreadable, has the paradigm-analyst write docs/PARADIGM.md, runs its measurement requests and frozen label sanity check, and asks Sebastian for one approval.
disable-model-invocation: true
---
You are the orchestrator of the onboarding run (`agent_runs/README.md`,
"Onboarding"). Update the run's `log.md` after every agent call (tokens and
wall time from `cost.jsonl`). Do not interpret the data yourself; the
profiler measures and the paradigm-analyst interprets.

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
stop and ask Sebastian. Per-round figures: `python .claude/hooks/log_cost.py --rounds
agent_runs/<run>` (differences of the running totals); the kit's `cost_report.py` and `run_cost.py`
give the reported totals after the run.

**Contacts with Sebastian.** Before any question, apply G16 (CLAUDE.md, "When
you don't know"): inputs in full, documents in the data folder,
documentation the inputs point to, measurement. Log every contact (question,
approval, request) in `human_contacts.md` before sending it, with a proposed
category; Sebastian confirms the category. Aim for one contact: the approval
in step 7.

0. **Inputs are the human's own words (L42, L46).** Run `python .harness/tools/check_inputs.py`. Do not
   start while it reports a finding: a template placeholder `<...>` left in `inputs/` (a template filled
   in only partly is not the request, and its examples are nobody's words), or a person's words reported
   without a verbatim quote and its date. Tell Sebastian the file and line, and wait for the corrected,
   committed inputs; never fill or reword them yourself. If it notes that `sources.names` is empty, ask
   Sebastian for the names to put in `.claude/harness.json` (local) before going on.
1. **Set up.** Create `agent_runs/<YYYY-MM-DD>_onboarding/` and copy the files
   of `agent_runs/_templates/onboarding/` except `PARADIGM.md`, plus
   `agent_runs/_templates/log.md` and `agent_runs/_templates/human_contacts.md`.
   Fill `00_assignment.md`: list every file in `inputs/` and quote the
   professor's request from it verbatim. Status: READY. Create the branch
   `onboarding` from `main` (`git switch -c onboarding`).
2. **Profile.** Run
   `python .harness/tools/run_profile.py --data data/raw --out docs/DATA_PROFILE`
   (add `--plugin readers/<name>.py` for every plugin in `readers/`). Summarize
   the console line and the Overview table in `01_profile.md`: files,
   profiled, no reader, errors, documents, formats. List the documents in the
   data folder: the paradigm-analyst must read every one, in full, with
   `python .harness/tools/read_document.py <path>` (it refuses recordings).
   If one cannot be converted (exit 4, e.g. a legacy .doc), say so in
   `01_profile.md`; that is a request for Sebastian, logged as such.
3. **Reader (only if recordings have no reader or reader errors).** Documents
   are not recordings and need no reader. Write the problem in
   `01_profile.md` (extensions, counts, error messages), then ask the
   pipeline-engineer for a reader plugin (naming the onboarding run), the
   synthetic-tester for its round-trip test, then the methods-auditor for an
   audit of the plugin. Rerun step 2 with the plugin. After two failed rounds
   ("Audit rounds" above: a wording-only round and auditor errors aside, at most 4), stop and report.
4. **Paradigm.** Ask the paradigm-analyst for `docs/PARADIGM.md`, naming
   the onboarding run.
5. **Freeze, measure, check labels.** If `docs/PARADIGM.md` has measurement
   requests (section 12) or a label sanity check (section 8b):
   - Commit `docs/PARADIGM.md` (draft, with the frozen 8b criteria) and the
     profile on `onboarding` first (G10): the check is frozen before it runs.
   - Ask the pipeline-engineer to implement them as committed scripts writing
     versioned outputs (G9), the synthetic-tester for known-answer tests (G12),
     and the methods-auditor for a short audit.
   - Run them yourself if each fits the CPU limit in `docs/COMPUTE.md`
     (G22); otherwise list them for Sebastian.
   - Ask the paradigm-analyst for a revision (`## Revision N`) with the
     logged outputs, the label check reported per participant and session
     (G14).
   - The paradigm-analyst has Edit for `docs/PARADIGM.md` only and appends its own revisions; frozen text stays unchanged and is checked by diff; a correction goes back to the analyst, never made by the orchestrator. After each revision run
     `python .harness/tools/check_frozen_text.py docs/PARADIGM.md --base <last commit of it>`;
     a FAIL goes back to the paradigm-analyst.
6. **Before asking.** Check every question in PARADIGM section 10: does it
   list the sources searched? Could a document in the data folder or the
   documentation an input names answer it? If so, send it back to the
   paradigm-analyst instead of to Sebastian.
7. **STOP for Sebastian (one message).** Show the paradigm family with its
   evidence, the label sanity result per participant, the UNKNOWN items and
   the questions only a human can answer, each with its sources checked.
   Sebastian answers in `02_paradigm_review.md` (with a category per
   question) and ticks "Approved by Sebastian: [x]" in `docs/PARADIGM.md`.
   If his answers change claims, ask the paradigm-analyst for a revision.
8. **Commit at approval.** Commit `docs/PARADIGM.md`, `docs/DATA_PROFILE.*`,
   `docs/DECISIONS.md` and any reader plugin and its test on `onboarding`,
   by explicit path, so later branches start from a clean tree. Tell
   Sebastian the branch is ready for him to merge into `main`.
9. **Close.** Log the outcome, the totals from `cost.jsonl`, and the counts
   per category from `human_contacts.md`. Assignments (`/assignment`) may
   start only when `docs/PARADIGM.md` is approved.

If an agent sets Status: BLOCKED, stop and report why.
