"""Known-answer tests for v0.4.1: MAS's P20 within-subject network protocol in eegpipe (Sebastian 2026-11-10, ssvep-apply
D-009). The reference is MAS's own code, copied verbatim into ``mas_p20_reference.py`` (f725369); eegpipe must match it
bit for bit where it ports it (augmentation, EEGNetSSVEP, fit_network, broadband filter). Plus: windows, folds grouped by
trial, trial aggregation, the settings rules (seed spacing, protocol keys), a positive control (planted SSVEP at the five
study frequencies is learned, noise is not), and the runner end to end (a P20 network part keeps the study's epochs and
folds hashes, so the stage runner's identity check is unchanged, and records its own window folds hash)."""

import copy
import csv
import json
import sys
from pathlib import Path

import numpy as np
import pytest
import torch

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parents[0] / "tools"
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(HERE))
import mas_p20_reference as M  # noqa: E402
from eegpipe import network_windows as nwin  # noqa: E402
from eegpipe import networks as nw  # noqa: E402
from eegpipe import settings as st  # noqa: E402
from eegpipe.runner import methods as rm  # noqa: E402
from eegpipe.testing import synth  # noqa: E402

PROFILES = TOOLS / "eegpipe" / "profiles"
SSVEP = json.loads((PROFILES / "ssvep.json").read_text())
FS = 256.0
FREQS = (24.0, 20.0, 15.0, 10.909090909090908, 8.571428571428571)   # the study's five frequencies (ssvep-apply)
NAMES = ["101", "102", "103", "104", "105"]


def p20(max_epochs=150, patience=25, seed=7):
  """networks section of the ssvep profile (P20) with a test model table; epochs lowered only where a test says so."""
  n = copy.deepcopy(SSVEP["networks"])
  n["trainer"].update(max_epochs=max_epochs, T_max=max_epochs, patience=patience)
  n["cv"]["seed"] = seed
  n["device"] = "cpu"
  n["models"]["eegnet"]["params"]["kernel_length"] = int(FS) // 2
  return n


def ssvep_trials(seed, n_per_class=8, amp=1.0, C=8, T=1024):
  rng = np.random.default_rng(seed)
  t = np.arange(T) / FS
  w = rng.uniform(0.3, 1.0, C)
  X, y = [], []
  for k, f in enumerate(FREQS):
    for _ in range(n_per_class):
      ph = rng.uniform(0, 2 * np.pi, 2)
      s = np.sin(2 * np.pi * f * t + ph[0]) + 0.5 * np.sin(2 * np.pi * 2 * f * t + ph[1])
      X.append(amp * w[:, None] * s[None] + rng.standard_normal((C, T)))
      y.append(k)
  return np.asarray(X), np.asarray(y)


# ------------------------------------------------------------------ exact ports of MAS
def test_mas_augmentation_is_reproduced_bit_for_bit():
  """Known answer: with the same seed, MasAugmentedDataset returns exactly MAS's SSVEPAugmentedDataset sample for 300
  draws (order mixup -> scale -> shift -> noise, Beta(0.4) folded mixup, int(0.1 T) shift). eegpipe's P300 class
  (AugmentedDataset: other order, U(0, 1) lambda, round) does not, so the test discriminates."""
  rng = np.random.default_rng(3)
  X = rng.standard_normal((40, 8, 256)).astype(np.float32)
  y = np.repeat(np.arange(5), 8)
  aug = SSVEP["networks"]["augmentation"]
  ours = nwin.mas_dataset(X, y, aug, 11)
  ref = M.SSVEPAugmentedDataset(X, y, seed=11)
  old = nw.AugmentedDataset(X, y, aug["p_scale"], aug["scale_range"], aug["p_noise"], aug["noise_std_frac"], 11,
                            aug["p_shift"], aug["shift_frac"], aug["p_mixup"])
  idx = np.random.default_rng(5).integers(0, 40, 300)
  a = [ours[int(i)][0].numpy() for i in idx]
  b = [ref[int(i)][0].numpy() for i in idx]
  c = [old[int(i)][0].numpy() for i in idx]
  assert all(np.array_equal(u, v) for u, v in zip(a, b))
  assert not all(np.array_equal(u, v) for u, v in zip(c, b))


