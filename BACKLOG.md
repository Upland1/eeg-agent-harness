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

**Approved and done in 0.5.0** (Sebastian, 2026-11-16: "Approved, all seven as worded: L37, L29, L32, L33, L34, L35, L36"), with the wording proposed on 2026-11-16, in onboard, assignment and apply-pipeline skills (**Agents.**); known-answer tests `kit_tests/test_v05_rules.py`, failing on 03c00f6.

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

**Approved and done in 0.5.0** (Sebastian, 2026-11-16: "Approved, all seven as worded: L37, L29, L32, L33, L34, L35, L36"), with the wording proposed on 2026-11-16, in G10; known-answer tests `kit_tests/test_v05_rules.py`, failing on 03c00f6.

In cold-pressor onboarding, the rest-period control M7 was frozen as "report only (no criterion,
cannot change the 8b verdict)". G10 asks for code and threshold to be fixed before real data, but a
report-only check has no threshold, so freezing it fixed nothing that decided anything, and the
reading of its result was left open until after the output was seen. Sebastian had M7 given a rule
before it ran (statistic and resampling unit, α, one- or two-sided, windows, and what each outcome
changes in the plan). Proposed for the next kit version, as an amendment to G10: a frozen check
states its decision rule, its sidedness (with a reason) and the consequence of each outcome; a check
without them is descriptive and gates nothing.

## L33 — participant free text quoted or paraphrased in committed docs (2026-11-10)

**Approved and done in 0.5.0** (Sebastian, 2026-11-16: "Approved, all seven as worded: L37, L29, L32, L33, L34, L35, L36"), with the wording proposed on 2026-11-16, in Data handling; paradigm-analyst and methods-auditor; known-answer tests `kit_tests/test_v05_rules.py`, failing on 03c00f6.

In cold-pressor onboarding, a draft committed file (76fae15, never pushed) quoted Formulario.docx (the
filled protocol form) verbatim, and docs/PARADIGM.md (lines 33 and 38 of Revision 1) paraphrased what
one participant wrote about their sensations. No personal details were included, but single-participant
free text can identify a person, and the paradigm description did not need it. "Data handling" covers
only the recordings. Proposed for the next kit version: a rule that committed files never quote or
paraphrase participants' own answers, comments or free text, or personal details from forms; protocol
facts from such documents are stated in the agent's own words without per-participant content; the
paradigm-analyst and auditor check it.

## L34 — a decision claimed more than its test checks (2026-11-10)

**Approved and done in 0.5.0** (Sebastian, 2026-11-16: "Approved, all seven as worded: L37, L29, L32, L33, L34, L35, L36"), with the wording proposed on 2026-11-16, in new kit rule G26; methods-auditor item 9; 05_audit row; known-answer tests `kit_tests/test_v05_rules.py`, failing on 03c00f6.

In cold-pressor onboarding, D-002 stated filter limits and named alternatives that the cited test did
not check: Round 2 R2-2 (G11; `05_audit.md` l.344) and Round 3 R3-1 (G26; `05_audit.md` l.555). It took
three audit rounds to make the decision text and the test agree. The project already had its own rule
G26 ("Evidence must be able to fail"), but G26 does not say what a decision may claim from its
evidence; that missing clause is why it still took three rounds. Proposed for the next kit version:
promote cold-pressor's project rule G26 into the kit, and add the missing clause: a decision that cites
a test states exactly what the test asserts (the alternatives it rules out and the limits it checks),
and nothing beyond; the auditor compares the entry with the test's assertions.

## L35 — placeholder text logged as a human's answers (2026-11-10)

**Approved and done in 0.5.0** (Sebastian, 2026-11-16: "Approved, all seven as worded: L37, L29, L32, L33, L34, L35, L36"), with the wording proposed on 2026-11-16, in G16; known-answer tests `kit_tests/test_v05_rules.py`, failing on 03c00f6.

In cold-pressor onboarding, Sebastian sent a reply containing unfilled bracketed placeholders for the
human-only questions Q1–Q7 ("[answer / UNKNOWN, …]"); the orchestrator logged the defaults inside the
brackets as his provisional answers in human_contacts.md (it did not write them into PARADIGM.md).
Proposed for the next kit version, as an amendment to G16's logging clause: only an explicit answer
is logged as an answer; template text, placeholders or suggested defaults are logged as "no answer",
and the agent asks once more, grouped.

