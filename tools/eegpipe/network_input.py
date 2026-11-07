"""Network input of the retained epochs: band-pass, polyphase resampling, epochs on the new grid.

Generic version of P300 ``p300/nn_input.py::network_epochs`` @ cd5db15. For the epochs that
``epochs.prepare_file`` retained (rejection decided there, never here; this module only cuts
the same events from another signal):
  1. zero-phase FIR band-pass of the CONTINUOUS record (``band_hz``, ``numtaps``, ``window``,
     filtfilt with ``padtype`` / ``padlen``);
  2. ``scipy.signal.resample_poly(up=1, down)`` with its window and padtype explicit; output
     sample k corresponds to input sample k * down;
  3. epochs of ``epoch_samples_out`` = floor((t1 - t0) * fs_out) samples starting at
     floor(onset / down) (window must start at 0).
Span gate: (numtaps - 1) + (resample_numtaps - 1) between units' used input samples, on all
events of the file (label-free). If it fails, the file is filtered unit by unit (gates.py
fallback, margin ``fallback.margin_s``); each segment's first sample is moved up to the next
multiple of ``down`` so the segment's grid is the file's grid; samples outside every segment are
NaN and an epoch touching one raises. Epochs within the full reach of their segment's edge are
counted. Every value comes from the settings (``network_input``, G5); the configured resampler
length and fs_out are checked against SciPy's and fs * up / down.
"""

import numpy as np

from eegpipe import filtering as flt
from eegpipe import gates as gt


def network_epochs(data, fs, events, kept, s, fallback_margin_s):
  """``events`` = the adapter's event table of the file; ``kept`` = ``prepare_file`` output (its
  ``keep`` mask selects the epochs); ``s`` = settings ``network_input``.
  Returns {"X": (n_kept, C, n_out), "gate", "filtering", "n_edge", "segments", "fs_out"}."""
  data = np.asarray(data, dtype=np.float64)
  ns = data.shape[1]
  up, down, n_out = int(s["resample_up"]), int(s["resample_down"]), int(s["epoch_samples_out"])
  if up != 1:
    raise ValueError("only up = 1 is supported (output sample k is input sample k * down)")
  if int(s["resample_numtaps"]) != flt.resampler_numtaps(up, down):
    raise ValueError(f"resample_numtaps {s['resample_numtaps']} != SciPy's {flt.resampler_numtaps(up, down)}")
  fs_out = float(fs) * up / down
  if float(s["fs_out_hz"]) != fs_out:
    raise ValueError(f"fs_out_hz {s['fs_out_hz']} != fs * up / down = {fs_out}")
  w0, w1 = s["epoch_window_s"]
  if int(np.floor((w1 - w0) * fs_out)) != n_out or w0 != 0.0:
    raise ValueError(f"epoch_samples_out {n_out} != floor({w1 - w0} * {fs_out}) or the window does not start at 0")
  onset_all = np.asarray(events["onset"], dtype=np.int64)
  unit_all = np.asarray(events["unit"], dtype=np.int64)
  n_units = len(events["unit_start"])
  keep = np.asarray(kept["keep"], dtype=bool)
  first, last = gt.resampled_epoch_extent(onset_all, down, n_out)
  span = flt.filter_half_span(s["numtaps"]) + (int(s["resample_numtaps"]) - 1)
  gate = gt.span_gate(first, last, unit_all, n_units, span)
  taps = flt.design_bandpass(fs, s["band_hz"], s["numtaps"], s["window"], scale=s["firwin_scale"])
  n_res = -(-ns * up // down)

  def res(x):
    return flt.resample(x, up, down, s["resample_window"], s["resample_padtype"])
  if gate["passes"]:
    x_out = res(flt.bandpass_continuous(data, taps, s["padtype"], s["padlen"], method=s["filtfilt_method"]))
    filtering, n_edge, segs = "continuous", 0, [(0, ns - 1)]
  else:
    lo, hi = gt.unit_extents(first, last, unit_all, n_units)
    margin = int(round(fallback_margin_s * fs))
    segs = gt.unitwise_segments(lo, hi, events["unit_start"], events["unit_end"], s["numtaps"], margin, ns)
    segs = [(a + (-a) % down, z) for a, z in segs]
    x_out = np.full((data.shape[0], n_res), np.nan)
    for a, z in segs:
      r = res(flt.bandpass_continuous(data[:, a:z + 1], taps, s["padtype"], s["padlen"], method=s["filtfilt_method"]))
      k = a // down
      x_out[:, k:k + r.shape[1]] = r[:, :n_res - k]
    kf, kl = gt.resampled_epoch_extent(onset_all[keep], down, n_out)
    edge = (int(s["numtaps"]) - 1) + (int(s["resample_numtaps"]) - 1)
    n_edge = gt.count_edge_epochs(kf, kl, unit_all[keep], segs, edge)
    filtering = "unitwise_fallback"
  if x_out.shape[1] != n_res:
    raise ValueError(f"resampled length {x_out.shape[1]} != ceil(n * up / down) = {n_res}")
  X = flt.cut_resampled(x_out, onset_all[keep], down, n_out)
  if not np.all(np.isfinite(X)):
    raise ValueError("a network epoch contains a sample outside every filtered segment")
  return {"X": X, "gate": gate, "filtering": filtering, "n_edge": int(n_edge), "segments": segs, "fs_out": fs_out}
