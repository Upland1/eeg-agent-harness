"""Known-answer tests for eegpipe.cca, classical and evaluate.

Moved from the P300 project (tests @ d833264, ``tests/test_ssvep_methods_step1.py`` sections
5-8 and the convergence tests of ``step2``), generalised to k classes, plus 5-class known
answers (the supervisor's decision D5)."""

import copy
import json
import pickle
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from scipy import stats

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
from eegpipe import classical as cl  # noqa: E402
from eegpipe import dataset as ds  # noqa: E402
from eegpipe import epochs as ep  # noqa: E402
from eegpipe import evaluate as evl  # noqa: E402
from eegpipe import folds as fo  # noqa: E402
from eegpipe.cca import CCASpatialFilter  # noqa: E402
from eegpipe.testing import synth  # noqa: E402

FS = 256.0
SEED_FOLDS, SEED_PERM = 20261107, 20261105
BIN = ["nontarget", "target"]
PROFILE = json.loads((TOOLS / "eegpipe" / "profiles" / "erp.json").read_text())


def cfg_with(model_order=("Shrinkage-LDA lsqr",), spaces=("raw",), k=2):
  f1 = copy.deepcopy(PROFILE["f1"])
  f1["model_order"], f1["feature_spaces"] = list(model_order), list(spaces)
  base = copy.deepcopy(PROFILE["baseline"])
  if k != 2:
    for spec in f1["models"].values():
      if "priors" in spec["params"]:
        spec["params"]["priors"] = cl.uniform_priors(k)
    base = None
  return {"f1": f1, "baseline": base}


def make_world(seed=0, n_files=3, n_units=6, amp=2.5):
  s = synth.erp_settings(FS)
  s["rejection"]["enabled"] = False
  res = []
  for f in range(n_files):
    data, events, info = synth.recording(seed * 100 + f, fs=FS, n_channels=4, n_units=n_units, n_epochs=24,
                                         isi=64, rest=1200, amp=amp, noise=1.0,
                                         unit_targets=np.arange(n_units) % 4)
    r = ep.prepare_file(data, FS, events, s)
    r["unit_targets"] = info["unit_targets"]
    res.append(r)
  sess = ds.assemble(res)
  uf = fo.assign_unit_folds(sess["unit_file"], 8, SEED_FOLDS)
  return {"sess": sess, "res": res, "splits": fo.fold_splits(sess["unit_uid"], uf, 8),
          "targets": [r["unit_targets"] for r in res]}


@pytest.fixture(scope="module")
def world():
  return make_world()


# ------------------------------------------------------------------ models
def test_build_model_refuses_missing_or_unknown_parameter_and_unknown_class():
  """Known answer: every one of the 10 profile tables builds; deleting any parameter -> ValueError
  naming it; adding 'bogus' -> ValueError naming it; an unknown class -> ValueError (G5)."""
  table = PROFILE["f1"]["models"]
  assert list(table) == list(cl.MODEL_NAMES)
  for spec in table.values():
    cl.build_model(spec)
    for k in spec["params"]:
      bad = copy.deepcopy(spec)
      del bad["params"][k]
      with pytest.raises(ValueError, match=k):
        cl.build_model(bad)
    bad = copy.deepcopy(spec)
    bad["params"]["bogus"] = 1
    with pytest.raises(ValueError, match="bogus"):
      cl.build_model(bad)
  with pytest.raises(ValueError, match="unknown model class"):
    cl.build_model({"class": "SVC", "params": {}})


