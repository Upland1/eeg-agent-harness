"""Family F2 under MAS's P20 protocol (v0.4.1): overlapping windows of each trial, folds grouped by trial,
MAS's EEGNetSSVEP and augmentation, trial scores from the windows' mean probability.

Source: ``mas-ssvep-eeg-xai`` v1.0.4 (commit f725369) [M]:
  ``scripts/benchmarks/neural_networks/benchmark_nn_sweep.py`` l.1-21 (protocol), l.98-150 (fold loop:
  ``make_splits("grouped", y, groups, seed)``, ``assert_no_shared_trials``, ``cnn_fold(..., seed=seed + k)``);
  ``src/models/cnn/training.py`` l.1-43 (constants), l.46-57 (``model_factory``: kernel = fs // 2),
  l.59-66, l.79-155 (``fit_network``), l.157-175 (``cnn_fold``);
  ``src/models/cnn/eegnet.py`` l.20-63 (``EEGNetSSVEP``);
  ``src/preprocessing/dataset/augmentation.py`` l.1-110 (``SSVEPAugmentedDataset``, order mixup -> scale ->
  shift -> noise, mixup lambda ~ Beta(0.4, 0.4) folded to max(lam, 1 - lam), shift s = floor(0.1 T));
  ``src/preprocessing/signal/filters.py`` l.9-50 (``broadband_filter``: ``iirfilter`` Butterworth band-pass
  then ``iirnotch``, each applied with ``filtfilt(b, a)`` and SciPy's default padding);
  ``scripts/build_windows.py`` l.1-26, l.203-217 (windows of ``window_sec`` every ``int(stride_sec * fs)``
  samples inside each trial, one true trial id per window).
Pieces:
  * ``iir_network_input``: MAS's broadband filter on the CONTINUOUS record, the trial window cut at fs (no
    resampling). The leakage gate between units uses the effective span of the band-pass followed by the
    notch (impulse-response envelope below ``tol`` of its peak, doubled for filtfilt; as
    ``ssvep.filterbank.effective_span``); if it fails the record is filtered unit by unit (G1).
  * ``window_starts`` / ``crop_trials``: window k of a trial starts k * stride samples after the trial start.
  * ``window_grouped_splits``: StratifiedGroupKFold(n_splits, shuffle=True, random_state=seed) over windows,
    groups = trial uid; no trial on both sides (checked).
  * ``EEGNetSSVEP``: exact port of [M] (symmetric padding k // 2 and 8, max-norm on the spatial filters
    only); registered in ``networks.CLASSES``.
  * ``MasAugmentedDataset``: exact port of [M] ``SSVEPAugmentedDataset``; used by ``networks.fit_network``
    when ``augmentation.kind`` is ``"mas_p10"``.
  * ``cv_network_windows``: every fold k trains ``networks.fit_network`` with seed = seed base + k for the
    model, the DataLoader, the augmentation and the inner validation split ([M] nn_sweep l.117 and
    training.py l.104); out-of-fold window probabilities; trial probability = mean over its windows.
Every value comes from the settings (G5): ``network_input`` (kind ``iir_ba``), ``networks.windows``,
``networks.cv``, ``networks.trainer``, ``networks.augmentation``.
"""

import hashlib
import json
import time

import numpy as np
import torch
from scipy import signal
from sklearn.model_selection import StratifiedGroupKFold
from torch import nn
from torch.utils.data import Dataset

from eegpipe import evaluate as evl
from eegpipe import filtering as flt
from eegpipe import gates as gt
from eegpipe import networks as nw


# ---------------------------------------------------------------- input: MAS broadband IIR filter
def iir_design(fs, s):
  """[(b, a), ...] of MAS's broadband filter: Butterworth band-pass (iirfilter, ba), then the notch if set."""
  nyq = 0.5 * float(fs)
  lo, hi = float(s["band_hz"][0]), float(s["band_hz"][1])
  if not 0 < lo < hi < nyq:
    raise ValueError(f"network_input.band_hz needs 0 < low < high < fs/2 = {nyq:g}, got {lo}, {hi}")
  stages = [signal.iirfilter(int(s["order"]), [lo / nyq, hi / nyq], btype="bandpass", ftype="butter")]
  if s.get("notch_hz") is not None:
    stages.append(signal.iirnotch(float(s["notch_hz"]), float(s["notch_q"]), fs=float(fs)))
  return stages


