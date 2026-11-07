---
name: connectivity
description: Checklist for any plan, code, test, audit or result that estimates functional connectivity (coherence, PLV, wPLI, imaginary coherency, Granger/PDC, correlation) or tests it statistically (permutation tests, FDR, network-based statistic, graph measures). Read it when a plan uses connectivity; each agent applies its part.
---

# Connectivity checklist (CLAUDE.md G20, G13, G12, G21)

Every item is answered with evidence (`path:line`, plan section or output file). The kit
gives unit-level permutation (`eegharness.permutation`) and grouped splits; estimators,
FDR and NBS are project code, built and tested as below.

## Plan (orchestrator; checked in 02b_plan_audit)

- [ ] **Estimator and its bias.** Which estimator, on which segments, at what sample
  size. Conditions compared at matched sample sizes, or estimated once per condition over
  concatenated data. Never average per-segment estimates of a biased estimator (G20 a).
- [ ] **Phase.** Taken by a method valid for the segment length (e.g. from the
  cross-spectral density); filtering on continuous data before cutting (G20 b, G21).
- [ ] **Baseline.** Same band, same estimator, same channels as the stimulus condition.
- [ ] **Permutation unit.** Whole trials/blocks/sessions (G13), observed group sizes kept;
  the observed labelling is in the null; number of permutations resolves α
  (smallest p = 1/(n+1)).
- [ ] **Criteria.** Global statistic, edge-wise FDR and component-wise NBS reported as
  separate criteria; FDR level, NBS threshold and component measure fixed before results;
  a threshold sweep only as sensitivity.
- [ ] **Directed measures** symmetrized (estimate and null) before undirected statistics.
- [ ] **Channels.** Embedded by name, missing channels as NaN, before averaging across
  participants.
- [ ] **Subgroups** defined independently of connectivity (no circular responder sets).
- [ ] **Confounds.** Power/SNR changes that can drive the connectivity change are measured
  and reported alongside.
- [ ] **Graph models.** If connectivity feeds a classifier or GNN: everything fitted
  in-fold (G17); also apply the `deep-learning` checklist.

## Tests (synthetic-tester; all before any real-data run, G12)

- [ ] **Bias on noise:** independent noise at the sample size used → the estimator's
  value is reported and the plan's comparison removes it (matched sizes or concatenation).
- [ ] **Planted coupling:** a known phase lag / coupling between two channels is recovered
  where planted and not elsewhere.
- [ ] **Edge immunity:** corrupting the first and last samples of each segment barely
  changes a phase estimate (tolerance stated).
- [ ] **Layout:** matrix indices (directed i→j vs j→i, upper triangle order, coefficient
  slicing) recover a known synthetic system; the test fails on the swapped/contiguous
  variant (G2).
- [ ] **Permutation FPR:** on pure noise the test rejects at about α (binomial tolerance),
  using unit-level permutation.
- [ ] **FDR:** known-answer on a hand-computed set of p-values.
- [ ] **NBS:** a planted connected component is found with small p; pure noise gives
  p ≥ α at about the nominal rate.

## Audit (methods-auditor)

FAIL if: averaged per-segment estimates of a biased estimator; window-level permutation
when windows share a trial; criteria merged into one flag; thresholds chosen after seeing
results; directed estimates in undirected statistics; circular subgroups; any test above
missing before the real-data run.

## Results (results-analyst)

Per participant: each criterion separately (global p, FDR edges, NBS component with
size and p), the permutation count, the bias reference, and cells that change between
permutation counts marked inconclusive.
