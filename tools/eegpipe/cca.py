"""Target-template CCA spatial filter (ERP option; the P300 baseline's feature step).

Ported unchanged from P300 ``p300/cca.py`` @ cd5db15 (Chailloux Peguero, Mendoza-Montoya,
Antelis 2020, Sensors 20:7198, section 2.5.2, Eqs. 1-2). Fit (training epochs only, inside
the fold): the epochs of class ``target_label`` are averaged to Xbar; P = the stacked target
epochs, Q = Xbar replicated, both (N_target * N_d) x N_e and centred; w_p = eigenvectors of
C_pp^-1 C_pq C_qq^-1 C_qp (generalised symmetric problem) in descending eigenvalue order;
the first ``n_filters`` columns, each sign-fixed so its largest-magnitude entry is positive.
``reg`` adds reg * trace / N_e to the diagonals. transform: (n, N_e, N_d) -> (n, N_d * n_filters),
flattened time-major (sample, then filter).
"""

import numpy as np
from scipy import linalg
from sklearn.base import BaseEstimator, TransformerMixin


class CCASpatialFilter(TransformerMixin, BaseEstimator):
  def __init__(self, n_filters=3, reg=0.0, target_label=1):
    self.n_filters = n_filters
    self.reg = reg
    self.target_label = target_label

  def fit(self, X, y):
    X = np.asarray(X, dtype=np.float64)
    y = np.asarray(y)
    if X.ndim != 3:
      raise ValueError("X must be (n_epochs, n_channels, n_samples)")
    tgt = X[y == self.target_label]
    if tgt.shape[0] == 0:
      raise ValueError("no target epochs in the training data")
    n_e = X.shape[1]
    if not 1 <= self.n_filters <= n_e:
      raise ValueError(f"n_filters {self.n_filters} must be in 1..{n_e}")
    xbar = tgt.mean(axis=0)
    P = np.transpose(tgt, (0, 2, 1)).reshape(-1, n_e)
    Q = np.tile(xbar.T, (tgt.shape[0], 1))
    P = P - P.mean(axis=0)
    Q = Q - Q.mean(axis=0)
    n = P.shape[0]
    Cpp, Cqq, Cpq = P.T @ P / (n - 1), Q.T @ Q / (n - 1), P.T @ Q / (n - 1)
    if self.reg:
      Cpp = Cpp + self.reg * np.trace(Cpp) / n_e * np.eye(n_e)
      Cqq = Cqq + self.reg * np.trace(Cqq) / n_e * np.eye(n_e)
    A = Cpq @ linalg.solve(Cqq, Cpq.T, assume_a="pos")
    A = (A + A.T) / 2.0
    evals, evecs = linalg.eigh(A, Cpp)
    order = np.argsort(evals)[::-1][: self.n_filters]
    W = evecs[:, order]
    flip = np.sign(W[np.argmax(np.abs(W), axis=0), np.arange(W.shape[1])])
    flip[flip == 0] = 1.0
    self.filters_ = W * flip
    self.eigenvalues_ = evals[order]
    self.n_features_in_ = n_e
    return self

  def transform(self, X):
    X = np.asarray(X, dtype=np.float64)
    Z = np.einsum("nct,cf->ntf", X, self.filters_)
    return Z.reshape(Z.shape[0], -1)
