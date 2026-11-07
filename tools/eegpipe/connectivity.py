"""Family F3(a): condition-level phase connectivity between two classes (G20).

Ported from P300 ``p300/phase.py`` @ cd5db15 (``dwpli_from_sums``, ``debiased_wpli``, ``wpli``,
``plv``, ``band_spectra``, ``subsample_matrix``, ``labelling_statistics``,
``class_residual_cross``, ``condition_level``). The P300 contrast target vs non-target is a
declared contrast (class a, class b) of the settings (``f3.condition_level.contrast``);
epochs of other classes do not enter (their units are left out of the permutations too).

For the observed labelling and for every permutation p (labels from ``labels_of(p)``):
  (1) the per-class mean spectrum is subtracted within each stratum (file) and class, with
      THAT labelling's labels (exact equivalent of subtracting the class-mean epoch: detrend,
      taper and DFT are linear);
  (2) class b is subsampled to class a's count, ``n_subsample_repeats`` times, repeat r drawn
      with ``default_rng([subsample_seed, key, r]).choice(n_b, n_a, replace=False)``; key = p,
      or ``observed_key`` (larger than any p) for the observed labelling;
  (3) debiased squared wPLI (Vinck et al. 2011; computed as mne-connectivity
      ``_WPLIDebiasedEst``: ((sum Im)^2 - sum Im^2) / ((sum |Im|)^2 - sum Im^2), 0 where the
      denominator is 0) of Im(S) per class; class b's value is the mean over repeats; the
      statistic is a - b per pair and band.
Edge p = (1 + #{|null| >= |observed|}) / (n_perm + 1), two-sided; BH-FDR over pairs x bands.
NBS: edge statistic = paired t over pairing groups of the per-group (a - b) debiased wPLI (all
epochs of the group, after step 1; groups with fewer than ``min_trials_per_class`` epochs of a
class left out); components per band and direction (graphstats.nbs). The pairing group is
``nbs.pair_by``: "unit" (P300: every block holds both classes) or "stratum" (the file; for
designs whose label is constant within a unit, e.g. SSVEP trials, where no unit holds both
classes). With fewer than 2 usable groups the NBS is not applicable: the summary says so and
no component is reported. PLV of the observed labelling is
reported for comparison only. The four NBS analyses (bands x directions) are not corrected
against each other; that is stated in every row.
"""

import numpy as np

from eegpipe import graphstats as gs
from eegpipe import phase as ph

MULTIPLICITY_NOTE = ("BH-FDR covers the pairs x bands jointly; the NBS analyses (bands x directions) are not "
                     "corrected against each other")


def dwpli_from_sums(s, a, q):
  s, a, q = (np.asarray(v, dtype=np.float64) for v in (s, a, q))
  den = a ** 2 - q
  z = den == 0.0
  out = (s ** 2 - q) / np.where(z, 1.0, den)
  return np.where(z, 0.0, out)


def debiased_wpli(im):
  im = np.asarray(im, dtype=np.float64)
  return dwpli_from_sums(im.sum(0), np.abs(im).sum(0), (im ** 2).sum(0))


def wpli(im):
  im = np.asarray(im, dtype=np.float64)
  num, den = np.abs(im.mean(0)), np.abs(im).mean(0)
  return np.where(den > 0, num / np.where(den > 0, den, 1.0), 0.0)


def plv(S):
  return np.abs(np.exp(1j * np.angle(S)).mean(axis=0))


def band_spectra(X_raw, bands, fs, window, fftbins, detrend):
  Z = ph.spectra(X_raw, window, fftbins, detrend)
  return [Z[..., ph.band_bins(X_raw.shape[-1], fs, b)] for b in bands]


def subsample_matrix(n_b, n_a, n_repeats, seed, key):
  """(n_repeats, n_b) 0/1 matrix; row r = default_rng([seed, key, r]).choice(n_b, n_a)."""
  if n_a > n_b:
    raise ValueError("class b has fewer epochs than class a; cannot subsample to equal counts")
  M = np.zeros((n_repeats, n_b))
  for r in range(n_repeats):
    M[r, np.random.default_rng([int(seed), int(key), r]).choice(n_b, size=n_a, replace=False)] = 1.0
  return M


