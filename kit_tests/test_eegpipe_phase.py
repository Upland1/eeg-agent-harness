"""Known-answer tests for eegpipe.phase, connectivity and graphstats, moved from the P300 project
(tests @ d833264, ``tests/test_ssvep_methods_step3.py`` sections 1-4), plus a 5-class contrast test.
The epoch-level synthetic world is the P300 one (8 channels, 307-sample raw epochs at 256 Hz)."""

import copy
import json
import sys
from pathlib import Path

import numpy as np
import pytest
from scipy import stats

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
from eegpipe import classical as cl  # noqa: E402
from eegpipe import connectivity as cn  # noqa: E402
from eegpipe import evaluate as evl  # noqa: E402
from eegpipe import folds as fo  # noqa: E402
from eegpipe import graphstats as gs  # noqa: E402
from eegpipe import phase as ph  # noqa: E402

PROFILE = json.loads((TOOLS / "eegpipe" / "profiles" / "erp.json").read_text())
FS = 256.0
N_CH, T, N_NODE = 8, 307, 51
DELTA, THETA = [1.0, 4.0], [4.0, 8.0]
SEED_PERM, SEED_SUB, SEED_FOLDS = 20261105, 20261112, 20261107
OBS_KEY = 4294967295
TT = np.arange(T) / FS
BIN = ["nontarget", "target"]


def f3_section(n_perm=20, repeats=10):
  return {
    "enabled": True, "window_s": [-0.2, 1.0], "window_rounding": "round", "window_samples": T, "nfft": T,
    "spectrum": {"detrend": "constant", "window": "hann", "window_fftbins": True},
    "bands": {"delta": list(DELTA), "theta": list(THETA)},
    "classification": {
      "primary": "delta", "order": ["delta", "delta_nosub", "delta_sin", "theta"],
      "variants": {"delta": {"bands": ["delta"], "subtract_template": True, "components": ["cos", "sin"]},
                   "delta_nosub": {"bands": ["delta"], "subtract_template": False, "components": ["cos", "sin"]},
                   "delta_sin": {"bands": ["delta"], "subtract_template": True, "components": ["sin"]},
                   "theta": {"bands": ["theta"], "subtract_template": True, "components": ["cos", "sin"]}},
      "model": "Shrinkage-LDA lsqr", "scaler": {"class": "StandardScaler", "with_mean": True, "with_std": True}},
    "condition_level": {
      "enabled": True, "bands": ["delta", "theta"], "n_permutations": n_perm, "permutation_seed": SEED_PERM,
      "subsample_seed": SEED_SUB, "n_subsample_repeats": repeats, "observed_key": OBS_KEY, "contrast": [1, 0],
      "min_trials_per_class": 2, "fdr": {"method": "benjamini_hochberg", "alpha": 0.05},
      "nbs": {"threshold": 3.0, "directions": ["a_gt_b", "b_gt_a"], "alpha": 0.05}},
  }


def base_cfg(**kw):
  return {"fs_hz": FS, "f1": copy.deepcopy(PROFILE["f1"]), "f3": f3_section(**kw)}


def transformer(bands=(DELTA,), sub=True, comps=("cos", "sin")):
  return ph.PhaseFeatures(fs=FS, bands=[list(b) for b in bands], subtract_template=sub, components=list(comps),
                          window="hann", window_fftbins=True, detrend="constant", nfft=T)


