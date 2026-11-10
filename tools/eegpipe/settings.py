"""The settings file of an "apply the pipeline" run (``configs/pipeline.json``) and its validator.

Every value the pipeline uses comes from this file (G5); every paradigm-dependent value has a
SOURCE in ``sources`` (dotted key -> where it came from):
  "PARADIGM.md §<section>"   a fact of the study (classes, unit, timing, frequencies, contrast);
  "header"                   measured from the file header (fs, channel names; G21);
  "plan"                     a decision of the approved plan (primaries, seeds, budget);
  "profile:<name>"           a default of a shipped profile (``profiles/<name>.json``), NOT yet
                             confirmed; the plan must confirm it (then "profile:<name>, confirmed in
                             plan") or change it, with a reason (G17 i). ``unconfirmed`` lists them;
                             the plan audit fails while any is left.
``validate`` refuses: a missing required key, an unknown top-level key, a family section that is
enabled but incomplete, inconsistent class/contrast/seed settings, fs-derived sample counts that
do not match fs, and (with ``require_sources``) a required key without a source. It never fills
anything in silently.

Profiles: ``erp`` (the P300 Stage-2 values, cd5db15) and ``ssvep`` (the mas-ssvep-eeg-xai v1.0.4
values; stimulus frequencies, harmonics and window have no default: "from PARADIGM, required").
``from_profile(name)`` returns a draft whose every key is sourced "profile:<name>".
"""

import copy
import json
from pathlib import Path

PROFILES = Path(__file__).resolve().parent / "profiles"
TOP_KEYS = {"settings_version", "description", "classes", "fs_hz", "channels", "units", "adapter", "data_root",
            "label_scheme", "epochs", "folds", "baseline", "f1", "ssvep", "networks", "network_input", "f3", "f4",
            "permutation", "statistics", "comparator", "selection", "stage", "sources", "comparator_label"}
REQUIRED = ("classes", "fs_hz", "channels", "adapter", "data_root", "label_scheme", "epochs", "folds", "permutation",
            "statistics", "comparator", "selection", "stage")
PARADIGM_KEYS = ("classes", "fs_hz", "channels", "label_scheme", "epochs.epoch.window_s", "epochs.rejection.window_s",
                 "epochs.bandpass.band_hz", "comparator", "statistics.holm_family", "selection.development_participants",
                 "folds.n_folds", "folds.seed")


IIR_INPUT_KEYS = ("band_hz", "order", "notch_hz", "notch_q", "fs_out_hz", "epoch_window_s", "epoch_samples_out",
                  "span_tol")
MAS_AUG_KEYS = ("p_noise", "p_scale", "p_shift", "p_mixup", "noise_std_frac", "scale_range", "shift_frac", "mixup_alpha")


class SettingsError(ValueError):
  pass


def _get(d, dotted):
  for k in dotted.split("."):
    if not isinstance(d, dict) or k not in d:
      raise KeyError(dotted)
    d = d[k]
  return d


def required_sources(cfg):
  keys = list(PARADIGM_KEYS)
  if cfg.get("ssvep", {}).get("enabled"):
    keys += ["ssvep.stimulus_freqs_hz", "ssvep.fbcca.n_harmonics", "ssvep.fbcca.response_multiple",
             "ssvep.filterbank.bank", "ssvep.filterbank.window_s"]
  if cfg.get("f3", {}).get("enabled"):
    keys += ["f3.bands", "f3.window_s", "f3.condition_level.contrast"]
  if cfg.get("networks", {}).get("enabled"):
    keys += ["networks.seeds", "network_input.band_hz", "network_input.fs_out_hz"]
  return keys


def unconfirmed(cfg):
  """Keys whose source is a profile default not yet confirmed in the plan."""
  return sorted(k for k, v in cfg.get("sources", {}).items()
                if str(v).startswith("profile:") and "confirmed in plan" not in str(v))


