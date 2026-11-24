"""Known-answer tests for eegpipe.networks (torch), moved from the P300 project (tests @ d833264,
``tests/test_ssvep_methods_step2.py`` sections 4-11 and the D-013 EEGNet tests), generalised to
k classes, plus 5-class known answers (the supervisor's decision D5). Data sizes are reduced where a
test only needs a planted effect to be learnable; the ERP data have the P300 tests' size (3 files x 8 units x 40 epochs)."""

import copy
import json
import sys
from pathlib import Path

import numpy as np
import pytest

torch = pytest.importorskip("torch")
TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
from eegpipe import evaluate as evl  # noqa: E402
from eegpipe import folds as fo  # noqa: E402
from eegpipe import networks as nw  # noqa: E402

PROFILE = json.loads((TOOLS / "eegpipe" / "profiles" / "erp.json").read_text())
EEGNET = copy.deepcopy(PROFILE["networks"]["models"]["eegnet"])
SHALLOW = copy.deepcopy(PROFILE["networks"]["models"]["shallowconvnet"])
for _s in (EEGNET, SHALLOW):
  _s.pop("source", None)
  _s.pop("input_shape", None)
N_CH, N_OUT = 8, 102
VAL_SEED = 20261113
BIN = ["nontarget", "target"]
CUDA = torch.cuda.is_available()


def trainer(max_epochs=6, patience=25, batch_size=32, lr=1e-3, **over):
  t = {k: v for k, v in PROFILE["networks"]["trainer"].items() if not isinstance(v, str) or k == "class_weights"}
  t.update({"max_epochs": max_epochs, "patience": patience, "batch_size": batch_size, "lr": lr})
  t.update(over)
  return t


AUG_OFF = {"enabled": False, "p_scale": 0.5, "scale_range": [0.9, 1.1], "p_noise": 0.5, "noise_std_frac": 0.05}


def ncfg(max_epochs=6, patience=25, **tr_over):
  return {"trainer": trainer(max_epochs, patience, **tr_over), "augmentation": copy.deepcopy(AUG_OFF),
          "deterministic": PROFILE["networks"]["deterministic"]}


def test_profile_trainer_is_the_p300_trainer():
  t = trainer()
  assert (t["val_frac"], t["val_seed"], t["label_smoothing"], t["norm_eps"], t["class_weights"]) == \
      (0.2, 20261113, 0.1, 1e-6, "balanced")


def erp_data(seed, n_files=3, units_per_file=8, rounds=10, amp=0.5, planted=True, n_codes=4):
  """Epochs (n, 8, 102) of white noise; target epochs carry a Gaussian bump (sd 5 samples, peak at
  sample 45) of amplitude ``amp`` on 6 of 8 channels; label = code == unit target."""
  rng = np.random.default_rng(seed)
  post = np.array([0, 0, 1, 1, 1, 1, 1, 1], float)
  bump = np.exp(-0.5 * ((np.arange(N_OUT) - 45) / 5.0) ** 2)
  X, y, uid, fidx = [], [], [], []
  u = 0
  for f in range(n_files):
    for b in range(units_per_file):
      x = int(rng.integers(1, n_codes + 1))
      codes = np.concatenate([rng.permutation(np.arange(1, n_codes + 1)) for _ in range(rounds)])
      for c in codes:
        e = rng.normal(size=(N_CH, N_OUT))
        if planted and c == x:
          e += amp * np.outer(post, bump)
        X.append(e), y.append(int(c == x)), uid.append(u), fidx.append(f)
      u += 1
  return np.stack(X), np.array(y), np.array(uid), np.array(fidx)


def folds_of(uid, fidx, n_folds=4, seed=20261107, unit_label=None):
  unit_file = np.array([fidx[uid == u][0] for u in np.unique(uid)])
  return fo.fold_splits(uid, fo.assign_unit_folds(unit_file, n_folds, seed, unit_label=unit_label), n_folds)


@pytest.fixture(scope="module")
def erp():
  X, y, uid, fidx = erp_data(2024)
  return {"X": X, "y": y, "uid": uid, "fidx": fidx, "splits": folds_of(uid, fidx)}


