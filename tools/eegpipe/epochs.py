"""One recording -> retained, filtered, decimated epochs with metadata, counts and gates.

Generic version of P300 ``p300/session.py::prepare_recording`` @ cd5db15. What the P300
code derived from its event codes (flash table, blocks, label rule) comes from the
project ADAPTER as an event table (paradigm-specific, written per study):

  events = {
    "onset":      (n,) int   epoch onset sample (the event the epoch is locked to),
    "unit":       (n,) int   index of its exchangeable unit within the file (G13), units
                             numbered 0..U-1 in time order,
    "label":      (n,) int   class index 0..k-1,
    "unit_start": (U,) int   first sample of each unit's own interval (e.g. stimulus start),
    "unit_end":   (U,) int   last sample of it (inclusive),
    optional per-epoch columns (e.g. "code"), carried through to the output.
  }

Steps (every parameter from the settings, G5):
  1. rejection on raw epochs ``rejection.window_s`` (ptp, SD, band-power ratio on any
     channel); epochs whose rejection window leaves the recording are dropped and counted.
     ``rejection.enabled`` False keeps every in-bounds epoch;
  2. span gate of the band-pass on ALL epochs of the file (label-free): numtaps - 1;
     extra span gates (``span_gates``: other filter + resampler paths, recorded) and window
     gates (``window_gates``: windows that must not cross units, e.g. a connectivity window);
  3. band-pass of the continuous record if the span gate passes, otherwise unit by unit
     (gates.py fallback, margin ``fallback.margin_s``), then cut ``epoch.window_s`` and
     decimate by ``epoch.decim``.
Counts are per class index; each criterion's rejections are counted separately (G14).
"""

import numpy as np

from eegpipe import filtering as flt
from eegpipe import gates as gt

REQUIRED_EVENTS = ("onset", "unit", "label", "unit_start", "unit_end")


def check_events(events, n_samples):
  missing = [k for k in REQUIRED_EVENTS if k not in events]
  if missing:
    raise ValueError(f"event table lacks {missing}")
  onset, unit, label = (np.asarray(events[k], dtype=np.int64) for k in ("onset", "unit", "label"))
  if not (len(onset) == len(unit) == len(label)):
    raise ValueError("onset, unit and label must have the same length")
  n_units = len(events["unit_start"])
  if len(events["unit_end"]) != n_units:
    raise ValueError("unit_start and unit_end must have one entry per unit")
  if n_units == 0 or len(onset) == 0:
    raise ValueError("no units or no epochs in the file")
  if unit.min() < 0 or unit.max() >= n_units or len(np.unique(unit)) != n_units:
    raise ValueError("unit indices must be 0..U-1 and every unit must have an epoch")
  if np.any(np.diff(np.asarray(events["unit_start"], dtype=np.int64)) <= 0):
    raise ValueError("units must be numbered in time order (unit_start increasing)")
  if np.any(onset < 0) or np.any(onset >= n_samples):
    raise ValueError("an onset lies outside the recording")
  if label.min() < 0:
    raise ValueError("labels are class indices >= 0")
  return onset, unit, label, n_units


