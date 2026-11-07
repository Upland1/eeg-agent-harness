"""Family F3(b): single-trial band phase features (classifier input and GNN edges).

Ported from P300 ``p300/phase.py`` @ cd5db15 (``band_bins``, ``spectra``, ``band_cross``,
``unit_phasor``, ``PhaseFeatures``, ``phase_transformer``, ``make_f3``), itself from
``mas-ssvep-eeg-xai`` v1.0.4 (``connectivity_graph_features.py``: ``_hann_fft``,
``edge_phase``, ``upper_tri_flat``; ``graph_inputs.py::build_inputs``).

Spectrum of one epoch and channel: constant detrend, taper ``window`` (``get_window(window,
T, fftbins)``), ONE segment, rfft with n = nfft = T. A band holds the bins with low <= f <=
high (closed). Band cross-spectrum S_ij = sum over the band's bins of X_i conj(X_j), i < j
(row-major pairs); its angle is the band phase difference (never a mean of angles). Unit
phasor S / |S|, (1, 0) where |S| <= 1e-12.
``PhaseFeatures``: ``fit(X)`` stores the LABEL-FREE template = mean over all epochs it is
given (the training fold; ``y`` is never read), or zero with ``subtract_template`` False;
``transform`` subtracts it from every epoch and returns (cos, sin) or the chosen subset,
layout pair-major, then band, then component; ``edge_tensor`` gives the same phasors as a full
(n, C, C, n_bands * n_components) tensor ([j, i] the conjugate of [i, j], diagonal (1, 0)).
These are PHASE FEATURES, reported as such, never as connectivity (P300 plan P2-7).
Method ids ``f3/phase_features/<variant>``; the model and scaler tables come from the
settings (``f3.classification.model`` names an entry of ``f1.models``).
"""

import numpy as np
from scipy.signal import get_window
from sklearn.base import BaseEstimator, TransformerMixin

from eegpipe import filtering as flt
from eegpipe.graphstats import pairs

PHASOR_FLOOR = 1e-12
COMPONENTS = ("cos", "sin")
F3_PREFIX = "f3/phase_features/"


def phase_epochs(data, fs, kept_onsets, f3):
  """Raw epochs ``f3.window_s`` (rounding ``f3.window_rounding``) of the retained events, checked
  against ``f3.window_samples`` and nfft = window length (one segment, no padding)."""
  start, stop = flt.window_bounds(f3["window_s"], fs, f3["window_rounding"])
  if stop - start != int(f3["window_samples"]):
    raise ValueError(f"window has {stop - start} samples, settings say {f3['window_samples']}")
  if int(f3["nfft"]) != stop - start:
    raise ValueError("nfft must equal the window length (one segment, no padding)")
  return flt.cut_epochs(np.asarray(data, dtype=np.float64), kept_onsets, start, stop)


def band_bins(n_fft, fs, band):
  f = np.fft.rfftfreq(int(n_fft), d=1.0 / float(fs))
  lo, hi = band
  idx = np.flatnonzero((f >= lo) & (f <= hi))
  if idx.size == 0:
    raise ValueError(f"band {band} holds no bin at nfft {n_fft}, fs {fs}")
  return idx


def spectra(X, window, fftbins, detrend):
  X = np.asarray(X, dtype=np.float64)
  if detrend != "constant":
    raise ValueError("only detrend 'constant' is implemented")
  T = X.shape[-1]
  w = get_window(window, T, fftbins=bool(fftbins))
  return np.fft.rfft((X - X.mean(axis=-1, keepdims=True)) * w, n=T, axis=-1)


def band_cross(Z):
  iu, ju = pairs(Z.shape[1])
  return np.einsum("npk,npk->np", Z[:, iu, :], np.conj(Z[:, ju, :]))


def unit_phasor(S):
  mag = np.abs(S)
  ok = mag > PHASOR_FLOOR
  return np.where(ok, S / np.where(ok, mag, 1.0), 1.0 + 0j)