def iir_apply(x, stages):
  """filtfilt(b, a, x, axis=-1) per stage with SciPy's default padding (padtype 'odd', padlen 3 max(len(a),
  len(b))) [M filters.py l.9-50]."""
  out = np.asarray(x, dtype=np.float64)
  for b, a in stages:
    out = signal.filtfilt(b, a, out, axis=-1)
  return out


def iir_effective_span(stages, tol, max_samples=400000):
  """Samples until the cascade's impulse-response envelope stays below tol * peak, times two (filtfilt)."""
  n = 2048
  while True:
    h = np.zeros(n)
    h[0] = 1.0
    for b, a in stages:
      h = signal.lfilter(b, a, h)
    h = np.abs(h)
    above = np.flatnonzero(h >= tol * h.max())
    last = int(above[-1]) if above.size else 0
    if last < n - 64 or n >= max_samples:
      return 2 * (last + 1)
    n *= 2


def iir_network_input(data, fs, events, kept, s, fallback_margin_s):
  """Trials (n_kept, C, n_out) of the retained events on MAS's broadband-filtered record, no resampling.
  ``s`` = settings ``network_input`` (kind ``iir_ba``). Returns {"X", "gate", "filtering", "fs_out", "padlen"}."""
  data = np.asarray(data, dtype=np.float64)
  ns = data.shape[1]
  if float(s["fs_out_hz"]) != float(fs):
    raise ValueError(f"network_input.fs_out_hz {s['fs_out_hz']} != fs {fs}: kind iir_ba does not resample")
  w0, w1 = s["epoch_window_s"]
  n_out = int(s["epoch_samples_out"])
  if w0 < 0.0 or int(np.floor((w1 - w0) * float(fs))) != n_out:
    raise ValueError(f"epoch_samples_out {n_out} != floor({w1 - w0} * {fs}) or the window starts before the event")
  s0 = int(np.floor(w0 * float(fs)))
  onset_all = np.asarray(events["onset"], dtype=np.int64) + s0
  unit_all = np.asarray(events["unit"], dtype=np.int64)
  n_units = len(events["unit_start"])
  keep = np.asarray(kept["keep"], dtype=bool)
  stages = iir_design(fs, s)
  span = iir_effective_span(stages, float(s["span_tol"]))
  first, last = gt.epoch_extent(onset_all, 0, n_out)
  gate = {**gt.span_gate(first, last, unit_all, n_units, span), "effective_span": int(span)}
  padlen = [3 * max(len(a), len(b)) for b, a in stages]
  if gate["passes"]:
    x = iir_apply(data, stages)
    filtering = "continuous"
  else:
    lo, hi = gt.unit_extents(first, last, unit_all, n_units)
    segs = gt.unitwise_segments(lo, hi, events["unit_start"], events["unit_end"], span,
                                int(round(fallback_margin_s * fs)), ns)
    x = np.full(data.shape, np.nan)
    for a, z in segs:
      x[:, a:z + 1] = iir_apply(data[:, a:z + 1], stages)
    filtering = "unitwise_fallback"
  if not np.all(flt.in_bounds(onset_all[keep], 0, n_out, ns)):
    raise ValueError("a network trial runs past the recording")
  X = flt.cut_epochs(x, onset_all[keep], 0, n_out)
  if not np.all(np.isfinite(X)):
    raise ValueError("a network trial contains a sample outside every filtered segment")
  return {"X": X, "gate": gate, "filtering": filtering, "fs_out": float(fs), "padlen": padlen}


# ---------------------------------------------------------------- windows
def window_geometry(fs, w):
  """(n, stride) in samples: n = round(window_s * fs), stride = int(stride_s * fs) [M build_windows l.210]."""
  n, stride = int(round(float(w["window_s"]) * fs)), int(float(w["stride_s"]) * fs)
  if n < 1 or stride < 1:
    raise ValueError(f"window {n} and stride {stride} samples must be >= 1")
  return n, stride


