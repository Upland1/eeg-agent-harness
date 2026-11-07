"""Family F2: EEGNet and ShallowConvNet, Sebastian's trainer, and grouped cross-validation (torch).

Ported from P300 ``p300/networks.py`` @ cd5db15 (itself ported from ``mas-ssvep-eeg-xai`` v1.0.4,
f725369: ``src/models/cnn/eegnet.py::EEGNetSSVEP``, ``shallow_conv_net.py::ShallowConvNet``,
``training.py::fit_network``, ``src/preprocessing/dataset/augmentation.py``), generalised to k
classes (Sebastian's decision D5): labels 0..k-1, balanced class weights w_c = n / (k n_c) over
the fitting epochs, softmax over k outputs. Everything else is the P300 code:
  EEGNet with the Lawhern et al. 2018 corrections of the P300 audit (dense max-norm on the
  classifier rows, 'same' padding: left (K-1)//2, right K//2); ShallowConvNet with kernel and
  pool clamped to the window;
  trainer: validation set = first split of StratifiedGroupKFold over the TRAINING-fold epochs
  grouped by unit uid (seed ``val_seed``; the test fold never enters); per-channel
  normalisation from the fitting epochs (or per-feature for the GNN); balanced class weights
  in the training loss and, if set, in the validation loss; ``torch.manual_seed(seed)``
  immediately before the model is built, DataLoader generator and augmentation generator
  seeded with the same seed; AdamW + CosineAnnealingLR stepped per epoch; label smoothing on
  the training loss only; batches below ``min_batch_size`` skipped (BatchNorm); max-norm after
  every step; best validation state restored; early stopping after ``patience`` epochs;
  ``hit_max_epochs`` reported;
  augmentation (off by default): scale, noise, and the [M] time shift and same-class mixup;
  determinism flags and CUBLAS_WORKSPACE_CONFIG from the settings; a configured CUDA device
  that is unavailable is an error, never a silent CPU fallback.
Every hyperparameter comes from the settings (G5); a parameter table must name exactly the
constructor's parameters. ``CLASSES`` is extended by ``eegpipe.ssvep`` (CCNN, DualBranchFusionCNN)
and ``eegpipe.graph`` (the GNN).
Sources: Lawhern et al. (2018) J. Neural Eng. 15:056013 (arXiv:1611.08024v4, Table 2);
Schirrmeister et al. (2017) Hum. Brain Mapp. 38:5391-5420; PyTorch 2.13 documentation
(Conv2d, BatchNorm2d, AdamW, CosineAnnealingLR, CrossEntropyLoss, Reproducibility notes);
scikit-learn 1.9.1 StratifiedGroupKFold.
"""

import copy
import inspect
import os
import time

import numpy as np
import torch
from sklearn.model_selection import StratifiedGroupKFold
from torch import nn
from torch.utils.data import DataLoader, Dataset, TensorDataset

from eegpipe import evaluate as evl

LOG_EPS = 1e-6  # [M] shallow_conv_net.py LOG_EPS


