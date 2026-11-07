"""Known-answer and false-positive-rate tests for the v0.3 eegharness modules
(splits, permutation, chance: core; seeds, folds: torch optional)."""

import itertools
import json
import sys
import types
from fractions import Fraction
from math import comb
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from eegharness import chance, folds, outputs, permutation, seeds, splits  # noqa: E402


# ---------- splits ----------

def _design(n_part=2, n_trials=12, per_trial=5):
  part = np.repeat(np.arange(n_part), n_trials * per_trial)
  trial = np.tile(np.repeat(np.arange(n_trials), per_trial), n_part)       # restarts per participant
  y = np.tile(np.repeat(np.arange(n_trials) % 2, per_trial), n_part)
  return part, trial, y


def test_group_ids_unique_across_participants():
  """Known answer: trial 0 of participant 0 and trial 0 of participant 1 get different ids."""
  part, trial, _ = _design()
  g = splits.group_ids(part, trial)
  assert len(np.unique(g)) == 24
  assert g[0] != g[12 * 5]
  assert len(np.unique(splits.group_ids(trial))) == 12      # the collision group_ids prevents


def test_grouped_kfold_no_leak_every_group_tested_once_and_stratified():
  part, trial, y = _design()
  g = splits.group_ids(part, trial)
  folds_ = splits.grouped_kfold(g, 4, y=y, seed=1)
  tested = np.concatenate([te for _, te in folds_])
  assert sorted(tested.tolist()) == list(range(len(g)))       # every sample tested exactly once
  for tr, te in folds_:
    assert not set(g[tr]) & set(g[te])
    n_cls = [len(set(g[te][y[te] == c])) for c in (0, 1)]
    assert n_cls == [3, 3]                                       # 12 groups per class / 4 folds


def test_grouped_kfold_rejects_label_varying_within_group():
  with pytest.raises(ValueError, match="not constant"):
    splits.grouped_kfold([0, 0, 1, 1], 2, y=[0, 1, 0, 1])


def test_check_no_leak_fails_on_the_buggy_sample_level_split():
  """G2: a split by sample (windows of one trial on both sides) must fail the check."""
  _, trial, _ = _design(n_part=1)
  idx = np.arange(len(trial))
  with pytest.raises(splits.LeakError, match="group"):
    splits.check_no_leak(idx[::2], idx[1::2], trial)
  with pytest.raises(splits.LeakError, match="index"):
    splits.check_no_leak([0, 1], [1, 2], [0, 1, 2])


def test_inner_split_uses_training_groups_only():
  part, trial, y = _design()
  g = splits.group_ids(part, trial)
  for tr, te in splits.grouped_kfold(g, 4, y=y, seed=0):
    fit, val = splits.inner_split(tr, g, 0.25, seed=3, y=y)
    assert set(fit) | set(val) == set(tr) and not set(val) & set(te)
    assert not set(g[fit]) & set(g[val])
    assert {0, 1} <= set(y[val])                                 # stratified validation


def test_leave_one_group_out_holds_out_each_participant():
  part, _, _ = _design(n_part=3)
  out = splits.leave_one_group_out(part)
  assert [set(part[te]) for _, te in out] == [{0}, {1}, {2}]


# ---------- permutation ----------

def test_permutation_p_matches_exact_enumeration():
  """Known answer: 6 units, 3 per label; exact p is the rank among all C(6,3) = 20 labellings."""
  x = np.array([5.1, 4.0, 3.2, 2.2, 1.9, 0.3])
  lab = np.array([1, 1, 0, 1, 0, 0])
  stat = lambda L: x[L == 1].mean() - x[L == 0].mean()
  obs = stat(lab)
  exact = []
  for c in itertools.combinations(range(6), 3):
    L = np.zeros(6, int)
    L[list(c)] = 1
    exact.append(stat(L))
  p_exact = np.mean(np.array(exact) >= obs - 1e-12)
  r = permutation.permutation_test(stat, lab, n_permutations=20000, seed=0)
  assert abs(r["p"] - p_exact) < 0.01
  assert r["permutation_unit"] == "sample"