@pytest.mark.parametrize("k", [2, 5])
def test_lda_priors_are_the_explicit_uniform_priors_not_the_class_proportions(k):
  """Known answer (exact): fitted on imbalanced data (class 0 is 3x as frequent as each other
  class), every LDA of the suite has priors_ = 1/k for all k classes; the scikit-learn default
  (priors inferred) would give the class proportions (buggy variant, checked)."""
  cfg = cfg_with(model_order=cl.MODEL_NAMES, spaces=("raw",), k=k)
  rng = np.random.default_rng(0)
  y = np.concatenate([np.zeros(60, int), np.repeat(np.arange(1, k), 20)])
  X = rng.normal(size=(len(y), 4, 20)) + y[:, None, None] * 0.3
  for name in ("LDA svd", "Shrinkage-LDA lsqr", "Shrinkage-LDA eigen"):
    m = cl.make_f1("raw", name, cfg["f1"]).fit(X, y)
    assert np.allclose(m.named_steps["model"].priors_, [1 / k] * k)
  from sklearn.discriminant_analysis import LinearDiscriminantAnalysis as LDA
  emp = np.bincount(y) / len(y)
  assert np.allclose(LDA(solver="svd").fit(X.reshape(len(y), -1), y).priors_, emp)
  assert not np.allclose(emp, [1 / k] * k)


def test_method_ids_and_primary():
  cfg = cfg_with(model_order=cl.MODEL_NAMES, spaces=("raw", "cca"))
  ids = cl.method_ids(cfg)
  assert ids[0] == "baseline" and len(ids) == 21 and ids[1] == "f1/raw/Ridge" and ids[-1] == "f1/cca/QDA"
  assert cl.primary_f1_id({"f1": PROFILE["f1"]}) == "f1/raw/Shrinkage-LDA lsqr"


def test_scaler_and_cca_are_fitted_on_training_folds_only(world):
  """Known answer (exact up to 1e-12; moved from step1): per fold, StandardScaler.mean_/scale_
  equal the TRAINING epochs' statistics and differ from the all-data mean; the CCA filters equal
  a fresh CCA fitted on the training epochs only; a spy shows CCASpatialFilter.fit sees exactly
  the training indices. Buggy variant: a pipeline fitted on all data fails the same check."""
  sess, splits = world["sess"], world["splits"]
  X = sess["X"].copy()
  X[:, 0, 0] = 1000.0 + np.arange(len(X))
  cfg = cfg_with(spaces=("raw", "cca"))
  seen = []
  orig = CCASpatialFilter.fit

  def spy(self, Xf, yf):
    seen.append(set((np.round(Xf[:, 0, 0]).astype(int) - 1000).tolist()))
    return orig(self, Xf, yf)
  CCASpatialFilter.fit = spy
  try:
    for space in ("raw", "cca"):
      made = []

      def mk():
        m = cl.make_method(f"f1/{space}/Shrinkage-LDA lsqr", cfg)
        made.append(m)
        return m
      seen.clear()
      evl.cv_predict(X, sess["y"], splits, mk, BIN)
      seen_cv = list(seen)
      for (k, tr, te), m in zip(splits, made):
        if space == "raw":
          F = X[tr].reshape(len(tr), -1)
          assert np.allclose(m.named_steps["scaler"].mean_, F.mean(0), atol=1e-12)
          assert np.allclose(m.named_steps["scaler"].scale_, F.std(0), atol=1e-12)
          assert not np.allclose(m.named_steps["scaler"].mean_, X.reshape(len(X), -1).mean(0), atol=1e-6)
        else:
          ref = orig(CCASpatialFilter(n_filters=3, reg=0.0), X[tr], sess["y"][tr])
          assert np.allclose(m.named_steps["cca"].filters_, ref.filters_, atol=1e-12)
      if space == "cca":
        assert seen_cv == [set(tr.tolist()) for _, tr, _ in splits]
  finally:
    CCASpatialFilter.fit = orig
  leaky = cl.make_f1("raw", "Ridge", cfg_with(model_order=("Ridge",))["f1"]).fit(X, sess["y"])
  tr = splits[0][1]
  assert not np.allclose(leaky.named_steps["scaler"].mean_, X[tr].reshape(len(tr), -1).mean(0), atol=1e-12)