# ------------------------------------------------------------------ models
@pytest.mark.parametrize("name,n_params", [("EEGNet", 1330), ("ShallowConvNet", 13962)])
def test_model_shapes_parameter_counts_and_builder(name, n_params):
  """Known answer (exact, P300 D-012/D-013): EEGNet 1330, ShallowConvNet 13962 trainable parameters
  for (8, 102) and 2 classes; with 5 classes the head grows by 3 x (in_features + 1)."""
  spec = EEGNET if name == "EEGNet" else SHALLOW
  m = nw.model_builder(spec)(2, N_CH, N_OUT)
  assert nw.count_parameters(m) == n_params
  x = torch.zeros(5, 1, N_CH, N_OUT)
  assert tuple(m(x).shape) == (5, 2) and tuple(m(x[:, 0]).shape) == (5, 2)
  m5 = nw.model_builder(spec)(5, N_CH, N_OUT)
  assert nw.count_parameters(m5) == n_params + 3 * (m.head.in_features + 1) and tuple(m5(x).shape) == (5, 5)
  with pytest.raises(ValueError):
    m(torch.zeros(5, 1, N_CH + 1, N_OUT))
  for k in spec["params"]:
    with pytest.raises(ValueError, match=k):
      nw.model_builder({"class": name, "params": {kk: v for kk, v in spec["params"].items() if kk != k}})
  with pytest.raises(ValueError, match="unknown"):
    nw.model_builder({"class": name, "params": {**spec["params"], "extra": 1}})
  with pytest.raises(ValueError, match="unknown network class"):
    nw.model_builder({"class": "Nope", "params": {}})


def test_eegnet_max_norms_bound_spatial_filters_and_head_rows():
  """Known answer: apply_max_norm rescales a spatial filter of norm 20 to 1 and a head row of norm
  10 x to 0.25, leaves a filter of norm 0.5 / a row of norm 0.1 and the bias unchanged; after 3
  epochs at lr 0.5 the bounds hold; without the dense bound (inf) the same fit exceeds 0.25."""
  m = nw.model_builder(EEGNET)(2, N_CH, N_OUT)
  with torch.no_grad():
    w = m.spatial.weight
    w[0] *= 20.0 / w[0].flatten().norm()
    w[1] *= 0.5 / w[1].flatten().norm()
    h = m.head.weight
    h[0] *= 10.0 / h[0].norm()
    h[1] *= 0.1 / h[1].norm()
    m.head.bias.fill_(5.0)
  s1, r1 = m.spatial.weight[1].clone(), m.head.weight[1].clone()
  m.apply_max_norm()
  assert abs(float(m.spatial.weight[0].flatten().norm()) - 1.0) < 1e-6 and torch.equal(m.spatial.weight[1], s1)
  assert abs(float(m.head.weight[0].norm()) - 0.25) < 1e-6 and torch.equal(m.head.weight[1], r1)
  assert torch.all(m.head.bias == 5.0)
  X, y, uid, _ = erp_data(1, amp=0.5)
  f = nw.fit_network(X, y, uid, nw.model_builder(EEGNET), 1, VAL_SEED, "cpu", trainer(max_epochs=3, lr=0.5), AUG_OFF)
  assert float(f["model"].head.weight.norm(dim=1).max()) <= 0.25 + 1e-6
  assert float(f["model"].spatial.weight.flatten(1).norm(dim=1).max()) <= 1 + 1e-6
  free = copy.deepcopy(EEGNET)
  free["params"]["dense_max_norm"] = float("inf")
  g = nw.fit_network(X, y, uid, nw.model_builder(free), 1, VAL_SEED, "cpu", trainer(max_epochs=3, lr=0.5), AUG_OFF)
  assert float(g["model"].head.weight.norm(dim=1).max()) > 0.25


def test_eegnet_same_padding_lengths_102_25_3_and_left_pad():
  """Known answer: 102 -> temporal 102 -> pool 25 -> separable 25 -> pool 3; head input 16 x 3 = 48;
  pads (31, 32) and (7, 8); an impulse at sample 0 through a kernel with its 1 at tap 31 appears at
  output 0; equal to Conv2d(padding='same') (atol 1e-6). The old symmetric pad gave 103."""
  m = nw.model_builder(EEGNET)(2, N_CH, N_OUT).eval()
  with torch.no_grad():
    assert tuple(m.features(torch.randn(4, 1, N_CH, N_OUT)).shape) == (4, 48) and m.head.in_features == 48
  assert (m.pad_temporal.padding[:2], m.pad_sep.padding[:2]) == ((31, 32), (7, 8))
  with torch.no_grad():
    m.temporal.weight.zero_()
    m.temporal.weight[:, :, :, 31] = 1.0
    x = torch.zeros(1, 1, N_CH, N_OUT)
    x[..., 0] = 1.0
    out = m.temporal(m.pad_temporal(x))
    assert out.shape[-1] == 102 and float(out[0, 0, 0, 0]) == 1.0 and float(out[0, 0, 0, 1:].abs().sum()) == 0.0
    torch.manual_seed(3)
    ref_t = torch.nn.Conv2d(1, 8, (1, 64), padding="same", bias=False)
    m.temporal.weight.copy_(ref_t.weight)
    z = torch.randn(2, 1, N_CH, N_OUT)
    assert torch.allclose(m.temporal(m.pad_temporal(z)), ref_t(z), atol=1e-6)