def world(seed, n_files=3, units=4, rounds=10, n_codes=4, couple=None, couple_all=None, erp_amp=0.0):
  """P300 step-3 world: raw epochs (n, 8, 307) white noise; ``couple`` = (channels, lags, amp)
  induced 2.5 Hz coupling (random phase per epoch) in TARGET epochs only; ``couple_all`` in every
  epoch. Unit targets of a file: a permutation of 1..n_codes; label = code == target."""
  rng = np.random.default_rng(seed)
  post = np.array([0, 0, 1, 1, 1, 1, 1, 1], float)
  bump = np.exp(-0.5 * ((np.arange(N_NODE) - 22) / 3.0) ** 2)
  Xr, Xn, y, uid, fidx, code, uloc = [], [], [], [], [], [], []
  targets, ufile, u = [], [], 0
  for f in range(n_files):
    xs = rng.permutation(np.arange(1, n_codes + 1))[:units]
    targets.append(np.array(xs))
    for b, x in enumerate(xs):
      for c in np.concatenate([rng.permutation(np.arange(1, n_codes + 1)) for _ in range(rounds)]):
        e = rng.normal(size=(N_CH, T))
        n_ = rng.normal(size=(N_CH, N_NODE))
        for spec, on in ((couple, c == x), (couple_all, True)):
          if spec is not None and on:
            chans, lags, amp = spec
            a = rng.uniform(0, 2 * np.pi)
            for ch, lag in zip(chans, lags):
              e[ch] += amp * np.cos(2 * np.pi * 2.5 * TT + a - lag)
        if c == x:
          n_ += erp_amp * np.outer(post, bump)
        Xr.append(e), Xn.append(n_), y.append(int(c == x)), uid.append(u), fidx.append(f)
        code.append(int(c)), uloc.append(b)
      ufile.append(f)
      u += 1
  sess = {"y": np.array(y), "unit_uid": np.array(uid), "file_idx": np.array(fidx), "code": np.array(code),
          "unit_local": np.array(uloc), "unit_file": np.array(ufile)}
  return np.stack(Xr), np.stack(Xn), sess, targets


def labels_fn(sess, targets, n_perm, seed=SEED_PERM):
  sh = evl.draw_shuffles(targets, n_perm, seed)
  return (lambda p: evl.labels_for(sess, [s[p] for s in sh], "unit_target")), sh


def folds_of(sess, n_folds=4):
  return fo.fold_splits(sess["unit_uid"], fo.assign_unit_folds(sess["unit_file"], n_folds, SEED_FOLDS), n_folds)


# ------------------------------------------------------------------ spectra and phasors
def test_band_bins_closed_rule_at_307_samples():
  f = np.fft.rfftfreq(T, 1 / FS)
  assert ph.band_bins(T, FS, DELTA).tolist() == [2, 3, 4]
  assert ph.band_bins(T, FS, THETA).tolist() == [5, 6, 7, 8, 9]
  assert np.allclose(f[[2, 3, 4]], [512 / 307, 768 / 307, 1024 / 307], rtol=0, atol=1e-12)


@pytest.mark.parametrize("lag", [-2.0, -0.5, 0.3, 1.2, 2.9])
def test_phasor_recovers_a_planted_lag_in_delta_only(lag):
  rng = np.random.default_rng(11)
  X = 0.3 * rng.normal(size=(200, N_CH, T))
  a = rng.uniform(0, 2 * np.pi, size=200)[:, None]
  X[:, 0] += np.cos(2 * np.pi * 2.5 * TT + a)
  X[:, 1] += np.cos(2 * np.pi * 2.5 * TT + a - lag)
  pf = transformer((DELTA, THETA)).fit(X)
  p = pf.phasors(X)
  m = p[:, 0, 0].mean()
  assert abs(np.angle(m) - lag) < 0.02 and abs(m) > 0.99
  F = pf.transform(X).reshape(200, 28, 2, 2)
  assert np.mean(F[:, 0, 0, 0]) == pytest.approx(np.cos(lag), abs=0.02)
  assert np.mean(F[:, 0, 0, 1]) == pytest.approx(np.sin(lag), abs=0.02)
  assert abs(p[:, 0, 1].mean()) < 0.25


