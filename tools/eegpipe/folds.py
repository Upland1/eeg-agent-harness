"""Grouped k-fold over exchangeable units, balanced by stratum (G1, G13).

Ported from P300 ``p300/session.py::assign_block_folds, fold_splits`` @ cd5db15; the
algorithm is unchanged (bitwise: the same seed gives the same folds as the P300 run):
one generator ``numpy.random.default_rng(seed)``; strata (e.g. files) in ascending order;
for each stratum its units are permuted with ``rng.permutation`` and dealt to folds
round-robin, starting at the fold after the last one used by the previous stratum. So per
stratum and overall the unit counts per fold differ by at most 1. A unit is never split:
the fold is a property of the unit and every epoch takes its unit's fold. Every split is
checked with ``eegharness.splits.check_no_leak``.
"""

import numpy as np

try:  # vendored next to eegpipe in a project; tools/ in the kit
  from eegharness.splits import check_no_leak
except ImportError:  # pragma: no cover
  raise ImportError("eegpipe.folds needs eegharness (vendored next to eegpipe)")


def assign_unit_folds(unit_stratum, n_folds, seed):
  """Fold of every unit uid. ``unit_stratum``: stratum index per unit uid, the units of each
  stratum contiguous and in stratum order."""
  unit_stratum = np.asarray(unit_stratum, dtype=np.int64)
  if n_folds < 2:
    raise ValueError("n_folds must be >= 2")
  rng = np.random.default_rng(seed)
  fold = np.full(unit_stratum.size, -1, dtype=np.int64)
  nxt = 0
  for f in np.unique(unit_stratum):
    uids = np.flatnonzero(unit_stratum == f)
    perm = rng.permutation(uids.size)
    for i, j in enumerate(perm):
      fold[uids[j]] = (nxt + i) % n_folds
    nxt = (nxt + uids.size) % n_folds
  return fold


def fold_splits(unit_uid, unit_fold, n_folds):
  """[(fold, train idx, test idx)] over epochs; an epoch takes its unit's fold."""
  unit_uid = np.asarray(unit_uid, dtype=np.int64)
  ef = np.asarray(unit_fold, dtype=np.int64)[unit_uid]
  idx = np.arange(unit_uid.size)
  out = []
  for k in range(n_folds):
    te = idx[ef == k]
    if te.size == 0:
      raise ValueError(f"fold {k} has no epochs")
    tr = idx[ef != k]
    check_no_leak(tr, te, unit_uid)
    out.append((k, tr, te))
  return out
