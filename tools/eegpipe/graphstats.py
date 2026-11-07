"""Edge-wise BH-FDR, network-based statistic and the per-unit paired t (G20 d-e).

Ported unchanged from P300 ``p300/phase.py`` @ cd5db15 (``benjamini_hochberg``,
``edge_components``, ``max_component_size``, ``nbs``, ``paired_t``), themselves ported from
``mas-ssvep-eeg-xai`` v1.0.4 (``src/features/connectivity/permutation.py::benjamini_hochberg``,
``src/stats/nbs.py``). Pairs are ``numpy.triu_indices(C, 1)`` (row-major i < j).
  BH (Benjamini and Hochberg 1995): reject the k smallest p with p_(k) <= alpha k / m.
  NBS (Zalesky, Fornito, Bullmore 2010): supra-threshold edges (t > threshold for direction
  "a_gt_b", -t > threshold for "b_gt_a"), components by
  ``scipy.sparse.csgraph.connected_components``, size = number of edges; component p =
  (1 + #{null max size >= size}) / (n_perm + 1), null max sizes from the t-maps of the same
  permutations. The P300 direction names "target_gt_nontarget" / "nontarget_gt_target" are
  accepted as aliases of "a_gt_b" / "b_gt_a".
  paired t: one-sample t of the rows of d (n_units, P) against 0; 0 where sd = 0 or n < 2.
"""

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

DIRECTIONS = ("a_gt_b", "b_gt_a")
ALIASES = {"target_gt_nontarget": "a_gt_b", "nontarget_gt_target": "b_gt_a"}


def pairs(n_channels):
  return np.triu_indices(int(n_channels), 1)


def benjamini_hochberg(p_values, alpha):
  p = np.asarray(p_values, dtype=float)
  flat = p.reshape(-1)
  m = len(flat)
  order = np.argsort(flat, kind="stable")
  ok = flat[order] <= alpha * np.arange(1, m + 1) / m
  reject = np.zeros(m, dtype=bool)
  if ok.any():
    reject[order[:int(np.flatnonzero(ok).max()) + 1]] = True
  return reject.reshape(p.shape)


def edge_components(supra, n_channels):
  """(component label per edge (-1 if not supra-threshold), edge count per label)."""
  supra = np.asarray(supra, dtype=bool)
  iu, ju = pairs(n_channels)
  i, j = iu[supra], ju[supra]
  lab_e = np.full(len(supra), -1, dtype=int)
  if len(i) == 0:
    return lab_e, np.zeros(0, dtype=int)
  g = coo_matrix((np.ones(len(i)), (i, j)), shape=(n_channels, n_channels))
  _, lab = connected_components(g, directed=False)
  _, compact = np.unique(lab[i], return_inverse=True)
  lab_e[supra] = compact
  return lab_e, np.bincount(compact)


def max_component_size(supra, n_channels):
  return int(edge_components(supra, n_channels)[1].max(initial=0))


def nbs(t_obs, t_null, threshold, n_channels, direction):
  """t_obs (P,), t_null (n_perm, P) -> {"components": [{edges, size, p}], "null_max"}."""
  direction = ALIASES.get(direction, direction)
  if direction not in DIRECTIONS:
    raise ValueError(f"direction {direction!r}; choose from {DIRECTIONS} (or {sorted(ALIASES)})")
  sgn = 1.0 if direction == "a_gt_b" else -1.0
  t_obs, t_null = sgn * np.asarray(t_obs, float), sgn * np.asarray(t_null, float)
  lab, sizes = edge_components(t_obs > threshold, n_channels)
  null_max = np.array([max_component_size(z > threshold, n_channels) for z in t_null], dtype=int)
  n = len(t_null)
  comps = [{"edges": np.flatnonzero(lab == c).tolist(), "size": int(s),
            "p": float((1 + np.sum(null_max >= s)) / (n + 1))} for c, s in enumerate(sizes)]
  return {"components": comps, "null_max": null_max}


def paired_t(d):
  d = np.asarray(d, dtype=np.float64)
  if d.shape[0] < 2:
    return np.zeros(d.shape[1])
  sd = d.std(axis=0, ddof=1)
  return np.where(sd > 0, d.mean(0) / (np.where(sd > 0, sd, 1.0) / np.sqrt(d.shape[0])), 0.0)