def test_eegnetssvep_matches_mas_parameters_weights_and_outputs():
  """Known answer: 2,349 trainable parameters at 7 channels x 256 samples, 5 classes, kernel 125 (MAS README R-8);
  same seed -> identical state dict and forward pass to MAS's EEGNetSSVEP, and identical max-norm."""
  spec = {"class": "EEGNetSSVEP", "params": {"F1": 8, "D": 2, "F2": 16, "kernel_length": 125, "dropout_rate": 0.25,
                                             "max_norm": 1.0}}
  torch.manual_seed(0)
  a = nw.model_builder(spec)(5, 7, 256)
  torch.manual_seed(0)
  b = M.EEGNetSSVEP(5, 7, 256)
  assert nw.count_parameters(a) == 2349 == sum(p.numel() for p in b.parameters())
  sa, sb = a.state_dict(), b.state_dict()
  assert list(sa) == list(sb) and all(torch.equal(sa[k], sb[k]) for k in sa)
  with torch.no_grad():
    a.spatial.weight.mul_(5.0)
    b.spatial.weight.mul_(5.0)
  a.apply_max_norm()
  b.apply_max_norm()
  a.eval()
  b.eval()
  x = torch.randn(3, 7, 256)
  assert torch.equal(a(x), b(x))


def test_fit_network_with_p20_settings_equals_mas_fit_network():
  """Known answer: eegpipe's fit_network with the profile's P20 trainer and augmentation (mas_p10), the same seed as
  validation seed, and EEGNetSSVEP gives MAS's fit_network exactly on CPU: same fitting/validation split, normalisation,
  best epoch, epochs run, per-epoch losses, and test probabilities."""
  torch.use_deterministic_algorithms(True)
  X, y = ssvep_trials(1, n_per_class=6, amp=0.6)
  Xw, t = nwin.crop_trials(X, 256, 64)
  yw, g = y[t], t
  n = p20(max_epochs=6, patience=3)
  spec = {"class": "EEGNetSSVEP", "params": {**n["models"]["eegnet"]["params"]}}
  ours = nw.fit_network(Xw, yw, g, nw.model_builder(spec), 42, 42, "cpu", n["trainer"], n["augmentation"], n_classes=5)
  ref = M.fit_network(Xw, yw, g, lambda nc, ch, T: M.EEGNetSSVEP(nc, ch, T, kernel_length=128), seed=42, device="cpu",
                      augment=True, max_epochs=6, patience=3)
  assert np.array_equal(ours["fit_idx"], ref["fit_idx"]) and np.array_equal(ours["val_idx"], ref["val_idx"])
  assert np.array_equal(ours["mean"], ref["mean"]) and np.array_equal(ours["std"], ref["std"])
  assert ours["best_epoch"] == ref["best_epoch"] and ours["epochs_run"] == ref["epochs_run"]
  assert np.allclose([h["train_loss"] for h in ours["history"]], [h[0] for h in ref["history"]], rtol=0, atol=1e-12)
  assert [h["val_loss"] for h in ours["history"]] == [h[1] for h in ref["history"]]
  Xt = M.normalise(Xw[:20], ref["mean"], ref["std"])
  assert np.array_equal(nw.predict_proba(ours["model"], Xt, torch.device("cpu"), 256),
                        M.predict_proba(ref["model"], Xt, torch.device("cpu")))