# ---------------------------------------------------------------- models
class EEGNet(nn.Module):
  """EEGNet; adapted from [M] eegnet.py::EEGNetSSVEP (module docstring)."""

  def __init__(self, n_classes, n_channels, n_samples, F1, D, F2, kernel_length, sep_kernel_length,
               pool1, pool2, dropout_rate, max_norm, dense_max_norm):
    super().__init__()
    self.n_channels, self.n_samples, self.max_norm = n_channels, n_samples, max_norm
    self.dense_max_norm = dense_max_norm
    # adapted from [M] eegnet.py l.30-44; 'same' padding per [L Table 2] / [R] (module docstring (b))
    self.pad_temporal = same_pad(kernel_length)
    self.temporal = nn.Conv2d(1, F1, (1, kernel_length), bias=False)
    self.bn1 = nn.BatchNorm2d(F1)
    self.spatial = nn.Conv2d(F1, F1 * D, (n_channels, 1), groups=F1, bias=False)
    self.bn2 = nn.BatchNorm2d(F1 * D)
    self.pad_sep = same_pad(sep_kernel_length)
    self.depthwise2 = nn.Conv2d(F1 * D, F1 * D, (1, sep_kernel_length), groups=F1 * D, bias=False)
    self.pointwise = nn.Conv2d(F1 * D, F2, (1, 1), bias=False)
    self.bn3 = nn.BatchNorm2d(F2)
    self.block1_tail = nn.Sequential(nn.ELU(), nn.AvgPool2d((1, pool1)), nn.Dropout(dropout_rate))
    self.block2_tail = nn.Sequential(nn.ELU(), nn.AvgPool2d((1, pool2)), nn.Dropout(dropout_rate))
    with torch.no_grad():
      was = self.training
      self.eval()
      n_flat = self.features(torch.zeros(1, 1, n_channels, n_samples)).shape[1]
      self.train(was)
    self.head = nn.Linear(n_flat, n_classes)

  def features(self, x):
    # adapted from [M] eegnet.py l.46-49
    x = self.block1_tail(self.bn2(self.spatial(self.bn1(self.temporal(self.pad_temporal(x))))))
    x = self.block2_tail(self.bn3(self.pointwise(self.depthwise2(self.pad_sep(x)))))
    return x.flatten(1)

  def forward(self, x):
    if x.dim() == 3:
      x = x.unsqueeze(1)
    if x.dim() != 4 or x.shape[1] != 1 or x.shape[2] != self.n_channels:
      raise ValueError(f"expected (B, {self.n_channels}, T) or (B, 1, {self.n_channels}, T), got {tuple(x.shape)}")
    return self.head(self.features(x))

  @torch.no_grad()
  def apply_max_norm(self):
    """Rescale every depthwise spatial filter with L2 norm > max_norm to max_norm [M l.58-63],
    and every row of the dense weight (one output unit) with L2 norm > dense_max_norm to
    dense_max_norm [L Table 2; R] (module docstring (a))."""
    _renorm_rows(self.spatial.weight, self.max_norm)
    _renorm_rows(self.head.weight, self.dense_max_norm)


def _renorm_rows(w, limit):
  """In place: w[i] *= min(||w[i]||, limit) / ||w[i]|| over the flattened trailing dims."""
  norms = w.flatten(1).norm(dim=1).clamp_min(1e-12).view(-1, *([1] * (w.dim() - 1)))
  w.mul_(torch.clamp(norms, max=limit) / norms)


