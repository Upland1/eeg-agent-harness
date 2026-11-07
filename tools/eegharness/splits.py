"""Grouped splits with a leakage check (G1, G13, G17). numpy only.

    from eegharness.splits import group_ids, grouped_kfold, inner_split, check_no_leak
    groups = group_ids(participant, trial)              # unique across participants
    for train, test in grouped_kfold(groups, 5, y=y, seed=42):
        fit, val = inner_split(train, groups, 0.2, seed=42, y=y)   # early stopping, selection
        ...

Definitions:
  A *group* is the exchangeable unit of G13 (trial, block, session, participant): every
  sample of a group is on the same side of every split.
  ``check_no_leak`` raises ``LeakError`` if an index or a group is on both sides; every
  splitter here calls it before returning, and project code should call it on any split it
  makes itself.
  ``grouped_kfold``: groups are shuffled with ``seed`` and dealt to folds; with ``y`` the
  groups of each class are dealt separately (stratified by group label), which needs ``y``
  constant within each group. Every group is in exactly one test fold.
  ``leave_one_group_out``: one fold per group (e.g. per participant).
  ``inner_split``: splits the *training* indices only into fit and validation, grouped the
  same way, so validation never comes from the test fold (G17 a).
"""

import numpy as np


class LeakError(AssertionError):
  """A sample or a group is on both sides of a split."""


def group_ids(*levels) -> np.ndarray:
  """Integer ids unique for each combination of the given per-sample labels.

  ``group_ids(participant, trial)`` keeps trial 0 of participant A apart from trial 0 of
  participant B (ids that restart per participant collide when pooled).
  """
  if not levels:
    raise ValueError("give at least one per-sample label array")
  arrays = [np.asarray(lv) for lv in levels]
  n = len(arrays[0])
  if any(len(a) != n for a in arrays):
    raise ValueError("all label arrays must have the same length")
  keys = [tuple(str(a[i]) for a in arrays) for i in range(n)]
  index = {}
  return np.array([index.setdefault(k, len(index)) for k in keys], dtype=np.int64)


def check_no_leak(train_idx, test_idx, groups) -> None:
  """Raise LeakError if an index or a group appears on both sides."""
  train_idx, test_idx, groups = np.asarray(train_idx), np.asarray(test_idx), np.asarray(groups)
  shared_idx = np.intersect1d(train_idx, test_idx)
  if shared_idx.size:
    raise LeakError(f"{shared_idx.size} sample index(es) on both sides, e.g. {shared_idx[:5].tolist()}")
  shared = np.intersect1d(groups[train_idx], groups[test_idx])
  if shared.size:
    raise LeakError(f"{shared.size} group(s) on both sides of the split, e.g. {shared[:5].tolist()}")


def _group_labels(groups, y):
  out = {}
  for g, lab in zip(groups.tolist(), np.asarray(y).tolist()):
    if out.setdefault(g, lab) != lab:
      raise ValueError(f"y is not constant within group {g!r}; stratify by a group-level label instead")
  return out


def _deal(unique_groups, n_bins, rng, y_of=None):
  """Shuffle groups and deal them round-robin to bins (per class when y_of is given)."""
  bins = [[] for _ in range(n_bins)]
  if y_of is None:
    batches = [list(unique_groups)]
  else:
    classes = sorted({y_of[g] for g in unique_groups}, key=str)
    batches = [[g for g in unique_groups if y_of[g] == c] for c in classes]
  start = 0
  for batch in batches:
    order = rng.permutation(len(batch))
    for j, k in enumerate(order):
      bins[(start + j) % n_bins].append(batch[k])
    start += len(batch)
  return bins


def grouped_kfold(groups, n_splits: int, *, y=None, seed: int = 0) -> list:
  """List of (train_idx, test_idx); each group in exactly one test fold."""
  groups = np.asarray(groups)
  uniq = list(dict.fromkeys(groups.tolist()))
  if n_splits < 2 or n_splits > len(uniq):
    raise ValueError(f"n_splits must be between 2 and the number of groups ({len(uniq)})")
  y_of = _group_labels(groups, y) if y is not None else None
  bins = _deal(uniq, n_splits, np.random.default_rng(seed), y_of)
  idx = np.arange(len(groups))
  out = []
  for b in bins:
    test_mask = np.isin(groups, np.array(b, dtype=groups.dtype))
    tr, te = idx[~test_mask], idx[test_mask]
    check_no_leak(tr, te, groups)
    out.append((tr, te))
  return out


def leave_one_group_out(groups) -> list:
  """One (train_idx, test_idx) per group, in order of first appearance."""
  groups = np.asarray(groups)
  idx = np.arange(len(groups))
  out = []
  for g in dict.fromkeys(groups.tolist()):
    test_mask = groups == g
    tr, te = idx[~test_mask], idx[test_mask]
    check_no_leak(tr, te, groups)
    out.append((tr, te))
  return out


def inner_split(train_idx, groups, val_frac: float, *, seed: int = 0, y=None):
  """Split training indices into (fit_idx, val_idx) by group; validation has at least one group."""
  train_idx, groups = np.asarray(train_idx), np.asarray(groups)
  if not 0 < val_frac < 1:
    raise ValueError("val_frac must be between 0 and 1")
  g_train = groups[train_idx]
  uniq = list(dict.fromkeys(g_train.tolist()))
  if len(uniq) < 2:
    raise ValueError("need at least two training groups for a grouped validation split")
  rng = np.random.default_rng(seed)
  if y is None:
    order = [uniq[k] for k in rng.permutation(len(uniq))]
    n_val = min(len(uniq) - 1, max(1, int(round(val_frac * len(uniq)))))
    val_groups = order[:n_val]
  else:
    y_of = _group_labels(g_train, np.asarray(y)[train_idx])
    val_groups = []
    for c in sorted({y_of[g] for g in uniq}, key=str):
      cg = [g for g in uniq if y_of[g] == c]
      cg = [cg[k] for k in rng.permutation(len(cg))]
      n_val = min(len(cg) - 1, int(round(val_frac * len(cg))))
      val_groups += cg[:max(n_val, 0)]
    if not val_groups:
      raise ValueError("val_frac too small: no class has a group to spare for validation")
  val_mask = np.isin(g_train, np.array(val_groups, dtype=g_train.dtype))
  fit, val = train_idx[~val_mask], train_idx[val_mask]
  check_no_leak(fit, val, groups)
  return fit, val
