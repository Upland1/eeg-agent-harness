"""Filter-bank CCA (training-free) for SSVEP; Chen, Wang, Gao, Jung, Gao (2015) J. Neural Eng.
12:046008.

Ported from ``mas-ssvep-eeg-xai`` v1.0.4 ``src/features/ssvep/fbcca_extraction.py``
(``generate_reference_signals`` l.35, ``reference_bases`` l.85, ``_orthonormal_data_bases``,
``fbcca_scores_vectorized`` l.114, ``fbcca_weights`` l.51): the vectorised P20 path, not the
legacy scikit-learn CCA path (l.56) nor the quality-gate coupling of ``extract_fbcca_features``.
Changes: stimulus frequencies, harmonics and fs are arguments (the [M] constants TARGET_FREQS and
the fs-250 default are gone, PF-04); ``response_multiple`` (1, or 2 for pattern-reversal /
checkerboard stimulation whose response is at twice the stimulation rate, PF-39) multiplies
every reference frequency; the weights w_b = b^-a + b0 take a, b0 from the settings (1.25,
0.25 in [M] and Chen et al.).
Per epoch, band and target: centre the data over time, orthonormal basis (QR; rank-deficient
epochs via SVD, unused columns zero), r = top singular value of Qx^T Qy (the first canonical
correlation), clipped to [0, 1]; score_k = sum_b w_b r_bk^2. Nothing is fitted, so an epoch's
score never depends on other epochs (no leakage possible); the classifier is argmax_k.
Inputs are filter-bank epochs (n, B, C, T) from ``filterbank.subband_epochs``.
"""

import numpy as np
from sklearn.base import BaseEstimator, ClassifierMixin, TransformerMixin


def reference_signals(f, fs, n_samples, n_harmonics):
  """(2H, T): rows sin(2 pi h f t), cos(2 pi h f t), h = 1..H, t = n / fs."""
  t = np.arange(n_samples) / fs
  rows = []
  for h in range(1, n_harmonics + 1):
    rows += [np.sin(2 * np.pi * h * f * t), np.cos(2 * np.pi * h * f * t)]
  return np.stack(rows)


def reference_frequencies(f, n_harmonics, response_multiple, fs):
  """Reference frequencies of one target: f * m * h for every response multiple m (an int or a list, e.g.
  (1, 2) for on-off and checkerboard runs in one study) and h = 1..H, each once, in order of first
  appearance (m outer, h inner), keeping only those below Nyquist (v0.4 gap 2)."""
  ms = [response_multiple] if np.isscalar(response_multiple) else list(response_multiple)
  out = []
  for m in ms:
    for h in range(1, n_harmonics + 1):
      v = float(f) * float(m) * h
      if v < fs / 2.0 and not any(abs(v - u) < 1e-9 for u in out):
        out.append(v)
  return out


def reference_bases(fs, n_samples, freqs, n_harmonics, response_multiple=1):
  """(K, T, R) orthonormal bases of the mean-centred references of each target; R = 2 x the largest number of
  reference frequencies (targets with fewer get zero columns, which add nothing to the canonical correlation)."""
  t = np.arange(n_samples) / fs
  qs = []
  for f in freqs:
    rf = reference_frequencies(f, n_harmonics, response_multiple, fs)
    if not rf:
      raise ValueError(f"no reference frequency of {f} Hz (x{response_multiple}) is below Nyquist at fs {fs}")
    ref = np.stack([g(2 * np.pi * v * t) for v in rf for g in (np.sin, np.cos)], axis=1)
    q, r = np.linalg.qr(ref - ref.mean(axis=0, keepdims=True))
    if np.abs(np.diag(r)).min() <= 1e-10 * np.abs(np.diag(r)).max():
      raise ValueError(f"references of {f} Hz (x{response_multiple}) are rank deficient at fs {fs}, T {n_samples}")
    qs.append(q)
  width = max(q.shape[1] for q in qs)
  return np.stack([np.pad(q, ((0, 0), (0, width - q.shape[1]))) for q in qs])


def weights(n_bands, a=1.25, b=0.25):
  return np.arange(1, n_bands + 1, dtype=float) ** -a + b


