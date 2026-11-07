"""Cross-validated evaluation, k-class metrics and per-stratum permutation tests (G1, G3, G4, G13).

Ported from P300 ``p300/evaluate.py`` and ``p300/session_eval.py`` @ cd5db15, generalised
from two classes (target / non-target) to k classes (Sebastian's decision D5, 2026-11-07).

Metrics (``class_metrics``): recall of every class c (``ca_<name>``) and balanced accuracy
BA = mean of the k recalls. A class absent from the evaluated epochs gives NaN for its
recall and for BA. With class names ("nontarget", "target") the keys are the P300 run's
``ca_nontarget`` / ``ca_target``.

Cross-validation (``cv_predict``): fixed splits (eegpipe.folds); a fresh estimator from
``make_est()`` is fitted on every training fold (every fitted step inside it, G1) and
predicts the test fold; out-of-fold predictions are pooled. Scikit-learn
``ConvergenceWarning``s per fold are counted (``n_convergence_warnings``).

Permutation tests per stratum (e.g. per file). What is shuffled is the exchangeable
LABEL UNIT of the study (G13), within each stratum, keeping the stratum's multiset:
  scheme ``"unit_label"`` (labels constant within a unit, e.g. SSVEP trials): the vector of
    unit labels of the stratum is permuted across its units; every epoch takes its unit's
    label;
  scheme ``"unit_target"`` (labels from a per-unit target and a per-epoch code, e.g. P300
    blocks: label = 1 iff code == target of the unit): the vector of unit targets is
    permuted across the stratum's units and labels are recomputed with the same rule
    (``labels_from_targets``); a target that is not among the codes of the unit it lands
    in raises (never relabelled silently).
Permutation p uses ``numpy.random.default_rng([seed, p])``; strata in order, each draws
``rng.permutation(values)`` once (bitwise the P300 run's draws for the same seed). The whole
method is refitted in every fold on the permuted labels and the per-stratum BA is read from
the pooled out-of-fold predictions. Monte Carlo p = (C + 1) / (n + 1), C = #{null BA >=
observed BA} (scikit-learn ``permutation_test_score``; Phipson and Smyth 2010); the exact-null
floor 1 / n_distinct (n_distinct = multinomial number of distinct label vectors of the
stratum) is reported separately with a flag when the Monte Carlo p is below it; Holm across
the strata. All draws are made in the parent process, so results do not depend on n_jobs.
"""

import math
import multiprocessing as mp
import os
import warnings
from collections import Counter
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from sklearn.exceptions import ConvergenceWarning

BLAS_ENV = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
SCHEMES = ("unit_label", "unit_target")


# ------------------------------------------------------------------ metrics
def class_metrics(y_true, y_pred, class_names):
  y_true, y_pred = np.asarray(y_true), np.asarray(y_pred)
  out, rec = {}, []
  for c, name in enumerate(class_names):
    m = y_true == c
    r = float(np.mean(y_pred[m] == c)) if m.any() else float("nan")
    out[f"ca_{name}"] = r
    out[f"n_{name}"] = int(m.sum())
    rec.append(r)
  out["ba"] = float(np.mean(rec))
  return out


def group_metrics(y, pred, groups, class_names):
  """{group value: class_metrics} over the epochs of each group (sorted group values)."""
  y, pred, groups = np.asarray(y), np.asarray(pred), np.asarray(groups)
  return {g: class_metrics(y[groups == g], pred[groups == g], class_names) for g in sorted(set(groups.tolist()))}


def _decision(est, X):
  if hasattr(est, "decision_function"):
    try:
      return np.asarray(est.decision_function(X), dtype=np.float64)
    except (AttributeError, NotImplementedError):
      pass
  return None


def fit_predict(make_est, X, y, train, test):
  if len(np.unique(y[train])) < 2:
    raise ValueError("a training set lacks a class")
  est = make_est()
  est.fit(X[train], y[train])
  return est.predict(X[test]), _decision(est, X[test])