def test_permutation_observed_labelling_counts_in_the_null():
  """G13: with a huge effect p is exactly 1/(n+1), never 0."""
  lab = np.repeat([0, 1], 10)
  x = lab * 100.0
  r = permutation.permutation_test(lambda L: x[L == 1].mean() - x[L == 0].mean(), lab, n_permutations=99)
  assert r["p"] == pytest.approx(1 / 100) == r["min_p"]


def test_permutation_keeps_units_whole_and_rejects_mixed_units():
  units = np.repeat(np.arange(6), 4)
  lab = np.repeat([0, 1, 0, 1, 0, 1], 4)
  seen = []
  def stat(L):
    seen.append(L.copy())
    return 0.0
  permutation.permutation_test(stat, lab, units=units, n_permutations=50)
  for L in seen:
    assert all(len(set(L[units == u])) == 1 for u in range(6))  # a unit never splits
    assert L.sum() == lab.sum()                                   # observed group sizes
  with pytest.raises(ValueError, match="vary within unit"):
    permutation.permutation_test(stat, np.arange(24) % 2, units=units)


def _clustered(rng, n_units=16, per_unit=6):
  units = np.repeat(np.arange(n_units), per_unit)
  lab = np.repeat(np.arange(n_units) % 2, per_unit)
  x = rng.normal(0, 1, n_units)[units] + rng.normal(0, 0.3, len(units))   # shared unit effect, no label effect
  return x, lab, units


def test_false_positive_rate_unit_level_nominal_window_level_inflated():
  """G12/G13 FPR test. No label effect; samples share a unit effect.
  Unit-level permutation rejects at about alpha = 0.05: 300 datasets, binomial 99.9 % band
  [0.02, 0.10]. Window-level permutation (the buggy variant) rejects far more (> 0.25)."""
  rng = np.random.default_rng(7)
  rej_unit = rej_win = 0
  n = 300
  for _ in range(n):
    x, lab, units = _clustered(rng)
    stat = lambda L: x[L == 1].mean() - x[L == 0].mean()
    rej_unit += permutation.permutation_test(stat, lab, units=units, n_permutations=99,
                                             seed=int(rng.integers(1 << 30)), alternative="two-sided")["p"] <= 0.05
    rej_win += permutation.permutation_test(stat, lab, n_permutations=99,
                                            seed=int(rng.integers(1 << 30)), alternative="two-sided")["p"] <= 0.05
  assert 0.02 <= rej_unit / n <= 0.10
  assert rej_win / n > 0.25


def test_permutation_bad_arguments():
  with pytest.raises(ValueError):
    permutation.permutation_test(lambda L: 0.0, [0, 1], alternative="bigger")
  with pytest.raises(ValueError):
    permutation.permutation_test(lambda L: 0.0, [0, 1], n_permutations=0)


# ---------- chance ----------

def test_binom_sf_exact_against_fractions():
  for n, p in ((10, Fraction(1, 2)), (12, Fraction(1, 4)), (7, Fraction(1, 5))):
    for k in range(n + 2):
      exact = sum(comb(n, j) * p**j * (1 - p) ** (n - j) for j in range(k, n + 1))
      assert chance.binom_sf(k, n, float(p)) == pytest.approx(float(exact), rel=1e-9, abs=1e-15)


def test_chance_level_known_answers():
  """Known answer: n = 10, 2 classes: P(X >= 9) = 11/1024 = .0107 <= .05 < P(X >= 8) = 56/1024
  -> 0.9. One trial can never be significant. Large n stays finite and tends to 1/k."""
  assert chance.chance_level(10, 2, 0.05) == 0.9
  assert chance.chance_level(1, 2, 0.05) == float("inf")
  lvl = chance.chance_level(2000, 4, 0.05)
  assert 0.25 < lvl < 0.27
  assert chance.p_above_chance(9, 10, 2) == pytest.approx(11 / 1024)
  assert chance.chance_level(10, p0=0.7) > chance.chance_level(10, 2)


# ---------- seeds (torch optional) ----------

def test_fold_seed_distinct_and_same_for_both_arms():
  s = {seeds.fold_seed(42, r, f) for r in range(3) for f in range(10)}
  assert len(s) == 30 and seeds.fold_seed(42, 1, 3) == 1045
  with pytest.raises(ValueError):
    seeds.fold_seed(42, 0, 1000)