def test_edge_tensor_layout_conjugate_diagonal_and_flat_order():
  rng = np.random.default_rng(3)
  X = rng.normal(size=(5, N_CH, T))
  pf = transformer((DELTA, THETA)).fit(X)
  F = pf.transform(X).reshape(5, 28, 2, 2)
  E = pf.edge_tensor(X).reshape(5, N_CH, N_CH, 2, 2)
  iu, ju = np.triu_indices(N_CH, 1)
  for k, (i, j) in enumerate(zip(iu, ju)):
    assert np.array_equal(E[:, i, j], F[:, k])
    assert np.array_equal(E[:, j, i, :, 0], F[:, k, :, 0]) and np.array_equal(E[:, j, i, :, 1], -F[:, k, :, 1])
  for i in range(N_CH):
    assert np.all(E[:, i, i, :, 0] == 1.0) and np.all(E[:, i, i, :, 1] == 0.0)
  assert np.array_equal(transformer((DELTA,), comps=("sin",)).fit(X).transform(X), F[:, :, 0, 1])


# ------------------------------------------------------------------ debiased wPLI
def _pairwise_dwpli(im):
  num = den = 0.0
  for a in range(len(im)):
    for b in range(len(im)):
      if a != b:
        num += im[a] * im[b]
        den += abs(im[a]) * abs(im[b])
  return num / den


def _delta_im(X):
  return ph.band_cross(ph.spectra(X, "hann", True, "constant")[..., ph.band_bins(T, FS, DELTA)]).imag


def test_debiased_wpli_zero_for_noise_one_for_consistent_lag_and_equals_pairwise_definition():
  rng = np.random.default_rng(5)
  im = _delta_im(rng.normal(size=(15, N_CH, T)))
  for e in (0, 7, 27):
    assert cn.debiased_wpli(im)[e] == pytest.approx(_pairwise_dwpli(im[:, e]), abs=1e-12)
  dw, w = [], []
  for k in range(60):
    imk = _delta_im(np.random.default_rng(100 + k).normal(size=(20, N_CH, T)))
    dw.append(cn.debiased_wpli(imk)), w.append(cn.wpli(imk))
  assert abs(np.mean(dw)) < 0.03 and np.mean(w) > 0.15
  X = 0.3 * rng.normal(size=(40, N_CH, T))
  a = rng.uniform(0, 2 * np.pi, size=40)[:, None]
  X[:, 0] += np.cos(2 * np.pi * 2.5 * TT + a)
  X[:, 1] += np.cos(2 * np.pi * 2.5 * TT + a - np.pi / 4)
  assert cn.debiased_wpli(_delta_im(X))[0] > 0.95
  assert cn.dwpli_from_sums(np.zeros(2), np.zeros(2), np.zeros(2)).tolist() == [0.0, 0.0]


# ------------------------------------------------------------------ label-free template
class _ClassTemplate(ph.PhaseFeatures):
  """Buggy variant: subtracts a class-specific mean (needs labels)."""

  def fit(self, X, y=None):
    super().fit(X, y)
    self.y_ = None if y is None else np.asarray(y)
    self.means_ = {c: np.asarray(X)[self.y_ == c].mean(0) for c in (0, 1)} if y is not None else None
    return self

  def transform(self, X):
    X = np.asarray(X, dtype=np.float64).copy()
    for c in (0, 1):
      X[self.y_ == c] -= self.means_[c] - self.template_
    return super().transform(X)


def test_label_free_template_equals_training_mean_and_ignores_labels():
  Xr, _, sess, _ = world(1, couple=([0, 1], [0.0, 0.7], 1.0))
  y = sess["y"]
  tr, te = np.arange(0, 300), np.arange(300, len(y))
  ys = np.random.default_rng(0).permutation(y[tr])
  fits = [transformer().fit(Xr[tr], yy) for yy in (y[tr], ys, None)]
  for f in fits:
    assert np.array_equal(f.template_, Xr[tr].mean(0)) and f.n_fit_epochs_ == 300
    assert np.array_equal(f.transform(Xr[te]), fits[0].transform(Xr[te]))
  bad_a = _ClassTemplate(**transformer().get_params()).fit(Xr[tr], y[tr])
  bad_b = _ClassTemplate(**transformer().get_params()).fit(Xr[tr], ys)
  assert not np.allclose(bad_a.transform(Xr[tr]), bad_b.transform(Xr[tr]))
  assert np.array_equal(transformer(sub=False).fit(Xr[tr]).template_, np.zeros((N_CH, T)))