def cv_predict(X, y, splits, make_est, class_names):
  """splits: (fold id, train idx, test idx) -> (pred, decision or None, fold rows)."""
  pred = np.full(len(y), -1, dtype=np.int64)
  dec = None
  rows = []
  k = len(class_names)
  for fold, train, test in splits:
    missing = sorted(set(range(k)) - set(np.unique(y[train]).tolist()))
    if missing:
      raise ValueError(f"fold {fold}: the training set lacks class(es) {[class_names[c] for c in missing]}; "
                       "balance the folds by label (folds.assign_unit_folds unit_label=...) or use fewer folds")
    with warnings.catch_warnings(record=True) as caught:
      warnings.simplefilter("always", ConvergenceWarning)
      p, d = fit_predict(make_est, X, y, train, test)
    n_warn = sum(issubclass(w.category, ConvergenceWarning) for w in caught)
    pred[test] = p
    if d is not None:
      if dec is None:
        dec = np.full((len(y),) + d.shape[1:], np.nan)
      dec[test] = d
    rows.append({"fold": fold, "n_train": int(len(train)), "n_test": int(len(test)),
                 **class_metrics(y[test], p, class_names), "n_convergence_warnings": int(n_warn)})
  if np.any(pred < 0):
    raise ValueError("some epochs received no out-of-fold prediction")
  return pred, dec, rows


def convergence_status(n_folds_not_converged):
  n = int(n_folds_not_converged)
  return "ok" if n == 0 else f"ok, not converged ({n} folds)"


def differences_vs(rows, group_fields, comparator, methods, metrics):
  """Rows of ``method - comparator`` for ``metrics`` within each group (G11)."""
  key = lambda r: tuple(r.get(f) for f in group_fields)  # noqa: E731
  base = {key(r): r for r in rows if r["method"] == comparator}
  out = []
  for r in rows:
    if r["method"] not in methods or r["method"] == comparator or key(r) not in base:
      continue
    b = base[key(r)]
    out.append({"method": r["method"], "comparator": comparator, **{f: r.get(f) for f in group_fields},
                **{f"diff_{m}": float(r[m]) - float(b[m]) for m in metrics}})
  return out


# ------------------------------------------------------------------ permutation nulls
def labels_from_targets(code, unit_local, unit_targets):
  """scheme unit_target: label 1 iff the epoch's code equals its unit's target."""
  code = np.asarray(code, dtype=np.int64)
  t = np.asarray(unit_targets, dtype=np.int64)
  return (code == t[np.asarray(unit_local, dtype=np.int64)]).astype(np.int64)


def labels_from_unit_labels(unit_local, unit_labels):
  """scheme unit_label: every epoch takes its unit's label."""
  return np.asarray(unit_labels, dtype=np.int64)[np.asarray(unit_local, dtype=np.int64)]


def unit_values(sess, scheme, unit_targets=None):
  """Observed per-stratum vectors of what the null shuffles (strata = files, in order).

  unit_label: the label of each unit (must be constant within the unit);
  unit_target: ``unit_targets[file]`` as given by the adapter (one target per unit)."""
  n_files = int(sess["unit_file"].max()) + 1
  out = []
  for f in range(n_files):
    m = sess["file_idx"] == f
    n_u = int(np.sum(sess["unit_file"] == f))
    if scheme == "unit_label":
      v = np.full(n_u, -1, dtype=np.int64)
      for u in range(n_u):
        lab = np.unique(sess["y"][m & (sess["unit_local"] == u)])
        if lab.size > 1:
          raise ValueError(f"file {f} unit {u}: labels vary within the unit; scheme unit_label needs constant labels")
        if lab.size:
          v[u] = lab[0]
      if np.any(v < 0):
        raise ValueError(f"file {f}: a unit has no retained epoch; its label is unknown")
      out.append(v)
    elif scheme == "unit_target":
      out.append(np.asarray(unit_targets[f], dtype=np.int64))
    else:
      raise ValueError(f"unknown scheme {scheme!r}; known: {SCHEMES}")
  return out


def unit_code_sets(sess, f):
  """Sorted code set of each unit of file f (scheme unit_target)."""
  m = sess["file_idx"] == f
  n_u = int(np.sum(sess["unit_file"] == f))
  return [np.asarray(sorted(set(sess["code"][m & (sess["unit_local"] == u)].tolist())), dtype=np.int64)
          for u in range(n_u)]