def test_test_fold_labels_are_never_read_when_fitting(world):
  """Known answer (exact): a sentinel label 7 on the test epochs of a fold leaves its predictions
  and decision values unchanged for the baseline and every F1 model except QDA, both spaces; a
  sentinel in the TRAINING labels is seen by the model (positive control)."""
  sess, splits = world["sess"], world["splits"]
  X, y = sess["X"], sess["y"]
  cfg = cfg_with(model_order=[n for n in cl.MODEL_NAMES if n != "QDA"], spaces=("raw", "cca"))
  for mid in cl.method_ids(cfg):
    for k, tr, te in splits[:2]:
      p0, d0 = evl.fit_predict(lambda: cl.make_method(mid, cfg), X, y, tr, te)
      y2 = y.copy()
      y2[te] = 7
      p1, d1 = evl.fit_predict(lambda: cl.make_method(mid, cfg), X, y2, tr, te)
      assert np.array_equal(p0, p1) and (d0 is None or np.array_equal(d0, d1)), mid
  y3 = y.copy()
  y3[splits[0][1][:50]] = 7
  est = cl.make_method("f1/raw/Ridge", cfg).fit(X[splits[0][1]], y3[splits[0][1]])
  assert 7 in est.named_steps["model"].classes_


def test_planted_erp_is_recovered_and_shuffled_targets_give_chance(world):
  """Known answer: a planted ERP (amplitude 2.5 x noise SD on target epochs) is recovered by the
  baseline and the primary (pooled out-of-fold BA >= 0.80, both class recalls >= 0.70); with unit
  targets shuffled within files the BA is within 0.5 +- 0.10 [own bounds, a priori]."""
  sess, splits = world["sess"], world["splits"]
  cfg = cfg_with()
  for mid in ("baseline", "f1/raw/Shrinkage-LDA lsqr"):
    pred, _, _ = evl.cv_predict(sess["X"], sess["y"], splits, lambda: cl.make_method(mid, cfg), BIN)
    m = evl.class_metrics(sess["y"], pred, BIN)
    assert m["ba"] >= 0.80 and m["ca_target"] >= 0.70 and m["ca_nontarget"] >= 0.70, (mid, m)
  sh = evl.draw_shuffles(world["targets"], 1, SEED_PERM)
  ysh = evl.labels_for(sess, [s[0] for s in sh], "unit_target")
  pred, _, _ = evl.cv_predict(sess["X"], ysh, splits, lambda: cl.make_method("f1/raw/Shrinkage-LDA lsqr", cfg), BIN)
  assert abs(evl.class_metrics(ysh, pred, BIN)["ba"] - 0.5) <= 0.10


def test_five_class_planted_effect_is_learned_with_uniform_priors():
  """Known answer (5 classes): units of class c carry an ERP of amplitude c * 1.5 noise SD; the
  raw Shrinkage-LDA learns it (pooled 5-class BA >= 0.6, chance 0.2) under grouped folds; on
  noise-only data the BA is within 0.2 +- 0.12 [own bounds, a priori]."""
  s = synth.erp_settings(FS)
  s["rejection"]["enabled"] = False
  s["classes"] = [f"c{i}" for i in range(5)]
  names = s["classes"]
  for effect, check in (("erp", lambda ba: ba >= 0.6), ("none", lambda ba: abs(ba - 0.2) <= 0.12)):
    res = []
    for f in range(3):
      data, events, _ = synth.recording(500 + f, fs=FS, n_channels=4, n_units=10, n_epochs=12, isi=64, rest=1200,
                                        scheme="per_unit", n_classes=5, effect=effect, amp=1.5)
      res.append(ep.prepare_file(data, FS, events, s))
    sess = ds.assemble(res)
    splits = fo.fold_splits(sess["unit_uid"], fo.assign_unit_folds(sess["unit_file"], 5, 1), 5)
    cfg = cfg_with(k=5)
    pred, _, _ = evl.cv_predict(sess["X"], sess["y"], splits, lambda: cl.make_method("f1/raw/Shrinkage-LDA lsqr", cfg), names)
    ba = evl.class_metrics(sess["y"], pred, names)["ba"]
    assert check(ba), (effect, ba)