def test_iir_input_equals_mas_broadband_filter_and_the_gate_isolates_units():
  """Known answer: with the gate passing, the network trials are MAS's broadband_filter (Butterworth 1-90 Hz order 4,
  notch 60 Hz Q 30, filtfilt with default padding) of the whole record, cut at the onsets, no resampling. With units
  closer than the effective span, the gate fails and unit-wise filtering keeps a large tone in unit 1 out of unit 0's
  trial (continuous filtering would leak it)."""
  s = copy.deepcopy(SSVEP["network_input"])
  s.update(fs_out_hz=FS, epoch_window_s=[0.0, 1.0], epoch_samples_out=256)
  rng = np.random.default_rng(2)
  data = rng.standard_normal((3, 30000))
  ev = {"onset": np.array([3000, 20000]), "unit": np.array([0, 1]), "unit_start": np.array([3000, 20000]),
        "unit_end": np.array([3300, 20300])}
  kept = {"keep": np.array([True, True])}
  out = nwin.iir_network_input(data, FS, ev, kept, s, 1.0)
  ref = M.broadband_filter(data, FS, 1.0, 90.0, 4, 60.0, 30.0)
  assert out["gate"]["passes"] and out["filtering"] == "continuous" and out["fs_out"] == FS
  assert np.array_equal(out["X"][0], ref[:, 3000:3256]) and np.array_equal(out["X"][1], ref[:, 20000:20256])
  assert out["padlen"] == [27, 9]
  span = out["gate"]["effective_span"]
  d2 = 1e-3 * rng.standard_normal((3, 12000))
  on = np.array([3000, 3000 + 256 + span // 3])
  d2[:, on[1]:on[1] + 400] += 50.0 * np.sin(2 * np.pi * 10.0 * np.arange(400) / FS)
  ev2 = {"onset": on, "unit": np.array([0, 1]), "unit_start": on, "unit_end": on + 256}
  out2 = nwin.iir_network_input(d2, FS, ev2, kept, s, 0.0)
  cont = M.broadband_filter(d2, FS, 1.0, 90.0, 4, 60.0, 30.0)[:, on[0]:on[0] + 256]
  assert not out2["gate"]["passes"] and out2["filtering"] == "unitwise_fallback"
  assert np.abs(out2["X"][0]).max() < 0.01 < np.abs(cont).max()


# ------------------------------------------------------------------ windows, folds, aggregation
def test_windows_of_a_four_second_trial_are_thirteen_and_carry_the_trial():
  """Known answer: 1 s windows every 0.25 s at 256 Hz: n 256, stride 64, starts 0, 64, ..., 768 (13 per 1024-sample
  trial; MAS has 17 in its 5 s stimulus); window j of trial i is samples [64 j, 64 j + 256) of trial i."""
  n, stride = nwin.window_geometry(FS, SSVEP["networks"]["windows"])
  assert (n, stride) == (256, 64)
  assert nwin.window_starts(1024, n, stride).tolist() == list(range(0, 769, 64))
  assert len(nwin.window_starts(1280, n, stride)) == 17
  X = np.arange(2 * 3 * 1024, dtype=float).reshape(2, 3, 1024)
  W, t = nwin.crop_trials(X, n, stride)
  assert W.shape == (26, 3, 256) and t.tolist() == [0] * 13 + [1] * 13
  assert np.array_equal(W[13 + 5], X[1, :, 320:576])


def test_window_folds_group_trials_and_equal_sklearn():
  """Known answer: the folds are sklearn's StratifiedGroupKFold(5, shuffle=True, seed) over windows grouped by trial;
  no trial has windows on both sides; every window is tested once; a fake leak is refused."""
  from sklearn.model_selection import StratifiedGroupKFold
  y = np.repeat(np.repeat(np.arange(5), 8), 13)
  g = np.repeat(np.arange(40), 13)
  sp = nwin.window_grouped_splits(y, g, 5, 20261107)
  ref = list(StratifiedGroupKFold(5, shuffle=True, random_state=20261107).split(np.zeros((len(y), 1)), y, g))
  assert all(np.array_equal(a[2], b[1]) for a, b in zip(sp, ref))
  for _, tr, te in sp:
    assert not set(g[tr]) & set(g[te])
  assert len(nwin.splits_sha256(sp, g)) == 64


def test_trial_probability_is_the_mean_of_its_windows():
  p = np.array([[0.6, 0.4], [0.2, 0.8], [0.9, 0.1], [0.5, 0.5]])
  t = np.array([0, 0, 1, 1])
  assert np.allclose(nwin.trial_probabilities(p, t, 2), [[0.4, 0.6], [0.7, 0.3]])


# ------------------------------------------------------------------ settings rules
def _cfg_windows(seeds):
  cfg = st.from_profile("ssvep", {"classes": NAMES, "fs_hz": FS, "channels": ["C0"], "adapter": "a", "data_root": "d",
                                  "label_scheme": "unit_label", "epochs": {}, "folds": {"n_folds": 8, "seed": 1},
                                  "permutation": {}, "statistics": {"holm_family": []}, "comparator": "ssvep/fbcca",
                                  "selection": {"development_participants": ["P0"]}, "stage": {"name": "development"}})
  cfg["ssvep"]["stimulus_freqs_hz"] = list(FREQS)
  cfg.pop("f1")                      # the classical section is not under test here
  cfg["networks"]["enabled"] = True
  cfg["networks"]["seeds"] = seeds
  cfg["networks"]["cv"]["seed"] = 1
  cfg["network_input"].update(fs_out_hz=FS, epoch_window_s=[0.0, 4.0], epoch_samples_out=1024)
  return cfg


def test_settings_refuse_seed_bases_that_share_fold_seeds_and_accept_spacing_of_1000():
  """Known answer: seed bases 20261107, 20261108, 20261109 with 5 folds share fold seeds (seed base + fold): refused;
  20261107, 20262107, 20263107 (the profile's): accepted. Windows without grouped folds, an iir_ba input that
  resamples, and a mas_p10 augmentation missing mixup_alpha are refused."""
  with pytest.raises(st.SettingsError, match="share fold seeds"):
    st.validate(_cfg_windows([20261107, 20261108, 20261109]), require_sources=False)
  st.validate(_cfg_windows([20261107, 20262107, 20263107]), require_sources=False)
  c = _cfg_windows([1, 1001, 2001])
  c["networks"]["cv"]["scheme"] = "study"
  with pytest.raises(st.SettingsError, match="window_grouped"):
    st.validate(c, require_sources=False)
  c = _cfg_windows([1, 1001, 2001])
  c["network_input"]["fs_out_hz"] = 128.0
  with pytest.raises(st.SettingsError, match="does not resample"):
    st.validate(c, require_sources=False)
  c = _cfg_windows([1, 1001, 2001])
  del c["networks"]["augmentation"]["mixup_alpha"]
  with pytest.raises(st.SettingsError, match="mixup_alpha"):
    st.validate(c, require_sources=False)


# ------------------------------------------------------------------ positive control
@pytest.mark.parametrize("net", ["eegnet", "shallowconvnet"])
def test_positive_control_planted_ssvep_is_learned_under_p20(net):
  """Known answer (positive control, Sebastian 2026-11-10): 40 synthetic 4 s trials, 8 per class at the five study
  frequencies plus the 2nd harmonic (amplitude 1 in unit noise): trial BA >= 0.9 under the P20 protocol (13 windows
  per trial, 5 grouped folds, MAS trainer and augmentation); epochs lowered to 40 for test time only."""
  X, y = ssvep_trials(4, amp=1.0)
  n = p20(max_epochs=40)
  pred, pt, rows, curves, info = nwin.cv_network_windows(X, y, np.arange(len(y)), n["models"][net], 20261107, n, "cpu",
                                                          NAMES, FS)
  ba = float(np.mean([np.mean(pred[y == c] == c) for c in range(5)]))
  assert ba >= 0.9, ba
  assert info["n_windows_per_trial"] == 13 and len(rows) == 5 and {r["fold_seed"] for r in rows} == set(range(20261107, 20261112))
  assert np.allclose(pt.sum(1), 1.0)


def test_noise_trials_stay_near_chance_under_p20():
  """Known answer (negative control): pure noise, same protocol and labels: trial BA <= 0.45 (chance 0.2)."""
  X, y = ssvep_trials(5, amp=0.0)
  n = p20(max_epochs=15)
  pred, _, _, _, _ = nwin.cv_network_windows(X, y, np.arange(len(y)), n["models"]["eegnet"], 20261107, n, "cpu", NAMES, FS)
  assert float(np.mean([np.mean(pred[y == c] == c) for c in range(5)])) <= 0.45


# ------------------------------------------------------------------ runner end to end
ADAPTER = '''
import numpy as np
from pathlib import Path

def dataset_parts(root):
  root = Path(root)
  return [{"participant": "P1", "part": "P1/s1", "files": sorted(f"P1/s1/{f.name}" for f in (root / "P1" / "s1").glob("*.npz"))}]

def read(path):
  z = np.load(path)
  return z["data"], float(z["fs"]), [str(c) for c in z["ch"]]

def events(path, data, fs, ch, settings):
  z = np.load(path)
  return {k: z[k] for k in ("onset", "unit", "label", "unit_start", "unit_end", "code")}

def condition_of(path):
  return Path(path).stem
'''


def _run_cfg(part):
  epochs = synth.erp_settings(FS)
  epochs.pop("classes")
  epochs["rejection"].update(enabled=False, window_s=[0.0, 4.0], window_rounding="floor")
  epochs["epoch"] = {"window_s": [0.0, 4.0], "window_rounding": "floor", "decim": 1}
  epochs["span_gates"], epochs["window_gates"] = [], []
  erp = json.loads((PROFILES / "erp.json").read_text())
  f1 = copy.deepcopy(erp["f1"])
  f1["feature_spaces"], f1["model_order"] = ["raw"], ["Shrinkage-LDA lsqr"]
  f1["models"] = {"Shrinkage-LDA lsqr": f1["models"]["Shrinkage-LDA lsqr"]}
  f1["models"]["Shrinkage-LDA lsqr"]["params"]["priors"] = [0.2] * 5
  n = p20(max_epochs=4)
  n["enabled"], n["seeds"] = True, [20261107, 20262107, 20263107]
  n["models"] = {"eegnet": n["models"]["eegnet"]}
  ni = copy.deepcopy(SSVEP["network_input"])
  ni.update(fs_out_hz=FS, epoch_window_s=[0.0, 4.0], epoch_samples_out=1024)
  return {"settings_version": 1, "classes": NAMES, "fs_hz": FS, "channels": ["C0", "C1", "C2", "C3"],
          "adapter": "adapter_p20", "data_root": "data/raw", "label_scheme": "unit_label", "epochs": epochs,
          "folds": {"n_folds": 4, "seed": 20261107}, "baseline": copy.deepcopy(erp["baseline"]), "f1": f1,
          "networks": n, "network_input": ni,
          "permutation": {"methods": [], "n_permutations": 0, "seed": 1, "alpha": 0.05, "critical_value_percentile": 95.0,
                          "percentile_method": "linear", "n_jobs": 1, "chunk_size": 8},
          "statistics": copy.deepcopy(erp["statistics"]), "comparator": "baseline",
          "selection": {"seed": 1, "development_participants": ["P0"], "excluded_files": [], "reported_separately": []},
          "stage": {"name": "development", "scope": "primaries", "scopes": {"primaries": {}}, "job_timeout_hours": 0.2,
                    "retry": {"max_attempts": 1}, "tracked": [], "selection_output": None, "part": part,
                    "dataset_part": "P1/s1"}}


def _project(tmp_path):
  root = tmp_path / "proj"
  for f in range(2):
    data, ev, info = synth.recording(70 + f, fs=FS, n_channels=4, n_units=10, n_epochs=1, tail=1100, rest=600,
                                     scheme="per_unit", n_classes=5, effect="ssvep", amp=1.5, freqs=FREQS)
    p = root / "data" / "raw" / "P1" / "s1" / f"f{f}.npz"
    p.parent.mkdir(parents=True, exist_ok=True)
    np.savez(p, data=data, fs=FS, ch=np.array(info["ch_names"]), **ev)
  (root / "adapter_p20.py").write_text(ADAPTER)
  return root


def _out(tmp_path, name):
  out = tmp_path / name
  out.mkdir()
  (out / "provenance.json").write_text(json.dumps({"commit_short": "test", "tracked_files_dirty": False}))
  return out


def test_runner_p20_network_part_keeps_the_study_hashes_and_records_its_window_folds(tmp_path):
  """Known answer (end to end, rm.run): a P20 EEGNet part and the classical part of the same data part have the same
  epochs_sha256 and folds_sha256 (the stage runner's identity check is unchanged); the network part records its
  protocol, 13 windows per trial, and one window-folds hash (the same for every seed, the folds do not depend on
  the seed); pooled.csv has three seed rows and a mean row with window_ba; per_fold.csv has 5 folds per seed with
  fold seeds seed base + fold."""
  root = _project(tmp_path)
  o_net, o_cls = _out(tmp_path, "net"), _out(tmp_path, "cls")
  r_net = rm.run(_run_cfg("f2__eegnet"), o_net, root)
  r_cls = rm.run(_run_cfg("classical"), o_cls, root)
  assert r_net["methods"]["f2/eegnet"] == "ok", r_net["methods"]
  assert (r_net["epochs_sha256"], r_net["folds_sha256"]) == (r_cls["epochs_sha256"], r_cls["folds_sha256"])
  proto = r_net["network_protocol"]
  assert proto["protocol"] == "windows (P20)" and set(proto["per_seed"]) == {"20261107", "20262107", "20263107"}
  shas = {v["network_folds_sha256"] for v in proto["per_seed"].values()}
  assert len(shas) == 1 and all(v["n_windows_per_trial"] == 13 for v in proto["per_seed"].values())
  pooled = [r for r in csv.DictReader(open(o_net / "pooled.csv")) if r["method"] == "f2/eegnet"]
  assert sorted(r["seed"] for r in pooled) == ["20261107", "20262107", "20263107", "mean"]
  assert all(r["window_ba"] != "" for r in pooled)
  folds = [r for r in csv.DictReader(open(o_net / "per_fold.csv")) if r["method"] == "f2/eegnet"]
  assert len(folds) == 15 and {int(r["fold_seed"]) - int(r["seed"]) for r in folds} == set(range(5))
  gates = list(csv.DictReader(open(o_net / "gates.csv")))
  assert all(g["network_input_filtering"] in ("continuous", "unitwise_fallback") for g in gates)