def _check_targets_fit(x, cands):
  for v in sorted(set(np.asarray(x).tolist())):
    for u, c in enumerate(cands):
      if v not in c:
        raise ValueError(f"target {v} can be shuffled into unit {u}, whose codes {c.tolist()} do not include it")


def draw_shuffles(values_per_stratum, n_perm, seed, code_sets=None):
  """List over strata of (n_perm, n_units) permuted value arrays (module docstring)."""
  if code_sets is not None:
    for x, cands in zip(values_per_stratum, code_sets):
      _check_targets_fit(x, cands)
  out = [np.empty((n_perm, len(x)), dtype=np.int64) for x in values_per_stratum]
  for p in range(n_perm):
    rng = np.random.default_rng([seed, p])
    for f, x in enumerate(values_per_stratum):
      out[f][p] = rng.permutation(np.asarray(x, dtype=np.int64))
  return out


def draw_shuffles_constrained(values_per_stratum, n_perm, seed, accept, max_redraws=10000, code_sets=None):
  """As ``draw_shuffles``, restricted to labellings ``accept(values_per_stratum)`` admits.

  Permutation p uses default_rng([seed, p]) and redraws (from the same generator) until the
  draw is accepted. The restriction depends only on the labels and the fixed design (e.g.
  every training fold holds every class, ``every_class_in_training``), never on the data, and
  the observed labelling satisfies it, so the restricted permutation test is valid (uniform
  over the admissible labellings under H0). Returns (draws, number of redraws per permutation);
  the redraws are reported with the test. With an accept that admits everything the draws equal
  ``draw_shuffles``."""
  if code_sets is not None:
    for x, cands in zip(values_per_stratum, code_sets):
      _check_targets_fit(x, cands)
  if not accept([np.asarray(x, dtype=np.int64) for x in values_per_stratum]):
    raise ValueError("the observed labelling is not admissible under the restriction")
  out = [np.empty((n_perm, len(x)), dtype=np.int64) for x in values_per_stratum]
  redraws = np.zeros(n_perm, dtype=np.int64)
  for p in range(n_perm):
    rng = np.random.default_rng([seed, p])
    for tries in range(max_redraws + 1):
      d = [rng.permutation(np.asarray(x, dtype=np.int64)) for x in values_per_stratum]
      if accept(d):
        break
    else:
      raise ValueError(f"permutation {p}: no admissible labelling in {max_redraws} redraws")
    redraws[p] = tries
    for f in range(len(out)):
      out[f][p] = d[f]
  return out, redraws


def every_class_in_training(sess, splits, scheme, n_classes):
  """accept() for ``draw_shuffles_constrained``: every training set holds all n_classes."""
  def accept(values):
    y = labels_for(sess, values, scheme)
    return all(len(np.unique(y[tr])) == n_classes for _, tr, _ in splits)
  return accept


def n_distinct_shuffles(values):
  """n! / prod over values v of count_v! (distinct permutations of a multiset)."""
  out = math.factorial(len(values))
  for cnt in Counter(int(v) for v in values).values():
    out //= math.factorial(cnt)
  return out


def monte_carlo_p_floor(n_perm):
  return 1.0 / (n_perm + 1.0)


def exact_null_p_floor(n_distinct):
  return 1.0 / float(n_distinct)


def larger_p_floor(n_perm, n_distinct):
  return max(monte_carlo_p_floor(n_perm), exact_null_p_floor(n_distinct))


def permutation_p(observed, null):
  null = np.asarray(null, dtype=np.float64)
  return float((np.sum(null >= observed) + 1.0) / (null.size + 1.0))


def holm(pvals):
  """Holm step-down adjusted p-values, in the input order."""
  p = np.asarray(pvals, dtype=np.float64)
  m = p.size
  order = np.argsort(p, kind="stable")
  adj_sorted = np.maximum.accumulate(np.minimum(1.0, (m - np.arange(m)) * p[order]))
  out = np.empty(m)
  out[order] = adj_sorted
  return out


