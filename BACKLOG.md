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

## L32 — a check frozen as "report only", with no decision rule (2026-11-10)

In cold-pressor onboarding, the rest-period control M7 was frozen as "report only (no criterion,
cannot change the 8b verdict)". G10 asks for code and threshold to be fixed before real data, but a
report-only check has no threshold, so freezing it fixed nothing that decided anything, and the
reading of its result was left open until after the output was seen. Sebastian had M7 given a rule
before it ran (statistic and resampling unit, α, one- or two-sided, windows, and what each outcome
changes in the plan). Proposed for the next kit version: G10 and the plan/handoff templates require
every frozen check to state its decision rule, sidedness with a reason, and the consequence of each
outcome; a check without them is labelled descriptive and cannot gate or steer anything.

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
not check (audit items R2-2, R3-1); it took three audit rounds to make the decision text and the test
agree. Proposed for the next kit version: a DECISIONS.md entry that cites a test as evidence names
exactly what that test asserts (the alternatives it rules out and the limits it checks) and nothing
beyond; the auditor compares the entry with the test's assertions.

## L35 — placeholder text logged as a human's answers (2026-11-10)

In cold-pressor onboarding, Sebastian sent a reply containing unfilled bracketed placeholders for the
human-only questions Q1–Q7 ("[answer / UNKNOWN, …]"); the orchestrator logged the defaults inside the
brackets as his provisional answers in human_contacts.md (it did not write them into PARADIGM.md).
Proposed for the next kit version: G16 and the human-contact template state that only an explicit
answer counts; template text, placeholders or suggested defaults are recorded as "no answer", and the
agent asks once more, grouped.