def same_pad(k):
  """Zero pad along time giving 'same' output length for a stride-1 kernel of length k: left
  (k - 1) // 2, right k // 2 (module docstring (b))."""
  return nn.ZeroPad2d(((k - 1) // 2, k // 2, 0, 0))


class ShallowConvNet(nn.Module):
  """ShallowConvNet; adapted from [M] shallow_conv_net.py::ShallowConvNet."""

  def __init__(self, n_classes, n_channels, n_samples, F1, temporal_kernel_length, pool_kernel_length,
               pool_stride, dropout_rate):
    super().__init__()
    # adapted from [M] shallow_conv_net.py l.30-45
    self.n_channels, self.n_samples = n_channels, n_samples
    self.kernel_length = k = max(1, min(temporal_kernel_length, n_samples))
    n_conv = n_samples - k + 1
    self.pool_kernel = pk = max(1, min(pool_kernel_length, n_conv))
    self.pool_stride = max(1, min(pool_stride, pk))
    self.temporal = nn.Conv2d(1, F1, (1, k), bias=False)
    self.spatial = nn.Conv2d(F1, F1, (n_channels, 1), bias=False)
    self.bn = nn.BatchNorm2d(F1)
    self.pool = nn.AvgPool2d((1, pk), stride=(1, self.pool_stride))
    self.drop = nn.Dropout(dropout_rate)
    with torch.no_grad():
      was = self.training
      self.eval()
      n_flat = self.features(torch.zeros(1, 1, n_channels, n_samples)).shape[1]
      self.train(was)
    self.head = nn.Linear(n_flat, n_classes)

  def features(self, x):
    x = self.bn(self.spatial(self.temporal(x)))
    x = torch.log(torch.clamp(self.pool(x * x), min=LOG_EPS))
    return self.drop(x).flatten(1)

  def forward(self, x):
    if x.dim() == 3:
      x = x.unsqueeze(1)
    if x.dim() != 4 or x.shape[1] != 1 or x.shape[2] != self.n_channels:
      raise ValueError(f"expected (B, {self.n_channels}, T) or (B, 1, {self.n_channels}, T), got {tuple(x.shape)}")
    return self.head(self.features(x))


CLASSES = {"EEGNet": EEGNet, "ShallowConvNet": ShallowConvNet}
SHAPE_ARGS = ("n_classes", "n_channels", "n_samples")


def required_params(cls):
  return sorted(k for k in inspect.signature(cls.__init__).parameters if k not in ("self",) + SHAPE_ARGS)


def model_builder(spec):
  """``{"class", "params"}`` -> build(n_classes, n_channels, n_samples); refuses a table that
  does not name exactly the constructor's parameters (G5)."""
  if spec["class"] not in CLASSES:
    raise ValueError(f"unknown network class {spec['class']!r}; choose from {sorted(CLASSES)}")
  cls = CLASSES[spec["class"]]
  need, got = set(required_params(cls)), set(spec["params"])
  if need != got:
    raise ValueError(f"{spec['class']}: missing {sorted(need - got)}, unknown {sorted(got - need)}")
  params = dict(spec["params"])
  return lambda nc, ch, T: cls(nc, ch, T, **params)


def count_parameters(model):
  return int(sum(p.numel() for p in model.parameters() if p.requires_grad))


# ---------------------------------------------------------------- determinism, device
def set_determinism(det):
  """Deterministic settings from the config (module docstring)."""
  if det.get("cublas_workspace_config"):
    os.environ["CUBLAS_WORKSPACE_CONFIG"] = det["cublas_workspace_config"]
  torch.backends.cudnn.deterministic = bool(det["cudnn_deterministic"])
  torch.backends.cudnn.benchmark = bool(det["cudnn_benchmark"])
  torch.use_deterministic_algorithms(bool(det["use_deterministic_algorithms"]))


def resolve_device(name):
  """The configured device; a CUDA device that is not available is an error, never a silent
  fallback to the CPU (G5)."""
  if name.startswith("cuda") and not torch.cuda.is_available():
    raise RuntimeError(f"device {name!r} configured but CUDA is not available")
  return torch.device(name)


def environment(device):
  dev = torch.device(device)
  return {"torch": torch.__version__, "torch_cuda": torch.version.cuda,
          "cudnn": torch.backends.cudnn.version() if torch.backends.cudnn.is_available() else None,
          "device": str(dev),
          "device_name": torch.cuda.get_device_name(dev) if dev.type == "cuda" else "cpu",
          "cudnn_deterministic": bool(torch.backends.cudnn.deterministic),
          "cudnn_benchmark": bool(torch.backends.cudnn.benchmark),
          "deterministic_algorithms": bool(torch.are_deterministic_algorithms_enabled()),
          "cublas_workspace_config": os.environ.get("CUBLAS_WORKSPACE_CONFIG")}


# ---------------------------------------------------------------- trainer pieces
def fit_stats(X, eps):
  """Per-channel mean and std (1, C, 1) over epochs and time [M training.py fit_stats]."""
  X = np.asarray(X, dtype=np.float64)
  return X.mean(axis=(0, 2), keepdims=True), X.std(axis=(0, 2), keepdims=True) + eps


def fit_stats_per_feature(X, std_floor):
  """Mean and std (1, C, F) over epochs per (row, column); a std below ``std_floor`` is replaced
  by 1 ([M] src/features/connectivity/graph_inputs.py ``_stats``, STD_FLOOR; used by the F4 GNN,
  p300/graph.py)."""
  X = np.asarray(X, dtype=np.float64)
  sd = X.std(axis=0, keepdims=True)
  return X.mean(axis=0, keepdims=True), np.where(sd < std_floor, 1.0, sd)


def fit_normalisation(X, tr, norm):
  """``norm`` None: per channel (F2, [M] fit_stats, ``tr["norm_eps"]``); ``{"kind":
  "per_feature", "std_floor"}``: per (row, column) (F4)."""
  if norm is None:
    return fit_stats(X, tr["norm_eps"])
  if norm.get("kind") == "per_feature":
    return fit_stats_per_feature(X, float(norm["std_floor"]))
  raise ValueError(f"unknown normalisation {norm!r}")


def normalise(X, mean, std):
  return ((np.asarray(X, dtype=np.float64) - mean) / std).astype(np.float32)


def split_validation(y, groups, val_frac, seed):
  """(fit idx, val idx): first split of the inner grouped CV [M training.py split_validation]."""
  n_splits = max(2, int(round(1.0 / val_frac)))
  sgk = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=seed)
  fit, val = next(iter(sgk.split(np.zeros((len(y), 1)), y, groups)))
  return fit, val


def balanced_class_weights(y, n_classes):
  """w_c = n / (n_classes * n_c) over the given (fitting) labels."""
  counts = np.bincount(np.asarray(y, dtype=np.int64), minlength=n_classes)
  if np.any(counts == 0):
    raise ValueError("a class is absent from the fitting epochs")
  return len(y) / (n_classes * counts.astype(np.float64))


def predict_proba(model, X, device, chunk):
  """Softmax probabilities of normalised float32 X, eval mode [M training.py predict_proba]."""
  model.eval()
  out = []
  with torch.no_grad():
    for i in range(0, len(X), chunk):
      out.append(torch.softmax(model(torch.from_numpy(X[i:i + chunk]).to(device)), 1).cpu().numpy())
  return np.concatenate(out)


def weighted_nll(proba, y, weights):
  """sum_i w_{y_i} (-log p_i[y_i]) / sum_i w_{y_i}; weights None = plain mean."""
  nll = -np.log(np.clip(proba[np.arange(len(y)), y], 1e-12, None))
  if weights is None:
    return float(nll.mean())
  w = np.asarray(weights)[y]
  return float(np.sum(w * nll) / np.sum(w))


class AugmentedDataset(Dataset):
  """Per-epoch on-the-fly augmentation of TRAINING epochs only (G17 c), own numpy generator,
  never the torch RNG. Order: scale, noise (P300 port of [M] augmentation.py), then the
  [M] operations the P300 run did not use: time shift (circular, up to ``shift_frac`` of the
  length) and same-class mixup (convex combination with a random epoch OF THE SAME CLASS,
  lambda ~ U(0, 1); classes are never mixed). An operation with probability 0 draws nothing,
  so with p_shift = p_mixup = 0 the random stream equals the P300 run's."""

  def __init__(self, X, y, p_scale, scale_range, p_noise, noise_std_frac, seed, p_shift=0.0, shift_frac=0.0,
               p_mixup=0.0):
    self.X = np.asarray(X, dtype=np.float32)
    self.y = np.asarray(y).astype(np.int64)
    self.p_scale, self.scale_range = float(p_scale), tuple(scale_range)
    self.p_noise, self.noise_std_frac = float(p_noise), float(noise_std_frac)
    self.p_shift, self.shift_frac, self.p_mixup = float(p_shift), float(shift_frac), float(p_mixup)
    self.by_class = {int(c): np.flatnonzero(self.y == c) for c in np.unique(self.y)}
    self.rng = np.random.default_rng(seed)

  def __len__(self):
    return len(self.y)

  def augment(self, i):
    x = self.X[i].astype(np.float64)
    if self.rng.random() < self.p_scale:
      x = x * self.rng.uniform(self.scale_range[0], self.scale_range[1])
    if self.rng.random() < self.p_noise:
      x = x + self.rng.standard_normal(x.shape) * self.noise_std_frac * x.std(axis=-1, keepdims=True)
    if self.p_shift > 0 and self.rng.random() < self.p_shift:
      m = int(round(self.shift_frac * x.shape[-1]))
      if m > 0:
        x = np.roll(x, int(self.rng.integers(-m, m + 1)), axis=-1)
    if self.p_mixup > 0 and self.rng.random() < self.p_mixup:
      j = int(self.rng.choice(self.by_class[int(self.y[i])]))
      lam = float(self.rng.uniform(0.0, 1.0))
      x = lam * x + (1.0 - lam) * self.X[j].astype(np.float64)
    return x

  def __getitem__(self, i):
    return torch.from_numpy(self.augment(int(i)).astype(np.float32)), torch.tensor(int(self.y[i]), dtype=torch.long)


# ---------------------------------------------------------------- trainer
def fit_network(X, y, groups, build, seed, val_seed, device, tr, aug, norm=None, n_classes=2):
  """Train on training-fold epochs X (n, C, T), labels y in 0..n_classes-1, unit uids ``groups``.

  ``tr`` = config ``networks.trainer``, ``aug`` = ``networks.augmentation``. Returns dict:
  model (best state, eval mode), mean, std, class_weights, fit_idx, val_idx, best_epoch
  (1-based), epochs_run, hit_max_epochs, best_val_loss, n_params, history (list of dicts
  epoch, train_loss, val_loss, lr). Adapted from [M] training.py::fit_network (l.93-154).
  ``norm``: None = the F2 per-channel normalisation; a dict selects ``fit_normalisation``'s
  per-feature rule (F4, Step 3), always fitted on the fitting epochs only.
  """
  X, y, groups = np.asarray(X), np.asarray(y).astype(np.int64), np.asarray(groups)
  if set(np.unique(y)) - set(range(n_classes)):
    raise ValueError(f"labels must be in 0..{n_classes - 1}")
  fit_idx, val_idx = split_validation(y, groups, tr["val_frac"], val_seed)
  if set(groups[fit_idx]) & set(groups[val_idx]):
    raise AssertionError("unit shared between fitting and validation epochs")
  mean, std = fit_normalisation(X[fit_idx], tr, norm)
  Xf, Xv = normalise(X[fit_idx], mean, std), normalise(X[val_idx], mean, std)
  yf, yv = y[fit_idx], y[val_idx]
  cw = balanced_class_weights(yf, n_classes) if tr["class_weights"] == "balanced" else None
  if tr["class_weights"] not in ("balanced", "none"):
    raise ValueError(f"class_weights {tr['class_weights']!r}")
  vw = cw if tr["val_loss_class_weighted"] else None
  dev = torch.device(device)
  torch.manual_seed(seed)                       # immediately before the model [M]
  model = build(n_classes, X.shape[1], X.shape[2]).to(dev)
  max_norm = getattr(model, "apply_max_norm", None)
  opt = torch.optim.AdamW(model.parameters(), lr=tr["lr"], betas=tuple(tr["betas"]), eps=tr["eps"],
                          weight_decay=tr["weight_decay"], amsgrad=tr["amsgrad"])
  sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=tr["T_max"], eta_min=tr["eta_min"])
  crit = nn.CrossEntropyLoss(weight=None if cw is None else torch.tensor(cw, dtype=torch.float32, device=dev),
                             label_smoothing=tr["label_smoothing"])
  gen = torch.Generator().manual_seed(seed)
  data = (AugmentedDataset(Xf, yf, aug["p_scale"], aug["scale_range"], aug["p_noise"], aug["noise_std_frac"], seed,
                           aug.get("p_shift", 0.0), aug.get("shift_frac", 0.0), aug.get("p_mixup", 0.0))
          if aug["enabled"] else TensorDataset(torch.from_numpy(Xf), torch.from_numpy(yf)))
  loader = DataLoader(data, batch_size=tr["batch_size"], shuffle=True, generator=gen, num_workers=0)
  if max_norm:
    max_norm()
  best = {"loss": np.inf, "epoch": 0, "state": copy.deepcopy(model.state_dict())}
  history, since = [], 0
  for epoch in range(1, tr["max_epochs"] + 1):
    model.train()
    tot, cnt = torch.zeros((), dtype=torch.float64, device=dev), 0
    lr_epoch = opt.param_groups[0]["lr"]
    for bx, by in loader:
      if len(by) < tr["min_batch_size"]:
        continue
      bx, by = bx.to(dev), by.to(dev)
      opt.zero_grad()
      loss = crit(model(bx), by)
      loss.backward()
      opt.step()
      if max_norm:
        max_norm()
      tot += loss.detach().double() * len(by)
      cnt += len(by)
    sched.step()
    vloss = weighted_nll(predict_proba(model, Xv, dev, tr["predict_chunk"]), yv, vw)
    history.append({"epoch": epoch, "train_loss": float(tot.item()) / max(cnt, 1), "val_loss": vloss,
                    "lr": float(lr_epoch)})
    if vloss < best["loss"]:
      best.update(loss=vloss, epoch=epoch, state=copy.deepcopy(model.state_dict()))
      since = 0
    else:
      since += 1
      if since >= tr["patience"]:
        break
  model.load_state_dict(best["state"])
  model.eval()
  return {"model": model, "mean": mean, "std": std, "class_weights": None if cw is None else cw.tolist(),
          "fit_idx": fit_idx, "val_idx": val_idx, "best_epoch": best["epoch"], "epochs_run": len(history),
          "hit_max_epochs": bool(len(history) == tr["max_epochs"] and since < tr["patience"]),
          "best_val_loss": float(best["loss"]), "n_params": count_parameters(model), "history": history}


