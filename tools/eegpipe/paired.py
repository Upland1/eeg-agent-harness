"""Participant-level paired comparison of each primary method against the comparator (G4, G19).

Ported from P300 ``tools/stage2_stats.py`` @ cd5db15 (``hodges_lehmann``, ``bootstrap_hl``,
``holm``, ``signed_rank_direction``, ``paired_test``, ``verdict``, ``analyse``); the I/O part
(reading a Stage-2 root) is ``eegpipe.runner.collect``. Every parameter comes from the
settings' ``statistics`` section (G5); the erp profile holds the P300 run's values.

Per comparison: d = method - comparator per participant, rounded to ``round_decimals`` for
zero/tie detection and the test.
  * No zero and no tied |d|: ``scipy.stats.wilcoxon`` with ``wilcoxon_exact`` (zero_method
    "wilcox", method "exact"); otherwise ``wilcoxon_zeros_or_ties`` (zero_method "pratt",
    method "approx", correction as set). The path taken is written in the row.
  * Sign test: ``binomtest(n_positive, n_nonzero, 0.5)``. Directions: Wilcoxon sign(R+ - R-)
    (average ranks of |d|; Pratt zeros ranked then dropped), sign test sign(n_pos - n_neg).
  * Effect: Hodges-Lehmann = median of the Walsh averages (d_i + d_j)/2, i <= j; percentile
    bootstrap interval over participant resamples, ``default_rng(bootstrap.seed)`` fresh per
    comparison.
  * Holm over exactly ``holm_family``; a comparison without a usable p (n < min_n, all d zero,
    no participant) enters with ``holm_missing_p`` (1: the family size never shrinks).
  * Verdict: n < min_n -> descriptive only; Holm p < alpha (strict) and HL > 0 -> "beats the
    <comparator>", HL < 0 -> "worse than the <comparator>", else "no evidence of a
    difference"; a significant row whose sign-test direction differs from the Wilcoxon
    direction -> "not robust (...)".
  * Participants whose role is in ``separate_roles`` (e.g. a reversed responder) are in the
    differences table but never in a test or in n.
Sources: Wilcoxon (1945); Hodges and Lehmann (1963) Ann. Math. Statist. 34:598-611; Holm (1979)
Scand. J. Statist. 6:65-70; Efron and Tibshirani (1993) ch. 13; SciPy 1.18.1 ``wilcoxon``,
``binomtest``, ``rankdata``.
"""

import re

import numpy as np
from scipy import stats


def hodges_lehmann(d):
  d = np.asarray(d, float)
  i, j = np.triu_indices(d.size)
  return float(np.median((d[i] + d[j]) / 2.0))


def bootstrap_hl(d, n_resamples, seed, ci):
  d = np.asarray(d, float)
  rng = np.random.default_rng(seed)
  idx = rng.integers(0, d.size, size=(n_resamples, d.size))
  db = d[idx]
  i, j = np.triu_indices(d.size)
  hl = np.median((db[:, i] + db[:, j]) / 2.0, axis=1)
  lo, hi = np.quantile(hl, [(1 - ci) / 2, 1 - (1 - ci) / 2], method="linear")
  return float(lo), float(hi)


def holm(pvals):
  p = np.asarray(pvals, float)
  m = p.size
  order = np.argsort(p, kind="stable")
  adj = np.empty(m)
  running = 0.0
  for rank, k in enumerate(order):
    running = max(running, min(1.0, (m - rank) * p[k]))
    adj[k] = running
  return adj


def signed_rank_direction(d, zero_method):
  d = np.asarray(d, float)
  if zero_method == "wilcox":
    d = d[d != 0]
  r = stats.rankdata(np.abs(d))
  return int(np.sign(r[d > 0].sum() - r[d < 0].sum()))


