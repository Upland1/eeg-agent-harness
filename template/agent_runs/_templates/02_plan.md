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

## What Sebastian will run

<!-- Exact commands, where (local or Colab), and expected runtime.
Agents never run these. -->

```bash

```

Outputs to drop into this folder (each a versioned folder `<out>/<UTC>_<commit>/`, G9):

## Sources

<!-- Every source cited above: papers (authors, year, title, DOI/URL, from
01_brief.md), rules, audit findings, files. -->

1.

## Success criteria

<!-- How we'll know it worked, stated before seeing results. -->