def test_f3_folds_fit_the_template_on_training_epochs_only_and_never_read_test_labels():
  Xr, _, sess, _ = world(2)
  y = sess["y"]
  cfg = base_cfg()
  for _, tr, te in folds_of(sess):
    est = ph.make_f3(ph.F3_PREFIX + "delta", cfg).fit(Xr[tr], y[tr])
    tpl = est.named_steps["phase"].template_
    assert np.array_equal(tpl, Xr[tr].mean(0)) and not np.allclose(tpl, Xr.mean(0))
    X2 = Xr.copy()
    X2[te] *= 1000.0
    est2 = ph.make_f3(ph.F3_PREFIX + "delta", cfg).fit(X2[tr], y[tr])
    assert np.array_equal(est2.named_steps["phase"].transform(X2[tr]), est.named_steps["phase"].transform(Xr[tr]))
    y2 = y.copy()
    y2[te] = 7
    est3 = ph.make_f3(ph.F3_PREFIX + "delta", cfg).fit(Xr[tr], y2[tr])
    assert np.array_equal(est3.predict(Xr[te]), est.predict(Xr[te]))


def test_f3_primary_pipeline_tables_and_planted_phase_difference_is_classified():
  cfg = base_cfg()
  ids = ph.f3_method_ids(cfg)
  assert ids[0] == ph.primary_f3_id(cfg) == "f3/phase_features/delta"
  assert all("phase_features" in m and "connectivity" not in m for m in ids)
  est = ph.make_f3(ids[0], cfg)
  assert [n for n, _ in est.steps] == ["phase", "scaler", "model"]
  lda = est.named_steps["model"]
  assert lda.solver == "lsqr" and lda.shrinkage == "auto" and np.array_equal(lda.priors, [0.5, 0.5])
  Xr, _, sess, _ = world(4, couple=([0, 1], [0.0, np.pi / 2], 1.5))
  splits = folds_of(sess)
  pred = evl.cv_predict(Xr, sess["y"], splits, lambda: ph.make_f3("f3/phase_features/delta", cfg), BIN)[0]
  assert evl.class_metrics(sess["y"], pred, BIN)["ba"] >= 0.80
  pred_t = evl.cv_predict(Xr, sess["y"], splits, lambda: ph.make_f3("f3/phase_features/theta", cfg), BIN)[0]
  assert evl.class_metrics(sess["y"], pred_t, BIN)["ba"] <= 0.62
  with pytest.raises(ValueError):
    ph.make_f3("f3/phase_features/nope", cfg)


# ------------------------------------------------------------------ condition level
def test_spectral_class_subtraction_equals_time_domain_subtraction():
  Xr, _, sess, _ = world(6, couple=([2, 5], [0.0, 1.0], 1.0))
  y, fi = sess["y"], sess["file_idx"]
  Zb = cn.band_spectra(Xr, [DELTA], FS, "hann", True, "constant")[0]
  got = cn.class_residual_cross(Zb, y, fi)
  R = Xr.copy()
  for f in np.unique(fi):
    for c in (0, 1):
      m = (fi == f) & (y == c)
      R[m] -= Xr[m].mean(0)
  ref = ph.band_cross(ph.spectra(R, "hann", True, "constant")[..., ph.band_bins(T, FS, DELTA)])
  assert np.allclose(got, ref, rtol=1e-9, atol=1e-9 * np.abs(ref).max())


