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
| G9+ Rules added from earlier incidents | | |
| Tests cover every change in 03 | | |
| Changes match 02_plan.md | | |

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