# ------------------------------------------------------------------ metrics
def test_class_metrics_known_values_binary_and_five_class():
  """Known answer (hand-derived): binary y = [0,0,0,1], pred = [0,1,0,1] -> ca_nontarget 2/3,
  ca_target 1, BA 5/6. Five classes y = [0,1,2,3,4,4], pred = [0,1,1,3,4,0] -> recalls
  1,1,0,1,0.5 -> BA 0.7; a class absent from y gives NaN recall and NaN BA."""
  m = evl.class_metrics([0, 0, 0, 1], [0, 1, 0, 1], BIN)
  assert m["ca_nontarget"] == pytest.approx(2 / 3) and m["ca_target"] == 1.0 and m["ba"] == pytest.approx(5 / 6)
  names = list("abcde")
  m5 = evl.class_metrics([0, 1, 2, 3, 4, 4], [0, 1, 1, 3, 4, 0], names)
  assert [m5[f"ca_{c}"] for c in names] == [1.0, 1.0, 0.0, 1.0, 0.5] and m5["ba"] == pytest.approx(0.7)
  assert np.isnan(evl.class_metrics([0, 1], [0, 1], names)["ba"])


def test_convergence_warnings_counted_and_predictions_unchanged(world):
  """Known answer: LogReg L1 (saga) with max_iter 1 warns in every fold: n_convergence_warnings
  >= 1 per fold and the status reads 'ok, not converged (8 folds)'."""
  sess, splits = world["sess"], world["splits"]
  cfg = cfg_with(model_order=("LogReg L1",))
  cfg["f1"]["models"]["LogReg L1"]["params"]["max_iter"] = 1
  _, _, rows = evl.cv_predict(sess["X"], sess["y"], splits, lambda: cl.make_method("f1/raw/LogReg L1", cfg), BIN)
  n = sum(r["n_convergence_warnings"] > 0 for r in rows)
  assert n == 8 and evl.convergence_status(n) == "ok, not converged (8 folds)"
  assert evl.convergence_status(0) == "ok"


def test_differences_vs_is_exact():
  rows = [{"method": "baseline", "file": "a", "ba": 0.6}, {"method": "m", "file": "a", "ba": 0.75},
          {"method": "m", "file": "b", "ba": 0.9}]
  d = evl.differences_vs(rows, ["file"], "baseline", ["m"], ["ba"])
  assert d == [{"method": "m", "comparator": "baseline", "file": "a", "diff_ba": pytest.approx(0.15)}]


# ------------------------------------------------------------------ permutation nulls
def test_null_draws_are_per_stratum_reproducible_and_keep_the_multiset(world):
  """Known answer (exact): draw p equals default_rng([seed, p]).permutation applied to the strata
  in order; each row is a permutation of THAT stratum's targets; draws do not depend on how many
  are requested."""
  t = [np.array([0, 1, 2, 3, 0, 1]), np.array([1, 1, 2, 3, 3, 0]), np.array([2, 2, 2, 0, 1, 3])]
  a = evl.draw_shuffles(t, 12, SEED_PERM)
  for p in (0, 5, 11):
    rng = np.random.default_rng([SEED_PERM, p])
    for f in range(3):
      assert np.array_equal(a[f][p], rng.permutation(t[f]))
  for f in range(3):
    assert np.array_equal(np.sort(a[f], axis=1), np.tile(np.sort(t[f]), (12, 1)))
  b = evl.draw_shuffles(t, 5, SEED_PERM)
  assert all(np.array_equal(a[f][:5], b[f]) for f in range(3))


def test_observed_labelling_occurs_at_rate_one_over_n_distinct():
  """Known answer: [1,2,3,4] -> 4! = 24 distinct; in 4800 draws the observed vector occurs
  200 +- 4 binomial SD times; [1,1,2,2] -> 6; 5 distinct SSVEP classes over 5 trials -> 120."""
  assert evl.n_distinct_shuffles([1, 2, 3, 4]) == 24 and evl.n_distinct_shuffles([1, 1, 2, 2]) == 6
  assert evl.n_distinct_shuffles([0, 1, 2, 3, 4]) == 120
  d = evl.draw_shuffles([np.array([1, 2, 3, 4])], 4800, SEED_PERM)[0]
  n_obs = int(np.sum(np.all(d == np.array([1, 2, 3, 4]), axis=1)))
  assert abs(n_obs - 200) <= 4 * np.sqrt(4800 * (1 / 24) * (23 / 24))
  assert len({tuple(r) for r in d.tolist()}) == 24


