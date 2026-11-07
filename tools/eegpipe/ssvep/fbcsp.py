"""Filter-bank common spatial patterns, one-vs-rest (fitted inside the fold only).

Ported from ``mas-ssvep-eeg-xai`` v1.0.4 ``src/features/ssvep/fbcsp_extraction.py``
(``_mean_normalized_cov``, ``MulticlassCSP`` l.60-95, ``FBCSPTransformer`` l.98-117); Ramoser et
al. (2000) IEEE Trans. Rehab. Eng. 8:441; Ang et al. (2008) IJCNN. Changes: scikit-learn
estimator API (so the CSP is refitted on every training fold inside the Pipeline, as
``legacy_eval.fold_matrices`` l.89-100 does); ``reg`` and ``var_floor`` are settings (1e-6,
1e-12 in [M]); class order from the training labels (sorted), not [M]'s 101..105. Not ported:
``extract_fbcsp_features`` (fits on all windows, visualisation only, PF-11) and the per-window
``filter_subbands`` (PF-14; filter banks are applied to the continuous record,
``filterbank.subband_epochs``).
Per class k (one vs rest): S = mean over epochs of W W^T / tr(W W^T); eigh(S_k, S_k + S_rest +
reg I); keep the m largest (descending) and the m smallest eigenvectors; features log10(var_j /
sum_j var_j) of the 2m projections (variances floored). Layout: band-major, then class, then
component: column ((b K) + k) 2m + j.
"""

import numpy as np
from scipy.linalg import eigh
from sklearn.base import BaseEstimator, TransformerMixin


def mean_normalized_cov(X):
  cov = np.einsum("nct,ndt->ncd", X, X)
  tr = np.trace(cov, axis1=1, axis2=2)
  tr = np.where(tr > 0, tr, 1.0)
  return (cov / tr[:, None, None]).mean(axis=0)


class MulticlassCSP(TransformerMixin, BaseEstimator):
  def __init__(self, n_components=1, reg=1e-6, var_floor=1e-12):
    self.n_components, self.reg, self.var_floor = n_components, reg, var_floor

  def fit(self, X, y):
    X = np.asarray(X, dtype=np.float64)
    y = np.asarray(y)
    self.classes_ = np.unique(y)
    n_ch, m = X.shape[1], int(self.n_components)
    if 2 * m > n_ch:
      raise ValueError(f"2 * n_components = {2 * m} exceeds the {n_ch} channels")
    if self.classes_.size < 2:
      raise ValueError("CSP needs at least two classes in the training data")
    filters, eigvals = [], []
    for c in self.classes_:
      s_t = mean_normalized_cov(X[y == c])
      s_r = mean_normalized_cov(X[y != c])
      vals, vecs = eigh(s_t, s_t + s_r + float(self.reg) * np.eye(n_ch))
      pick = np.r_[np.arange(n_ch - 1, n_ch - 1 - m, -1), np.arange(m)]
      filters.append(vecs[:, pick])
      eigvals.append(vals[pick])
    self.filters_ = np.stack(filters)
    self.eigenvalues_ = np.stack(eigvals)
    return self

  def transform(self, X):
    X = np.asarray(X, dtype=np.float64)
    proj = np.einsum("kcj,nct->nkjt", self.filters_, X)
    var = np.maximum(proj.var(axis=-1), float(self.var_floor))
    return np.log10(var / var.sum(axis=-1, keepdims=True)).reshape(len(X), -1)


class FBCSPTransformer(TransformerMixin, BaseEstimator):
  """Filter-bank epochs (n, B, C, T) -> (n, B * K * 2m); one MulticlassCSP per band."""

  def __init__(self, n_components=1, reg=1e-6, var_floor=1e-12):
    self.n_components, self.reg, self.var_floor = n_components, reg, var_floor

  def fit(self, X, y):
    sw = np.asarray(X, dtype=np.float64)
    if sw.ndim != 4:
      raise ValueError(f"FBCSP needs filter-bank epochs (n, B, C, T), got {sw.shape}")
    self.csps_ = [MulticlassCSP(self.n_components, self.reg, self.var_floor).fit(sw[:, b], y) for b in range(sw.shape[1])]
    return self

  def transform(self, X):
    sw = np.asarray(X, dtype=np.float64)
    if sw.shape[1] != len(self.csps_):
      raise ValueError(f"{sw.shape[1]} bands given, fitted on {len(self.csps_)}")
    return np.hstack([c.transform(sw[:, b]) for b, c in enumerate(self.csps_)])
