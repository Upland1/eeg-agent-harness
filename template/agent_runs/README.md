# Agent handoff contract

Every assignment runs in its own folder. Agents don't share a conversation:
they communicate only through the files below, plus `CLAUDE.md`.

## Folder layout

```
agent_runs/
  _templates/                 copy these to start a run, don't edit in place
  2026-11-01_onboarding/      always the first run of a project (/onboard)
    00_assignment.md
    01_profile.md             what the profiler measured, and reader problems
    02_paradigm_review.md     Sebastian's approval of docs/PARADIGM.md
    log.md
    human_contacts.md         every contact with Sebastian, categorized (G16)
    cost.jsonl                tokens and time per agent call (hook)
  2026-11-03_<slug>/          one folder per assignment: <YYYY-MM-DD>_<slug>
    00_assignment.md
    01_brief.md
    02_plan.md
    02b_plan_audit.md
    03_changes.md
    04_tests.md
    05_audit.md
    06_results.md
    log.md, human_contacts.md, cost.jsonl
```

## Onboarding (first run of every project, `/onboard`)

| Step | Who | Writes | Gate |
|---|---|---|---|
| Inventory and profile | `.harness/tools` profiler (a script, not an agent) | `docs/DATA_PROFILE.json`, `docs/DATA_PROFILE.md` | — |
| Missing file reader | pipeline-engineer + synthetic-tester, only if the profiler reports a format it cannot read | a reader plugin with a round-trip test (rule G2), then the profiler runs again | tests pass |
| Paradigm description | paradigm-analyst | `docs/PARADIGM.md`, with a frozen label sanity check (8b) and measurement requests (12) | — |
| Measurements and label check | pipeline-engineer + synthetic-tester + methods-auditor; orchestrator runs short jobs | committed scripts, versioned outputs (G9); the analyst revises PARADIGM with them | criteria committed before the run (G10); tests pass (G12) |
| Approval | Sebastian | `02_paradigm_review.md` | **one message: approval and the questions only a human can answer (G16)**; then the approved docs are committed |

No assignment run starts before `docs/PARADIGM.md` is approved
(`Approved by Sebastian: [x]`). Every later agent reads it.

## Who reads and writes what

| File | Written by | Reads | Gate |
|---|---|---|---|
| `00_assignment.md` | Sebastian | — | — |
| `01_brief.md` | literature-scout | 00 | — |
| `02_plan.md` | orchestrator (main session) | 00, 01 | — |
| `02b_plan_audit.md` | methods-auditor | 02, 01, the code the plan touches | PASS required before approval |
| (approval) | Sebastian | 02, 02b | **Sebastian approves before any code changes** |
| `03_changes.md` | pipeline-engineer | 02 (and 05 on a fix round) | — |
| `04_tests.md` | synthetic-tester | 02, 03 | tests must pass |
| `05_audit.md` | methods-auditor (read-only shell: git, pytest, compare_runs) | 02, 02b, 03, 04, and the changed files | PASS required |
| (runs) | orchestrator within `docs/COMPUTE.md` limits after a smoke test; Sebastian for longer or remote jobs (G22) | 02 "Runs" | audit PASS first |
| `06_results.md` | results-analyst | 02, the logged outputs of the runs | runs finished |
| `05_audit.md` `## Results check` | methods-auditor | 06 and the outputs it cites | **PASS before the close** (G23) |

## Rules

1. **Write only your own file.** Never edit another agent's handoff file.
2. **Every file starts with a status line:** `Status: DRAFT`, `READY`, or
   `BLOCKED`. The next agent starts only from `READY`. On `BLOCKED`, explain why
   under "Open questions" and stop.
3. **Cite, don't paraphrase, rules.** Reference methodological rules by their
   `CLAUDE.md` number (G1–G25, and any G26+) so the audit can be checked mechanically.
   **Cite every source** (G6): papers, documentation, code examples and
   Sebastian's code, in the formats of `.claude/skills/cite-sources/SKILL.md`,
   with a `## Sources` list at the end of the file.
4. **Evidence over claims.** "Verified" means a command was run and its output is
   summarized. Code claims carry `path:line` references.
5. **Audit loop.** On `FAIL`, the engineer reads `05_audit.md`, fixes the issues,
   and appends a `## Round N` section to `03_changes.md`. The auditor then appends
   its own `## Round N` to `05_audit.md`. After two failed rounds, stop and
   hand the problem to Sebastian.
6. **Real data stays where it is.** Agents may read `data/raw/` through project
   code (to build the dataset, and smoke runs on one file), but never modify,
   copy, upload or commit it. Subagents never run full benchmarks. After the
   audit PASS, the orchestrator runs the plan's jobs that fit the CPU or GPU
   limit in `docs/COMPUTE.md` and whose committed smoke test passed (G22);
   longer or remote jobs are given to Sebastian as exact commands, and he
   drops the outputs into the run folder. Every output is a new versioned
   folder (G9).
7. **Runs are kept locally, never committed.** The run folder is the audit
   trail of how every result was produced, but `agent_runs/`, `CLAUDE.md` and
   `.claude/` are excluded from git (`.git/info/exclude`) so Claude never
   appears in the public repository. Never `git add` them, never move their
   contents into tracked files, and never mention Claude in commit messages.
8. **Log every step.** The orchestrator adds one row per agent call to
   `log.md`: outcome, audit round, what was caught, sources cited, tokens and
   wall time (from `cost.jsonl`, written by the `log_cost.py` hook), and
   anything that reached a real run broken.
9. **Log every human contact** in `human_contacts.md` before it is sent
   (G16): the question or request, the written sources checked and what each
   said, a proposed category (approval / human-only fact /
   should-have-found). Sebastian confirms the category.
10. **No background work left behind.** No agent starts a background job it
    does not wait for.

## Starting a run

```bash
RUN=agent_runs/$(date +%F)_<slug>
mkdir -p "$RUN" && cp agent_runs/_templates/*.md "$RUN"/
```

Then fill in `00_assignment.md` with the professor's request, verbatim.
