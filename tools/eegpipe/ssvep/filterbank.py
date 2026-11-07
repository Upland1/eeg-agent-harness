"""Filter banks applied to the CONTINUOUS recording, then cut into epochs (G21; [M] PF-14, P16).

Source: ``mas-ssvep-eeg-xai`` v1.0.4 ``src/preprocessing/windowing.py`` (``fbcca_filter_bank``,
continuous sos filtering by ``scripts/build_windows.py``) and ``src/features/ssvep/
fbcsp_extraction.py::butter_bandpass_filter``. A bank is a list of band specs:
  {"kind": "cheby1", "order": 4, "ripple_db": 3.0, "band_hz": [6, 90]}   (FBCCA bank of [M])
  {"kind": "butter", "order": 4, "band_hz": [7, 12]}                       (FBCSP bank of [M])
each designed as second-order sections at the recording's fs (an upper edge at or above Nyquist
is capped at fs / 2 - 1, as [M]) and applied zero-phase with ``scipy.signal.sosfiltfilt``
(padtype "odd", padlen from the settings) along time.
IIR filters ring for ever, so the leakage gate between units uses an EFFECTIVE span: the number
of samples after which the impulse response envelope of the band's filter stays below ``tol``
(default 1e-3) of its peak, doubled for the two passes of filtfilt (``effective_span``). The
gate (``eegpipe.gates.span_gate`` with this span) is reported for every band; if it fails, the
bank is applied unit by unit (gates.unitwise_segments), so a neighbouring trial's stimulation
cannot ring into another trial's window.
"""

import numpy as np
from scipy import signal
from sklearn.base import BaseEstimator, TransformerMixin

from eegpipe import filtering as flt
from eegpipe import gates as gt


class BandSlice(TransformerMixin, BaseEstimator):
  """Selects bands [start, stop) of filter-bank epochs (n, B, C, T); nothing is fitted. Lets one union input
  hold the FBCCA bank first and the FBCSP bank after it (v0.4 gap 1)."""

  def __init__(self, start=0, stop=None):
    self.start, self.stop = start, stop

  def fit(self, X, y=None):
    return self

  def transform(self, X):
    return np.asarray(X)[:, self.start:self.stop]


def design(spec, fs):
  lo, hi = float(spec["band_hz"][0]), float(spec["band_hz"][1])
  hi = min(hi, fs / 2.0 - 1.0)
  if spec["kind"] == "cheby1":
    return signal.cheby1(int(spec["order"]), float(spec["ripple_db"]), [lo, hi], btype="band", fs=fs, output="sos")
  if spec["kind"] == "butter":
    return signal.butter(int(spec["order"]), [lo, hi], btype="band", fs=fs, output="sos")
  raise ValueError(f"unknown filter kind {spec['kind']!r}; known: cheby1, butter")


def effective_span(sos, tol=1e-3, max_samples=200000):
  """Samples until the impulse response's envelope stays below tol * peak, times two (filtfilt)."""
  n = 1024
  while True:
    imp = np.zeros(n)
    imp[0] = 1.0
    h = np.abs(signal.sosfilt(sos, imp))
    above = np.flatnonzero(h >= tol * h.max())
    last = int(above[-1]) if above.size else 0
    if last < n - 64 or n >= max_samples:
      return 2 * (last + 1)
    n *= 2


def apply_bank(data, fs, bank, padlen):
  """(C, N) -> (B, C, N): each band, zero-phase, on the whole record."""
  data = np.asarray(data, dtype=np.float64)
  return np.stack([signal.sosfiltfilt(design(b, fs), data, axis=-1, padtype="odd", padlen=padlen) for b in bank])


def subband_epochs(data, fs, events, kept, window_s, rounding, bank, padlen, tol=1e-3, margin_s=1.0):
  """Filter-bank epochs (n_kept, B, C, T) of the retained events (``kept`` = epochs.prepare_file
  output), window ``window_s`` relative to the onset. Returns {"X", "gates", "filtering"}."""
  data = np.asarray(data, dtype=np.float64)
  ns = data.shape[1]
  onset = np.asarray(events["onset"], dtype=np.int64)
  unit = np.asarray(events["unit"], dtype=np.int64)
  n_units = len(events["unit_start"])
  keep = np.asarray(kept["keep"], dtype=bool)
  start, stop = flt.window_bounds(window_s, fs, rounding)
  first, last = gt.epoch_extent(onset, start, stop)
  sos = [design(b, fs) for b in bank]
  spans = [effective_span(s, tol) for s in sos]
  gates = [gt.span_gate(first, last, unit, n_units, sp) for sp in spans]
  if all(g["passes"] for g in gates):
    fb = np.stack([signal.sosfiltfilt(s, data, axis=-1, padtype="odd", padlen=padlen) for s in sos])
    filtering = "continuous"
  else:
    lo, hi = gt.unit_extents(first, last, unit, n_units)
    segs = gt.unitwise_segments(lo, hi, events["unit_start"], events["unit_end"], max(spans), int(round(margin_s * fs)), ns)
    fb = np.full((len(sos),) + data.shape, np.nan)
    for a, z in segs:
      for i, s in enumerate(sos):
        fb[i][:, a:z + 1] = signal.sosfiltfilt(s, data[:, a:z + 1], axis=-1, padtype="odd",
                                               padlen=min(padlen, z - a - 1))
    filtering = "unitwise_fallback"
  idx = onset[keep][:, None] + np.arange(start, stop)[None, :]
  if np.any(idx < 0) or np.any(idx >= ns):
    raise ValueError("a filter-bank epoch runs past the recording")
  X = np.transpose(fb[:, :, idx], (2, 0, 1, 3))
  if not np.all(np.isfinite(X)):
    raise ValueError("a filter-bank epoch contains a sample outside every filtered segment")
  return {"X": X, "filtering": filtering,
          "gates": [{"band_hz": list(b["band_hz"]), "effective_span": int(sp), **g} for b, sp, g in zip(bank, spans, gates)]}
