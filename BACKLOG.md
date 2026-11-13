# Backlog

Changes planned for the next kit version. Evaluation round 2 was withdrawn; items are taken into the next version as approved.

## v0.3

### L27 — results-analyst derived write-up numbers with scratch scripts outside the repository

Added 2026-11-06. **Done in v0.3.0** (G23, results-analyst instructions, the auditor's
results check; the guard option was not taken: Sebastian chose the auditor).

**What happened.** The results-analyst computed numbers for the write-up with scratch scripts
in `/tmp`, although G11 (derived numbers come from committed scripts,
`template/CLAUDE.md:105`) and lesson L4 forbid it. The numbers in the handoff could not be
reproduced from the repository.

**Planned changes.**

1. `template/.claude/agents/results-analyst.md`: any derivation (difference, ratio, mean,
   p-value, count, interval) goes into a committed tool with a test before its numbers
   enter a handoff. No scratch scripts, no inline calculation.
2. Handoff contract (`template/agent_runs/README.md` and the templates): a handoff that
   cites a path outside the repository cannot be marked READY.
3. To consider, with known-answer tests whichever is chosen:
   - guard: block writes of scripts outside the project root (e.g. `/tmp`, `$TMPDIR`) and
     running them, for all agents or for the results-analyst only;
   - methods-auditor check: flag any path outside the repository cited in a handoff or a
     results file, and any number in `06_results.md` that no committed script outputs.

## L29 — headless orchestrator ended its turn with a subagent still running (2026-11-07)

In ssvep-apply, the headless `/apply-pipeline` run (claude -p) started the plan subagent in the
background and ended its turn. Claude Code stopped the background subagent 10 minutes later and
the run ended mid step C ($8.25 spent; adapter done at 84a3c6b). The CLAUDE.md "Never do" rule
on background work exists, but the skills don't say that a subagent counts. Proposed fix for the
next kit version: `onboard`, `assignment` and `apply-pipeline` say "run each agent in the
foreground and wait for its handoff before the next step or the end of the turn". Workaround
used: resume the session with that instruction.

## L30 — a pre-declared check failed on the real method id (2026-11-09)

In the P300 Stage-2 run, a pre-declared regression check parsed log lines with
`^(?P<method>\S+): pooled BA`. The real F1 id `f1/raw/Shrinkage-LDA lsqr` has a space, so the check
reported FAIL on real data; its synthetic tests had used a made-up id without a space. Fixed in 0.4.0:
G12 and the synthetic-tester require the study's real identifiers (method ids, part and file names such
as `Training 5 - F.ebr`) in fixtures for every parser and matcher; `kit_tests/test_real_identifiers.py`
runs the kit's own matchers on them (the `eegharness.folds` key pattern refused real file names).

## L31 — G11/G23 slipped again in the results step (2026-11-09)

In the P300 Stage-2 results step, the results analyst computed derived report numbers (pp conversions,
counts, percentages) in uncommitted /tmp scratch scripts, although G11, G23 and L27 forbid it: the kit
had no ready tool, so the agent improvised one. Fixed in 0.4.0: `eegharness.numbers` (a committed spec
of keyed derivations, a versioned numbers.json, `[num:key]` citations verified by `check`), used by the
results-analyst, the 06_results template and the auditor's results check.

L32–L36 come from cold-pressor onboarding. That project stays on its current pin, v0.4.0, with no
upgrade mid-onboarding; these proposals apply from the next kit version on, each rule wording approved by
Sebastian separately.

## L32 — a check frozen as "report only", with no decision rule (2026-11-10)

In cold-pressor onboarding, the rest-period control M7 was frozen as "report only (no criterion,
cannot change the 8b verdict)". G10 asks for code and threshold to be fixed before real data, but a
report-only check has no threshold, so freezing it fixed nothing that decided anything, and the
reading of its result was left open until after the output was seen. Sebastian had M7 given a rule
before it ran (statistic and resampling unit, α, one- or two-sided, windows, and what each outcome
changes in the plan). Proposed for the next kit version, as an amendment to G10: a frozen check
states its decision rule, its sidedness (with a reason) and the consequence of each outcome; a check
without them is descriptive and gates nothing.

## L33 — participant free text quoted or paraphrased in committed docs (2026-11-10)

In cold-pressor onboarding, a draft committed file (76fae15, never pushed) quoted Formulario.docx (the
filled protocol form) verbatim, and docs/PARADIGM.md (lines 33 and 38 of Revision 1) paraphrased what
one participant wrote about their sensations. No personal details were included, but single-participant
free text can identify a person, and the paradigm description did not need it. "Data handling" covers
only the recordings. Proposed for the next kit version: a rule that committed files never quote or
paraphrase participants' own answers, comments or free text, or personal details from forms; protocol
facts from such documents are stated in the agent's own words without per-participant content; the
paradigm-analyst and auditor check it.

## L34 — a decision claimed more than its test checks (2026-11-10)