# ------------------------------------------------------------------ learning
@pytest.mark.parametrize("spec_name", ["eegnet", "shallowconvnet"])
def test_planted_erp_is_learned_by_both_networks(erp, spec_name):
  """Known answer: planted bump (ideal d' = 3.65, ideal BA 0.966), grouped 4-fold by unit, 14
  epochs: pooled BA >= 0.85 and both recalls >= 0.75 [own bounds, a priori, as P300]."""
  spec = EEGNET if spec_name == "eegnet" else SHALLOW
  pred, pt, rows, curves = nw.cv_network(erp["X"], erp["y"], erp["uid"], erp["splits"], spec, 20261107,
                                         ncfg(max_epochs=14), "cpu", BIN)
  m = evl.class_metrics(erp["y"], pred, BIN)
  assert m["ba"] >= 0.85 and m["ca_target"] >= 0.75 and m["ca_nontarget"] >= 0.75, m
  assert len(rows) == 4 and len(curves) == sum(r["epochs_run"] for r in rows)
  assert pt.shape == (len(erp["y"]), 2) and np.allclose(pt.sum(1), 1.0, atol=1e-5)


def test_noise_gives_chance_for_eegnet():
  X, y, uid, fidx = erp_data(77, planted=False)
  pred, _, _, _ = nw.cv_network(X, y, uid, folds_of(uid, fidx), EEGNET, 20261107, ncfg(max_epochs=14), "cpu", BIN)
  assert abs(evl.class_metrics(y, pred, BIN)["ba"] - 0.5) <= 0.12


def five_class_data(seed, n_files=3, units_per_class=2, per_unit=24, amp=0.8, planted=True):
  """5 classes, label constant within a unit (SSVEP-like trials): class c carries a sinusoid of
  frequency (c + 2) cycles per epoch on all channels, random phase per epoch, amplitude ``amp``."""
  rng = np.random.default_rng(seed)
  t = np.arange(N_OUT) / N_OUT
  X, y, uid, fidx, ulab = [], [], [], [], []
  u = 0
  for f in range(n_files):
    labels = rng.permutation(np.repeat(np.arange(5), units_per_class))
    for c in labels:
      for _ in range(per_unit):
        e = rng.normal(size=(N_CH, N_OUT))
        if planted:
          e += amp * np.sin(2 * np.pi * (c + 2) * t + rng.uniform(0, 2 * np.pi))[None, :]
        X.append(e), y.append(int(c)), uid.append(u), fidx.append(f)
      ulab.append(int(c))
      u += 1
  return np.stack(X), np.array(y), np.array(uid), np.array(fidx), np.array(ulab)


def test_five_class_planted_frequencies_are_learned_and_noise_is_chance():
  """Known answer (5 classes): ShallowConvNet (band power) learns 5 planted frequencies under
  label-balanced grouped folds: BA >= 0.6 (chance 0.2); on noise BA within 0.2 +- 0.12; the
  balanced class weights over the fitting epochs are n / (5 n_c) [own bounds, a priori]."""
  names = [f"c{i}" for i in range(5)]
  for planted, check in ((True, lambda ba: ba >= 0.6), (False, lambda ba: abs(ba - 0.2) <= 0.12)):
    X, y, uid, fidx, ulab = five_class_data(31, planted=planted)
    splits = folds_of(uid, fidx, n_folds=3, unit_label=ulab)
    pred, proba, rows, _ = nw.cv_network(X, y, uid, splits, SHALLOW, 20261107, ncfg(max_epochs=12), "cpu", names)
    ba = evl.class_metrics(y, pred, names)["ba"]
    assert check(ba), (planted, ba)
    assert proba.shape == (len(y), 5) and all(f"class_weight_c{i}" in rows[0] for i in range(5))
  assert nw.balanced_class_weights(np.array([0, 0, 1, 2, 3, 4]), 5).tolist() == pytest.approx([0.6, 1.2, 1.2, 1.2, 1.2])