def test_per_file_class_mean_removes_a_file_specific_evoked_response():
  Xr, _, sess, _ = world(41)
  y, fi = sess["y"], sess["file_idx"]
  m = (y == 1) & (fi == 0)
  Xr[m, 0] += 2.0 * np.cos(2 * np.pi * 2.5 * TT)
  Xr[m, 1] += 2.0 * np.cos(2 * np.pi * 2.5 * TT - 1.0)
  Z = cn.band_spectra(Xr, [DELTA], FS, "hann", True, "constant")[0]
  assert abs(cn.debiased_wpli(cn.class_residual_cross(Z, y, fi).imag[y == 1])[0]) < 0.1
  assert cn.debiased_wpli(cn.class_residual_cross(Z, y, np.zeros_like(fi)).imag[y == 1])[0] > 0.3


def _reference_statistic(Xr, y, unit_uid, key, repeats, band, file_idx):
  R = Xr.copy()
  for f in np.unique(file_idx):
    for c in (0, 1):
      m = (file_idx == f) & (y == c)
      R[m] -= Xr[m].mean(0)
  im = ph.band_cross(ph.spectra(R, "hann", True, "constant")[..., ph.band_bins(T, FS, band)]).imag
  t_idx, n_idx = np.flatnonzero(y == 1), np.flatnonzero(y == 0)
  dt = np.array([_pairwise_dwpli(im[t_idx, e]) for e in range(28)])
  dn = np.zeros(28)
  for r in range(repeats):
    sub = n_idx[np.random.default_rng([SEED_SUB, key, r]).choice(n_idx.size, size=t_idx.size, replace=False)]
    dn += np.array([_pairwise_dwpli(im[sub, e]) for e in range(28)]) / repeats
  d = []
  for b in np.unique(unit_uid):
    tb, nb = t_idx[unit_uid[t_idx] == b], n_idx[unit_uid[n_idx] == b]
    d.append([_pairwise_dwpli(im[tb, e]) - _pairwise_dwpli(im[nb, e]) for e in range(28)])
  d = np.array(d)
  return dt - dn, d.mean(0) / (d.std(0, ddof=1) / np.sqrt(len(d)))


def test_per_class_subtraction_and_subsampling_are_recomputed_inside_each_permutation():
  """Known answer (1e-9): observed and permuted statistics equal an independent
  re-implementation that subtracts the class means with THAT labelling and draws subsample r with
  default_rng([20261112, key, r]); the buggy variant (observed class means subtracted once)
  differs."""
  Xr, _, sess, targets = world(7, couple=([0, 1, 2], [0.0, 0.5, 1.0], 0.8))
  n_perm, rep = 4, 3
  cfg = base_cfg(n_perm=n_perm, repeats=rep)
  labels_of, _ = labels_fn(sess, targets, n_perm)
  fi = sess["file_idx"]
  res = cn.condition_level(Xr, sess["y"], sess["unit_uid"], labels_of, n_perm, FS, cfg, fi)
  d_obs, t_obs = _reference_statistic(Xr, sess["y"], sess["unit_uid"], OBS_KEY, rep, DELTA, fi)
  assert np.allclose(res["observed"]["diff"][0], d_obs, atol=1e-9) and np.allclose(res["observed"]["t"][0], t_obs, atol=1e-9)
  for p in range(n_perm):
    yp = labels_of(p)
    d_p, t_p = _reference_statistic(Xr, yp, sess["unit_uid"], p, rep, DELTA, fi)
    assert np.allclose(res["null_diff"][p, 0], d_p, atol=1e-9) and np.allclose(res["null_t"][p, 0], t_p, atol=1e-9)
  Z0 = cn.band_spectra(Xr, [DELTA], FS, "hann", True, "constant")[0]
  yp = labels_of(0)
  assert not np.allclose(cn.debiased_wpli(cn.class_residual_cross(Z0, sess["y"], fi).imag[yp == 1]),
                         cn.debiased_wpli(cn.class_residual_cross(Z0, yp, fi).imag[yp == 1]))


def test_observed_subsample_key_never_collides_with_a_permutation_key():
  a = np.random.default_rng([SEED_SUB, 5]).integers(0, 2 ** 31, 4)
  b = np.random.default_rng([SEED_SUB, 5, 0]).integers(0, 2 ** 31, 4)
  assert np.array_equal(a, b)
  obs = cn.subsample_matrix(400, 100, 3, SEED_SUB, OBS_KEY)
  for p in range(1000):
    assert not np.array_equal(cn.subsample_matrix(400, 100, 1, SEED_SUB, p)[0], obs[0])


