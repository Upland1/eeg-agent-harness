"""VERBATIM reference code from mas-ssvep-eeg-xai v1.0.4 (commit f725369), the P20 network protocol, for the
v0.4.1 known-answer tests (kit_tests/test_eegpipe_v041_p20.py). Extracted mechanically with
`git show f725369:<file> | sed -n <lines>`; only the import lines of the MAS package are replaced by this
module's own names. Do not edit the copied bodies: a test compares eegpipe against them bit for bit.
Pieces: src/preprocessing/dataset/augmentation.py l.20-110; src/models/cnn/eegnet.py l.18-63;
src/models/cnn/training.py l.35-155; src/preprocessing/signal/filters.py l.9-50.
"""
import copy
from typing import Callable, Optional, Tuple

import numpy as np
import torch
from scipy.signal import filtfilt, iirfilter, iirnotch
from sklearn.model_selection import StratifiedGroupKFold
from torch import nn
from torch.utils.data import DataLoader, Dataset, TensorDataset

# ---- augmentation.py l.20-110
OP_ORDER = ("mixup", "scale", "shift", "noise")


def _rng(rng: Optional[np.random.Generator]) -> np.random.Generator:
  return rng if rng is not None else np.random.default_rng()


def add_gaussian_noise(window: np.ndarray, std_frac: float = 0.05, rng: Optional[np.random.Generator] = None) -> np.ndarray:
  """`window + N(0, (std_frac * std_c)^2)` per channel c (std over the window's own time axis)."""
  w = np.asarray(window)
  sd = w.std(axis=-1, keepdims=True)
  return w + _rng(rng).standard_normal(w.shape) * std_frac * sd


def scale_amplitude(window: np.ndarray, scale_range: Tuple[float, float] = (0.9, 1.1),
                    rng: Optional[np.random.Generator] = None) -> np.ndarray:
  """Multiply the whole window by one factor drawn from U(scale_range)."""
  return np.asarray(window) * _rng(rng).uniform(scale_range[0], scale_range[1])


def time_shift(window: np.ndarray, max_shift_frac: float = 0.1, rng: Optional[np.random.Generator] = None) -> np.ndarray:
  """Circular roll along time by an integer in [-s, s], s = floor(max_shift_frac * T)."""
  w = np.asarray(window)
  s = int(max_shift_frac * w.shape[-1])
  return np.roll(w, int(_rng(rng).integers(-s, s + 1)), axis=-1)


def mixup_intra_class(a: np.ndarray, b: np.ndarray, alpha: float = 0.4, rng: Optional[np.random.Generator] = None) -> np.ndarray:
  """`lam * a + (1 - lam) * b`, lam ~ Beta(alpha, alpha) folded to `max(lam, 1 - lam)` so the anchor `a` dominates.

  The caller guarantees that `a` and `b` belong to the same class (the dataset draws `b` from the anchor's class)."""
  lam = _rng(rng).beta(alpha, alpha)
  lam = max(lam, 1.0 - lam)
  return lam * np.asarray(a) + (1.0 - lam) * np.asarray(b)


class SSVEPAugmentedDataset(Dataset):
  """Training-fold dataset augmenting each sample on the fly; returns float32 `(C, T)` and long label tensors.

  `X (n, C, T)` and `y (n,)` are the training fold only. Each operation is applied with its own probability, in the
  order mixup -> scale -> shift -> noise. A class -> indices lookup is precomputed for the mixup partner. All
  randomness comes from `numpy.random.default_rng(seed)`; with a seeded, single-process DataLoader the stream is
  deterministic."""

  def __init__(self, X: np.ndarray, y: np.ndarray, p_noise: float = 0.5, p_scale: float = 0.5, p_shift: float = 0.5,
               p_mixup: float = 0.5, seed: int = 42):
    self.X = np.asarray(X, dtype=np.float32)
    self.y = np.asarray(y).astype(np.int64)
    self.p = {"mixup": p_mixup, "scale": p_scale, "shift": p_shift, "noise": p_noise}
    self.rng = np.random.default_rng(seed)
    self.class_idx = {int(c): np.flatnonzero(self.y == c) for c in np.unique(self.y)}

  def __len__(self) -> int:
    return len(self.y)

  def augment(self, i: int) -> np.ndarray:
    x = self.X[i].astype(np.float64)
    for op in OP_ORDER:
      if self.rng.random() >= self.p[op]:
        continue
      if op == "mixup":
        pool = self.class_idx[int(self.y[i])]
        x = mixup_intra_class(x, self.X[pool[self.rng.integers(len(pool))]], rng=self.rng)
      elif op == "scale":
        x = scale_amplitude(x, rng=self.rng)
      elif op == "shift":
        x = time_shift(x, rng=self.rng)
      else:
        x = add_gaussian_noise(x, rng=self.rng)
    return x

  def __getitem__(self, i: int):
    return torch.from_numpy(self.augment(int(i)).astype(np.float32)), torch.tensor(int(self.y[i]), dtype=torch.long)