def validate(cfg, require_sources=True):
  """Raise SettingsError listing every problem; return the list of unconfirmed profile defaults."""
  probs = []
  unknown = sorted(set(cfg) - TOP_KEYS)
  if unknown:
    probs.append(f"unknown top-level keys {unknown}")
  for k in REQUIRED:
    if k not in cfg:
      probs.append(f"missing required key {k!r}")
  if probs:
    raise SettingsError("; ".join(probs))
  k = len(cfg["classes"])
  if k < 2 or len(set(cfg["classes"])) != k:
    probs.append("classes must be >= 2 distinct names")
  if cfg["label_scheme"] not in ("unit_label", "unit_target"):
    probs.append("label_scheme must be 'unit_label' or 'unit_target'")
  if cfg["label_scheme"] == "unit_target" and k != 2:
    probs.append("label_scheme 'unit_target' (label = code == unit target) needs exactly 2 classes")
  fs = float(cfg["fs_hz"])
  ni = cfg.get("network_input")
  net = cfg.get("networks", {})
  if net.get("enabled") and ni:
    if ni.get("kind", "fir_resample") == "iir_ba":
      miss = [x for x in IIR_INPUT_KEYS if x not in ni]
      if miss:
        probs.append(f"network_input (kind iir_ba) misses {miss}")
      elif abs(float(ni["fs_out_hz"]) - fs) > 1e-9:
        probs.append("network_input (kind iir_ba) does not resample: fs_out_hz must equal fs_hz")
    elif ni.get("kind", "fir_resample") != "fir_resample":
      probs.append(f"network_input.kind {ni.get('kind')!r}: known fir_resample, iir_ba")
    elif abs(float(ni["fs_out_hz"]) - fs * ni["resample_up"] / ni["resample_down"]) > 1e-9:
      probs.append("network_input.fs_out_hz != fs_hz * up / down")
  if net.get("enabled") and len(net.get("seeds", [])) < 3:
    probs.append("networks.seeds: at least 3 seeds (G18)")
  if net.get("enabled") and net.get("windows", {}).get("enabled"):
    w, cv = net["windows"], net.get("cv", {})
    if cv.get("scheme") != "window_grouped":
      probs.append("networks.windows needs networks.cv.scheme 'window_grouped' (folds grouped by trial)")
    elif int(cv.get("n_splits", 0)) < 2:
      probs.append("networks.cv.n_splits must be >= 2")
    else:
      s = sorted(int(x) for x in net.get("seeds", []))
      if any(b - a < int(cv["n_splits"]) for a, b in zip(s, s[1:])):
        probs.append(f"networks.seeds: seed bases closer than networks.cv.n_splits ({cv['n_splits']}) share fold "
                     f"seeds (seed base + fold); space them (G18)")
    if not (float(w.get("window_s", 0)) > 0 and float(w.get("stride_s", 0)) > 0):
      probs.append("networks.windows.window_s and stride_s must be > 0")
    if w.get("aggregate") != "mean_proba":
      probs.append("networks.windows.aggregate must be 'mean_proba' (trial = mean of its windows' probabilities)")
    if cfg["label_scheme"] != "unit_label":
      probs.append("networks.windows needs label_scheme 'unit_label' (one trial = one unit)")
  aug = net.get("augmentation", {})
  if net.get("enabled") and aug.get("enabled") and aug.get("kind") == "mas_p10":
    miss = [x for x in MAS_AUG_KEYS if x not in aug]
    if miss:
      probs.append(f"networks.augmentation (kind mas_p10) misses {miss}")
  f3 = cfg.get("f3", {})
  if f3.get("enabled"):
    c = f3["condition_level"].get("contrast", [1, 0])
    if f3["condition_level"].get("enabled") and (len(c) != 2 or not all(0 <= int(x) < k for x in c) or c[0] == c[1]):
      probs.append("f3.condition_level.contrast must be two different class indices")
  if cfg.get("ssvep", {}).get("enabled"):
    sv = cfg["ssvep"]
    if not sv.get("stimulus_freqs_hz") or len(sv["stimulus_freqs_hz"]) != k:
      probs.append("ssvep.stimulus_freqs_hz: one frequency per class, from PARADIGM.md (no default)")
    nb = cfg.get("f1", {}).get("fbcca", {}).get("n_bands")
    bank = sv.get("filterbank", {}).get("bank") or []
    if nb is not None and int(nb) != len(bank):
      probs.append(f"f1.fbcca.n_bands {nb} != the {len(bank)} bands of ssvep.filterbank.bank (the union input slices them)")
  for mid in cfg["statistics"].get("holm_family", []):
    if mid == cfg["comparator"]:
      probs.append("the comparator cannot be in the Holm family")
  dev = set(cfg["selection"].get("development_participants", []))
  if not dev and cfg["stage"].get("name") == "confirmation":
    probs.append("selection.development_participants is empty: name the development data (G19)")
  for prior_owner in ("f1",):
    for name, spec in cfg.get(prior_owner, {}).get("models", {}).items():
      params = spec.get("params", {})
      if "priors" in params:
        pr = params["priors"]
        if pr is None:
          probs.append(f"{prior_owner}.models.{name}.priors is null (inferred from the data): set it explicitly (G17 i)")
        elif len(pr) != k:
          probs.append(f"{prior_owner}.models.{name}.priors has {len(pr)} entries for {k} classes")
  if require_sources:
    src = cfg.get("sources", {})
    for key in required_sources(cfg):
      try:
        _get(cfg, key)
      except KeyError:
        probs.append(f"missing {key}")
        continue
      if key not in src:
        probs.append(f"no source for {key}")
  if probs:
    raise SettingsError("; ".join(probs))
  return unconfirmed(cfg)


def load_profile(name):
  return json.loads((PROFILES / f"{name}.json").read_text())


def from_profile(name, overrides=None):
  """A draft settings dict from a profile; every key sourced 'profile:<name>'."""
  prof = load_profile(name)
  cfg = {k: copy.deepcopy(v) for k, v in prof.items() if k in TOP_KEYS}
  cfg.update(copy.deepcopy(overrides or {}))
  cfg["sources"] = {k: f"profile:{name}" for k in required_sources(cfg)}
  cfg["sources"].update((overrides or {}).get("sources", {}))
  return cfg


def table(cfg):
  """Markdown table of the paradigm-dependent settings and their sources (for 02_plan)."""
  rows = ["| Setting | Value | Source |", "|---|---|---|"]
  for key in required_sources(cfg):
    try:
      v = _get(cfg, key)
    except KeyError:
      v = "MISSING"
    rows.append(f"| `{key}` | `{json.dumps(v)}` | {cfg.get('sources', {}).get(key, 'NO SOURCE')} |")
  return "\n".join(rows)
