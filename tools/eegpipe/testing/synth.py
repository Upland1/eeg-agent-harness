"""Paradigm-neutral synthetic recordings with planted effects (replaces the P300 project's
``tests/ebr_synth.py`` / ``synth_recording``, which encode that study's event codes).

``recording(...)`` returns (data (C, N), events, info). Layout: units in time order, each
unit = ``n_epochs`` events ``isi`` samples apart, units separated by ``rest`` samples
after the last event's ``tail`` samples. The event table is the adapter contract of
``eegpipe.epochs`` (onset, unit, label, unit_start, unit_end, code).

Two labelling schemes:
  ``"per_epoch"`` (ERP-like, e.g. P300 blocks): every event has a code 0..n_codes-1 (each
    code ``n_epochs // n_codes`` times, shuffled within the unit); each unit has one target
    code; label 1 if the event's code is the unit's target, else 0. Labels vary within a
    unit; the unit target is the exchangeable label (null shuffles move unit targets).
  ``"per_unit"`` (SSVEP-like, trials): every unit has one class 0..k-1 (balanced, shuffled)
    and all its events (windows) carry it.
Planted effects (added to white noise of SD ``noise``):
  ``erp``: a Gaussian bump (amplitude ``amp``, centre ``erp_latency`` samples after onset,
    SD ``erp_width``) on every channel, for label-1 events (per_epoch) or class-c units
    scaled by c (per_unit);
  ``ssvep``: a sinusoid at ``freqs[c]`` (and ``harmonics`` multiples, amplitude halving)
    over the whole unit interval, for class-c units (per_unit only);
  ``phase``: a narrow-band oscillation at ``phase_freq`` on all channels, with channel j
    lagged by ``phase_lag`` * j radians for label-1 events / class-1 units and in phase
    otherwise (same amplitude: a phase-only difference);
  ``none``: noise only (null data).
Everything is drawn from ``numpy.random.default_rng(seed)``.
"""

import numpy as np


def recording(seed, *, fs=256.0, n_channels=4, n_units=6, n_epochs=12, isi=64, rest=400, tail=256,
              lead=300, scheme="per_epoch", n_codes=4, n_classes=2, effect="erp", amp=3.0, noise=1.0,
              erp_latency=77, erp_width=12, freqs=(8.0, 10.0, 12.0, 15.0, 20.0), harmonics=2,
              phase_freq=6.0, phase_lag=0.6, phase_amp=2.0, unit_classes=None, unit_targets=None):
  rng = np.random.default_rng(seed)
  onsets, units, labels, codes, u_start, u_end = [], [], [], [], [], []
  t = lead
  if scheme == "per_unit":
    if unit_classes is None:
      unit_classes = np.resize(np.arange(n_classes), n_units)
      rng.shuffle(unit_classes)
    unit_classes = np.asarray(unit_classes, dtype=np.int64)
  elif scheme == "per_epoch":
    if n_epochs % n_codes:
      raise ValueError("n_epochs must be a multiple of n_codes")
    if unit_targets is None:
      unit_targets = rng.integers(0, n_codes, n_units)
    unit_targets = np.asarray(unit_targets, dtype=np.int64)
  else:
    raise ValueError(f"unknown scheme {scheme!r}")
  for u in range(n_units):
    u_start.append(t)
    if scheme == "per_epoch":
      seq = np.repeat(np.arange(n_codes), n_epochs // n_codes)
      rng.shuffle(seq)
    for e in range(n_epochs):
      onsets.append(t + e * isi)
      units.append(u)
      if scheme == "per_epoch":
        codes.append(int(seq[e]))
        labels.append(int(seq[e] == unit_targets[u]))
      else:
        codes.append(int(unit_classes[u]))
        labels.append(int(unit_classes[u]))
    end = t + (n_epochs - 1) * isi + tail
    u_end.append(end)
    t = end + rest
  n = t + lead
  data = noise * rng.standard_normal((n_channels, n))
  tt = np.arange(n) / fs
  onsets = np.asarray(onsets, dtype=np.int64)
  labels = np.asarray(labels, dtype=np.int64)
  units = np.asarray(units, dtype=np.int64)
  if effect == "erp":
    k = np.arange(-4 * erp_width, 4 * erp_width + 1)
    bump = amp * np.exp(-0.5 * (k / erp_width) ** 2)
    for o, lab in zip(onsets, labels):
      w = lab if scheme == "per_unit" else (1 if lab == 1 else 0)
      if w:
        idx = o + erp_latency + k
        ok = (idx >= 0) & (idx < n)
        data[:, idx[ok]] += w * bump[ok]
  elif effect == "ssvep":
    if scheme != "per_unit":
      raise ValueError("ssvep needs scheme per_unit")
    for u in range(n_units):
      sl = slice(u_start[u], u_end[u] + 1)
      f0 = freqs[unit_classes[u]]
      for h in range(1, harmonics + 1):
        data[:, sl] += (amp / 2 ** (h - 1)) * np.sin(2 * np.pi * h * f0 * tt[sl])[None, :]
  elif effect == "phase":
    lags = phase_lag * np.arange(n_channels)
    for o, lab in zip(onsets, labels):
      sl = slice(max(o - isi // 2, 0), min(o + isi, n))
      lag = lags if lab == 1 else np.zeros(n_channels)
      ph0 = rng.uniform(0, 2 * np.pi)
      data[:, sl] += phase_amp * np.sin(2 * np.pi * phase_freq * tt[sl][None, :] + ph0 - lag[:, None])
  elif effect != "none":
    raise ValueError(f"unknown effect {effect!r}")
  events = {"onset": onsets, "unit": units, "label": labels, "code": np.asarray(codes, dtype=np.int64),
            "unit_start": np.asarray(u_start, dtype=np.int64), "unit_end": np.asarray(u_end, dtype=np.int64)}
  info = {"fs": fs, "ch_names": [f"C{i}" for i in range(n_channels)],
          "unit_classes": None if unit_classes is None else np.asarray(unit_classes),
          "unit_targets": None if unit_targets is None else np.asarray(unit_targets)}
  return data, events, info


def erp_settings(fs=256.0):
  """Settings of ``epochs.prepare_file`` with the P300 run's values (configs/ssvep_methods_stage2.json)."""
  return {
    "classes": ["nontarget", "target"],
    "rejection": {"enabled": True, "window_s": [-0.2, 1.0], "window_rounding": "round", "ptp_max": 200.0,
                  "sd_max": 50.0, "sd_ddof": 0, "power_ratio_max": 0.7, "ratio_num_hz": [20.0, 40.0],
                  "ratio_den_hz": [4.0, 40.0], "psd": {"window": "boxcar", "nfft": "epoch_length",
                                                       "detrend": "constant", "return_onesided": True,
                                                       "scaling": "density"}},
    "bandpass": {"band_hz": [4.0, 14.0], "numtaps": 257, "window": "hamming", "firwin_scale": True,
                 "filtfilt_method": "pad", "padtype": "odd", "padlen": 771},
    "epoch": {"window_s": [0.0, 0.8], "window_rounding": "floor", "decim": 4},
    "fallback": {"margin_s": 1.0},
    "span_gates": [{"name": "network_input", "numtaps": 845, "resample_down": 2, "resample_numtaps": 41,
                    "epoch_samples_out": 102}],
    "window_gates": [{"name": "connectivity", "window_s": [-0.2, 1.0], "window_rounding": "round"}],
  }