## L36 — the orchestrator appended and reworded the paradigm-analyst's revision (2026-11-11)

**Approved and done in 0.5.0** (Sebastian, 2026-11-16: "Approved, all seven as worded: L37, L29, L32, L33, L34, L35, L36"), with the wording proposed on 2026-11-16, in paradigm-analyst tools (Edit) and Output; guard (Edit only on docs/PARADIGM.md, no Write once it is committed); `tools/check_frozen_text.py`; onboard step 5; known-answer tests `kit_tests/test_v05_rules.py`, failing on 03c00f6.

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

**Approved and done in 0.5.0** (Sebastian, 2026-11-16: "Approved, all seven as worded: L37, L29, L32, L33, L34, L35, L36"), with the wording proposed on 2026-11-16, in G22; methods-auditor results check; known-answer tests `kit_tests/test_v05_rules.py`, failing on 03c00f6.

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
the real repositories: cold-pressor 5 findings (the PARADIGM lines above), ssvep-apply 0. Attributions
by name and date without a contact number ("Sebastian 2026-11-10: ...") are detected too, as Sebastian
chose on 2026-11-15 ("Yes to the names check via the uncommitted list in .claude/harness.json"): the
names come from the project's local `.claude/harness.json` (`{"sources": {"names": [...]}}`, empty by
default, so the check is off; `--name` adds one), never from the code; a name and an ISO date within 60
characters, either order, in a paragraph with no quote is `unquoted_attribution`; a names list in a
committed harness.json is reported (`committed_names`); `new_project.py --update` keeps the list. With
"Sebastian" on 2026-11-15: ssvep-apply 48 attributions and 2 contacts (both committed after the first
count: D-016 and the kit session's own rerun provenance), cold-pressor 7 attributions and 6 contacts.
Approved approval-line exemption (Sebastian, 2026-11-16: "Exempt approval lines in the standard form
("Approved by <name>, <date>[, <what>]")"): a whole line in that form, by a configured name, is not an
attribution; an unquoted instruction in the same paragraph is still flagged.

**Approved and done in 0.5.0** (Sebastian, 2026-11-16: "Approve the extended L38 wording, applied from
v0.5 on, with no fixes to past commits; the existing findings stay listed in BACKLOG L38"). G15 now reads,
after its first sentences: "A source that is an orchestrator's or a human's instruction is quoted, in its
own words, in the committed file that relies on it; a contact number, a name with a date, or an
`agent_runs/` path is never the only citation. `python -m eegharness.sources check` passes before a
commit." "Sebastian" goes into each project's `.claude/harness.json` `sources.names` when that project
moves to v0.5 (his choice, 2026-11-16), not before.

Existing findings, not fixed (past commits; `--name Sebastian`, 2026-11-16):
- ssvep-apply @ 841e833, 50: `configs/pipeline.json` 23 attributions (source and note fields of the
  settings); `docs/DECISIONS.md` 9 attributions and 1 contact (D-016, "as Sebastian instructed (contact
  9)"); `docs/PARADIGM.md` 7; `docs/COMPUTE.md` 2; `tools/dev_mas_networks.py` 3; `inputs/request.md`,
  `tests/test_p20_settings.py`, `tests/test_positive_control_p20.py`, `tools/exploratory_paired.py` 1
  each; `configs/mas_rerun/20261115_trial_grouped_rerun.provenance.json` `imported.by` 1 contact (written
  by the kit session: "per D-015 and Sebastian's contact 9").
- cold-pressor @ 72860f3, 13: `docs/PARADIGM.md` 5 contacts (l.807, 821, 908, 915, 1015, as above) and 4
  attributions (one is the approval box "Approved by Sebastian: [x]   Date: 2026-11-12", not the
  standard form); `docs/DECISIONS.md` 1 contact and 1 attribution; `docs/COMPUTE.md` 2 attributions.

Earlier proposal (superseded by the approved wording above): Proposed rule wording, as an amendment to G15 (for Sebastian's approval;
template not changed): "A source that is an orchestrator's or a human's instruction is quoted, in
its own words, in the committed file that relies on it; a contact number or an `agent_runs/` path is
never the only citation. `python -m eegharness.sources check` passes before a commit."

## L39 — a core limit is not a thermal limit (2026-11-17)

**Proposed for the next version, not approved** (Sebastian, 2026-11-17: "add its thermal lesson ... and the
proposed G27 to the kit BACKLOG, as proposals for the next version, each citing its source run"). Template
not changed.

Source run: cold-pressor `agent_runs/2026-11-12_apply-pipeline/harness_lessons.md` ("L-thermal", sha256
701422bf0cd5b9211b0ad9a6518a8ca718560132447602c8fb2d515bca4ae4a5; git-ignored), with its temperature log
`h_temps.csv` (one sample per minute, written by the run's step H driver). Committed in the project:
`docs/COMPUTE.md` section "Thread limit after the confirmatory stage of 2026-11-16/17", commit 7384894.

Step H (the confirmatory stage) ran about 8.8 h with 8 threads (`OMP_NUM_THREADS`, `MKL_NUM_THREADS`,
`OPENBLAS_NUM_THREADS` and torch) on the laptop CPU, within the 8-core per-job limit of its COMPUTE.md. The
CPU package temperature was at 95-98 °C in 7 of 528 samples (6 during the 42-part CPU stage at 95.0 °C,
peak 98.0 °C during a sanity null), against the 100 °C critical limit `sensors` reports; GPU peak 87 °C.
The limit was approached, not reached. Sebastian set 4-6 threads for long runs on that machine.

Proposal: the `compute-jobs` skill and the template `docs/COMPUTE.md` gain a "working threads for long runs"
value (set by Sebastian, e.g. 4-6 on a laptop), separate from the per-job core limit, which stays the upper
bound; and every long-run driver logs CPU (and GPU) temperature per minute alongside its job table.

## L40 — a group statistic took units by another method's validity flag (2026-11-17)

**Proposed for the next version, not approved** (same instruction as L39). Template not changed.

Source run: cold-pressor `agent_runs/2026-11-12_apply-pipeline/harness_lessons.md` ("G27", same sha256 as
L39). Committed in the project: `docs/DECISIONS.md` D-011 (commit f312769) and the fix in
`trialpair.conn_group` with known-answer tests at 1, 2 and 3 epochs per class (commit 214888c).

The connectivity group step selected participants by the f3 classifier row's validity. S1 (1 contributing
trial) was left out with no reason row; its debiased-wPLI difference is a structural zero (with a
class-mean stratum, 1 epoch per class leaves a zero residual and 2 epochs per class give wPLI 1 in both
classes; the estimate is defined only from 3). A 2-trial participant would have been kept. Caught by the
orchestrator (20 participants in the step versus 21 in the primary step) and ruled on by the methods-auditor
before any value of that step was opened.

Proposed rule, as the project approved it (project rule G27, approved by Sebastian 2026-11-17, in the
project's local CLAUDE.md; its kit number is set at approval, since project rules start after the kit's):
"A group statistic takes only estimates that exist at that sample size. Extends G20 (a). A per-participant
(or per-unit) estimate enters a group statistic only if its estimator is defined and non-degenerate at that
unit's sample size; the minimum is derived from the estimator and tested (a test at the minimum and one
below it), and inclusion is decided by the estimator's own criterion, never by another method's validity
flag. Every unit left out is listed with its reason in that runner's output."

## L41 — new_project.py without --case leaves no data/ and no inputs/ (2026-11-17)

**Proposed for the next version, not approved** (Sebastian, 2026-11-17: "Record as BACKLOG entries on
v0.6-dev, all \"not approved\""). Template not changed.

Source: imagined-speech-eeg, built with kit v0.5.0 (`.claude/harness.json`, created 2026-11-17T17:02:48-0600;
skeleton commit 5b6e7d2). `new_project.py` creates `inputs/` only inside `copy_inputs`, which returns at once
without `--case`, and never creates `data/`. Its last line and README step 1 still say to put the recordings in
`<dir>/data/raw/` and the material in `<dir>/inputs/`, so `ln -s <recordings> <dir>/data/raw` fails until
`data/` is made by hand (the project's `data/` was made at 17:07, after the build).

Proposal: `new_project.py` always creates `data/` and `inputs/` (harness and control arms, with or without
`--case`). Known-answer test: build without `--case` and assert both folders exist.

## L42 — a template request with placeholders committed as the professor's request (2026-11-17)

**Proposed for the next version, not approved** (same instruction as L41). Template not changed.

Source: imagined-speech-eeg commit e147a9a ("inputs: request") committed `inputs/request.md` with unfilled
`<...>` placeholders, among them an example goal ("compare HI vs HP") that the professor never stated; it was
replaced by the professor's notes verbatim in b71401a two minutes later, before `/onboard` ran. Had onboarding
started, the example goal would have been read as the professor's request.

Proposal: `/onboard` refuses to start while any file in `inputs/` holds a `<...>` placeholder, and names the
file and line. Same family as L35 (placeholder text logged as a human's answers; G16).

## L43 — the project made its own .venv instead of the kit's (2026-11-17)

**Proposed for the next version, not approved** (same instruction as L41). Template not changed.

Source: imagined-speech-eeg created its own `.venv` (17:17), because there is no `python` on PATH (only
`/usr/bin/python3`), and does not use `~/.venvs/eeg-harness-kit`. Nothing in the project records which
interpreter it is meant to use.

To decide: either `new_project.py --venv <path>`, recorded in `.claude/harness.json` and used by the hooks and
agents, or document the per-project `.venv` as the intended setup.

## L44 — recordings on a removable drive (2026-11-17)

**Proposed for the next version, not approved** (same instruction as L41). Template not changed.

Source: imagined-speech-eeg `data/raw` is a symlink to a folder on a removable exFAT drive
(`/media/user/USBDRIVE`, `/dev/sda1`); the recordings take 38 GB, more than the 28 GB free on the local
disk, so they cannot be copied. A long run depends on the drive staying mounted at the same path; an unmount
mid-run would fail parts or, worse, let a part see an empty or missing folder.

Proposal: the profiler records the mount point and filesystem type of `data/raw` (resolved) in DATA_PROFILE;
the compute rules (G22) say a run checks that `data/raw` resolves, and holds the profiled recordings, before
each part, and stops if not.

## L45 — a wording-only audit failure stopped the reader step (2026-11-17)

**Proposed for the next version, not approved** (Sebastian, 2026-11-17: "Add to BACKLOG on v0.6-dev, not
approved"). Template not changed.

Source run: imagined-speech-eeg `agent_runs/2026-11-17_onboarding/` (git-ignored): `log.md` rows "3 Reader"
to "3 Reader audit R2", `05_audit.md`, `cost.jsonl`.

The onboarding reader step (`readers/ebr.py`, D-001) failed audit twice, so the orchestrator stopped as onboard
step 3 requires. Round 1 found code, test and wording faults (G15 citations in tests, G2 missing buggy-variant
test, G26 overclaims in D-001). Round 2 failed on one required fix, wording only: two passages of D-001 claimed
more than the evidence showed (G26, L34): `:93-96` (a transposed memmap "reports a problem", but `load()`
raises ValueError first and the test accepts either) and `:80-82` ("shown for 3 files above", which was
reasoning, not printed output). The reader and its 42 tests were already correct in round 2.

Cost of the step, from `cost.jsonl`: about 7.9 M tokens (agents 6,168,009; orchestrator 1,753,635, the
growth of its running total from 17:18:25 to 18:35:53) and 1.3 h wall (17:18:25 to 18:35:53). The audit R2
call alone took 943,799 tokens and 3,242 s, most of it probably spent waiting on blocked or prompted commands
(its log row).

The orchestrator reported the step's cost as 16.2 M tokens and 3.0 h (Sebastian, 2026-11-17: "The 16.2 M /
3.0 h figure came from the imagined-speech orchestrator's own report, not from me"), and later, after round 3
(L47), as 31.0 M / 9.0 h. 16.2 M is the sum of every `cost.jsonl` row except the last: the `session` rows are
running totals (`log_cost.py`, docstring), so adding rows counts the orchestrator several times. With the 20
rows logged by 18:51:45, the plain row sum is 35.2 M tokens and 10.6 h; the correct total (last line per agent
id and per session, as `log_cost.py`'s summary takes them) is 11.6 M tokens, and the session wall time is
1.6 h.

Proposal:
1. The auditor sorts each required fix as "code/test" or "wording".
2. A failure whose required fixes are all wording gets one fix round, limited to the named lines (checked by
   diff), and does not count toward the two-round limit (onboard step 3, assignment steps).
3. The run log records the tokens and wall time of each round, taken as differences of the running totals.
4. `/onboard`, `/assignment` and `/apply-pipeline` take cost figures only from `cost_report.py` or
   `run_cost.py` (or the `log_cost.py` summary), never by adding up `cost.jsonl` rows.

## L46 — inputs/ text paraphrased a human without a quote (2026-11-17)

**Proposed for the next version, not approved** (same instruction as L45). Template not changed.

Source: imagined-speech-eeg `inputs/request.md`, committed in b71401a, was written by the orchestrating session
outside the project's agents. Line 3 reports Sebastian's words in paraphrase ("Sebastian says they are not the
complete information"), with no quote. The G15 source check flagged it (`inputs/request.md:3:
unquoted_attribution`, in the reader's `03_changes.md`), and the reader step's agents could not fix it because
the file was not theirs.

Proposal: any text in `inputs/` that reports a human's words quotes them verbatim, with the date. `/onboard`
runs this check before it starts, together with L42's placeholder check, and refuses to start while either
fails.

## L47 — the auditor's own suggested wording failed its next audit (2026-11-17)

**Proposed for the next version, not approved** (Sebastian, 2026-11-17: "L47 (not approved)"). Template not
changed.

Source run: imagined-speech-eeg `agent_runs/2026-11-17_onboarding/` (git-ignored): `05_audit.md` (R2 required
fix, R3 table and required fix), `log.md` rows "3 Reader fix R2 (round 3, approved)" and "3 Reader audit R3".

In audit round 2 the methods-auditor's required fix for D-001 `:80-82` proposed wording with a number, "a median
of about 1e-315", that the printed output does not give: the reader printed 6.68569e-315, 7.95758e-315 and
8.021e-315 for the 3 files (`03_changes.md:69,75,80`), about 7-8e-315. The pipeline-engineer copied it into
`docs/DECISIONS.md:82`, and the auditor failed that line in round 3 under G26/G7, writing "**The wrong figure is
mine.** My round-2 required fix suggested 'a median of about 1e-315', and the engineer copied it." Round 3
(510,079 tokens, 104 s for the audit) was caused by the auditor's own text, and its failure stopped the step
again.

Proposal:
1. Wording an auditor suggests in a required fix is held to G7 and G26 like any other text: a number in it is
   quoted from printed output with the line it comes from, or the suggestion gives no number.
2. An audit failure on text the auditor itself proposed is recorded in the audit and the run log as an auditor
   error. (How it counts toward the round limit is to be decided with L45.)

## L48 — the template's approval line fails the kit's own sources check (2026-11-19)

**Proposed for the next version, not approved** (Sebastian, 2026-11-19: "L48 (not approved)"). Template not
changed.

Source: imagined-speech-eeg commit 23f8a5d (PARADIGM revisions 2-3, approved) changed the template line
`Approved by Sebastian: [ ]   Date:` to `Approved by Sebastian, 2026-11-19, [x] docs/PARADIGM.md draft with
Revisions 1-3`, because the ticked template form fails G15's check. Reproduced with the kit at
ed49d0d: a committed `docs/PARADIGM.md` holding `Approved by Sebastian: [x]   Date: 2026-11-19`,
with `sources.names` ["Sebastian"], gives `docs/PARADIGM.md:3: unquoted_attribution` (rc 1). The check accepts
only `Approved by <name>, <date>[, <what>]` as a whole line (`tools/eegharness/sources.py:53-54`, the form
set on 2026-11-15); the template boxes in `template/agent_runs/_templates/onboarding/PARADIGM.md:6` and
`template/agent_runs/_templates/02_plan.md:6` predate it.

The two forms also diverge from the gates: `/assignment` (`SKILL.md:15`, `:61`), `/apply-pipeline`, `/onboard` and
the pipeline-engineer look for the literal "Approved by Sebastian: [x]", which the reworded project line no
longer contains.

Proposal: one approval form, used by the template boxes, the check and every gate that reads them (e.g. the
template box becomes `Approved by Sebastian, <date>, [ ] <what>`, or the check accepts the ticked box with a
date). Known-answer test: a committed file with the ticked template line (date filled) passes
`sources check`, the same line unticked or undated does not count as an approval at the gates, and the gate
strings match the template form.

## L49 — a part's attempt counter missed two runs killed from outside (2026-11-23)

**Proposed for the next version, not approved** (Sebastian, 2026-11-23: "Add L49–L55 to BACKLOG in the L39–L48
format"). Template not changed.

Source run: imagined-speech-eeg `agent_runs/2026-11-19_hi-word-decoding/` (git-ignored): `log.md` rows "Stage H
CPU B_loro (interrupted)" (2026-11-20) and "(interrupted again)" (2026-11-21); `05_audit.md` note C5. Outputs:
`outputs/stage2/B_loro_cbd61c9b07c3_ec60d9b/parts/S2_HI/classical/`.

Claude Code stopped the batch shell twice for critically low system memory while S2_HI classical (B_loro) was
running; the third start completed. The part folder holds three logs, all numbered as the first attempt
(`attempt_20261120T172833Z_1.log`, `attempt_20261121T050033Z_1.log`, `attempt_20261121T185634Z_1.log`), and
`part_status.json` says `"n_attempts": 1`. Cause: `eegpipe.runner.stage` writes `part_status.json` and
`attempts.jsonl` only after the job returns (`tools/eegpipe/runner/stage.py:318-347`), so a stage process killed
during a job leaves no record and the next start counts from the old status. `retry.max_attempts` never saw the
two kills. The auditor caught it (C5); no number came from the partial folders (no `results.json`).

Proposed wording (eegpipe, G25): "Before a job starts, the stage runner records the attempt (status `running`,
attempt number, start time) in `part_status.json` and `attempts.jsonl`. A part found `running` with no live
stage process is recorded as `interrupted` before anything else runs; interrupted attempts count in
`n_attempts` and toward `retry.max_attempts`, and the index lists them."

Known-answer test: start a stage on a synthetic part whose job sleeps, kill the stage process group (SIGKILL)
during the job, start the stage again: `n_attempts` is 2, the first attempt is `interrupted`, the log names end
in `_1` and `_2`; with `max_attempts` 2 and two kills the part is terminal. Fails on b361f81 (`n_attempts` 1,
both logs `_1`).

## L50 — the auditor's hook blocks the checks the template tells it to run (2026-11-23)

**Proposed for the next version, not approved** (same instruction as L49). Template not changed.

Source run: imagined-speech-eeg `agent_runs/2026-11-19_hi-word-decoding/05_audit.md:280-283` (results check r1:
"BLOCKED for me by the hook: `.venv/bin/python -m eegharness.outputs check ...`") and `:100` (`eegharness.sources
check` blocked); `log.md` row "Results check r1" (the auditor did not route around it and raised it with
Sebastian; the orchestrator ran the check under contact #10). Also onboarding `2026-11-17_onboarding/05_audit.md:67`
(`sources check` blocked).

G22 (`template/CLAUDE.md:252`) and `template/.claude/agents/methods-auditor.md:92-93` say the auditor runs
`python -m eegharness.outputs check` on the outputs a result cites; G15 needs `eegharness.sources check`. The
auditor's allowlist in `template/.claude/hooks/guard.py:547-563` permits only pytest, `compare_runs` and `numbers
check` among Python commands, so both checks are refused ("`python` is not on the auditor's list").

Proposed change: the auditor's allowlist adds `python -m eegharness.outputs check <paths>` and `python -m
eegharness.sources check [paths]` (both read only); no other subcommand of those modules.

Known-answer test (`check_auditor_bash`): both commands, with `.venv/bin/python` and `python`, pass; `python -m
eegharness.outputs` with any other first argument, and either command with a redirect to a file, are refused; a
test also asserts that every `python -m ...` command named in `methods-auditor.md` passes the hook. Fails on
b361f81 (both blocked).

## L51 — the orchestrator counted by hand (2026-11-23)

**Proposed for the next version, not approved** (same instruction as L49). Template not changed.

Source run: imagined-speech-eeg `agent_runs/2026-11-19_hi-word-decoding/log.md` row "Correction (orchestrator)":
the orchestrator recounted temperature batches from `outputs/stage2_logs/batches.tsv` by hand ("Pinned total
20 of 41, not 21 as told to Sebastian on 2026-11-23"); both the first count (21, sent to Sebastian) and the
correction were hand counts. The results-analyst caught the first miscount (A2); `05_audit.md` note C4 (G23): "a
count sent to Sebastian should come from a tool or be marked as a hand count". The count could not go through
`eegharness.numbers`, which reads only comma-separated files (L53, item 2).

Proposed wording (extends G11/G23 to the orchestrator): "A number the orchestrator writes in `log.md` or sends
to Sebastian that is derived from outputs (a count, sum, maximum, difference) comes from `eegharness.numbers`
or a committed, tested tool, cited by key or command; when no tool can derive it yet, it is sent marked `(hand
count, not derived)` with the tool gap named, and never corrected by another hand count."

Known-answer test: the template's G23 contains the wording; with L53, a spec counting the rows with
`temp_max >= 95` in a synthetic tab-separated batches file gives the planted count. The text assertion fails on
b361f81.

## L52 — a project wrapper for the outputs check split paths on whitespace (2026-11-23)

**Proposed for the next version, not approved** (same instruction as L49). Template not changed.

Source: imagined-speech-eeg commit 46f18c9 (`outputs_check.py`, a project wrapper that runs `eegharness.outputs
check` on a list of folders and records the result in a versioned output) reads the list with
`read_text().split()` (`outputs_check.py:35` at 46f18c9), so a folder name with a space becomes two paths. The
methods-auditor noted it as non-blocking (results check r3, `05_audit.md:534-536`): no listed path had a space
(grep count 0). The risk is real in this project: the data folder is "Habla imaginada con 5 palabras". The
wrapper existed because the kit's `outputs check` takes paths only as arguments (369 folders here) and does not
record its own result (`tools/eegharness/outputs.py:214-218`); the first run fed a stdin script, whose provenance
command was `.venv/bin/python -` (`05_audit.md:485-487`, N3).

Proposed change: `python -m eegharness.outputs check --paths-file <file>` (one path per line, spaces kept, blank
lines ignored) and `--record <out>` (writes the output, the path list and the exit code into a new versioned
folder with provenance and compute time, G9/G22), so no project writes its own wrapper.

Known-answer test: a paths file listing a folder named `run with spaces/20261123T000000Z_abc1234` (with
provenance and compute time) gives "1 output folder(s), 0 problem(s)", and a whitespace-splitting variant fails
the same test; `--record` writes `check_output.txt`, `paths.txt` and a provenance whose command is the real
command. Fails on b361f81 (no `--paths-file`).

## L53 — six report numbers left blocked by eegharness.numbers (2026-11-23)

**Proposed for the next version, not approved** (same instruction as L49). Template not changed.

Source run: imagined-speech-eeg `agent_runs/2026-11-19_hi-word-decoding/06_results.md` section "Derived numbers
needed" (6 items, READY with them blocked by the auditor's ruling). Five are blocked by missing operations:
item 1 counts failing rows across many `gates.csv` files ("no multi-file aggregate; needed: a `csv_glob`
operand"); item 2 counts in `outputs/stage2_logs/batches.tsv` ("reads comma-separated files only; needed: a tab
delimiter option"; also L51); item 3 compares CPU seconds with the plan's hours ("without a seconds-to-hours and
ratio operation"); item 5 counts network parts at the maximum epoch over many files; item 6 checks that
`n_epochs`/`n_units` agree across `results.json` files of four roots. Item 4 is not a tool gap (the value is
empty in the output). Correction to the item 3 text: `ratio` exists (`tools/eegharness/numbers.py:52-53`); the
missing piece is unit scaling (seconds to hours) of an operand.

Proposed change (`eegharness.numbers`): (a) `"delimiter": "\t"` on a csv operand (or `.tsv` by extension);
(b) `"glob"` operand: the rows of every matching file, each row tagged with its file, for `count`, `sum`,
`min`, `max`, `mean` and a new `all_equal`; zero matching files refuse; (c) op `scale` (a × factor, e.g.
1/3600, with the unit `h`); (d) a `json` operand (a dotted key in one or many JSON files). Each recorded with
the SHA-256 of every file read.

Known-answer tests: a TSV with planted values gives the planted count; three CSVs matched by a glob give the
planted row count and sum, and a variant reading only the first file fails; 7200 s scaled by 1/3600 gives
"2.0 h"; `all_equal` over three JSON files is 1 when equal and 0 when one differs. All fail on b361f81.

## L54 — no memory limit in COMPUTE.md (2026-11-23)

**Proposed for the next version, not approved** (same instruction as L49). Template not changed.

Source run: imagined-speech-eeg `docs/COMPUTE.md` (from the skeleton, 5b6e7d2) sets `cpu_max_minutes`,
`gpu_max_minutes` and `gpu_device`, and no memory figure; the template (`template/docs/COMPUTE.md`) has none
either. B_loro batches of 2 parts were stopped twice by Claude Code for critically low memory (L49; `log.md` rows
of 2026-11-20 and 2026-11-21) on a 23 GB machine with desktop applications open; a B_loro classical part peaked
at 5.50-5.71 GB max RSS in development (`log.md` row "F Dev classical (collected)", from `/usr/bin/time -v`).
The third start ran after Sebastian closed the applications ("I closed the apps, continue").

Proposed wording (G22, COMPUTE.md, `compute-jobs` skill): "`docs/COMPUTE.md` sets `memory_max_gb`, the memory
the orchestrator's jobs may use together (set by Sebastian). The plan states each part's peak memory, measured
in the development run (maximum RSS); a batch runs b parts at once only if b × peak fits `memory_max_gb`, and
before each batch the driver checks that available memory is at least that sum, and waits or stops if not."

Known-answer test: the template COMPUTE.md has `memory_max_gb`; a batch-size helper (`eegharness.compute`, or in
the skill's driver) returns b = 3 for peak 5.7 GB and 18 GB, refuses b = 4, and refuses to start when available
memory is planted below b × peak. Fails on b361f81.

## L55 — test suites take longer than G2's minute (2026-11-23)

**Proposed for the next version, not approved** (same instruction as L49). Template not changed.

Source run: imagined-speech-eeg `agent_runs/2026-11-19_hi-word-decoding/log.md`: 142 passed in 107 s and in
112.6 s (plan audit rounds), later 194-200 passed in 73-85 s (4 torch tests skipped). G2 says `pytest tests/`
"runs on CPU in about a minute with no real data" (`template/CLAUDE.md`, G2). The suite is run in every audit
round and before every commit, so its time multiplies.

To decide:
(a) a `slow` marker registered by the template's `tests/conftest.py`, deselected by default; the default run
stays under a minute, the full suite (`-m ""`) runs before every freeze and commit and in the auditor's check;
G2 names both; or
(b) revise G2: "the suite runs on CPU with no real data; its time is reported in each handoff; over 2 minutes,
the slowest tests are moved behind a `slow` marker".

Known-answer test (for a): in a synthetic project, a test marked `slow` is deselected by `pytest tests/` and run
by `pytest tests/ -m ""`; the template conftest registers the marker (no unknown-marker warning). Fails on b361f81.

## L56 — a plan's runtime rule relied on timings the code does not record (2026-11-23)

**Approved for 0.6.0** (Sebastian, 2026-11-24: "L56 is missing. Add it to BACKLOG and implement it in 0.6.0 (I
approved it on 2026-11-23)"), with the wording below; done in 0.6.0. Known-answer tests
`kit_tests/test_v06_rules.py::test_l56_*`, failing on 7ad1c35.

Source run: imagined-speech-eeg `agent_runs/2026-11-19_hi-word-decoding/` (git-ignored): `log.md` section
"Incident: GPU runtime rule relied on timings the code does not record (2026-11-23, harness lesson L56)" and
row "GPU smoke" (2026-11-20); `human_contacts.md` contact #8 and its answer ("(a): run the 30-epoch smoke"),
with Sebastian's confirmed note: "the plan's T_s rule relied on timings the code does not record, missed by
both plan audits".

The approved plan's GPU runtime rule (`02_plan.md:776-808`) bounds each network part as T_s = t_in + 3 x F_s x
150 x t_e x N_s/100 and states that the GPU smoke records the per-epoch time t_e and the network-input time
t_in. The code written in step E records neither: `loro/methods.py:297-308` writes only the part's total
compute time (`record_compute_time`). At the first GPU smoke the bound could not be computed; contact #8
offered a longer smoke, a timeout-based run, or new code; Sebastian chose a 30-epoch smoke and t_e from the
slope. Plan audit round 2 (`02b_plan_audit.md:347`) accepted "measured t_in, t_e from the GPU smoke", round 3
(`:480`) checked the formula and its arithmetic, and the step-E code audit passed G22: none checked that the
code produces the rule's inputs.

Approved wording (plan audit): "Every quantity a plan's gate or decision rule uses must be named with the code
path and output field that records it; the plan auditor checks that the field exists."

Done: the plan template's section "Gate and rule inputs" (Quantity | Used by | Code path | Output field);
`tools/check_plan_fields.py` (shipped in `.harness/tools/`): MISSING when the named code does not write the
field (in the named line range), INCOMPLETE without a path or field, NEW for code the plan adds (a failure
with `--final` in the change audit), and `--output` to require the field in a real output; the
methods-auditor runs it in the plan audit and, with `--final`, in the change audit (its hook allows it); rows
in `02b_plan_audit.md`, the apply-pipeline audit rows and `05_audit.md`.