def class_residual_cross(Zb, y, groups):
  """Band cross-spectrum (n, P) after subtracting each group's (file's) class-mean spectrum."""
  y, groups = np.asarray(y), np.asarray(groups)
  R = np.array(Zb, copy=True)
  for g in np.unique(groups):
    for c in np.unique(y):
      m = (groups == g) & (y == c)
      if m.any():
        R[m] -= Zb[m].mean(axis=0)
  return ph.band_cross(R)


def labelling_statistics(Z_bands, y, unit_uid, key, ccfg, file_idx):
  """y in {1 = class a, 0 = class b}. Returns diff, dw_a, dw_b, t (n_bands, P), S, n_units_used
  (pairing groups used for the NBS t, see ``nbs.pair_by``)."""
  pair_by = ccfg.get("nbs", {}).get("pair_by", "unit")
  if pair_by not in ("unit", "stratum"):
    raise ValueError(f"nbs.pair_by {pair_by!r}; choose 'unit' or 'stratum'")
  groups = np.asarray(unit_uid) if pair_by == "unit" else np.asarray(file_idx)
  y = np.asarray(y)
  a_idx, b_idx = np.flatnonzero(y == 1), np.flatnonzero(y == 0)
  M = subsample_matrix(b_idx.size, a_idx.size, int(ccfg["n_subsample_repeats"]), ccfg["subsample_seed"], key)
  ub, uinv = np.unique(groups, return_inverse=True)
  mins = int(ccfg["min_trials_per_class"])
  Ba = np.zeros((ub.size, y.size))
  Ba[uinv[a_idx], a_idx] = 1.0
  Bb = np.zeros((ub.size, y.size))
  Bb[uinv[b_idx], b_idx] = 1.0
  use = (Ba.sum(1) >= mins) & (Bb.sum(1) >= mins)
  out = {"diff": [], "dw_a": [], "dw_b": [], "t": [], "S": [], "n_units_used": int(use.sum())}
  for Zb in Z_bands:
    S = class_residual_cross(Zb, y, file_idx)
    im = S.imag
    da = debiased_wpli(im[a_idx])
    imb = im[b_idx]
    db = dwpli_from_sums(M @ imb, M @ np.abs(imb), M @ imb ** 2).mean(axis=0)
    ab, a2 = np.abs(im), im ** 2
    d_unit = (dwpli_from_sums(Ba @ im, Ba @ ab, Ba @ a2) - dwpli_from_sums(Bb @ im, Bb @ ab, Bb @ a2))[use]
    out["diff"].append(da - db)
    out["dw_a"].append(da)
    out["dw_b"].append(db)
    out["t"].append(gs.paired_t(d_unit))
    out["S"].append(S)
  for k in ("diff", "dw_a", "dw_b", "t"):
    out[k] = np.stack(out[k])
  return out


def contrast_labels(y, contrast):
  """(mask of epochs in the contrast, labels 1 = class a, 0 = class b on those epochs)."""
  y = np.asarray(y)
  a, b = int(contrast[0]), int(contrast[1])
  m = (y == a) | (y == b)
  return m, (y[m] == a).astype(np.int64)