# ------------------------------------------------------------------ only training data
def test_validation_and_fitting_use_only_training_fold_units(erp, monkeypatch):
  seen = []
  real = nw.fit_network

  def spy(X, y, groups, *a, **k):
    f = real(X, y, groups, *a, **k)
    seen.append((np.array(X), np.array(y), np.array(groups), f["fit_idx"], f["val_idx"]))
    return f
  monkeypatch.setattr(nw, "fit_network", spy)
  nw.cv_network(erp["X"], erp["y"], erp["uid"], erp["splits"], EEGNET, 1, ncfg(max_epochs=1), "cpu", BIN)
  assert len(seen) == 4
  for (fold, tr, te), (X, y, g, fi, vi) in zip(erp["splits"], seen):
    assert np.array_equal(X, erp["X"][tr]) and np.array_equal(y, erp["y"][tr]) and np.array_equal(g, erp["uid"][tr])
    tg, vg, fg = set(erp["uid"][te]), set(g[vi]), set(g[fi])
    assert not (set(g) & tg) and not (vg & fg) and not (vg & tg)
    assert sorted(np.concatenate([fi, vi]).tolist()) == list(range(len(tr))) and len(vi) > 0
  rng = np.random.default_rng(0)
  g0 = erp["uid"][erp["splits"][0][1]]
  bad_val = rng.choice(len(g0), 100, replace=False)
  assert set(g0[bad_val]) & set(g0[np.setdiff1d(np.arange(len(g0)), bad_val)])


def test_test_fold_labels_are_never_read_when_fitting_networks(erp):
  _, tr0, te0 = erp["splits"][0]
  cfg = ncfg(max_epochs=2)
  _, p0, _, _ = nw.cv_network(erp["X"], erp["y"], erp["uid"], erp["splits"], EEGNET, 5, cfg, "cpu", BIN)
  y2 = erp["y"].copy()
  y2[te0] = 1 - y2[te0]
  _, p1, _, _ = nw.cv_network(erp["X"], y2, erp["uid"], erp["splits"], EEGNET, 5, cfg, "cpu", BIN)
  assert np.array_equal(p0[te0], p1[te0])
  y3 = erp["y"].copy()
  y3[tr0[:60]] = 1 - y3[tr0[:60]]
  _, p2, _, _ = nw.cv_network(erp["X"], y3, erp["uid"], erp["splits"], EEGNET, 5, cfg, "cpu", BIN)
  assert not np.array_equal(p0[te0], p2[te0])


def test_normalisation_and_class_weights_come_from_fitting_epochs_only(erp, monkeypatch):
  X, y = erp["X"].copy(), erp["y"].copy()
  _, tr, te = erp["splits"][0]
  X[te, 0, :] += 50.0
  y[te] = (np.random.default_rng(4).random(len(te)) < 0.6).astype(int)
  calls = []
  real = nw.fit_stats
  monkeypatch.setattr(nw, "fit_stats", lambda A, eps: (calls.append(len(A)), real(A, eps))[1])
  f = nw.fit_network(X[tr], y[tr], erp["uid"][tr], nw.model_builder(EEGNET), 3, VAL_SEED, "cpu", trainer(max_epochs=1), AUG_OFF)
  fi = f["fit_idx"]
  assert calls == [len(fi)] and len(fi) < len(tr)
  Xf = X[tr][fi].astype(np.float64)
  assert np.allclose(f["mean"], Xf.mean(axis=(0, 2), keepdims=True), atol=1e-12)
  assert np.allclose(f["std"], Xf.std(axis=(0, 2), keepdims=True) + 1e-6, atol=1e-12)
  yf = y[tr][fi]
  assert np.allclose(f["class_weights"], len(yf) / (2.0 * np.bincount(yf)), atol=1e-12)
  assert np.abs(np.array(f["class_weights"]) - len(y) / (2.0 * np.bincount(y))).max() > 0.05
  assert abs(float(f["mean"][0, 0, 0]) - X[:, 0, :].mean()) > 5.0 and abs(float(f["mean"][0, 0, 0])) < 0.1