# ---- eegnet.py l.18-63

N_CLASSES = 5


class EEGNetSSVEP(nn.Module):
  """EEGNet: temporal conv -> spatial depthwise (max-norm) -> separable conv -> linear head."""

  def __init__(self, n_classes: int = N_CLASSES, n_channels: int = 7, n_samples: int = 256,
               F1: int = 8, D: int = 2, F2: int = 16, kernel_length: int = 125,
               dropout_rate: float = 0.25, max_norm: float = 1.0):
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
    with torch.no_grad():  # head size from a dummy forward (eval: BN statistics untouched)
      was = self.training
      self.eval()
      n_flat = self.features(torch.zeros(1, 1, n_channels, n_samples)).shape[1]
      self.train(was)
    self.head = nn.Linear(n_flat, n_classes)

  def features(self, x: torch.Tensor) -> torch.Tensor:
    x = self.block1_tail(self.bn2(self.spatial(self.bn1(self.temporal(x)))))
    x = self.block2_tail(self.bn3(self.pointwise(self.depthwise2(x))))
    return x.flatten(1)

  def forward(self, x: torch.Tensor) -> torch.Tensor:
    if x.dim() == 3:
      x = x.unsqueeze(1)
    if x.dim() != 4 or x.shape[1] != 1 or x.shape[2] != self.n_channels:
      raise ValueError(f"expected (B, {self.n_channels}, T) or (B, 1, {self.n_channels}, T), got {tuple(x.shape)}")
    return self.head(self.features(x))

  @torch.no_grad()
  def apply_max_norm(self) -> None:
    """Rescale every depthwise spatial filter with L2 norm > `max_norm` to `max_norm` (others unchanged)."""
    w = self.spatial.weight  # (F1*D, 1, C, 1)
    norms = w.flatten(1).norm(dim=1).clamp_min(1e-12).view(-1, 1, 1, 1)
    w.mul_(torch.clamp(norms, max=self.max_norm) / norms)

# ---- training.py l.35-155
BATCH_SIZE = 16
LR = 1e-3
WEIGHT_DECAY = 0.01
ETA_MIN = 1e-5
LABEL_SMOOTHING = 0.1
VAL_FRAC = 0.2
MAX_EPOCHS = 150
PATIENCE = 25
NORM_EPS = 1e-6


def model_factory(name: str, fs: float) -> Callable:
  """`build(n_classes, n_channels, n_samples)` of a named network at sampling rate `fs` (kernel = fs // 2)."""
  name = ALIASES.get(name, name)
  k = int(fs) // 2
  if name == "ccnn":
    return lambda nc, ch, T: CCNN(nc, ch, T, fs=fs)
  if name == "compact_eegnet":
    return lambda nc, ch, T: EEGNetSSVEP(nc, ch, T, F1=96, D=1, F2=96, kernel_length=k, dropout_rate=0.5)
  if name == "eegnet":
    return lambda nc, ch, T: EEGNetSSVEP(nc, ch, T, F1=8, D=2, F2=16, kernel_length=k, dropout_rate=0.25)
  raise ValueError(f"unknown model {name!r}; choose from {MODELS}")


