# 02b · Plan audit

Status: DRAFT
Author: methods-auditor
Reads: 02_plan.md, 01_brief.md, docs/PARADIGM.md, docs/DATA_PROFILE.md, CLAUDE.md, the code the plan touches

The plan is audited **before any code exists**, so that a design error is fixed in the
plan rather than after it has been built. Sebastian sees this file together with the plan.

## Round 1

Verdict: PASS / FAIL

### Checklist

| Rule | Result | Evidence (plan section, `path:line`, source) |
|---|---|---|
| G1 Unseen-sample argument written and sound (time overlap, shared trials/blocks, sessions, participants) | PASS / FAIL / CONCERN / N/A | |
| G4 Statistics: assumptions hold for this data; resampling unit stated | | |
| G13 Exchangeability unit named and argued from event timing vs epoch length; nulls can draw the observed labelling | | |
| G10 Every check, gate, threshold and selection rule is fixed in the plan before it touches real data | | |
| G12 Every new measurement or statistic has a known-answer test, and a false-positive-rate test if it is a test statistic, planned before its real-data run | | |
| G14 Quality, rejection and label-sanity claims planned per participant/session, with comparison set and absolute measures | | |
| G17 Training inside the training fold: validation, normalization, augmentation; test transforms label-free; inherited defaults listed and set | | |
| G18 Seed scheme, at least 3 seeds, paired A/B | | |
| G19 Primary configurations fixed; test, unit, alpha, correction; development data kept out of the confirmatory test | | |
| G20 Connectivity: bias, phase method, matched baseline, unit permutation, separate criteria fixed before results | | |
| G21 Filtering on continuous data; sampling rate and channels from the file, by name | | |
| G22 Each job: device, runtime, smoke test, resumable folds, who runs it under docs/COMPUTE.md | | |
| G24 The plan configures `eegpipe` only through `configs/pipeline.json`; any gap is a new project module with tests | | |
| G25 Development and confirmatory data named and disjoint; selection rule label-free and seeded; freeze before any confirmatory run | | |
| Method checklists (deep-learning / connectivity / compute-jobs) applied, if the plan uses them | | |
| G9 / G11 Outputs versioned; every derived number planned to come from a committed script | | |
| G5 Parameters explicit, with source | | |
| G6 Every row of "Changes" has a source that exists | | |
| "Typical mistakes" of docs/PARADIGM.md addressed | | |
| Success criteria stated before results, and measurable | | |

### Required changes to the plan

<!-- Only if FAIL. Each names the rule and the plan section. The orchestrator revises
02_plan.md (a "## Revision N" note at its end) and asks for Round 2. -->

1.

### Non-blocking notes

### Sources spot-check

<!-- At least one source cited in the plan, opened and confirmed. -->