def window_starts(n_trial, n, stride):
  """Starts 0, stride, ... of every whole window inside a trial of n_trial samples."""
  if n_trial < n:
    raise ValueError(f"trial of {n_trial} samples < window of {n}")
  return np.arange(0, n_trial - n + 1, stride, dtype=np.int64)


def crop_trials(X, n, stride):
  """(n_trials, C, T) -> windows (n_trials * m, C, n), trial index per window (m windows per trial, in order)."""
  X = np.asarray(X)
  st = window_starts(X.shape[-1], n, stride)
  W = np.stack([X[..., s:s + n] for s in st], axis=1)            # (n_trials, m, C, n)
  return W.reshape((-1,) + W.shape[2:]), np.repeat(np.arange(X.shape[0]), len(st))


def window_grouped_splits(y_w, groups_w, n_splits, seed):
  """[(fold, train, test)] of StratifiedGroupKFold(n_splits, shuffle=True, random_state=seed) over windows,
  groups = trial uid [M cv_utils.py l.96-99; nn_sweep l.106-110]; no group on both sides (checked)."""
  sgk = StratifiedGroupKFold(n_splits=int(n_splits), shuffle=True, random_state=int(seed))
  groups_w = np.asarray(groups_w)
  out = []
  for f, (tr, te) in enumerate(sgk.split(np.zeros((len(y_w), 1)), np.asarray(y_w), groups_w)):
    if set(groups_w[tr]) & set(groups_w[te]):
      raise AssertionError(f"fold {f}: a trial is in both the training and the test windows")
    out.append((f, tr, te))
  covered = np.concatenate([te for _, _, te in out])
  if len(covered) != len(y_w) or len(np.unique(covered)) != len(y_w):
    raise AssertionError("the test folds do not cover every window exactly once")
  return out


def splits_sha256(splits, groups_w):
  fold = np.full(len(groups_w), -1, dtype=np.int64)
  for f, _, te in splits:
    fold[te] = f
  text = json.dumps({"fold": fold.tolist(), "group": np.asarray(groups_w).tolist()}, separators=(",", ":"))
  return hashlib.sha256(text.encode()).hexdigest()


def trial_probabilities(proba_w, trial_w, n_trials):
  """(n_trials, k): mean of each trial's window probabilities."""
  proba_w, trial_w = np.asarray(proba_w), np.asarray(trial_w)
  out = np.full((n_trials, proba_w.shape[1]), np.nan)
  for t in range(n_trials):
    m = trial_w == t
    if m.any():
      out[t] = proba_w[m].mean(axis=0)
  return out