def test_bh_matches_scipy_and_nbs_components_and_p_on_planted_t_maps():
  rng = np.random.default_rng(0)
  for _ in range(200):
    p = rng.uniform(size=56) ** rng.uniform(0.3, 3)
    assert np.array_equal(gs.benjamini_hochberg(p, 0.05), stats.false_discovery_control(p, method="bh") <= 0.05)
  iu, ju = np.triu_indices(N_CH, 1)
  idx = {(int(i), int(j)): k for k, (i, j) in enumerate(zip(iu, ju))}
  t = np.zeros(28)
  for e in ((0, 1), (1, 2), (0, 2)):
    t[idx[e]] = 5.0
  t[idx[(5, 6)]] = 4.0
  null = []
  for size in (0, 1, 2, 3):
    z = np.zeros(28)
    for e in [(0, 1), (1, 2), (2, 3)][:size]:
      z[idx[e]] = 4.0
    null += [z] * 25
  for direction in ("a_gt_b", "target_gt_nontarget"):
    r = gs.nbs(t, np.array(null), 3.0, N_CH, direction)
    comps = sorted(r["components"], key=lambda c: -c["size"])
    assert [c["size"] for c in comps] == [3, 1]
    assert comps[0]["p"] == pytest.approx(26 / 101) and comps[1]["p"] == pytest.approx(76 / 101)
  assert gs.nbs(t, np.array(null), 3.0, N_CH, "b_gt_a")["components"] == []
  with pytest.raises(ValueError):
    gs.nbs(t, np.array(null), 3.0, N_CH, "up")


def test_fdr_and_nbs_find_a_planted_target_only_network():
  """Known answer (P300 step3): induced coupling among channels 0-3 in class-a epochs only, 300
  unit permutations: the delta FDR rejections are exactly the 6 clique edges (at most 1 other
  rejection); one significant NBS component, delta, a_gt_b, size 6, the clique."""
  Xr, _, sess, targets = world(21, couple=([0, 1, 2, 3], [0.0, 0.6, 1.2, 1.8], 1.0))
  n_perm = 300
  labels_of, _ = labels_fn(sess, targets, n_perm)
  res = cn.condition_level(Xr, sess["y"], sess["unit_uid"], labels_of, n_perm, FS, base_cfg(n_perm=n_perm, repeats=10),
                           sess["file_idx"])
  iu, ju = np.triu_indices(N_CH, 1)
  clique = {k for k, (i, j) in enumerate(zip(iu, ju)) if i < 4 and j < 4}
  rej = {(r["band"], r["pair"]) for r in res["edges"] if r["fdr_reject"]}
  assert {k for b, k in rej if b == "delta"} == clique
  assert len([1 for b, k in rej if b != "delta" or k not in clique]) <= 1
  sig = [r for r in res["nbs"] if r["significant"]]
  assert len(sig) == 1 and sig[0]["band"] == "delta" and sig[0]["direction"] == "a_gt_b" and sig[0]["size_edges"] == 6
  assert res["summary"]["n_tests_fdr"] == 56 and res["summary"]["n_units_used_observed"] == 12


def test_condition_level_type_one_on_null_data():
  Xr, _, sess, targets = world(31, couple_all=([0, 1, 2], [0.0, 0.6, 1.2], 1.0))
  n_perm = 200
  labels_of, _ = labels_fn(sess, targets, n_perm)
  res = cn.condition_level(Xr, sess["y"], sess["unit_uid"], labels_of, n_perm, FS, base_cfg(n_perm=n_perm, repeats=10),
                           sess["file_idx"])
  assert res["summary"]["n_edges_fdr"] == 0 and not any(r["significant"] for r in res["nbs"])
  assert abs(np.mean([r["p_two_sided"] for r in res["edges"]]) - 0.5) <= 0.12


