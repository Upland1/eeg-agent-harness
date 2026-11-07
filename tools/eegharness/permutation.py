"""Unit-level permutation tests (G13, G20 d). numpy only.

    from eegharness.permutation import permutation_test
    r = permutation_test(lambda lab: x[lab == 1].mean() - x[lab == 0].mean(),
                         labels, units=trial_ids, n_permutations=1999, seed=0)
    r["p"], r["observed"], r["null"]

Definitions:
  ``labels`` holds one label per sample. With ``units`` (the exchangeable unit of G13, e.g.
  the trial of each window), labels must be constant within a unit; a permutation shuffles
  the labels *of units* and gives every sample its unit's label. The number of units per
  label is therefore the observed one in every permutation; samples of one unit never
  split. Without ``units`` each sample is its own unit.
  ``statistic(labels) -> float`` is evaluated on the observed labels and on each permuted
  labelling.
  p counts the observed labelling as one draw of the null (G13):
    greater:   p = (1 + #{null >= observed}) / (1 + n)
    less:      p = (1 + #{null <= observed}) / (1 + n)
    two-sided: p = (1 + #{|null| >= |observed|}) / (1 + n)  (statistic centred on 0 under H0)
  The smallest possible p is 1 / (1 + n): choose n so that it is well below alpha.
"""

import numpy as np

ALTERNATIVES = ("greater", "less", "two-sided")


def min_p(n_permutations: int) -> float:
  return 1.0 / (1 + n_permutations)


def unit_labels(labels, units):
  """(unique units in first-appearance order, label of each unit, unit index per sample)."""
  labels, units = np.asarray(labels), np.asarray(units)
  if len(labels) != len(units):
    raise ValueError("labels and units must have the same length")
  uniq, first, inverse = np.unique(units, return_index=True, return_inverse=True)
  lab_of_unit = labels[first]
  bad = np.flatnonzero(labels != lab_of_unit[inverse])
  if bad.size:
    raise ValueError(f"labels vary within unit {units[bad[0]]!r}: permute at a level where the label is constant")
  return uniq, lab_of_unit, inverse.ravel()


def permutation_test(statistic, labels, *, units=None, n_permutations: int = 1999, seed: int = 0,
                     alternative: str = "greater") -> dict:
  if alternative not in ALTERNATIVES:
    raise ValueError(f"alternative must be one of {ALTERNATIVES}")
  if n_permutations < 1:
    raise ValueError("n_permutations must be >= 1")
  labels = np.asarray(labels)
  if units is None:
    units = np.arange(len(labels))
    unit_kind = "sample"
  else:
    unit_kind = "unit"
  uniq, lab_of_unit, inverse = unit_labels(labels, units)
  observed = float(statistic(labels))
  rng = np.random.default_rng(seed)
  null = np.empty(n_permutations)
  for i in range(n_permutations):
    null[i] = statistic(rng.permutation(lab_of_unit)[inverse])
  if alternative == "greater":
    hits = np.sum(null >= observed)
  elif alternative == "less":
    hits = np.sum(null <= observed)
  else:
    hits = np.sum(np.abs(null) >= abs(observed))
  return {"observed": observed, "null": null, "p": float((1 + hits) / (1 + n_permutations)),
          "n_permutations": n_permutations, "alternative": alternative, "permutation_unit": unit_kind,
          "n_units": int(len(uniq)), "min_p": min_p(n_permutations)}
