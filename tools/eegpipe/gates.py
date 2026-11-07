"""Leakage gates between exchangeable units and the unit-wise filtering fallback (G1, G13, G21).

Ported from P300 ``p300/session.py`` @ cd5db15 (``epoch_extent``, ``resampled_epoch_extent``,
``block_extents``, ``block_gaps``, ``span_gate``, ``window_gate``, ``blockwise_segments``,
``filter_blockwise``, ``count_edge_epochs``); "block" is generalised to "unit" (the G13
exchangeable unit of the study: block, trial, run). Units of a file are indexed 0..n-1 in
time order.

For each epoch the first and last raw sample a transform uses are known (``epoch_extent``,
or ``resampled_epoch_extent`` for an epoch cut on a grid decimated by ``down`` at
floor(onset / down)). Per unit, lo = smallest first sample of its epochs, hi = largest last
sample; between consecutive units the gap is lo[u+1] - hi[u].
  Span gate: a zero-phase FIR (filtfilt) of numtaps taps reaches numtaps - 1 samples on each
  side; a resampler with r taps reaches a further r - 1. The gate passes iff every gap is
  greater than the span: no filtered sample of one unit's epochs depends on a sample used
  by another unit's epochs.
  Window gate: the analysis windows of different units must not share a sample; a unit's
  extent is the union of its own interval (``unit_start``..``unit_end``, e.g. stimulus
  start to stimulus end, from the adapter) and its epochs' windows; passes iff consecutive
  extents are disjoint (gap > 0).
Fallback when the span gate fails: filter unit by unit. Segment of unit u = from
min(unit_start - margin, lo - numtaps) to max(unit_end + margin, hi + numtaps), clipped to
the recording and so that it never contains a sample used by another unit's epochs; each
segment is filtered on its own; samples outside every segment are NaN. If two units' used
samples overlap (gap <= 0) no segmentation exists: ValueError. Epochs with a used sample
within ``edge`` samples of their segment edge are counted.
"""

import numpy as np

from eegpipe import filtering as flt


def epoch_extent(onsets, start, stop):
  """First and last raw sample (inclusive) of epochs [onset + start, onset + stop)."""
  onsets = np.asarray(onsets, dtype=np.int64)
  return onsets + start, onsets + stop - 1


def resampled_epoch_extent(onsets, down, n_out):
  """First and last input sample (inclusive) behind an epoch of ``n_out`` samples on the grid
  decimated by ``down`` starting at floor(onset / down)."""
  onsets = np.asarray(onsets, dtype=np.int64)
  k0 = onsets // down
  return k0 * down, (k0 + n_out - 1) * down


def unit_extents(first, last, unit, n_units):
  """Per unit: min of ``first`` and max of ``last`` over its epochs."""
  unit = np.asarray(unit, dtype=np.int64)
  first, last = np.asarray(first), np.asarray(last)
  lo = np.array([int(np.min(first[unit == u])) for u in range(n_units)], dtype=np.int64)
  hi = np.array([int(np.max(last[unit == u])) for u in range(n_units)], dtype=np.int64)
  return lo, hi


def unit_gaps(lo, hi):
  """gaps[u] = lo[u + 1] - hi[u] for consecutive units (length n_units - 1)."""
  return np.asarray(lo[1:], dtype=np.int64) - np.asarray(hi[:-1], dtype=np.int64)


def span_gate(first, last, unit, n_units, span):
  """Every gap between consecutive units' used samples > ``span``."""
  lo, hi = unit_extents(first, last, unit, n_units)
  gaps = unit_gaps(lo, hi)
  min_gap = int(gaps.min()) if gaps.size else None
  return {"span_samples": int(span), "min_gap_samples": min_gap,
          "passes": bool(min_gap is None or min_gap > span),
          "gap_exceeds_2x_span": bool(min_gap is None or min_gap > 2 * span)}


def window_gate(first, last, unit, n_units, unit_start, unit_end):
  """Unit extents (own interval united with the epochs' windows) are disjoint."""
  lo, hi = unit_extents(first, last, unit, n_units)
  lo = np.minimum(lo, np.asarray(unit_start, dtype=np.int64))
  hi = np.maximum(hi, np.asarray(unit_end, dtype=np.int64))
  gaps = unit_gaps(lo, hi)
  min_gap = int(gaps.min()) if gaps.size else None
  return {"min_gap_samples": min_gap, "passes": bool(min_gap is None or min_gap > 0)}


def unitwise_segments(lo, hi, unit_start, unit_end, numtaps, margin, n_samples):
  """Inclusive (seg_lo, seg_hi) per unit for the fallback (module docstring)."""
  lo, hi = np.asarray(lo, dtype=np.int64), np.asarray(hi, dtype=np.int64)
  n = lo.size
  if n > 1 and np.any(unit_gaps(lo, hi) <= 0):
    raise ValueError("the used samples of two units overlap; unit-wise filtering impossible")
  segs = []
  for u in range(n):
    s_lo = min(int(unit_start[u]) - margin, int(lo[u]) - numtaps)
    s_hi = max(int(unit_end[u]) + margin, int(hi[u]) + numtaps)
    s_lo, s_hi = max(s_lo, 0), min(s_hi, n_samples - 1)
    if u > 0:
      s_lo = max(s_lo, int(hi[u - 1]) + 1)
    if u < n - 1:
      s_hi = min(s_hi, int(lo[u + 1]) - 1)
    segs.append((s_lo, s_hi))
  for u in range(n):
    for o in range(n):
      if o != u and segs[u][0] <= hi[o] and lo[o] <= segs[u][1]:
        raise AssertionError(f"segment of unit {u} contains epoch samples of unit {o}")
  return segs


def filter_unitwise(data, taps, segments, padtype, padlen, method="pad"):
  """filtfilt each segment separately; samples outside every segment are NaN."""
  data = np.asarray(data, dtype=np.float64)
  out = np.full(data.shape, np.nan)
  for s_lo, s_hi in segments:
    out[:, s_lo:s_hi + 1] = flt.bandpass_continuous(data[:, s_lo:s_hi + 1], taps, padtype, padlen, method=method)
  return out


def count_edge_epochs(first, last, unit, segments, edge):
  """Epochs with a used sample within ``edge`` samples of their unit's segment edge."""
  unit = np.asarray(unit, dtype=np.int64)
  s_lo = np.array([segments[u][0] for u in unit], dtype=np.int64)
  s_hi = np.array([segments[u][1] for u in unit], dtype=np.int64)
  return int(np.sum((np.asarray(first) - s_lo < edge) | (s_hi - np.asarray(last) < edge)))
