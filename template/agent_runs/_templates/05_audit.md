# 05 · Audit

Status: DRAFT
Author: methods-auditor
Reads: 02_plan.md, 03_changes.md, 04_tests.md, every changed file, CLAUDE.md

## Round 1

Verdict: PASS / FAIL

### Checklist

| Rule | Result | Evidence (`path:line`) |
|---|---|---|
| G1 No evaluation data reaches training; unseen-sample argument written and sound | PASS / FAIL / N/A | |
| G2 Known-answer synthetic test for every new component | | |
| G3 Per-participant/session reporting, data source, imbalance-aware metric, chance level | | |
| G4 Honest statistics, resampling unit stated | | |
| G5 Explicit parameters, no inherited defaults | | |
| G6 Every change and test cites a source that exists and says what is claimed | | |
| G6 Copied lines marked `# adapted from [n]`, license compatible | | |
| G7 Every number traces to a logged run | | |
| G8 Decisions recorded in docs/DECISIONS.md | | |
| G9 Outputs in new versioned folders with provenance; nothing overwritten | | |
| G10 Checks and thresholds committed before their first real-data run; later changes recorded as deviations | | |
| G11 Every derived number comes from a committed script's logged output | | |
| G12 Known-answer tests before the first real-data run; false-positive-rate test on noise for each test statistic | | |
| G13 Exchangeability unit stated and argued; nulls can draw the observed labelling | | |
| G14 Quality/rejection/label claims per participant and session, with comparison set and absolute measures | | |
| G15 No committed file references an uncommitted file (`agent_runs/`, scratchpads) | | |
| G16 Questions to Sebastian list the written sources checked | | |
| G17 Training and preprocessing inside the training data; test transforms label-free; defaults set explicitly | | |
| G18 Seeds set before each model; at least 3 seeds; per-seed values saved; train accuracy and parameter count | | |
| G19 Only primary comparisons can be significant; development data not in the confirmatory test | | |
| G20 Connectivity estimator and statistics (checklist items) | | |
| G21 Continuous filtering; metadata from the file; channels by name | | |
| G22 Smoke test committed; resumable folds with configuration; runtimes and device | | |
| G23 Derivations through committed, tested tools; no paths outside the repository | | |
| G24 `eegpipe/` untouched; gaps are new project modules with tests | | |
| G25 Confirmatory outputs from the frozen commit only; selection label-free; refusals logged | | |
| G26 Each decision claims only what its test asserts; evidence could have failed | | |
| L56 `check_plan_fields.py --final` on 02_plan.md: every gate/rule input written by the code (and in the smoke output) | | |
| G27 Group statistics take only estimates defined at the unit's sample size; units left out listed | | |
| G28+ Rules added from later incidents | | |
| 02b_plan_audit.md required changes were made | | |
| Tests cover every change in 03 | | |
| Changes match 02_plan.md | | |

### Commands run

<!-- Every command you ran (git diff/show/log, pytest, compare_runs) and a summary of its
output. "Verified" means a command here, not another agent's claim. -->

### Required fixes

<!-- Only if FAIL. Each fix names its rule and exact location, and its kind: code/test, wording, or auditor error
(a failure on wording this audit proposed in an earlier round). A suggested wording quotes every number from
printed output with its line, or gives none (G7/G26). -->

| # | Rule | Location | Kind (code/test, wording, auditor error) | Fix |
|---|---|---|---|---|
| 1 | | | | |

### Sources spot-check

<!-- Open at least two cited sources from 03/04 and confirm they say what the
handoff claims (paper section, docs page, code lines). List what was
checked. -->

### Non-blocking notes

<!-- On a fix round, append "## Round 2" with the same structure. After two failed rounds, set Status: BLOCKED
and hand to Sebastian; a wording-only round and an auditor error do not count toward the two, but every round
counts toward the hard limit of 4 per step (L45, L47). -->

## Results check (after 06_results.md, G23)

Verdict: PASS / FAIL

| Number in 06_results.md | Found verbatim in (output file:line, or committed tool + its output) | OK |
|---|---|---|
| | | |

`eegharness.numbers check` on 06_results.md (last line; any problem → FAIL):
Derived numbers without a [num:key]: (none / list → FAIL)
Paths outside the repository cited in the run's handoffs: (none / list → FAIL)
G18 seeds and spread reported: 
G19 only primary comparisons called significant: 