def labels_for(sess, values_per_stratum, scheme):
  y = np.empty(sess["y"].size, dtype=np.int64)
  for f, v in enumerate(values_per_stratum):
    m = sess["file_idx"] == f
    if scheme == "unit_target":
      y[m] = labels_from_targets(sess["code"][m], sess["unit_local"][m], v)
    else:
      y[m] = labels_from_unit_labels(sess["unit_local"][m], v)
  return y


def per_stratum_ba(sess, y, splits, make_est, class_names):
  """(per-stratum BA array, pooled BA) of one method under fixed folds."""
  pred, _, _ = cv_predict(sess["X"], y, splits, make_est, class_names)
  n_files = int(sess["file_idx"].max()) + 1
  ba = np.array([class_metrics(y[sess["file_idx"] == f], pred[sess["file_idx"] == f], class_names)["ba"]
                 for f in range(n_files)])
  return ba, class_metrics(y, pred, class_names)["ba"]


_W = {}


def _init_worker(sess, splits, method_ids, factory, cfg, scheme, class_names):
  _W.update(sess=sess, splits=splits, method_ids=method_ids, factory=factory, cfg=cfg, scheme=scheme,
            class_names=class_names)


def _null_chunk(chunk):
  sess, cfg = _W["sess"], _W["cfg"]
  out = []
  for values in chunk:
    y = labels_for(sess, values, _W["scheme"])
    rows = []
    for mid in _W["method_ids"]:
      ba, pooled = per_stratum_ba(sess, y, _W["splits"], lambda m=mid: _W["factory"](m, cfg), _W["class_names"])
      rows.append(np.append(ba, pooled))
    out.append(np.vstack(rows))
  return out


def permutation_null(sess, splits, method_ids, factory, cfg, scheme, class_names, shuffles, n_jobs, chunk_size):
  """Null BAs (n_methods, n_perm, n_strata + 1); the last column is the pooled BA.

  ``factory(method_id, cfg)`` -> unfitted estimator; it must be a module-level function
  (workers are spawned processes)."""
  n_perm = shuffles[0].shape[0]
  per_perm = [[s[p] for s in shuffles] for p in range(n_perm)]
  chunks = [per_perm[i:i + chunk_size] for i in range(0, n_perm, chunk_size)]
  args = (sess, splits, method_ids, factory, cfg, scheme, class_names)
  if n_jobs == 1:
    _init_worker(*args)
    res = [_null_chunk(c) for c in chunks]
  else:
    saved = {k: os.environ.get(k) for k in BLAS_ENV}
    try:
      for k in BLAS_ENV:
        os.environ[k] = "1"
      with ProcessPoolExecutor(max_workers=n_jobs, mp_context=mp.get_context("spawn"),
                               initializer=_init_worker, initargs=args) as pool:
        res = list(pool.map(_null_chunk, chunks))
    finally:
      for k, v in saved.items():
        if v is None:
          os.environ.pop(k, None)
        else:
          os.environ[k] = v
  return np.stack([a for r in res for a in r], axis=1)


def per_stratum_tests(observed_ba, null_ba, n_distinct, alpha, percentile, percentile_method):
  """Per stratum: Monte Carlo p, floors and flag, null mean and critical value, Holm p, decision."""
  n_perm = null_ba.shape[0]
  p = [permutation_p(o, null_ba[:, f]) for f, o in enumerate(observed_ba)]
  ph = holm(p)
  rows = []
  for f in range(len(observed_ba)):
    floor = exact_null_p_floor(int(n_distinct[f]))
    rows.append({"perm_p_monte_carlo": float(p[f]), "monte_carlo_p_floor": monte_carlo_p_floor(n_perm),
                 "n_distinct_shuffles": int(n_distinct[f]), "exact_null_p_floor": floor,
                 "monte_carlo_p_below_exact_floor": bool(p[f] < floor),
                 "null_ba_mean": float(np.mean(null_ba[:, f])),
                 "null_ba_critical": float(np.percentile(null_ba[:, f], percentile, method=percentile_method)),
                 "n_permutations": int(n_perm), "perm_p_holm": float(ph[f]), "above_chance_holm": bool(ph[f] < alpha)})
  return rows
