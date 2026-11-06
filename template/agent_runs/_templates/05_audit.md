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
| G17+ Rules added from later incidents | | |
| 02b_plan_audit.md required changes were made | | |
| Tests cover every change in 03 | | |
| Changes match 02_plan.md | | |

### Commands run

<!-- Every command you ran (git diff/show/log, pytest, compare_runs) and a summary of its
output. "Verified" means a command here, not another agent's claim. -->

### Required fixes

<!-- Only if FAIL. Each fix names its rule and exact location. -->

1.

### Sources spot-check

<!-- Open at least two cited sources from 03/04 and confirm they say what the
handoff claims (paper section, docs page, code lines). List what was
checked. -->

### Non-blocking notes

<!-- On a fix round, append "## Round 2" with the same structure.
After two failed rounds, set Status: BLOCKED and hand to Sebastian. -->