def test_unit_target_refuses_a_target_missing_from_a_unit():
  with pytest.raises(ValueError, match="do not include"):
    evl.draw_shuffles([np.array([1, 4])], 3, 0, code_sets=[[np.array([1, 2, 3, 4]), np.array([1, 2, 3])]])


def test_per_stratum_tests_known_answer_mc_p_floors_flag_and_holm():
  """Known answer (exact, hand-derived; moved from step1): n_perm 19; stratum 0 p = 0.05,
  mean 0.49, 95th percentile 0.571; stratum 1 p = 0.5; floors 0.1 / 0.001; Holm (0.10, 0.5)."""
  null = np.zeros((19, 2))
  null[:, 0] = 0.40 + 0.01 * np.arange(19)
  null[:, 1] = [0.5] * 9 + [0.4] * 10
  r0, r1 = evl.per_stratum_tests(np.array([0.9, 0.5]), null, [10, 1000], 0.05, 95.0, "linear")
  assert r0["perm_p_monte_carlo"] == pytest.approx(0.05) and r1["perm_p_monte_carlo"] == pytest.approx(0.5)
  assert r0["monte_carlo_p_floor"] == pytest.approx(1 / 20)
  assert r0["exact_null_p_floor"] == pytest.approx(0.1) and r1["exact_null_p_floor"] == pytest.approx(0.001)
  assert r0["monte_carlo_p_below_exact_floor"] is True and r1["monte_carlo_p_below_exact_floor"] is False
  assert r0["null_ba_mean"] == pytest.approx(0.49) and r0["null_ba_critical"] == pytest.approx(0.571)
  assert r0["perm_p_holm"] == pytest.approx(0.10) and r1["perm_p_holm"] == pytest.approx(0.5)
  assert not r0["above_chance_holm"] and not r1["above_chance_holm"]


@pytest.mark.parametrize("n_perm,n_distinct", [(999, 6), (999, 1000), (999, 5000), (49, 20), (1000, 1)])
def test_p_floors(n_perm, n_distinct):
  mc, ex = 1.0 / (n_perm + 1), 1.0 / n_distinct
  assert evl.monte_carlo_p_floor(n_perm) == pytest.approx(mc)
  assert evl.exact_null_p_floor(n_distinct) == pytest.approx(ex)
  assert evl.larger_p_floor(n_perm, n_distinct) == pytest.approx(max(mc, ex))