# ------------------------------------------------------------------ early stopping, seeds, determinism
def test_best_state_is_restored_and_patience_stops_exactly():
  X, y, uid, _ = erp_data(5, planted=False, units_per_file=6)
  tr = trainer(max_epochs=150, patience=25, batch_size=16, lr=5e-3)
  f = nw.fit_network(X, y, uid, nw.model_builder(EEGNET), 11, VAL_SEED, "cpu", tr, AUG_OFF)
  h = [r["val_loss"] for r in f["history"]]
  assert f["best_epoch"] == int(np.argmin(h)) + 1 and abs(f["best_val_loss"] - min(h)) < 1e-12
  vi = f["val_idx"]
  p = nw.predict_proba(f["model"], nw.normalise(X[vi], f["mean"], f["std"]), torch.device("cpu"), 256)
  assert abs(nw.weighted_nll(p, y[vi], f["class_weights"]) - min(h)) < 1e-6 and h[-1] > min(h) + 1e-6
  assert f["epochs_run"] == f["best_epoch"] + 25 and f["hit_max_epochs"] is False
  c = nw.fit_network(X, y, uid, nw.model_builder(EEGNET), 11, VAL_SEED, "cpu", {**tr, "max_epochs": f["best_epoch"] + 2}, AUG_OFF)
  assert c["epochs_run"] == f["best_epoch"] + 2 and c["hit_max_epochs"] is True


def test_same_seed_is_bitwise_reproducible_and_validation_follows_val_seed(erp):
  X, y, uid, splits = erp["X"], erp["y"], erp["uid"], erp["splits"]
  cfg = ncfg(max_epochs=2)
  a = nw.cv_network(X, y, uid, splits, EEGNET, 20261107, cfg, "cpu", BIN)
  b = nw.cv_network(X, y, uid, splits, EEGNET, 20261107, cfg, "cpu", BIN)
  c = nw.cv_network(X, y, uid, splits, EEGNET, 20261108, cfg, "cpu", BIN)
  assert np.array_equal(a[1], b[1]) and a[3] == b[3] and not np.array_equal(a[1], c[1])
  _, tr, _ = splits[0]
  vals = [nw.fit_network(X[tr], y[tr], uid[tr], nw.model_builder(EEGNET), s, VAL_SEED, "cpu", trainer(max_epochs=1), AUG_OFF)["val_idx"]
          for s in (20261107, 20261108)]
  assert np.array_equal(vals[0], vals[1])


def test_initial_weights_follow_the_seed_set_immediately_before_building(erp):
  X, y, uid = erp["X"][:300], erp["y"][:300], erp["uid"][:300]
  init = {}

  def build(seed):
    base = nw.model_builder(EEGNET)

    def b(nc, ch, T):
      m = base(nc, ch, T)
      init[seed] = {k: v.clone() for k, v in m.state_dict().items()}
      return m
    return b
  for s in (7, 8):
    torch.rand(13)
    nw.fit_network(X, y, uid, build(s), s, VAL_SEED, "cpu", trainer(max_epochs=1), AUG_OFF)
  torch.manual_seed(7)
  ref = nw.model_builder(EEGNET)(2, N_CH, N_OUT).state_dict()
  assert all(torch.equal(init[7][k], ref[k]) for k in ref)
  assert not all(torch.equal(init[7][k], init[8][k]) for k in ref)


def test_device_resolution_and_determinism_flags(monkeypatch):
  monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
  with pytest.raises(RuntimeError, match="CUDA is not available"):
    nw.resolve_device("cuda")
  assert nw.resolve_device("cpu").type == "cpu"
  monkeypatch.delenv("CUBLAS_WORKSPACE_CONFIG", raising=False)
  nw.set_determinism({"cudnn_deterministic": True, "cudnn_benchmark": False, "use_deterministic_algorithms": True,
                      "cublas_workspace_config": ":4096:8"})
  env = nw.environment("cpu")
  assert env["cudnn_deterministic"] is True and env["deterministic_algorithms"] is True
  assert env["cublas_workspace_config"] == ":4096:8"
  nw.set_determinism({"cudnn_deterministic": False, "cudnn_benchmark": True, "use_deterministic_algorithms": False,
                      "cublas_workspace_config": None})
  assert nw.environment("cpu")["deterministic_algorithms"] is False


@pytest.mark.skipif(not CUDA, reason="CUDA not available")
def test_tiny_gpu_fit_runs_deterministically():
  nw.set_determinism(PROFILE["networks"]["deterministic"])
  X, y, uid, fidx = erp_data(9, n_files=2, units_per_file=6, amp=1.0)
  splits = folds_of(uid, fidx, 3)
  a = nw.cv_network(X, y, uid, splits, EEGNET, 1, ncfg(max_epochs=6), "cuda", BIN)
  b = nw.cv_network(X, y, uid, splits, EEGNET, 1, ncfg(max_epochs=6), "cuda", BIN)
  assert np.array_equal(a[1], b[1]) and evl.class_metrics(y, a[0], BIN)["ba"] >= 0.8