def paired_test(d_raw, sc):
  """Wilcoxon / sign test / HL for one comparison; ``sc`` = the statistics settings."""
  d = np.round(np.asarray(d_raw, float), int(sc["round_decimals"]))
  n = int(d.size)
  n_zero = int(np.sum(d == 0))
  absd = np.abs(d)
  ties = bool(np.unique(absd).size < absd.size)
  out = {"n": n, "n_zero_differences": n_zero, "tied_abs_differences": ties,
         "n_positive": int(np.sum(d > 0)), "n_negative": int(np.sum(d < 0))}
  if n == 0:
    return {**out, "test_path": "none (no participant)", "p": None}
  out["hodges_lehmann"] = hodges_lehmann(d)
  b = sc["bootstrap"]
  out["hl_ci_low"], out["hl_ci_high"] = bootstrap_hl(d, int(b["n_resamples"]), int(b["seed"]), float(b["ci"]))
  out["median_difference"] = float(np.median(d))
  n_nz = out["n_positive"] + out["n_negative"]
  if n_nz == 0:
    return {**out, "test_path": "none (all differences zero)", "p": None, "sign_test_p": None,
            "wilcoxon_direction": 0, "sign_test_direction": 0, "directions_agree": True}
  if n_zero == 0 and not ties:
    w = sc["wilcoxon_exact"]
    res = stats.wilcoxon(d, zero_method=w["zero_method"], method=w["method"], alternative=sc["alternative"])
    path = f"exact (zero_method={w['zero_method']}, method={w['method']})"
  else:
    w = sc["wilcoxon_zeros_or_ties"]
    res = stats.wilcoxon(d, zero_method=w["zero_method"], method=w["method"], correction=bool(w["correction"]),
                         alternative=sc["alternative"])
    path = (f"normal approximation because of {n_zero} zero difference(s) and tied |d| = {ties} "
            f"(zero_method={w['zero_method']}, method={w['method']}, correction={w['correction']})")
  st = stats.binomtest(out["n_positive"], n_nz, 0.5, alternative=sc["alternative"])
  wd = signed_rank_direction(d, w["zero_method"])
  sd = int(np.sign(out["n_positive"] - out["n_negative"]))
  return {**out, "test_path": path, "wilcoxon_statistic": float(res.statistic), "p": float(res.pvalue),
          "sign_test_p": float(st.pvalue), "wilcoxon_direction": wd, "sign_test_direction": sd,
          "directions_agree": wd == sd}


def verdict(row, sc, comparator_label="baseline"):
  if row["n"] < int(sc["min_n"]):
    return f"descriptive only (n = {row['n']} < {sc['min_n']})"
  ph = row.get("p_holm")
  hl = row.get("hodges_lehmann")
  if ph is None or ph >= float(sc["alpha"]) or hl is None or hl == 0:
    return "no evidence of a difference"
  v = f"beats the {comparator_label}" if hl > 0 else f"worse than the {comparator_label}"
  if not row["directions_agree"]:
    return f"not robust ({v} by Wilcoxon/HL, but the sign-test direction differs)"
  return v


def natural_key(p):
  """'S2' < 'S10': digits compared as numbers."""
  return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", str(p))]


def analyse(scores, roles, comparator, sc, comparator_label="baseline"):
  """scores: {participant: {method: score or None}} (None = not valid); roles: {participant: role}.
  Returns (test rows, difference rows)."""
  sep = set(sc["separate_roles"])
  rows, drows = [], []
  for mid in sc["holm_family"]:
    parts, d = [], []
    for p in sorted(scores, key=natural_key):
      a, b = scores[p].get(mid), scores[p].get(comparator)
      in_test = roles[p] not in sep and a is not None and b is not None
      if a is not None and b is not None:
        drows.append({"participant": p, "role": roles[p], "method": mid, "method_score": a, "comparator_score": b,
                      "difference": a - b, "difference_rounded": round(a - b, int(sc["round_decimals"])),
                      "in_test": in_test})
      if in_test:
        parts.append(p)
        d.append(a - b)
    n_missing = sum(1 for p in scores if roles[p] not in sep and
                    (scores[p].get(mid) is None or scores[p].get(comparator) is None))
    rows.append({"method": mid, "comparator": comparator, **paired_test(d, sc), "participants": " ".join(parts),
                 "n_missing_confirmatory": n_missing})
  usable = [r["p"] if (r["p"] is not None and r["n"] >= int(sc["min_n"])) else float(sc["holm_missing_p"]) for r in rows]
  adj = holm(usable)
  for r, u, a in zip(rows, usable, adj):
    r["p_entering_holm"] = float(u)
    r["p_holm"] = float(a)
    r["holm_m"] = len(rows)
    r["verdict"] = verdict(r, sc, comparator_label)
  return rows, drows