def predict(fit, X, device, chunk):
  """(argmax, softmax probabilities (n, k)) of X normalised with the fitting statistics."""
  p = predict_proba(fit["model"], normalise(X, fit["mean"], fit["std"]), torch.device(device), chunk)
  return p.argmax(1).astype(np.int64), p


def cv_network(X, y, unit_uid, splits, spec, seed, ncfg, device, class_names, fold_inputs=None, norm=None,
               build=None):
  """Out-of-fold predictions of one network and seed under the fixed folds.

  Step 3 (F4): ``fold_inputs(train, test) -> (X_train, X_test)`` builds fold-dependent inputs
  (then ``X`` is unused), ``norm`` is passed to ``fit_network``, ``build`` replaces
  ``model_builder(spec)``. With the defaults the behaviour is that of Step 2.

  Returns (pred, proba (n, k), fold rows, curve rows). Fold rows: fold, n_train, n_test,
  metrics, n_fit, n_val, n_val_units, best_epoch, epochs_run, hit_max_epochs, best_val_loss,
  n_params, class weight per class, seconds. Curve rows: fold, epoch, train_loss, val_loss, lr.
  """
  build = model_builder(spec) if build is None else build
  tr, aug = ncfg["trainer"], ncfg["augmentation"]
  y, unit_uid = np.asarray(y).astype(np.int64), np.asarray(unit_uid)
  k = len(class_names)
  if fold_inputs is None:
    X = np.asarray(X)
    fold_inputs = lambda train, test: (X[train], X[test])  # noqa: E731
  pred = np.full(len(y), -1, dtype=np.int64)
  pt = np.full((len(y), k), np.nan)
  rows, curves = [], []
  for fold, train, test in splits:
    if len(np.unique(y[train])) < k:
      raise ValueError(f"fold {fold}: a training set lacks a class")
    t0 = time.time()
    X_tr, X_te = fold_inputs(train, test)
    f = fit_network(X_tr, y[train], unit_uid[train], build, seed, tr["val_seed"], device, tr, aug, norm=norm,
                    n_classes=k)
    p, q = predict(f, X_te, device, tr["predict_chunk"])
    p_tr, _ = predict(f, X_tr, device, tr["predict_chunk"])   # un-augmented training fold (G18)
    pred[test], pt[test] = p, q
    rows.append({"fold": fold, "n_train": int(len(train)), "n_test": int(len(test)),
                 **evl.class_metrics(y[test], p, class_names),
                 "train_ba": evl.class_metrics(y[train], p_tr, class_names)["ba"], "n_fit": int(len(f["fit_idx"])),
                 "n_val": int(len(f["val_idx"])), "n_val_units": int(len(np.unique(unit_uid[train][f["val_idx"]]))),
                 "best_epoch": f["best_epoch"], "epochs_run": f["epochs_run"], "hit_max_epochs": f["hit_max_epochs"],
                 "best_val_loss": f["best_val_loss"], "n_params": f["n_params"],
                 **{f"class_weight_{c}": None if f["class_weights"] is None else f["class_weights"][i]
                    for i, c in enumerate(class_names)},
                 "seconds": time.time() - t0})
    curves += [{"fold": fold, **h} for h in f["history"]]
  if np.any(pred < 0):
    raise ValueError("some epochs received no out-of-fold prediction")
  return pred, pt, rows, curves