def _orthonormal_data_bases(x, tol=1e-10):
  q, r = np.linalg.qr(x)
  d = np.abs(np.diagonal(r, axis1=-2, axis2=-1))
  bad = d.min(axis=-1) <= tol * np.maximum(d.max(axis=-1), 1e-300)
  bad |= d.max(axis=-1) <= 1e-12
  if bad.any():
    u, s, _ = np.linalg.svd(x[bad], full_matrices=False)
    keep = (s > tol * np.maximum(s.max(axis=-1, keepdims=True), 1e-300)) & (s > 1e-12)
    q[bad] = u * keep[..., None, :]
  return q


def fbcca_scores(bands, bases, w, chunk=256):
  """Scores (n, K) of filter-bank epochs (n, B, C, T) against bases (K, T, 2H)."""
  bands = np.asarray(bands, dtype=np.float64)
  if bands.ndim != 4 or bases.shape[1] != bands.shape[-1]:
    raise ValueError(f"bands {bands.shape} and bases {bases.shape} do not match (need (n, B, C, T), (K, T, R))")
  w = np.asarray(w, dtype=float)
  if w.size != bands.shape[1]:
    raise ValueError(f"{w.size} weights for {bands.shape[1]} bands")
  out = np.zeros((len(bands), len(bases)))
  for lo in range(0, len(bands), chunk):
    x = np.swapaxes(bands[lo:lo + chunk], -1, -2)
    qx = _orthonormal_data_bases(x - x.mean(axis=-2, keepdims=True))
    m = np.einsum("nbtc,ktr->nbkcr", qx, bases)
    r = np.clip(np.linalg.svd(m, compute_uv=False)[..., 0], 0.0, 1.0)
    out[lo:lo + chunk] = np.einsum("b,nbk->nk", w, r ** 2)
  return out


class FBCCAFeatures(TransformerMixin, BaseEstimator):
  """(n, B, C, T) -> (n, K) FBCCA scores; fit stores nothing data-dependent (y never read)."""

  def __init__(self, fs=None, stimulus_freqs_hz=None, n_harmonics=None, response_multiple=1, weight_a=1.25,
               weight_b=0.25):
    self.fs, self.stimulus_freqs_hz, self.n_harmonics = fs, stimulus_freqs_hz, n_harmonics
    self.response_multiple, self.weight_a, self.weight_b = response_multiple, weight_a, weight_b

  def fit(self, X, y=None):
    X = np.asarray(X)
    self.bases_ = reference_bases(float(self.fs), X.shape[-1], self.stimulus_freqs_hz, int(self.n_harmonics),
                                  self.response_multiple)
    self.w_ = weights(X.shape[1], self.weight_a, self.weight_b)
    return self

  def transform(self, X):
    return fbcca_scores(X, self.bases_, self.w_)


class FBCCAClassifier(ClassifierMixin, BaseEstimator):
  """Training-free FBCCA: class c = the target whose frequency is ``stimulus_freqs_hz[c]``;
  predict = argmax of the scores; decision_function = the scores. ``fit`` reads only the class
  set (to check it matches the stimulus list), never the data."""

  def __init__(self, fs=None, stimulus_freqs_hz=None, n_harmonics=None, response_multiple=1, weight_a=1.25,
               weight_b=0.25):
    self.fs, self.stimulus_freqs_hz, self.n_harmonics = fs, stimulus_freqs_hz, n_harmonics
    self.response_multiple, self.weight_a, self.weight_b = response_multiple, weight_a, weight_b

  def fit(self, X, y):
    k = len(self.stimulus_freqs_hz)
    self.classes_ = np.arange(k)
    bad = set(np.unique(y).tolist()) - set(range(k))
    if bad:
      raise ValueError(f"labels {sorted(bad)} have no stimulus frequency (classes 0..{k - 1})")
    self.features_ = FBCCAFeatures(self.fs, self.stimulus_freqs_hz, self.n_harmonics, self.response_multiple,
                                   self.weight_a, self.weight_b).fit(X)
    return self

  def decision_function(self, X):
    return self.features_.transform(X)

  def predict(self, X):
    return self.decision_function(X).argmax(axis=1).astype(np.int64)


def make_fbcca(cfg):
  """The training-free method ``ssvep/fbcca`` from the settings section ``ssvep.fbcca``."""
  c = cfg["ssvep"]["fbcca"]
  rm = c["response_multiple"]
  return FBCCAClassifier(fs=float(cfg["fs_hz"]), stimulus_freqs_hz=list(cfg["ssvep"]["stimulus_freqs_hz"]),
                         n_harmonics=int(c["n_harmonics"]), response_multiple=rm if np.isscalar(rm) else list(rm),
                         weight_a=float(c["weight_a"]), weight_b=float(c["weight_b"]))