def test_seed_everything_reproducible_without_torch(monkeypatch):
  monkeypatch.setitem(sys.modules, "torch", None)            # import torch -> ImportError
  a = seeds.seed_everything(5)
  x1 = np.random.rand(3)
  seeds.seed_everything(5)
  assert np.array_equal(x1, np.random.rand(3)) and a["torch"] is False
  with pytest.raises(ImportError):
    seeds.torch_generator(1)


def _fake_torch(calls):
  t = types.ModuleType("torch")
  t.__version__ = "9.9-fake"
  t.manual_seed = lambda s: calls.append(("manual_seed", s))
  t.use_deterministic_algorithms = lambda flag, warn_only=False: calls.append(("det", flag, warn_only))
  t.are_deterministic_algorithms_enabled = lambda: True
  t.cuda = types.SimpleNamespace(is_available=lambda: False, manual_seed_all=lambda s: calls.append(("cuda", s)),
                                 device_count=lambda: 0, get_device_name=lambda i: "")
  t.version = types.SimpleNamespace(cuda=None)
  t.backends = types.SimpleNamespace(cudnn=types.SimpleNamespace(deterministic=False, benchmark=True))

  class Gen:
    def manual_seed(self, s):
      calls.append(("gen", s))
      return self
  t.Generator = Gen
  return t


def test_seed_everything_and_provenance_with_torch(monkeypatch, tmp_path):
  calls = []
  t = _fake_torch(calls)
  monkeypatch.setitem(sys.modules, "torch", t)
  done = seeds.seed_everything(7)
  seeds.torch_generator(7)
  assert done["torch"] and ("manual_seed", 7) in calls and ("det", True, True) in calls and ("gen", 7) in calls
  assert t.backends.cudnn.deterministic is True and t.backends.cudnn.benchmark is False
  out = outputs.new_output_dir(tmp_path / "o", root=tmp_path)
  comp = json.loads((out / "provenance.json").read_text())["compute"]
  assert comp["torch"] == "9.9-fake" and comp["cudnn_deterministic"] is True and comp["cuda_available"] is False


def test_provenance_compute_null_when_torch_not_imported(monkeypatch, tmp_path):
  monkeypatch.delitem(sys.modules, "torch", raising=False)
  out = outputs.new_output_dir(tmp_path / "o", root=tmp_path)
  assert json.loads((out / "provenance.json").read_text())["compute"] is None


def test_seed_summary():
  s = seeds.seed_summary([0.70, 0.74, 0.72])
  assert s["n"] == 3 and s["mean"] == pytest.approx(0.72) and s["sd"] == pytest.approx(0.02) and s["meets_minimum"]
  assert seeds.seed_summary([0.7])["meets_minimum"] is False


# ---------- folds ----------

def test_foldstore_roundtrip_resume_and_refuse_other_config(tmp_path):
  cfg = {"model": "net", "channels": ["Cz", "Pz"], "seeds": 3}
  st = folds.FoldStore(tmp_path / "f", cfg)
  st.save("test-S01__seed-0", meta={"best_epoch": 12}, y_true=np.arange(4), y_pred=np.array([0, 1, 1, 3]))
  assert st.done("test-S01__seed-0") and not st.done("test-S02__seed-0")
  st2 = folds.FoldStore(tmp_path / "f", dict(reversed(list(cfg.items()))))   # same config, other key order
  arrays, meta = st2.load("test-S01__seed-0")
  assert np.array_equal(arrays["y_pred"], [0, 1, 1, 3]) and meta == {"best_epoch": 12}
  assert st2.keys() == ["test-S01__seed-0"]
  with pytest.raises(FileExistsError):
    st2.save("test-S01__seed-0", y_true=np.arange(4))
  with pytest.raises(folds.ConfigMismatch):
    folds.FoldStore(tmp_path / "f", {**cfg, "channels": ["Cz"]})
  with pytest.raises(ValueError):
    st.save("../escape", y=np.arange(2))
  assert not list((tmp_path / "f").glob(".*tmp*"))


def test_core_modules_do_not_import_torch(monkeypatch):
  """torch is never required: the package imports with torch unavailable."""
  import importlib
  monkeypatch.setitem(sys.modules, "torch", None)
  for name in ("splits", "permutation", "chance", "seeds", "folds", "outputs"):
    importlib.reload(importlib.import_module(f"eegharness.{name}"))
