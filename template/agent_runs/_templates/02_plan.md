# 02 · Plan

Status: DRAFT
Author: orchestrator
Reads: 00_assignment.md, 01_brief.md, CLAUDE.md
Approved by Sebastian: [ ]   Date:

## Goal

<!-- One sentence. -->

## Branch

## Data source

<!-- Which participants, sessions and files (paths relative to the data
folder), which conditions (as named in docs/PARADIGM.md), which
preprocessing and segmentation settings, which evaluation protocol. Results are only
comparable across runs that use the same source (CLAUDE.md G3). -->

## Scope

**In:**

**Out:**

## Changes

<!-- Source: where the solution came from — 01_brief.md [n], CLAUDE.md Gn,
05_audit.md finding, code path:line, Sebastian's request, or [own] with a
reason. Formats: .claude/skills/cite-sources/SKILL.md (G6). Name the
reference implementation the engineer should study for each change. -->

| File | NEW / MODIFIED | What | Why | Source |
|---|---|---|---|---|
| | | | | |

## Evaluation unit and exchangeability (G1, G13)

<!-- What counts as an unseen sample; the exchangeable unit of every evaluation and
resampling procedure (epoch, trial, block, session, participant), argued from event
timing vs epoch length (overlap, shared trials or blocks). For a permutation test: what
is permuted, and that the observed labelling is in the null set. "N/A" with a reason if
there is no evaluation. -->

## Checks frozen before real data (G10, G12, G14)

<!-- Every gate, screening rule, threshold, quality or label-sanity check this run will
apply to real recordings: its code path, threshold, the known-answer test (and
false-positive-rate test for a test statistic) that must pass first, and how results are
reported per participant/session with a comparison set. -->

| Check | Threshold / rule | Test that must pass first | Reported per | Comparison set |
|---|---|---|---|---|
| | | | | |

## Gate and rule inputs (L56)

<!-- Every quantity a plan's gate or decision rule uses must be named with the code path and output field that records it; the plan auditor checks that the field exists. One row per quantity that any gate,
runtime bound, selection or decision rule above or below uses (a timing, a count, a statistic, a flag):
the code that writes it (`file.py` or `file.py:first-last`; code this plan adds is named too) and the
field of its output (JSON key or CSV column). Checked by
`python .harness/tools/check_plan_fields.py agent_runs/<run>/02_plan.md`. -->

| Quantity | Used by | Code path | Output field |
|---|---|---|---|
| | | | |

## Training, seeds and inherited defaults (G17, G18)

<!-- Only if a model is trained (otherwise N/A). Checklist: .claude/skills/deep-learning/SKILL.md.
Validation split (from the training fold, grouped by the G13 unit); normalization (per sample,
or fitted on the training fold); augmentation (training only, class-preserving); every
transform applied to test samples computable without their labels; test-time normalization
labelled; seed scheme and number of seeds (at least 3); every default of ported or library
code listed and set. -->

| Default (ported / library code) | Library value | Value set here | Why |
|---|---|---|---|
| | | | |

## Significance budget (G19)

<!-- Before results. Development data (participants/sessions/runs used to build, tune or
debug) vs confirmatory data, and why they do not overlap. The fixed set of primary
configurations; the comparisons that may be called significant, their test and unit (G13),
alpha, family-wise correction (e.g. Holm); chance level for the number of test trials.
Everything else is exploratory. "N/A" with a reason if nothing will be tested. -->

Development data:
Confirmatory data:

| Primary comparison | Test, unit | alpha | Correction |
|---|---|---|---|
| | | | |

## Methodological risks

<!-- For each rule this change could break, say how the plan prevents it. -->

| Rule | Risk | Prevention |
|---|---|---|
| G1 | | |
| G13 | | |

## Tests required

<!-- Synthetic only. Each test states its known answer and tolerance. -->

| Test | Simulated input | Expected result | Tolerance |
|---|---|---|---|
| | | | |

## Runs (G22)

<!-- One row per job. Device: cpu / local GPU / remote. Runtime estimated from the smoke
test. Who: "orchestrator" only if it fits the limit for its device in docs/COMPUTE.md and its
committed smoke test passed; otherwise "Sebastian". Checklist: .claude/skills/compute-jobs/SKILL.md. -->

| Job | Exact command | Device | Expected runtime (basis) | Seeds | Smoke test | Output folder | Who |
|---|---|---|---|---|---|---|---|
| | | | | | | | |

Outputs Sebastian drops into this folder (each a versioned folder `<out>/<UTC>_<commit>/`, G9):

## Sources

<!-- Every source cited above: papers (authors, year, title, DOI/URL, from
01_brief.md), rules, audit findings, files. -->

1.

## Success criteria

<!-- How we'll know it worked, stated before seeing results. -->