# ------------------------------------------------------------------ augmentation
def test_augmentation_off_by_default_and_ranges(erp, monkeypatch):
  """Known answer: disabled -> TensorDataset, enabled -> AugmentedDataset; scale factors within
  [0.9, 1.1] with mean 1 +- 0.01; noise fraction 0.05 +- 0.002; X and the torch RNG untouched;
  same seed same stream; with p_shift = p_mixup = 0 the stream equals the P300 two-operation
  stream (draw-for-draw)."""
  seen = []
  real = nw.DataLoader
  monkeypatch.setattr(nw, "DataLoader", lambda ds, **k: (seen.append(type(ds).__name__), real(ds, **k))[1])
  X, y, uid = erp["X"][:200], erp["y"][:200], erp["uid"][:200]
  for enabled in (False, True):
    nw.fit_network(X, y, uid, nw.model_builder(EEGNET), 1, VAL_SEED, "cpu", trainer(max_epochs=1), {**AUG_OFF, "enabled": enabled})
  assert seen == ["TensorDataset", "AugmentedDataset"]
  Xs, ys = erp["X"][:50].astype(np.float32), erp["y"][:50]
  ds = nw.AugmentedDataset(Xs, ys, 1.0, (0.9, 1.1), 0.0, 0.05, 3)
  st = torch.get_rng_state().clone()
  ratios = np.array([float(np.median(ds[i][0].numpy() / Xs[i])) for _ in range(40) for i in range(50)])
  assert ratios.min() >= 0.9 - 1e-6 and ratios.max() <= 1.1 + 1e-6 and abs(ratios.mean() - 1.0) <= 0.01
  assert torch.equal(st, torch.get_rng_state()) and np.array_equal(Xs, erp["X"][:50].astype(np.float32))
  dn = nw.AugmentedDataset(Xs, ys, 0.0, (0.9, 1.1), 1.0, 0.05, 3)
  frac = [float(np.mean((dn[i][0].numpy() - Xs[i]).std(axis=-1) / Xs[i].std(axis=-1))) for i in range(50)]
  assert abs(np.mean(frac) - 0.05) <= 0.002
  rng = np.random.default_rng(9)
  d1 = nw.AugmentedDataset(Xs, ys, 0.5, (0.9, 1.1), 0.5, 0.05, 9)
  for i in range(50):                      # independent re-implementation of the P300 two-op stream
    x = Xs[i].astype(np.float64)
    if rng.random() < 0.5:
      x = x * rng.uniform(0.9, 1.1)
    if rng.random() < 0.5:
      x = x + rng.standard_normal(x.shape) * 0.05 * x.std(axis=-1, keepdims=True)
    assert np.array_equal(d1[i][0].numpy(), x.astype(np.float32))


def test_mixup_never_mixes_classes_and_shift_is_a_circular_roll():
  """Known answer: with class 0 epochs all = 1.0 and class 1 epochs all = -1.0, same-class mixup
  (p 1) leaves every class-0 sample at exactly 1.0 and class-1 at -1.0 (a cross-class mix would
  give values in (-1, 1)); a shift (p 1, frac 0.1) of a ramp is a circular roll by at most 10
  samples."""
  X = np.concatenate([np.ones((10, 2, 50)), -np.ones((10, 2, 50))]).astype(np.float32)
  y = np.repeat([0, 1], 10)
  d = nw.AugmentedDataset(X, y, 0.0, (1, 1), 0.0, 0.0, 1, p_mixup=1.0)
  for i in range(20):
    assert np.all(d[i][0].numpy() == (1.0 if y[i] == 0 else -1.0))
  ramp = np.tile(np.arange(50, dtype=np.float32), (1, 2, 1))
  ds = nw.AugmentedDataset(ramp, np.array([0]), 0.0, (1, 1), 0.0, 0.0, 2, p_shift=1.0, shift_frac=0.1)
  for _ in range(20):
    x = ds[0][0].numpy()[0]
    k = int(np.argmin(x))
    assert any(np.array_equal(x, np.roll(np.arange(50), s)) for s in range(-5, 6)) and min(k, 50 - k) <= 5
