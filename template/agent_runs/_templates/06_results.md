# 06 · Results

Status: DRAFT
Author: results-analyst
Reads: 02_plan.md, CLAUDE.md, the logged outputs of the runs

## Sources

<!-- Exact files used: CSV paths, console logs. Numbers below come verbatim from
these; nothing is estimated. -->

Data source of these results (files, participant, session, preprocessing, protocol):
Data source of the comparison numbers:
Output folders (versioned, G9) and the regression check against the previous run, if any
(`python -m eegharness.compare_runs`, its exit status and summary):

<!-- Compare like with like. If the comparison is with the reference paper, state
how its data, preprocessing and evaluation protocol differ from ours before the
table. -->

## Per-participant / per-session results

| Participant | Session | File(s) | Condition(s) | Metric(s) | Chance level | Comparison | Δ |
|---|---|---|---|---|---|---|---|
| | | | | | | | |

## Stochastic models (G18) and the significance budget (G19)

<!-- Per participant: mean ± SD over seeds (n seeds), training accuracy, chance level for the
number of test trials. Primary comparisons from 02_plan.md with their corrected p; every other
comparison labelled exploratory. A difference smaller than the seed spread: "no difference
shown". Every derived number from `eegharness.numbers` (G23): its text followed by its key,
e.g. `4.2 pp [num:gain_f1_pp]`; numbers the tool cannot derive go under "Derived numbers
needed" with Status: BLOCKED. -->

Numbers spec (committed): `configs/numbers/<run>.json` @ <commit>
numbers.json: `outputs/numbers/<UTC>_<commit>/numbers.json`
`eegharness.numbers check` (last line): 

| Participant | Model / configuration | Test metric mean ± SD (n seeds) | Train accuracy | Chance level | Primary or exploratory |
|---|---|---|---|---|---|
| | | | | | |

Derived numbers needed:

## Against the success criteria in 02_plan.md

| Criterion | Met? | Evidence |
|---|---|---|
| | | |

## Rejection and data quality (G14)

<!-- Required. Per participant and session: units in, units rejected per criterion
(count and %), units kept, from the run's logged output. A high rejection rate is an
anomaly: diagnose it before interpreting the results above. -->

| Participant | Session | Units in | Rejected (criterion: n, %) | Kept | Output file |
|---|---|---|---|---|---|
| | | | | | |

## Regressions and anomalies

<!-- Anything worse than expected, any gain that looks too good (CLAUDE.md:
assume a bug until tests and audit say otherwise), any change in accepted or
rejected epoch counts. -->

## Summary for the professor

<!-- At most 150 words, academic tone, per-participant numbers, limitations
stated. Sebastian edits before presenting. -->