def test_five_class_contrast_uses_only_the_two_declared_classes():
  """Known answer (5 classes, labels constant within a unit, 6 units per class per file): coupling
  planted in class-3 units only; contrast (3, 1) finds it (delta clique edges rejected by FDR), contrast (2, 1) finds
  nothing; NBS paired by unit is reported as not applicable (no unit holds both classes); epochs of other classes never enter (n_a + n_b = the epochs of the two classes);
  a permuted labelling that brings another class onto the contrast's epochs is refused."""
  rng = np.random.default_rng(8)
  n_units, per_unit = 60, 8                 # 2 files x 30 units, 6 units per class per file:
  ulab = np.tile(np.arange(5), 12)          # C(12, 6)^2 distinct contrast labellings (2 per file would give 36)
  X, y, uid, fidx = [], [], [], []
  for u in range(n_units):
    for _ in range(per_unit):
      e = rng.normal(size=(N_CH, T))
      if ulab[u] == 3:
        a = rng.uniform(0, 2 * np.pi)
        for ch, lag in zip([0, 1, 2], [0.0, 0.7, 1.4]):
          e[ch] += 1.0 * np.cos(2 * np.pi * 2.5 * TT + a - lag)
      X.append(e), y.append(int(ulab[u])), uid.append(u), fidx.append(u // 30)
  X, y, uid, fidx = np.stack(X), np.array(y), np.array(uid), np.array(fidx)
  sess = {"y": y, "unit_local": uid % 30, "file_idx": fidx, "unit_file": np.repeat([0, 1], 30)}
  vals = [ulab[:30], ulab[30:]]

  def run(contrast, n_perm=200):
    cfg = base_cfg(n_perm=n_perm, repeats=5)
    cfg["f3"]["condition_level"]["contrast"] = list(contrast)
    keep = [np.isin(v, contrast) for v in vals]
    sub = [v[k] for v, k in zip(vals, keep)]
    sh = evl.draw_shuffles(sub, n_perm, SEED_PERM)

    def labels_of(p):
      full = [v.copy() for v in vals]
      for f in range(2):
        full[f][keep[f]] = sh[f][p]
      return evl.labels_for(sess, full, "unit_label")
    return cn.condition_level(X, y, uid, labels_of, n_perm, FS, cfg, fidx)
  r31 = run((3, 1), n_perm=1000)            # min p 1/1001 < BH threshold 0.05 * 3 / 56 for the 3 edges
  assert r31["summary"]["n_a"] + r31["summary"]["n_b"] == int(np.isin(y, [3, 1]).sum())
  assert r31["summary"]["n_units_used_observed"] == 0 and r31["summary"]["nbs_applicable"] is False
  assert r31["nbs"] == []                   # no unit holds both classes: NBS paired by unit is not applicable
  delta_rej = {r["pair"] for r in r31["edges"] if r["fdr_reject"] and r["band"] == "delta"}
  assert {0, 1, 7} <= delta_rej                                    # pairs (0,1), (0,2), (1,2)
  assert run((2, 1))["summary"]["n_edges_fdr"] == 0
  cfg_s = base_cfg(n_perm=50, repeats=2)
  cfg_s["f3"]["condition_level"]["contrast"] = [3, 1]
  cfg_s["f3"]["condition_level"]["nbs"]["pair_by"] = "stratum"
  rs = cn.condition_level(X, y, uid, lambda p: y, 50, FS, cfg_s, fidx)
  assert rs["summary"]["nbs_applicable"] is True and rs["summary"]["n_units_used_observed"] == 2
  cfg = base_cfg(n_perm=1, repeats=2)
  cfg["f3"]["condition_level"]["contrast"] = [3, 1]
  with pytest.raises(ValueError, match="outside the contrast"):
    cn.condition_level(X, y, uid, lambda p: (y + 1) % 5, 1, FS, cfg, fidx)