def prepare_file(data, fs, events, s):
  """See the module docstring. ``s`` = settings with keys rejection, bandpass, epoch,
  fallback, and optional span_gates, window_gates, classes (names, for counts)."""
  data = np.asarray(data, dtype=np.float64)
  fs = float(fs)
  ns = data.shape[1]
  onset, unit, label, n_units = check_events(events, ns)
  k = len(s["classes"]) if "classes" in s else int(label.max()) + 1

  r = s["rejection"]
  rs, rst = flt.window_bounds(r["window_s"], fs, r["window_rounding"])
  inb = flt.in_bounds(onset, rs, rst, ns)
  if r.get("enabled", True):
    flags = flt.rejection_flags(flt.cut_epochs(data, onset[inb], rs, rst), fs, r["ptp_max"], r["sd_max"],
                                r["sd_ddof"], r["power_ratio_max"], r["ratio_num_hz"], r["ratio_den_hz"],
                                psd=r["psd"])
  else:
    z = np.zeros(int(inb.sum()), bool)
    flags = {"ptp": z, "sd": z, "power_ratio": z, "reject": z}
  keep = np.zeros(len(onset), bool)
  keep[np.flatnonzero(inb)[~flags["reject"]]] = True

  b, p = s["bandpass"], s["epoch"]
  cs, cst = flt.window_bounds(p["window_s"], fs, p["window_rounding"])
  c_first, c_last = gt.epoch_extent(onset, cs, cst)
  g_bp = gt.span_gate(c_first, c_last, unit, n_units, flt.filter_half_span(b["numtaps"]))
  gates = {f"span__bandpass__{key}": v for key, v in g_bp.items()}
  for g in s.get("span_gates", []):
    f0, l0 = gt.resampled_epoch_extent(onset, g["resample_down"], g["epoch_samples_out"])
    span = flt.filter_half_span(g["numtaps"]) + (g["resample_numtaps"] - 1)
    for key, v in gt.span_gate(f0, l0, unit, n_units, span).items():
      gates[f"span__{g['name']}__{key}"] = v
  for g in s.get("window_gates", []):
    ws, wst = flt.window_bounds(g["window_s"], fs, g["window_rounding"])
    w0, w1 = gt.epoch_extent(onset, ws, wst)
    for key, v in gt.window_gate(w0, w1, unit, n_units, events["unit_start"], events["unit_end"]).items():
      gates[f"window__{g['name']}__{key}"] = v

  taps = flt.design_bandpass(fs, b["band_hz"], b["numtaps"], b["window"], scale=b["firwin_scale"])
  n_edge = n_edge_half = 0
  segs = [(0, ns - 1)]
  if g_bp["passes"]:
    filt = flt.bandpass_continuous(data, taps, b["padtype"], b["padlen"], method=b["filtfilt_method"])
    filtering = "continuous"
  else:
    lo, hi = gt.unit_extents(c_first, c_last, unit, n_units)
    margin = int(round(s["fallback"]["margin_s"] * fs))
    segs = gt.unitwise_segments(lo, hi, events["unit_start"], events["unit_end"], b["numtaps"], margin, ns)
    filt = gt.filter_unitwise(data, taps, segs, b["padtype"], b["padlen"], method=b["filtfilt_method"])
    n_edge = gt.count_edge_epochs(c_first[keep], c_last[keep], unit[keep], segs, flt.filter_half_span(b["numtaps"]))
    n_edge_half = gt.count_edge_epochs(c_first[keep], c_last[keep], unit[keep], segs, (b["numtaps"] - 1) // 2)
    filtering = "unitwise_fallback"
  X = flt.decimate(flt.cut_epochs(filt, onset[keep], cs, cst), p["decim"])
  if not np.all(np.isfinite(X)):
    raise ValueError("an epoch contains a sample outside every filtered segment")
  gates.update({"filtering": filtering, "n_used_epochs_near_fallback_segment_edge": n_edge,
                "n_used_epochs_near_fallback_segment_edge_half_reach": n_edge_half})

  half = flt.filter_half_span(b["numtaps"])
  near_end = int(np.sum((onset[keep] + cs < half) | (onset[keep] + cst > ns - half)))
  rej = np.zeros(len(onset), bool)
  rej[np.flatnonzero(inb)[flags["reject"]]] = True
  crit = {c: np.zeros(len(onset), bool) for c in ("ptp", "sd", "power_ratio")}
  for c in crit:
    crit[c][np.flatnonzero(inb)[flags[c]]] = True
  per_class = {}
  for c in range(k):
    m = label == c
    per_class[c] = {"labelled": int(m.sum()), "out_of_bounds": int((m & ~inb).sum()),
                    "rejected": int((m & rej).sum()), "used": int((m & keep).sum()),
                    **{f"rejected_by_{x}": int((m & crit[x]).sum()) for x in crit}}
  counts = {"n_samples": ns, "n_units": n_units, "per_class": per_class,
            "n_used_epochs_within_filter_span_of_file_edge": near_end}
  out = {"X": X, "y": label[keep], "unit": unit[keep], "onset": onset[keep], "keep": keep,
         "counts": counts, "gates": gates, "segments": segs,
         "unit_start": np.asarray(events["unit_start"], dtype=np.int64),
         "unit_end": np.asarray(events["unit_end"], dtype=np.int64)}
  for key, v in events.items():
    if key not in REQUIRED_EVENTS:
      out[key] = np.asarray(v)[keep]
  return out