def fit_stats(X: np.ndarray) -> tuple:
  """Per-channel mean and std `(1, C, 1)` over windows and time of `X (n, C, T)` (fitting windows only)."""
  X = np.asarray(X, dtype=np.float64)
  return X.mean(axis=(0, 2), keepdims=True), X.std(axis=(0, 2), keepdims=True) + NORM_EPS


def normalise(X: np.ndarray, mean: np.ndarray, std: np.ndarray) -> np.ndarray:
  return ((np.asarray(X, dtype=np.float64) - mean) / std).astype(np.float32)


def predict_proba(model: nn.Module, X: np.ndarray, device: torch.device, chunk: int = 256) -> np.ndarray:
  """Softmax probabilities `(n, K)` of normalised float32 `X`, eval mode."""
  model.eval()
  out = []
  with torch.no_grad():
    for i in range(0, len(X), chunk):
      out.append(torch.softmax(model(torch.from_numpy(X[i:i + chunk]).to(device)), 1).cpu().numpy())
  return np.concatenate(out) if out else np.zeros((0, 0))


def split_validation(y: np.ndarray, groups: np.ndarray, val_frac: float, seed: int) -> tuple:
  """`(fit_idx, val_idx)` inside the training windows: first split of the inner grouped CV (PF-32)."""
  n_splits = max(2, int(round(1.0 / val_frac)))
  sgk = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=seed)
  fit, val = next(iter(sgk.split(np.zeros((len(y), 1)), y, groups)))
  return fit, val


def _loss_acc(model: nn.Module, X: np.ndarray, y: np.ndarray, device: torch.device) -> tuple:
  p = predict_proba(model, X, device)
  nll = -np.log(np.clip(p[np.arange(len(y)), y], 1e-12, None))
  return float(nll.mean()), float(np.mean(p.argmax(1) == y))


def fit_network(X: np.ndarray, y: np.ndarray, groups: np.ndarray, build_model: Callable, seed: int = 42,
                device: str = "cpu", augment: bool = True, val_frac: float = VAL_FRAC, max_epochs: int = MAX_EPOCHS,
                patience: int = PATIENCE, batch_size: int = BATCH_SIZE, lr: float = LR,
                weight_decay: float = WEIGHT_DECAY, label_smoothing: float = LABEL_SMOOTHING) -> dict:
  """Train on the training windows `X (n, C, T)` with labels `y` in `0..K-1` and trial ids `groups`.

  Returns `model` (best-validation-loss state restored, eval mode), `mean`/`std` (normalisation of the fitting windows),
  `fit_idx`/`val_idx` (indices into the arguments), `train_acc`, `val_acc`, `val_loss`, `best_epoch` (1-based),
  `epochs_run`, `n_params`, `history` (per epoch train loss and val loss)."""
  X, y, groups = np.asarray(X), np.asarray(y).astype(np.int64), np.asarray(groups)
  dev = torch.device(device)
  fit_idx, val_idx = split_validation(y, groups, val_frac, seed)
  if set(groups[fit_idx]) & set(groups[val_idx]):
    raise AssertionError("trial shared between fitting and validation windows")
  mean, std = fit_stats(X[fit_idx])
  Xf, Xv = normalise(X[fit_idx], mean, std), normalise(X[val_idx], mean, std)
  yf, yv = y[fit_idx], y[val_idx]
  torch.manual_seed(seed)
  n_classes = int(y.max()) + 1
  model = build_model(n_classes, X.shape[1], X.shape[2]).to(dev)
  max_norm = getattr(model, "apply_max_norm", None)
  opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
  sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=max_epochs, eta_min=ETA_MIN)
  crit = nn.CrossEntropyLoss(label_smoothing=label_smoothing)
  gen = torch.Generator().manual_seed(seed)
  data = SSVEPAugmentedDataset(Xf, yf, seed=seed) if augment else TensorDataset(torch.from_numpy(Xf), torch.from_numpy(yf))
  loader = DataLoader(data, batch_size=batch_size, shuffle=True, generator=gen)
  if max_norm:
    max_norm()
  best = {"loss": np.inf, "epoch": 0, "state": copy.deepcopy(model.state_dict())}
  history, since = [], 0
  for epoch in range(1, max_epochs + 1):
    model.train()
    tot, cnt = 0.0, 0
    for bx, by in loader:
      if len(by) < 2:  # BatchNorm cannot train on one row
        continue
      bx, by = bx.to(dev), by.to(dev)
      opt.zero_grad()
      loss = crit(model(bx), by)
      loss.backward()
      opt.step()
      if max_norm:
        max_norm()
      tot, cnt = tot + loss.item() * len(by), cnt + len(by)
    sched.step()
    vloss, _ = _loss_acc(model, Xv, yv, dev)
    history.append((tot / max(cnt, 1), vloss))
    if vloss < best["loss"]:
      best.update(loss=vloss, epoch=epoch, state=copy.deepcopy(model.state_dict()))
      since = 0
    else:
      since += 1
      if since >= patience:
        break
  model.load_state_dict(best["state"])
  model.eval()
  _, train_acc = _loss_acc(model, Xf, yf, dev)
  vloss, val_acc = _loss_acc(model, Xv, yv, dev)
  return {"model": model, "mean": mean, "std": std, "fit_idx": fit_idx, "val_idx": val_idx, "train_acc": train_acc,
          "val_acc": val_acc, "val_loss": vloss, "best_epoch": best["epoch"], "epochs_run": len(history),
          "n_params": int(sum(p.numel() for p in model.parameters() if p.requires_grad)), "history": history}