class PhaseFeatures(BaseEstimator, TransformerMixin):
  def __init__(self, fs=None, bands=None, subtract_template=None, components=None, window=None,
               window_fftbins=None, detrend=None, nfft=None):
    self.fs, self.bands, self.subtract_template = fs, bands, subtract_template
    self.components, self.window, self.window_fftbins = components, window, window_fftbins
    self.detrend, self.nfft = detrend, nfft

  def _check(self, X):
    X = np.asarray(X, dtype=np.float64)
    if X.ndim != 3:
      raise ValueError(f"expected (n, C, T) epochs, got {X.shape}")
    if int(self.nfft) != X.shape[-1]:
      raise ValueError(f"nfft {self.nfft} != epoch length {X.shape[-1]}")
    bad = [c for c in self.components if c not in COMPONENTS]
    if bad or not self.components:
      raise ValueError(f"components {self.components}; choose from {COMPONENTS}")
    return X

  def fit(self, X, y=None):  # y is never read: the template is label-free
    X = self._check(X)
    self.template_ = X.mean(axis=0) if self.subtract_template else np.zeros(X.shape[1:])
    self.n_fit_epochs_ = int(X.shape[0])
    self.bins_ = [band_bins(self.nfft, self.fs, b) for b in self.bands]
    return self

  def phasors(self, X):
    X = self._check(X)
    Z = spectra(X - self.template_[None], self.window, self.window_fftbins, self.detrend)
    return np.stack([unit_phasor(band_cross(Z[..., b])) for b in self.bins_], axis=-1)

  def _parts(self, ph):
    return np.stack([ph.real if c == "cos" else ph.imag for c in self.components], axis=-1)

  def transform(self, X):
    ph = self.phasors(X)
    return self._parts(ph).reshape(ph.shape[0], -1)

  def edge_tensor(self, X):
    ph = self.phasors(X)
    n, _, nb = ph.shape
    C = np.asarray(X).shape[1]
    full = np.ones((n, C, C, nb), dtype=np.complex128)
    iu, ju = pairs(C)
    full[:, iu, ju, :] = ph
    full[:, ju, iu, :] = np.conj(ph)
    return self._parts(full).reshape(n, C, C, -1)


def f3_enabled(cfg):
  return bool(cfg.get("f3", {}).get("enabled", False))


def f3_method_ids(cfg):
  return [F3_PREFIX + v for v in cfg["f3"]["classification"]["order"]]


def primary_f3_id(cfg):
  return F3_PREFIX + cfg["f3"]["classification"]["primary"]


def phase_transformer(variant, cfg, subtract_template=None):
  f3 = cfg["f3"]
  sp = f3["spectrum"]
  return PhaseFeatures(fs=float(cfg["fs_hz"]), bands=[list(f3["bands"][b]) for b in variant["bands"]],
                       subtract_template=bool(variant["subtract_template"] if subtract_template is None
                                              else subtract_template),
                       components=list(variant["components"]), window=sp["window"],
                       window_fftbins=bool(sp["window_fftbins"]), detrend=sp["detrend"], nfft=int(f3["nfft"]))


def make_f3(method_id, cfg):
  """Pipeline(PhaseFeatures, StandardScaler, model) for ``f3/phase_features/<variant>``."""
  from sklearn.pipeline import Pipeline

  from eegpipe import classical as cl
  if not method_id.startswith(F3_PREFIX):
    raise ValueError(f"not an F3 method id: {method_id!r}")
  c = cfg["f3"]["classification"]
  v = method_id[len(F3_PREFIX):]
  if v not in c["variants"]:
    raise ValueError(f"unknown F3 variant {v!r}")
  return Pipeline([("phase", phase_transformer(c["variants"][v], cfg)), ("scaler", cl.build_scaler(c["scaler"])),
                   ("model", cl.build_model(cfg["f1"]["models"][c["model"]]))])