def condition_level(X_raw, y_obs, unit_uid, labels_of, n_perm, fs, cfg, file_idx):
  """F3(a) (module docstring). ``y_obs`` and ``labels_of(p)`` are full class-index labels; the
  contrast selects the epochs whose OBSERVED class is a or b (the permutation then moves labels
  only among those units). Returns edges, nbs rows, nulls, observed statistics, summary."""
  f3, ccfg = cfg["f3"], cfg["f3"]["condition_level"]
  contrast = ccfg.get("contrast", [1, 0])
  names = list(ccfg["bands"])
  bands = [f3["bands"][b] for b in names]
  sp = f3["spectrum"]
  sel, y_ab = contrast_labels(y_obs, contrast)
  X_raw = np.asarray(X_raw, dtype=np.float64)[sel]
  unit_uid, file_idx = np.asarray(unit_uid)[sel], np.asarray(file_idx)[sel]
  Zs = band_spectra(X_raw, bands, fs, sp["window"], sp["window_fftbins"], sp["detrend"])
  if n_perm >= int(ccfg["observed_key"]):
    raise ValueError("observed_key must exceed every permutation index")
  obs = labelling_statistics(Zs, y_ab, unit_uid, ccfg["observed_key"], ccfg, file_idx)
  P = obs["diff"].shape[1]
  null_diff = np.empty((n_perm, len(names), P))
  null_t = np.empty((n_perm, len(names), P))
  for p in range(n_perm):
    lp = np.asarray(labels_of(p))[sel]
    if not np.all(np.isin(lp, contrast)):
      raise ValueError("a permuted labelling moves a class outside the contrast onto the contrast's epochs; "
                       "permute only among the contrast's units")
    s = labelling_statistics(Zs, (lp == int(contrast[0])).astype(np.int64), unit_uid, p, ccfg, file_idx)
    null_diff[p], null_t[p] = s["diff"], s["t"]
  p_two = (1 + np.sum(np.abs(null_diff) >= np.abs(obs["diff"])[None], axis=0)) / (n_perm + 1)
  fdr = gs.benjamini_hochberg(p_two, float(ccfg["fdr"]["alpha"]))
  n_ch = int(X_raw.shape[1])
  iu, ju = gs.pairs(n_ch)
  a_idx, b_idx = np.flatnonzero(y_ab == 1), np.flatnonzero(y_ab == 0)
  M = subsample_matrix(b_idx.size, a_idx.size, int(ccfg["n_subsample_repeats"]), ccfg["subsample_seed"],
                       ccfg["observed_key"])
  edges = []
  for bi, b in enumerate(names):
    S = obs["S"][bi]
    plv_a = plv(S[a_idx])
    phb = np.exp(1j * np.angle(S[b_idx]))
    plv_b = (np.abs(M @ phb) / M.sum(1, keepdims=True)).mean(axis=0)
    for e in range(P):
      edges.append({"band": b, "pair": e, "channel_i": int(iu[e]), "channel_j": int(ju[e]),
                    "dwpli_a": float(obs["dw_a"][bi, e]), "dwpli_b_subsample_mean": float(obs["dw_b"][bi, e]),
                    "dwpli_diff": float(obs["diff"][bi, e]), "p_two_sided": float(p_two[bi, e]),
                    "fdr_reject": bool(fdr[bi, e]), "t_units": float(obs["t"][bi, e]),
                    "plv_a_comparison_only": float(plv_a[e]), "plv_b_comparison_only": float(plv_b[e])})
  nrows, nbs_null = [], {}
  thr = float(ccfg["nbs"]["threshold"])
  nbs_ok = obs["n_units_used"] >= 2
  for bi, b in enumerate(names):
    for d in (ccfg["nbs"]["directions"] if nbs_ok else []):
      r = gs.nbs(obs["t"][bi], null_t[:, bi], thr, n_ch, d)
      nbs_null[f"{b}__{d}"] = r["null_max"]
      for c, comp in enumerate(r["components"]):
        nrows.append({"band": b, "direction": d, "component": c, "size_edges": comp["size"], "p": comp["p"],
                      "significant": bool(comp["p"] < float(ccfg["nbs"]["alpha"])),
                      "pairs": ";".join(f"{iu[e]}-{ju[e]}" for e in comp["edges"]), "threshold": thr,
                      "multiplicity": MULTIPLICITY_NOTE})
  summary = {"bands": names, "contrast": [int(contrast[0]), int(contrast[1])], "n_permutations": int(n_perm),
             "n_pairs": int(P), "n_a": int(a_idx.size), "n_b": int(b_idx.size),
             "n_units_used_observed": obs["n_units_used"], "nbs_pair_by": ccfg["nbs"].get("pair_by", "unit"),
             "nbs_applicable": bool(nbs_ok), "n_edges_fdr": int(fdr.sum()), "n_tests_fdr": int(fdr.size),
             "n_nbs_components_significant": int(sum(r["significant"] for r in nrows))}
  return {"edges": edges, "nbs": nrows, "null_diff": null_diff, "null_t": null_t, "nbs_null_max": nbs_null,
          "observed": {k: obs[k] for k in ("diff", "dw_a", "dw_b", "t")}, "summary": summary}
