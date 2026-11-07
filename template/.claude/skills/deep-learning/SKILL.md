---
name: deep-learning
description: Checklist for any plan, code, test, audit or result that trains a neural network (CNNs such as EEGNet or ShallowConvNet, graph neural networks, any model trained by gradient descent) - in-fold training, seeds and spread, significance budget, inherited defaults. Read it when a plan uses such a model; the orchestrator, pipeline-engineer, synthetic-tester, methods-auditor and results-analyst each apply their part.
---

# Deep-learning checklist (CLAUDE.md G17, G18, G19, G22)

Every item is a yes/no question with evidence (`path:line`, plan section or output file).
The plan answers it; the engineer implements it; the tester tests it; the auditor checks
it in the plan audit and the change audit; the results-analyst reports it.

## Plan (orchestrator; checked in 02b_plan_audit)

- [ ] **Units and splits.** Outer split grouped by the G13 unit (`eegharness.splits`).
  Validation for early stopping / model selection is drawn from the *training* fold,
  grouped the same way (`inner_split`). Test fold and held-out participants never seen.
- [ ] **Normalization.** Per-sample (no statistics across samples) or fitted on the
  training fold; which one, stated. Test-time normalization only if labelled as such, with
  the source of its statistics (G17 f).
- [ ] **Label-free test transforms.** Every transform applied to a test sample can be
  computed without its label (G17 e).
- [ ] **Augmentation.** Training fold only, on the fly, class-preserving (mixing only
  within a class). Off for validation and test data.
- [ ] **Inherited defaults.** List every default of the ported or library code (loss
  weights and label smoothing, class priors, augmentation probabilities, optimizer and
  scheduler settings, epochs, patience, segment lengths, dropout). Each one set explicitly
  in config; any that contradicts the plan is changed or the plan says why (G17 i, G5).
- [ ] **Pooled participants.** Group ids unique across participants; one channel set,
  chosen by name; nothing from the held-out participant in any fit (G17 g).
- [ ] **Seeds.** Scheme written (e.g. `eegharness.seeds.fold_seed(base, repeat, fold)`),
  set before building each model, data-loader generator seeded; at least 3 seeds per
  configuration; A/B arms share seeds and folds (G18).
- [ ] **Budget.** Primary configurations listed (a fixed set), the test and its unit, α,
  family-wise correction; every other configuration exploratory. Development data named
  and kept out of the confirmatory test (G19).
- [ ] **Chance level** for the actual number of test trials (`eegharness.chance`).
- [ ] **Compute.** Device, expected runtime per job, smoke test, resumable folds, who runs
  it under `docs/COMPUTE.md` (G22, `compute-jobs` checklist).

## Code (pipeline-engineer)

- [ ] `eegharness.splits.check_no_leak(...)` (or an equivalent assertion) runs on every
  split the code makes, outer and inner, before training.
- [ ] Normalizers, scalers and any fitted preprocessing are fitted inside the fold loop.
- [ ] Augmentation lives in the training data loader only.
- [ ] Seeds set before model construction (`eegharness.seeds.seed_everything`), generator
  passed to the data loader.
- [ ] Each fold saves: per-seed test metric, final training accuracy on un-augmented
  training data, best epoch, parameter count, configuration (`eegharness.folds`).
- [ ] Model selection reads validation metrics only; nothing reads test metrics before
  the final evaluation.

## Tests (synthetic-tester)

- [ ] Leakage: a split helper or training loop with a deliberately shared group fails the
  leakage check (G2: the test fails on the buggy variant).
- [ ] Planted signal: the network (tiny, CPU, seconds) learns a planted class difference
  above chance; with labels shuffled it stays near chance.
- [ ] Determinism: same seed → same predictions on CPU; different seeds → different
  initial weights.
- [ ] Augmentation: applied to training batches only; class-preserving.
- [ ] Parameter count of each architecture equals the value computed from its definition.

## Audit (methods-auditor)

Every box above, with evidence. FAIL if: any fit sees test data; validation from the test
fold; a test transform uses the test label; a stochastic result reported from one seed;
a default contradicts the plan; a comparison outside the budget is called significant;
development data in the confirmatory test.

## Results (results-analyst)

Per participant: mean ± SD over seeds, each seed's value available, training accuracy next
to test accuracy, chance level for that participant's number of test trials. A difference
smaller than the seed spread is "no difference shown". Exploratory comparisons labelled.
