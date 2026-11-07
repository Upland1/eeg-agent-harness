"""Filtering, epoching, rejection, decimation and resampling (G5, G21).

Ported from P300 ``p300/preprocess.py`` and ``p300/nn_input.py`` @ cd5db15 (functions of the
same names), unchanged except that nothing is P300-specific: every parameter is an argument.

Window bounds: start = R(t0 * fs), stop = R(t1 * fs), samples [start, stop) relative to the
event onset; R = ``round`` (numpy round-half-even) or ``floor``.
Band-pass: linear-phase type-I FIR (``scipy.signal.firwin``, pass_zero False) applied with
``scipy.signal.filtfilt`` (method "pad", padtype and padlen explicit) to the CONTINUOUS
recording; epochs are cut afterwards (G21).
Rejection on raw epochs: an epoch is rejected if any channel has peak-to-peak above
``ptp_max``, SD above ``sd_max``, or periodogram power ratio P[num band] / P[den band] above
``power_ratio_max`` (closed bands; a flat channel gives ratio inf, i.e. rejected).
Decimation keeps every ``factor``-th sample starting at the onset sample (no anti-alias
filter: the caller low-passes first). Polyphase resampling: ``scipy.signal.resample_poly``
with its window and padtype passed explicitly; its FIR has 2 * 10 * max(up, down) + 1 taps.

Sources: SciPy 1.18.1 docstrings of ``firwin``, ``filtfilt``, ``periodogram``,
``resample_poly`` (scipy/signal/_signaltools.py l.4044-4049 for the resampler length).
"""

import math

import numpy as np
from scipy import signal

PSD_DEFAULT = {"window": "boxcar", "nfft": "epoch_length", "detrend": "constant",
               "return_onesided": True, "scaling": "density"}


def window_bounds(window_s, fs, rounding):
  """(t0, t1) in seconds -> (start, stop) sample offsets, samples [start, stop)."""
  if rounding == "round":
    f = lambda v: int(np.round(v))  # noqa: E731
  elif rounding == "floor":
    f = lambda v: int(math.floor(v))  # noqa: E731
  else:
    raise ValueError(f"rounding {rounding!r} must be 'round' or 'floor'")
  start, stop = f(window_s[0] * fs), f(window_s[1] * fs)
  if stop <= start:
    raise ValueError(f"empty window {window_s} at fs {fs}")
  return start, stop


def design_bandpass(fs, band_hz, numtaps, window, scale=True):
  """Linear-phase FIR band-pass taps (type I: odd numtaps)."""
  if numtaps % 2 != 1:
    raise ValueError("numtaps must be odd for a type I band-pass FIR")
  return signal.firwin(numtaps, list(band_hz), window=window, pass_zero=False, scale=bool(scale), fs=fs)


def filter_half_span(numtaps):
  """Samples on each side of a sample that reach it through filtfilt (two passes)."""
  return numtaps - 1


def bandpass_continuous(data, taps, padtype, padlen, method="pad"):
  """Zero-phase FIR filtering of (n_channels, n_samples) along time."""
  if method != "pad":
    raise ValueError("only method 'pad' is supported (padtype/padlen apply to it)")
  return signal.filtfilt(taps, [1.0], np.asarray(data, dtype=np.float64), axis=-1,
                         padtype=padtype, padlen=padlen, method=method)


def in_bounds(onsets, start, stop, n_samples):
  onsets = np.asarray(onsets, dtype=np.int64)
  return (onsets + start >= 0) & (onsets + stop <= n_samples)


def cut_epochs(data, onsets, start, stop):
  """(n_channels, n_samples), onsets -> (n_epochs, n_channels, stop - start)."""
  onsets = np.asarray(onsets, dtype=np.int64)
  if not np.all(in_bounds(onsets, start, stop, data.shape[1])):
    raise ValueError("an epoch runs past the recording; filter onsets with in_bounds first")
  idx = onsets[:, None] + np.arange(start, stop)[None, :]
  return np.transpose(data[:, idx], (1, 0, 2))


def band_power_ratio(raw_epochs, fs, ratio_num_hz, ratio_den_hz, psd=None):
  """Per epoch and channel: (num, den, ratio) of the power-ratio criterion."""
  x = np.asarray(raw_epochs, dtype=np.float64)
  q = dict(PSD_DEFAULT if psd is None else psd)
  nfft = x.shape[-1] if q["nfft"] == "epoch_length" else int(q["nfft"])
  f, pxx = signal.periodogram(x, fs=fs, window=q["window"], nfft=nfft, detrend=q["detrend"],
                              return_onesided=bool(q["return_onesided"]), scaling=q["scaling"], axis=-1)
  num = pxx[..., (f >= ratio_num_hz[0]) & (f <= ratio_num_hz[1])].sum(axis=-1)
  den = pxx[..., (f >= ratio_den_hz[0]) & (f <= ratio_den_hz[1])].sum(axis=-1)
  with np.errstate(divide="ignore", invalid="ignore"):
    ratio = np.where(den > 0, num / den, np.inf)
  return num, den, ratio


def rejection_flags(raw_epochs, fs, ptp_max, sd_max, sd_ddof, power_ratio_max, ratio_num_hz,
                    ratio_den_hz, psd=None):
  """Per-epoch booleans per criterion (True = met on any channel) and ``reject`` (any)."""
  x = np.asarray(raw_epochs, dtype=np.float64)
  ptp = np.ptp(x, axis=-1) > ptp_max
  sd = np.std(x, axis=-1, ddof=sd_ddof) > sd_max
  _, _, ratio = band_power_ratio(x, fs, ratio_num_hz, ratio_den_hz, psd=psd)
  pr = ratio > power_ratio_max
  out = {"ptp": ptp.any(axis=1), "sd": sd.any(axis=1), "power_ratio": pr.any(axis=1)}
  out["reject"] = out["ptp"] | out["sd"] | out["power_ratio"]
  return out


def decimate(epochs, factor):
  """Keep every ``factor``-th sample, starting at the first (onset) sample."""
  return np.asarray(epochs)[..., ::factor]


def resampler_numtaps(up, down):
  """Length of resample_poly's default FIR for this up/down."""
  return 2 * 10 * max(int(up), int(down)) + 1


def resample(data, up, down, window, padtype):
  """resample_poly along the last axis with every parameter explicit."""
  return signal.resample_poly(np.asarray(data, dtype=np.float64), int(up), int(down), axis=-1,
                              window=tuple(window) if isinstance(window, (list, tuple)) else window,
                              padtype=padtype)


def cut_resampled(x_out, onsets, down, n_out):
  """(n_channels, n_resampled) -> (n_epochs, n_channels, n_out) starting at floor(onset / down)."""
  k0 = np.asarray(onsets, dtype=np.int64) // int(down)
  if np.any(k0 < 0) or np.any(k0 + n_out > x_out.shape[1]):
    raise ValueError("a resampled epoch runs past the recording")
  idx = k0[:, None] + np.arange(n_out)[None, :]
  return np.transpose(x_out[:, idx], (1, 0, 2))