In cold-pressor onboarding, D-002 stated filter limits and named alternatives that the cited test did
not check: Round 2 R2-2 (G11; `05_audit.md` l.344) and Round 3 R3-1 (G26; `05_audit.md` l.555). It took
three audit rounds to make the decision text and the test agree. The project already had its own rule
G26 ("Evidence must be able to fail"), but G26 does not say what a decision may claim from its
evidence; that missing clause is why it still took three rounds. Proposed for the next kit version:
promote cold-pressor's project rule G26 into the kit, and add the missing clause: a decision that cites
a test states exactly what the test asserts (the alternatives it rules out and the limits it checks),
and nothing beyond; the auditor compares the entry with the test's assertions.

## L35 — placeholder text logged as a human's answers (2026-11-10)

In cold-pressor onboarding, Sebastian sent a reply containing unfilled bracketed placeholders for the
human-only questions Q1–Q7 ("[answer / UNKNOWN, …]"); the orchestrator logged the defaults inside the
brackets as his provisional answers in human_contacts.md (it did not write them into PARADIGM.md).
Proposed for the next kit version, as an amendment to G16's logging clause: only an explicit answer
is logged as an answer; template text, placeholders or suggested defaults are logged as "no answer",
and the agent asks once more, grouped.

## L36 — the orchestrator appended and reworded the paradigm-analyst's revision (2026-11-11)

In cold-pressor onboarding, the paradigm-analyst could not edit docs/PARADIGM.md: it has Write but no
Edit, and Write rewrites the whole file, frozen sections included (as in an earlier fix, where the
orchestrator could check the rewrite only by reading). For Revision 3 it therefore wrote its block to a
scratch file; the orchestrator appended the block and reworded one of its sentences (R3.4, marked in
PARADIGM.md as an orchestrator correction with the analyst's original sentence; log.md rows 5c Append
and 5c Note). The paradigm text is the analyst's; an orchestrator edit to it, even marked, is a change
nobody owns. Proposed for the next kit version: give the paradigm-analyst Edit for docs/PARADIGM.md
only, so it appends its own revisions; frozen text is kept unchanged and checked by diff; a correction
goes back to the analyst instead of being made by the orchestrator.

## L37 — measurement and reporting outputs without their compute time (2026-11-13)

In cold-pressor onboarding, the measurement outputs did not record how long they took: the audit
noted "runtimes are not measured" (`05_audit.md` C5, carried over as N5), so G22's expected
runtimes could not be checked against real ones and the next plan had to estimate again. Built in
v0.5-dev (`eegharness.outputs`, known-answer tests `kit_tests/test_eegharness_v05_lessons.py`): a
`ComputeTimer` started before the work and `record_compute_time(out, timer)` add `compute_time`
(wall seconds, CPU seconds of the process and of its finished children, device, UTC end) to the
output's `provenance.json`; an output with no computation records `compute_time: null` with a
`compute_time_reason`; nothing is written by default, so a forgotten one fails
`python -m eegharness.outputs check <folder>`. The kit's own writers (stage parts, select, collect,
numbers, compare_runs) record it. Proposed rule wording, as an amendment to G22 (for Sebastian's
approval; template not changed): "Every measurement and reporting output records its compute time
(`record_compute_time`; no computation: null with a reason); the auditor runs
`python -m eegharness.outputs check` on the outputs a result cites."

## L38 — an instruction cited only from git-ignored agent_runs/ (2026-11-13)

In cold-pressor onboarding, docs/PARADIGM.md cites Sebastian's decisions by contact number only
("by Sebastian's decision (onboarding contact #3, 2026-11-11)", l.908 @ a558941; also l.807, 915,
1015, 1336); the contact log is in git-ignored agent_runs/, so the committed file points at text no
reader of the repository can see. In ssvep-apply, D-011 and D-015 first cited agent_runs/ paths
(audit Round 6 R3, Round 7 R5). G15 forbids the path but not the bare contact number. Built in
v0.5-dev (`eegharness.sources`, same test file): `python -m eegharness.sources check` reads the
committed files and reports an `agent_runs/` reference (quoted or not) and a paragraph that cites a
contact (`contact #N`, `contact N`, `human_contacts`) without quoting it (a quoted span of at least
3 words, or a `>` block quote, in the same paragraph; JSON string values checked one by one). On
the real repositories: cold-pressor 5 findings (the PARADIGM lines above), ssvep-apply 0. Open
choice for Sebastian: attributions by name and date without a contact number ("Sebastian
2026-11-10: ...", 51 lines in ssvep-apply, 6 in cold-pressor) are not detected; detecting them would
tie the check to a name. Proposed rule wording, as an amendment to G15 (for Sebastian's approval;
template not changed): "A source that is an orchestrator's or a human's instruction is quoted, in
its own words, in the committed file that relies on it; a contact number or an `agent_runs/` path is
never the only citation. `python -m eegharness.sources check` passes before a commit."