# ---- filters.py l.9-50
def apply_iir_bandpass(data: np.ndarray, fs: float, lowcut: float = 1.0,
                       highcut: float = 60.0, order: int = 4) -> np.ndarray:
  """Zero-phase Butterworth band-pass along the last axis.

  `b, a = iirfilter(order, [lowcut/nyq, highcut/nyq], btype="bandpass",
  ftype="butter")` with `nyq = fs / 2`, applied with `filtfilt(b, a, data,
  axis=-1)` and scipy's default padding (roadmap P01.3). `fs` is required (no
  sampling-rate default, PF-04). Returns a new float64 array of the input shape.
  Raises ValueError unless `fs > 0` and `0 < lowcut < highcut < fs / 2`.
  """
  if not fs > 0:
    raise ValueError(f"fs must be positive, got {fs}")
  nyq = 0.5 * fs
  if not 0 < lowcut < highcut < nyq:
    raise ValueError(f"need 0 < lowcut < highcut < fs/2 = {nyq:g} Hz, got {lowcut}, {highcut}")
  b, a = iirfilter(order, [lowcut / nyq, highcut / nyq], btype="bandpass", ftype="butter")
  return filtfilt(b, a, np.asarray(data, dtype=np.float64), axis=-1)


def apply_notch(data: np.ndarray, fs: float, notch_hz: float = 60.0, q: float = 30.0) -> np.ndarray:
  """Zero-phase IIR notch (`iirnotch(notch_hz, q, fs)`, `filtfilt`) along the last axis (P16, mains).

  Raises ValueError unless `fs > 0`, `0 < notch_hz < fs / 2` and `q > 0`.
  """
  if not fs > 0 or not 0 < notch_hz < 0.5 * fs or not q > 0:
    raise ValueError(f"need fs > 0, 0 < notch_hz < fs/2 and q > 0, got fs={fs}, notch_hz={notch_hz}, q={q}")
  b, a = iirnotch(notch_hz, q, fs=fs)
  return filtfilt(b, a, np.asarray(data, dtype=np.float64), axis=-1)


def broadband_filter(data: np.ndarray, fs: float, lowcut: float, highcut: float, order: int,
                     notch_hz: Optional[float] = None, notch_q: float = 30.0) -> np.ndarray:
  """The P16 continuous broadband filter: Butterworth band-pass (`apply_iir_bandpass`), then the notch.

  Apply it to the whole recording and cut windows afterwards (R3). `notch_hz=None` skips the notch.
  """
  out = apply_iir_bandpass(data, fs, lowcut, highcut, order)
  return out if notch_hz is None else apply_notch(out, fs, notch_hz, notch_q)