# ---------------------------------------------------------------- MAS EEGNetSSVEP (exact port)
class EEGNetSSVEP(nn.Module):
  """[M] eegnet.py l.20-63: temporal conv (padding k // 2) -> BN -> depthwise spatial (max-norm) -> BN -> ELU ->
  AvgPool(1, 4) -> Dropout; depthwise (1, 16) padding 8 + pointwise -> BN -> ELU -> AvgPool(1, 8) -> Dropout;
  Linear head sized by a dummy forward. All convolutions bias-free."""

  def __init__(self, n_classes, n_channels, n_samples, F1, D, F2, kernel_length, dropout_rate, max_norm):
    super().__init__()
    self.n_channels, self.n_samples, self.max_norm = n_channels, n_samples, max_norm
    self.temporal = nn.Conv2d(1, F1, (1, kernel_length), padding=(0, kernel_length // 2), bias=False)
    self.bn1 = nn.BatchNorm2d(F1)
    self.spatial = nn.Conv2d(F1, F1 * D, (n_channels, 1), groups=F1, bias=False)
    self.bn2 = nn.BatchNorm2d(F1 * D)
    self.depthwise2 = nn.Conv2d(F1 * D, F1 * D, (1, 16), padding=(0, 8), groups=F1 * D, bias=False)
    self.pointwise = nn.Conv2d(F1 * D, F2, (1, 1), bias=False)
    self.bn3 = nn.BatchNorm2d(F2)
    self.block1_tail = nn.Sequential(nn.ELU(), nn.AvgPool2d((1, 4)), nn.Dropout(dropout_rate))
    self.block2_tail = nn.Sequential(nn.ELU(), nn.AvgPool2d((1, 8)), nn.Dropout(dropout_rate))
    with torch.no_grad():
      was = self.training
      self.eval()
      n_flat = self.features(torch.zeros(1, 1, n_channels, n_samples)).shape[1]
      self.train(was)
    self.head = nn.Linear(n_flat, n_classes)

  def features(self, x):
    x = self.block1_tail(self.bn2(self.spatial(self.bn1(self.temporal(x)))))
    x = self.block2_tail(self.bn3(self.pointwise(self.depthwise2(x))))
    return x.flatten(1)

  def forward(self, x):
    if x.dim() == 3:
      x = x.unsqueeze(1)
    if x.dim() != 4 or x.shape[1] != 1 or x.shape[2] != self.n_channels:
      raise ValueError(f"expected (B, {self.n_channels}, T) or (B, 1, {self.n_channels}, T), got {tuple(x.shape)}")
    return self.head(self.features(x))

  @torch.no_grad()
  def apply_max_norm(self):
    w = self.spatial.weight
    norms = w.flatten(1).norm(dim=1).clamp_min(1e-12).view(-1, 1, 1, 1)
    w.mul_(torch.clamp(norms, max=self.max_norm) / norms)


nw.CLASSES["EEGNetSSVEP"] = EEGNetSSVEP


# ---------------------------------------------------------------- MAS augmentation (exact port)
MAS_OP_ORDER = ("mixup", "scale", "shift", "noise")


class MasAugmentedDataset(Dataset):
  """[M] augmentation.py ``SSVEPAugmentedDataset``: per sample, in the order mixup -> scale -> shift -> noise,
  each op with its probability (one ``rng.random()`` draw per op); mixup partner ``pool[rng.integers(len(pool))]``
  of the same class, lambda ~ Beta(alpha, alpha) folded to max(lam, 1 - lam); scale U(range); circular shift by
  an integer in [-s, s], s = int(frac * T); noise N(0, (std_frac * std_c)^2) per channel. Own numpy generator."""

  def __init__(self, X, y, p_noise, p_scale, p_shift, p_mixup, seed, noise_std_frac, scale_range, shift_frac,
               mixup_alpha):
    self.X = np.asarray(X, dtype=np.float32)
    self.y = np.asarray(y).astype(np.int64)
    self.p = {"mixup": float(p_mixup), "scale": float(p_scale), "shift": float(p_shift), "noise": float(p_noise)}
    self.noise_std_frac, self.scale_range = float(noise_std_frac), tuple(scale_range)
    self.shift_frac, self.mixup_alpha = float(shift_frac), float(mixup_alpha)
    self.rng = np.random.default_rng(seed)
    self.class_idx = {int(c): np.flatnonzero(self.y == c) for c in np.unique(self.y)}

  def __len__(self):
    return len(self.y)

  def augment(self, i):
    x = self.X[i].astype(np.float64)
    for op in MAS_OP_ORDER:
      if self.rng.random() >= self.p[op]:
        continue
      if op == "mixup":
        pool = self.class_idx[int(self.y[i])]
        b = self.X[pool[self.rng.integers(len(pool))]]
        lam = self.rng.beta(self.mixup_alpha, self.mixup_alpha)
        lam = max(lam, 1.0 - lam)
        x = lam * np.asarray(x) + (1.0 - lam) * np.asarray(b)
      elif op == "scale":
        x = np.asarray(x) * self.rng.uniform(self.scale_range[0], self.scale_range[1])
      elif op == "shift":
        s = int(self.shift_frac * x.shape[-1])
        x = np.roll(x, int(self.rng.integers(-s, s + 1)), axis=-1)
      else:
        sd = x.std(axis=-1, keepdims=True)
        x = x + self.rng.standard_normal(x.shape) * self.noise_std_frac * sd
    return x

  def __getitem__(self, i):
    return torch.from_numpy(self.augment(int(i)).astype(np.float32)), torch.tensor(int(self.y[i]), dtype=torch.long)


def mas_dataset(Xf, yf, aug, seed):
  return MasAugmentedDataset(Xf, yf, aug["p_noise"], aug["p_scale"], aug["p_shift"], aug["p_mixup"], seed,
                             aug["noise_std_frac"], aug["scale_range"], aug["shift_frac"], aug["mixup_alpha"])


# ---------------------------------------------------------------- cross-validation
def cv_network_windows(X_trials, y_trials, trial_uid, spec, seed_base, ncfg, device, class_names, fs):
  """Out-of-fold predictions of one network and seed base under the P20 protocol.

  ``X_trials`` (n_trials, C, T) from ``iir_network_input`` (or ``network_input``), ``y_trials`` labels 0..k-1,
  ``trial_uid`` unique per trial. Returns (trial pred, trial proba (n_trials, k), fold rows, curve rows,
  info) with info = {"n_windows_per_trial", "window_ba", "window_acc", "network_folds_sha256"}."""
  w, cv, tr, aug = ncfg["windows"], ncfg["cv"], ncfg["trainer"], ncfg["augmentation"]
  y_trials = np.asarray(y_trials).astype(np.int64)
  k = len(class_names)
  n_win, stride = window_geometry(fs, w)
  Xw, t_of_w = crop_trials(X_trials, n_win, stride)
  yw = y_trials[t_of_w]
  gw = np.asarray(trial_uid)[t_of_w]
  splits = window_grouped_splits(yw, gw, cv["n_splits"], cv["seed"])
  build = nw.model_builder(spec)
  proba_w = np.full((len(yw), k), np.nan)
  rows, curves = [], []
  for fold, train, test in splits:
    if len(np.unique(yw[train])) < k:
      raise ValueError(f"fold {fold}: a training set lacks a class")
    t0 = time.time()
    fseed = int(seed_base) + int(fold)
    f = nw.fit_network(Xw[train], yw[train], gw[train], build, fseed, fseed, device, tr, aug, n_classes=k)
    _, q = nw.predict(f, Xw[test], device, tr["predict_chunk"])
    proba_w[test] = q
    fit_idx, val_idx = train[f["fit_idx"]], train[f["val_idx"]]
    p_fit, _ = nw.predict(f, Xw[fit_idx], device, tr["predict_chunk"])
    p_val, _ = nw.predict(f, Xw[val_idx], device, tr["predict_chunk"])
    tq = trial_probabilities(q, t_of_w[test], len(y_trials))
    tt = np.unique(t_of_w[test])
    rows.append({"fold": fold, "fold_seed": fseed, "n_train_windows": int(len(train)), "n_test_windows": int(len(test)),
                 "n_test_trials": int(len(tt)),
                 **evl.class_metrics(y_trials[tt], tq[tt].argmax(1), class_names),
                 "window_ba": evl.class_metrics(yw[test], q.argmax(1), class_names)["ba"],
                 "window_acc": float(np.mean(q.argmax(1) == yw[test])),
                 "train_acc": float(np.mean(p_fit == yw[fit_idx])),
                 "train_ba": evl.class_metrics(yw[fit_idx], p_fit, class_names)["ba"],
                 "val_acc": float(np.mean(p_val == yw[val_idx])), "n_fit": int(len(fit_idx)), "n_val": int(len(val_idx)),
                 "n_val_trials": int(len(np.unique(gw[val_idx]))), "best_epoch": f["best_epoch"],
                 "epochs_run": f["epochs_run"], "hit_max_epochs": f["hit_max_epochs"],
                 "best_val_loss": f["best_val_loss"], "n_params": f["n_params"], "seconds": time.time() - t0})
    curves += [{"fold": fold, **h} for h in f["history"]]
  if np.isnan(proba_w).any():
    raise ValueError("some windows received no out-of-fold prediction")
  pt = trial_probabilities(proba_w, t_of_w, len(y_trials))
  if np.isnan(pt).any():
    raise ValueError("some trials received no out-of-fold prediction")
  info = {"n_windows_per_trial": int(len(window_starts(np.asarray(X_trials).shape[-1], n_win, stride))),
          "window_ba": evl.class_metrics(yw, proba_w.argmax(1), class_names)["ba"],
          "window_acc": float(np.mean(proba_w.argmax(1) == yw)),
          "network_folds_sha256": splits_sha256(splits, gw)}
  return pt.argmax(1).astype(np.int64), pt, rows, curves, info