def noise_session(seed, n_files=3, n_units=6, per_unit=12, unit_offset=1.0, scheme="unit_target", k=2):
  """Pure-noise epochs with a per-unit level shift (unit-level structure, no label effect)."""
  rng = np.random.default_rng(seed)
  cols = {c: [] for c in ("y", "code", "unit_local", "unit_uid", "file_idx", "onset")}
  Xs, values, ufile, ulocal = [], [], [], []
  uid = 0
  for f in range(n_files):
    if scheme == "unit_target":
      v = np.array([i % 4 for i in range(n_units)])
    else:
      v = np.resize(np.arange(k), n_units)
    values.append(v)
    for u in range(n_units):
      code = np.concatenate([rng.permutation(4) for _ in range(per_unit // 4)])
      Xs.append(rng.normal(size=(len(code), 4, 20)) + unit_offset * rng.normal())
      cols["code"].append(code)
      cols["y"].append((code == v[u]).astype(np.int64) if scheme == "unit_target" else np.full(len(code), v[u]))
      cols["unit_local"].append(np.full(len(code), u))
      cols["unit_uid"].append(np.full(len(code), uid))
      cols["file_idx"].append(np.full(len(code), f))
      cols["onset"].append(np.arange(len(code)))
      ufile.append(f)
      ulocal.append(u)
      uid += 1
  sess = {c: np.concatenate(v).astype(np.int64) for c, v in cols.items()}
  sess["X"] = np.concatenate(Xs)
  sess["unit_file"], sess["unit_local_of_uid"] = np.array(ufile), np.array(ulocal)
  return sess, values


def test_null_centres_near_half_on_noise_and_is_independent_of_n_jobs(tmp_path):
  """Known answer: on pure noise the null BAs of the baseline and the primary centre on 0.5
  (mean of 20 permutations within +-0.03) [own, a priori]; the null from 2 spawned worker
  processes (file-based run under a 240 s timeout) is bit-identical to n_jobs = 1."""
  sess, values = noise_session(1)
  splits = fo.fold_splits(sess["unit_uid"], fo.assign_unit_folds(sess["unit_file"], 8, SEED_FOLDS), 8)
  cfg = cfg_with()
  mids = ["baseline", "f1/raw/Shrinkage-LDA lsqr"]
  shuf = evl.draw_shuffles(values, 20, SEED_PERM)
  n1 = evl.permutation_null(sess, splits, mids, cl.make_method, cfg, "unit_target", BIN, shuf, 1, 8)
  assert n1.shape == (2, 20, 4)
  assert np.all(np.abs(n1.mean(axis=1) - 0.5) <= 0.03), n1.mean(axis=1)
  pk = tmp_path / "in.pkl"
  pk.write_bytes(pickle.dumps((sess, splits, mids, cfg, shuf)))
  helper = tmp_path / "pool_run.py"
  helper.write_text(
    "import sys, pickle\nimport numpy as np\nsys.path.insert(0, %r)\n"
    "from eegpipe import evaluate as evl, classical as cl\n"
    "if __name__ == '__main__':\n"
    "  sess, splits, mids, cfg, shuf = pickle.loads(open(sys.argv[1], 'rb').read())\n"
    "  np.save(sys.argv[2], evl.permutation_null(sess, splits, mids, cl.make_method, cfg, 'unit_target',\n"
    "          ['nontarget', 'target'], shuf, 2, 4))\n" % str(TOOLS))
  out = tmp_path / "n2.npy"
  subprocess.run([sys.executable, str(helper), str(pk), str(out)], check=True, timeout=240, capture_output=True,
                 env={"PYTHONPATH": str(TOOLS), "PATH": "/usr/bin:/bin", "OMP_NUM_THREADS": "1"})
  assert np.array_equal(np.load(out), n1)


@pytest.mark.parametrize("scheme,k", [("unit_target", 2), ("unit_label", 5)])
def test_per_stratum_null_false_positive_rate_on_pure_noise(scheme, k):
  """Known answer: under H0 (labels assigned at unit level, unrelated to the data, a per-unit
  level shift) P(p <= 0.05) <= 0.05; 30 noise sessions x 3 strata = 90 p-values; the count with
  p <= 0.05 must not exceed the 0.9999 quantile of Binomial(90, 0.05) (14); mean p > 0.45; no
  Holm rejection (min Holm p with 19 permutations is 0.15). Both schemes; 5 classes for
  unit_label (units of the 5 SSVEP classes, two units per class)."""
  cfg = cfg_with(k=k)
  names = BIN if k == 2 else [f"c{i}" for i in range(k)]
  mid = "baseline" if k == 2 else "f1/raw/Shrinkage-LDA lsqr"
  ps = []
  for rep in range(30):
    sess, values = noise_session(1000 + rep, per_unit=8, scheme=scheme, k=k, n_units=6 if k == 2 else 10)
    ul = np.concatenate(values) if scheme == "unit_label" else None
    splits = fo.fold_splits(sess["unit_uid"], fo.assign_unit_folds(sess["unit_file"], 3, SEED_FOLDS, unit_label=ul), 3)
    obs, _ = evl.per_stratum_ba(sess, sess["y"], splits, lambda: cl.make_method(mid, cfg), names)
    if scheme == "unit_label":
      shuf, _ = evl.draw_shuffles_constrained(values, 19, SEED_PERM + rep,
                                              evl.every_class_in_training(sess, splits, scheme, k))
    else:
      shuf = evl.draw_shuffles(values, 19, SEED_PERM + rep)
    null = evl.permutation_null(sess, splits, [mid], cl.make_method, cfg, scheme, names, shuf, 1, 8)[0, :, :3]
    nd = [evl.n_distinct_shuffles(v) for v in values]
    rows = evl.per_stratum_tests(obs, null, nd, 0.05, 95.0, "linear")
    ps += [r["perm_p_monte_carlo"] for r in rows]
    assert not any(r["above_chance_holm"] for r in rows)
  ps = np.array(ps)
  assert int(np.sum(ps <= 0.05)) <= int(stats.binom.ppf(0.9999, len(ps), 0.05))
  assert ps.mean() > 0.45 and ps.min() >= 1 / 20 - 1e-12


def test_unit_label_scheme_refuses_labels_that_vary_within_a_unit(world):
  with pytest.raises(ValueError, match="vary within the unit"):
    evl.unit_values(world["sess"], "unit_label")


def test_label_balanced_folds_keep_every_class_in_training_and_missing_class_is_refused():
  """Known answer: 3 strata x 10 units, 5 classes (2 units per class per stratum), 5 folds: with
  unit_label the 6 units of every class cycle through all 5 folds (at most 2 per fold), so every
  training set holds every class; per stratum the per-fold counts still differ by at most 1.
  Without unit_label (P300 dealing) the same seed can leave a class out of a training set, and
  cv_predict then refuses with a message naming the class (buggy variant: LDA with explicit
  5-class priors would fail on a shape error instead)."""
  ul = np.tile(np.repeat(np.arange(5), 2), 3)
  us = np.repeat(np.arange(3), 10)
  for seed in range(20):
    fo_l = fo.assign_unit_folds(us, 5, seed, unit_label=ul)
    for k in range(5):
      assert set(ul[fo_l != k].tolist()) == set(range(5))
      assert max(np.bincount(ul[fo_l == k], minlength=5)) <= 2
    for f in range(3):
      c = np.bincount(fo_l[us == f], minlength=5)
      assert c.max() - c.min() <= 1
  y = np.repeat(ul, 3)
  uid = np.repeat(np.arange(30), 3)
  bad = np.where(ul == 4, 0, np.arange(30) % 5)            # every class-4 unit in fold 0
  splits = fo.fold_splits(uid, bad, 5)
  X = np.random.default_rng(0).normal(size=(90, 2, 5))
  with pytest.raises(ValueError, match="lacks class"):
    evl.cv_predict(X, y, splits, lambda: cl.make_method("f1/raw/Shrinkage-LDA lsqr", cfg_with(k=5)),
                   [f"c{i}" for i in range(5)])


def test_constrained_draws_equal_plain_draws_when_everything_is_admissible_and_redraw_otherwise():
  """Known answer: accept-all gives exactly draw_shuffles (0 redraws); an accept that rejects the
  identity-like draws redraws from the same generator; an inadmissible observed labelling raises."""
  t = [np.array([0, 1, 2, 3, 4]), np.array([4, 3, 2, 1, 0])]
  a = evl.draw_shuffles(t, 10, 3)
  b, r = evl.draw_shuffles_constrained(t, 10, 3, lambda d: True)
  assert all(np.array_equal(x, y) for x, y in zip(a, b)) and r.sum() == 0
  c, r2 = evl.draw_shuffles_constrained(t, 10, 3, lambda d: d[0][0] != 1)   # observed has 0 first: admissible
  assert np.all(c[0][:, 0] != 1)
  first_rejected = a[0][:, 0] == 1                    # the first draw of p is the plain draw
  assert np.all(r2[first_rejected] >= 1) and np.all(r2[~first_rejected] == 0)
  assert all(np.array_equal(c[f][~first_rejected], a[f][~first_rejected]) for f in range(2))
  with pytest.raises(ValueError, match="not admissible"):
    evl.draw_shuffles_constrained(t, 3, 3, lambda d: d[0][0] != 0 or d[1][0] != 4)
