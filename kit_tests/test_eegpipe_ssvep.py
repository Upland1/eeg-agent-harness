"""Known-answer tests for eegpipe.ssvep (FBCCA, FBCSP, filter banks), moved from
``mas-ssvep-eeg-xai`` v1.0.4 (``tests/test_p05_known_answer.py`` l.39-316, 390;
``tests/test_p20_independent_known_answer.py`` l.250-276), with the [M] constants (5 target
frequencies, fs 250, 7 channels) passed as parameters; plus 5-class end-to-end tests under the
eegpipe protocol (label-balanced grouped folds)."""

import copy
import json
import sys
from pathlib import Path

import numpy as np
import pytest
from scipy.linalg import eigh, subspace_angles
from scipy.signal import butter, cheby1, filtfilt, freqz, sosfiltfilt

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
import eegpipe.ssvep  # noqa: E402,F401  (registers the feature steps)
from eegpipe import classical as cl  # noqa: E402
from eegpipe import dataset as ds  # noqa: E402
from eegpipe import epochs as ep  # noqa: E402
from eegpipe import evaluate as evl  # noqa: E402
from eegpipe import folds as fo  # noqa: E402
from eegpipe.ssvep import fbcca as fb  # noqa: E402
from eegpipe.ssvep import fbcsp as csp  # noqa: E402
from eegpipe.ssvep import filterbank as fbank  # noqa: E402
from eegpipe.testing import synth  # noqa: E402

FS, T = 250.0, 256
t = np.arange(T) / FS
M_FREQS = [24.0, 20.0, 15.0, 10.9091, 8.5714]     # [M] TARGET_FREQS (now a setting)
W3 = fb.weights(3)
CHEB_BANK = [{"kind": "cheby1", "order": 4, "ripple_db": 3.0, "band_hz": [lo, 90.0]} for lo in (6.0, 14.0, 22.0)]
CSP_BANDS = [(7, 12), (13, 17), (18, 26), (27, 36), (38, 52)]
BUTTER_BANK = [{"kind": "butter", "order": 4, "band_hz": list(b)} for b in CSP_BANDS]
PROFILE = json.loads((TOOLS / "eegpipe" / "profiles" / "erp.json").read_text())


# ------------------------------------------------------------------ references, Chebyshev bank
def test_reference_signals_closed_form():
  f = 8.5714
  r = fb.reference_signals(f, FS, T, 3)
  exp = np.stack([g(2 * np.pi * h * f * t) for h in (1, 2, 3) for g in (np.sin, np.cos)])
  assert r.shape == (6, T) and np.allclose(r, exp, atol=1e-12)
  assert fb.weights(3).tolist() == pytest.approx([1.25, 1 + 2 ** -1.25 - 0.75, 3 ** -1.25 + 0.25])
  assert fb.weights(3) == pytest.approx([1.25, 0.6704, 0.5033], abs=1e-4)


def _check_chebyshev(sos_list):
  """Order 4, 3 dB ripple, edges [low, 90]: edge gain 10^(-3/20) (+-5e-4), 4 ripple maxima, ~0 at 2 Hz."""
  for sos, low in zip(sos_list, (6.0, 14.0, 22.0)):
    assert sos.shape == (4, 6)
    f = np.linspace(low, 90.0, 4000)
    g = np.abs(freqz(*_ba(sos), worN=f, fs=FS)[1])
    assert abs(g[0] - 10 ** (-3 / 20)) < 5e-4 and abs(g[-1] - 10 ** (-3 / 20)) < 5e-4
    assert int(((g[1:-1] > g[:-2]) & (g[1:-1] > g[2:])).sum()) == 4
    assert abs(freqz(*_ba(sos), worN=[2.0], fs=FS)[1][0]) < 0.01


def _ba(sos):
  from scipy.signal import sos2tf
  return sos2tf(sos)


def test_chebyshev_bank_design_and_mutants():
  _check_chebyshev([fbank.design(b, FS) for b in CHEB_BANK])
  for mutant in ({"kind": "butter", "order": 4}, {"kind": "cheby1", "order": 3, "ripple_db": 3.0},
                 {"kind": "cheby1", "order": 4, "ripple_db": 1.0}):
    with pytest.raises(AssertionError):
      _check_chebyshev([fbank.design({**mutant, "band_hz": [lo, 90.0]}, FS) for lo in (6.0, 14.0, 22.0)])


# ------------------------------------------------------------------ FBCCA
def cca_ref(x, f, fs, n_harm=3):
  tt = np.arange(x.shape[0]) / fs
  y = np.stack([fn(2 * np.pi * h * f * tt) for h in range(1, n_harm + 1) for fn in (np.sin, np.cos)], 1)
  return float(np.cos(subspace_angles(x - x.mean(0), y - y.mean(0)).min()))


def test_fbcca_matches_independent_principal_angle_cca():
  """Known answer ([M] P20): scores equal sum_b w_b r_b^2 with r from principal angles (1e-10), are in
  [0, sum w], and one epoch's score does not depend on the others."""
  rng = np.random.default_rng(11)
  for TT in (128, 256, 384):
    bands = rng.normal(size=(6, 3, 5, TT))
    got = fb.fbcca_scores(bands, fb.reference_bases(FS, TT, M_FREQS, 3), W3, chunk=2)
    ref = np.array([[sum(W3[b] * cca_ref(bands[i, b].T, f, FS) ** 2 for b in range(3)) for f in M_FREQS]
                    for i in range(len(bands))])
    assert np.max(np.abs(got - ref)) < 1e-10 and got.min() >= 0 and got.max() <= W3.sum() + 1e-12
    assert np.allclose(fb.fbcca_scores(bands[3:4], fb.reference_bases(FS, TT, M_FREQS, 3), W3), got[3:4], atol=1e-12)


def test_fbcca_planted_tone_wins_dc_is_ignored_and_wrong_fs_loses_margin():
  """Known answers: a planted tone at each target frequency wins; +1000 DC changes nothing (1e-8);
  scoring a 250 Hz recording with references built at 256 Hz (PF-04) lowers the 24 Hz score by
  >= 25 %."""
  rng = np.random.default_rng(5)
  bases = fb.reference_bases(FS, T, M_FREQS, 3)
  for k, f in enumerate(M_FREQS):
    x = np.stack([np.sin(2 * np.pi * f * t + 0.5 * c) + 0.4 * rng.normal(size=T) for c in range(4)])
    bands = np.stack([x, x, x])[None]
    s = fb.fbcca_scores(bands, bases, W3)
    assert s.argmax() == k
    assert np.allclose(fb.fbcca_scores(bands + 1000.0, bases, W3), s, atol=1e-8)
  x = 8 * np.sin(2 * np.pi * 24 * t + 1.0)[None] * np.ones((7, 1)) + rng.normal(0, 1, (7, T))
  bands = np.stack([x] * 3)[None]
  s250 = fb.fbcca_scores(bands, fb.reference_bases(250.0, T, M_FREQS, 3), W3)[0, 0]
  s256 = fb.fbcca_scores(bands, fb.reference_bases(256.0, T, M_FREQS, 3), W3)[0, 0]
  assert s256 < 0.75 * s250


def test_fbcca_response_multiple_two_detects_a_checkerboard_response():
  """Known answer (PF-39): a response at 2 f (pattern reversal) is recovered with
  response_multiple 2 (argmax = the planted target); with response_multiple 1 and H = 1 the true
  target's score for a noiseless 2 f tone is < 0.05 (no reference at 2 f), and > 0.95 of the
  maximum sum(w) with response_multiple 2."""
  freqs = [6.0, 7.5, 8.57, 10.0]
  rng = np.random.default_rng(3)
  for k, f in enumerate(freqs):
    x = np.stack([np.sin(2 * np.pi * 2 * f * t + 0.3 * c) + 0.3 * rng.normal(size=T) for c in range(4)])
    bands = np.stack([x] * 3)[None]
    assert fb.fbcca_scores(bands, fb.reference_bases(FS, T, freqs, 2, response_multiple=2), W3).argmax() == k
  x = np.stack([np.sin(2 * np.pi * 15.0 * t + 0.3 * c) for c in range(4)])     # 2 x 7.5 Hz (target 1)
  bands = np.stack([x] * 3)[None]
  assert fb.fbcca_scores(bands, fb.reference_bases(FS, T, freqs, 1), W3)[0, 1] < 0.05
  assert fb.fbcca_scores(bands, fb.reference_bases(FS, T, freqs, 1, response_multiple=2), W3)[0, 1] > 0.95 * W3.sum()


def test_fbcca_classifier_never_reads_epochs_in_fit_and_refuses_unknown_labels():
  clf = fb.FBCCAClassifier(fs=FS, stimulus_freqs_hz=M_FREQS, n_harmonics=3)
  rng = np.random.default_rng(0)
  X = rng.normal(size=(10, 3, 4, T))
  a = clf.fit(X, np.arange(10) % 5).predict(X)
  b = fb.FBCCAClassifier(fs=FS, stimulus_freqs_hz=M_FREQS, n_harmonics=3).fit(X * 0 + 1.0, np.zeros(10, int)).predict(X)
  assert np.array_equal(a, b)                         # training data never change the decision
  with pytest.raises(ValueError, match="no stimulus frequency"):
    clf.fit(X, np.full(10, 7))
  with pytest.raises(ValueError, match="rank deficient"):
    fb.reference_bases(FS, T, [100.0], 3)              # harmonics above Nyquist


# ------------------------------------------------------------------ CSP / FBCSP
def _two_class_csp_data(seed=0, C=4, n=60, amp=4.0):
  rng = np.random.default_rng(seed)
  X, y = [], []
  for cls, ax in ((0, 0), (1, 1)):
    for _ in range(n):
      w = rng.normal(size=(C, T))
      w[ax] += amp * rng.normal(size=T)
      X.append(w)
      y.append(cls)
  return np.stack(X), np.array(y)


def test_csp_analytic_eigenvalues_and_vector():
  """Known answer: S_A = I + 16 e0 e0^T-ish -> eigenvalues 16/17 (filter ~ e0) and 1/17 (+-0.03)."""
  X, y = _two_class_csp_data()
  c = csp.MulticlassCSP(1).fit(X, y)
  assert c.filters_.shape == (2, 4, 2) and abs(c.eigenvalues_[0, 0] - 16 / 17) < 0.03
  assert abs(c.eigenvalues_[0, 1] - 1 / 17) < 0.03 and abs(c.eigenvalues_[1, 0] - 16 / 17) < 0.03
  fa, fv = c.filters_[0][:, 0], c.filters_[0][:, 1]
  assert abs(fa[0]) / np.linalg.norm(fa) > 0.95 and abs(fv[1]) / np.linalg.norm(fv) > 0.95


def test_csp_filters_solve_the_generalized_eigenproblem_independently():
  rng = np.random.default_rng(3)
  C = 6
  X = np.stack([(rng.normal(size=(C, C)) @ rng.normal(size=(C, 128))) for _ in range(45)])
  y = np.repeat([0, 1, 2], 15)
  c = csp.MulticlassCSP(2).fit(X, y)

  def cov(sel):
    return np.mean([w @ w.T / np.trace(w @ w.T) for w in X[sel]], axis=0)
  for ci in range(3):
    st, sr = cov(y == ci), cov(y != ci)
    vals, vecs = eigh(st, st + sr + 1e-6 * np.eye(C))
    pick = [C - 1, C - 2, 0, 1]
    assert np.allclose(c.eigenvalues_[ci], vals[pick], atol=1e-9)
    for j, p in enumerate(pick):
      a, b = c.filters_[ci][:, j], vecs[:, p]
      assert abs(a @ b) / (np.linalg.norm(a) * np.linalg.norm(b)) > 1 - 1e-8


def test_csp_features_log10_ratio_and_variance_floor():
  X, y = _two_class_csp_data(seed=1)
  c = csp.MulticlassCSP(1).fit(X, y)
  assert np.allclose(c.transform(np.zeros((1, 4, T))), np.log10(0.5), atol=1e-9)
  c.filters_ = np.zeros_like(c.filters_)
  c.filters_[:, 0, 0] = 1.0
  v = np.var(X[3][0])
  exp = [np.log10(v / (v + 1e-12)), np.log10(1e-12 / (v + 1e-12))]
  F = c.transform(X[3][None])
  assert np.allclose(F[0, :2], exp, atol=1e-9) and np.allclose(F[0, 2:], exp, atol=1e-9)


def test_csp_trace_normalisation_resists_one_huge_epoch():
  X, y = _two_class_csp_data(seed=2)
  X[0, 3] *= 1000.0
  fa = csp.MulticlassCSP(1).fit(X, y).filters_[0][:, 0]
  assert abs(fa[0]) / np.linalg.norm(fa) > 0.95
  st = np.mean([w @ w.T for w in X[y == 0]], axis=0)       # buggy variant: no trace normalisation
  sr = np.mean([w @ w.T for w in X[y == 1]], axis=0)
  fm = eigh(st, st + sr + 1e-6 * np.eye(4))[1][:, -1]
  assert abs(fm[0]) / np.linalg.norm(fm) < 0.95


def _layout_epochs(seed=8, n=14, C=7):
  rng = np.random.default_rng(seed)
  gains = rng.uniform(0.5, 3.0, size=(5, C))
  X, y = [], []
  for k in range(5):
    for _ in range(n):
      tone = np.sin(2 * np.pi * (9.5 + 8.0 * k) * t + rng.uniform(0, 6.28))
      X.append(gains[k][:, None] * rng.normal(size=(C, T)) + 2.0 * rng.normal(size=(C, 1)) * tone[None])
      y.append(k)
  return np.stack(X), np.array(y)


def _oracle_fbcsp(xb_list, y, m=1):
  cols = []
  for xb in xb_list:
    covs = np.array([w @ w.T / np.trace(w @ w.T) for w in xb])
    for cls in np.unique(y):
      st, sr = covs[y == cls].mean(0), covs[y != cls].mean(0)
      _, vecs = eigh(st, st + sr + 1e-6 * np.eye(xb.shape[1]))
      W = np.hstack([vecs[:, ::-1][:, :m], vecs[:, :m]])
      v = np.maximum(np.einsum("cj,nct->njt", W, xb).var(-1), 1e-12)
      cols.append(np.log10(v / v.sum(1, keepdims=True)))
  return np.hstack(cols)


def test_fbcsp_layout_band_major_class_known_answer_and_mutants():
  """Known answer ([M] R6): (n, 50) for 5 bands x 5 classes x 2, equal to an independent oracle
  (1e-6); class-major or component-flipped layouts fail the same check."""
  X, y = _layout_epochs()
  sw = np.stack([sosfiltfilt(fbank.design(b, FS), X, axis=-1) for b in BUTTER_BANK], axis=1)
  F = csp.FBCSPTransformer(1).fit(sw, y).transform(sw)
  ora = _oracle_fbcsp([sw[:, b] for b in range(5)], y)
  assert F.shape == (len(X), 50) and np.allclose(F, ora, atol=1e-6)
  class_major = F.reshape(len(F), 5, 5, 2).transpose(0, 2, 1, 3).reshape(len(F), -1)
  flipped = F.reshape(len(F), 5, 5, 2)[..., ::-1].reshape(len(F), -1)
  assert not np.allclose(class_major, ora, atol=1e-6) and not np.allclose(flipped, ora, atol=1e-6)


def _fb_cfg(k=5, stim=M_FREQS):
  f1 = copy.deepcopy(PROFILE["f1"])
  for spec in f1["models"].values():
    if "priors" in spec["params"]:
      spec["params"]["priors"] = cl.uniform_priors(k)
  f1["fbcsp"] = {"n_components": 1, "reg": 1e-6, "var_floor": 1e-12}
  f1["fbcca"] = {"fs_hz": FS, "stimulus_freqs_hz": list(stim), "n_harmonics": 3, "response_multiple": 1,
                 "weight_a": 1.25, "weight_b": 0.25}
  return {"f1": f1, "baseline": None}


def test_in_fold_fbcsp_gives_chance_on_noise_and_a_full_data_fit_does_not():
  """Known answer ([M] PF-11): pure noise, 5 classes of 20 epochs, 5 grouped folds (each epoch its own
  unit): in-fold FBCSP + Shrinkage-LDA stays <= 0.35 BA; the buggy variant with the CSP fitted on
  all epochs (test labels seen) exceeds 0.45 and the honest value by >= 0.15."""
  rng = np.random.default_rng(0)
  X = rng.normal(0, 8, size=(100, 7, T))
  y = np.repeat(np.arange(5), 20)
  sw = np.stack([sosfiltfilt(fbank.design(b, FS), X, axis=-1) for b in BUTTER_BANK], axis=1)
  uid = np.arange(100)
  splits = fo.fold_splits(uid, fo.assign_unit_folds(np.zeros(100, int), 5, 0, unit_label=y), 5)
  cfg = _fb_cfg()
  names = [f"c{i}" for i in range(5)]
  pred = evl.cv_predict(sw, y, splits, lambda: cl.make_method("f1/fbcsp/Shrinkage-LDA lsqr", cfg), names)[0]
  honest = evl.class_metrics(y, pred, names)["ba"]
  Fall = csp.FBCSPTransformer(1).fit(sw, y).transform(sw)
  leaky_pred = np.empty_like(y)
  for _, tr, te in splits:
    leaky_pred[te] = cl.make_method("f1/raw/Shrinkage-LDA lsqr", cfg).fit(Fall[tr][:, :, None], y[tr]).predict(Fall[te][:, :, None])
  leaky = evl.class_metrics(y, leaky_pred, names)["ba"]
  assert honest <= 0.35 and leaky > 0.45 and leaky - honest >= 0.15, (honest, leaky)


# ------------------------------------------------------------------ continuous filter bank, 5 classes end to end
SSVEP_FREQS = [8.0, 10.0, 12.0, 15.0, 20.0]


def ssvep_session(seed, n_files=3, units_per_class=4, amp=1.0, effect="ssvep", fs=256.0):
  s = synth.erp_settings(fs)
  s["rejection"]["enabled"] = False
  s["classes"] = [f"{f:g}Hz" for f in SSVEP_FREQS]
  s["window_gates"] = []
  s["span_gates"] = []
  res, fbs = [], []
  for f in range(n_files):
    data, events, _ = synth.recording(seed + f, fs=fs, n_channels=6, n_units=5 * units_per_class, n_epochs=4,
                                      isi=256, rest=512, tail=512, scheme="per_unit", n_classes=5, effect=effect,
                                      amp=amp, noise=1.0, freqs=SSVEP_FREQS, harmonics=2)
    r = ep.prepare_file(data, fs, events, s)
    fbr = fbank.subband_epochs(data, fs, events, r, [0.0, 1.0], "floor", CHEB_BANK, padlen=1000)
    res.append(r)
    fbs.append(fbr)
  sess = ds.assemble(res)
  sess["X_fb"] = np.concatenate([f["X"] for f in fbs])
  return sess, fbs


def test_filterbank_is_continuous_its_gate_reports_the_iir_span_and_fallback_isolates_units():
  """Known answer: the bank output equals sosfiltfilt of the whole record cut afterwards (1e-12)
  when the effective-span gate passes; a per-window filtering (PF-14 buggy variant) differs; with
  units close together the gate fails, filtering is unit-wise, and a step in unit 1 leaves unit-0
  epochs unchanged."""
  data, events, _ = synth.recording(1, fs=256.0, n_channels=3, n_units=3, n_epochs=4, isi=256, rest=4000,
                                    tail=512, scheme="per_unit", n_classes=3, effect="ssvep", freqs=SSVEP_FREQS)
  s = synth.erp_settings(256.0)
  s["rejection"]["enabled"] = False
  r = ep.prepare_file(data, 256.0, events, s)
  out = fbank.subband_epochs(data, 256.0, events, r, [0.0, 1.0], "floor", CHEB_BANK, padlen=1000)
  assert out["filtering"] == "continuous" and all(g["passes"] for g in out["gates"])
  assert all(g["effective_span"] > 50 for g in out["gates"])
  whole = sosfiltfilt(fbank.design(CHEB_BANK[0], 256.0), data, axis=-1, padtype="odd", padlen=1000)
  on = events["onset"][r["keep"]]
  ref = np.stack([whole[:, o:o + 256] for o in on])
  assert np.abs(out["X"][:, 0] - ref).max() < 1e-12
  per_win = np.stack([sosfiltfilt(fbank.design(CHEB_BANK[0], 256.0), data[:, o:o + 256], axis=-1) for o in on])
  assert np.abs(per_win - ref).max() > 1e-3
  data2, events2, _ = synth.recording(1, fs=256.0, n_channels=3, n_units=3, n_epochs=12, isi=256, rest=40,
                                      tail=300, scheme="per_unit", n_classes=3, effect="ssvep", freqs=SSVEP_FREQS)
  r2 = ep.prepare_file(data2, 256.0, events2, {**s, "bandpass": {**s["bandpass"], "numtaps": 33, "padlen": 99}})
  o1 = fbank.subband_epochs(data2, 256.0, events2, r2, [0.0, 1.0], "floor", CHEB_BANK, padlen=1000)
  assert o1["filtering"] == "unitwise_fallback" and not all(g["passes"] for g in o1["gates"])
  d3 = data2.copy()
  d3[:, events2["unit_start"][1]:] += 5000.0
  o2 = fbank.subband_epochs(d3, 256.0, events2, r2, [0.0, 1.0], "floor", CHEB_BANK, padlen=1000)
  m0 = r2["unit"] == 0
  assert np.allclose(o1["X"][m0], o2["X"][m0], atol=1e-9)


def test_five_class_fbcca_and_fbcsp_lda_learn_planted_frequencies_and_noise_is_chance():
  """Known answer (5 SSVEP classes, label-balanced grouped folds by trial): FBCCA (training-free)
  reaches BA >= 0.9 and FBCSP + Shrinkage-LDA >= 0.6 on planted sinusoids (amp 1 x noise SD,
  with a 2nd harmonic); on noise both are within 0.2 +- 0.12 [own bounds, a priori]."""
  names = [f"{f:g}Hz" for f in SSVEP_FREQS]
  cfg = _fb_cfg(stim=SSVEP_FREQS)
  cfg["f1"]["fbcca"]["fs_hz"] = 256.0
  for effect, lo_fbcca, lo_csp in (("ssvep", 0.9, 0.6), ("none", None, None)):
    sess, _ = ssvep_session(70, effect=effect)
    ul = np.array([sess["y"][sess["unit_uid"] == u][0] for u in np.unique(sess["unit_uid"])])
    splits = fo.fold_splits(sess["unit_uid"], fo.assign_unit_folds(sess["unit_file"], 4, 1, unit_label=ul), 4)
    p1 = evl.cv_predict(sess["X_fb"], sess["y"], splits,
                        lambda: fb.FBCCAClassifier(256.0, SSVEP_FREQS, 3), names)[0]
    p2 = evl.cv_predict(sess["X_fb"], sess["y"], splits,
                        lambda: cl.make_method("f1/fbcsp/Shrinkage-LDA lsqr", cfg), names)[0]
    b1, b2 = evl.class_metrics(sess["y"], p1, names)["ba"], evl.class_metrics(sess["y"], p2, names)["ba"]
    if effect == "ssvep":
      assert b1 >= lo_fbcca and b2 >= lo_csp, (b1, b2)
    else:
      assert abs(b1 - 0.2) <= 0.12 and abs(b2 - 0.2) <= 0.12, (b1, b2)


def test_fbcsp_plus_fbcca_feature_union_has_both_blocks():
  cfg = _fb_cfg()
  rng = np.random.default_rng(1)
  X = rng.normal(size=(30, 3, 4, T))
  y = np.repeat(np.arange(5), 6)
  est = cl.make_method("f1/fbcsp+fbcca/Shrinkage-LDA lsqr", cfg).fit(X, y)
  Z = est.named_steps["fbcsp+fbcca"].transform(X)
  assert Z.shape == (30, 3 * 5 * 2 + 5)


# ------------------------------------------------------------------ CCNN and fusion (torch)
def _torch():
  return pytest.importorskip("torch")


def ccnn_spec(C, F=None, fs=256.0):
  return {"class": "CCNN", "params": {"fs": fs, "f_min": 3.0, "f_max": 50.0, "resolution_hz": 0.25,
                                      "n_filters": F or 2 * C, "spectral_kernel": 10, "dropout": 0.25}}


@pytest.mark.parametrize("C,n_params", [(7, 27977), (8, 32309)])
def test_ccnn_parameter_count_matches_the_source(C, n_params):
  """Known answer ([M] ccnn.py R-8): 256 samples, 256 Hz, 3-50 Hz, 0.25 Hz (189 bins), 5 classes,
  F = 2C: 27,977 parameters for C 7 and 32,309 for C 8; the builder refuses a missing parameter."""
  _torch()
  from eegpipe import networks as nw
  from eegpipe.ssvep import ccnn  # noqa: F401  (registers CCNN)
  m = nw.model_builder(ccnn_spec(C))(5, C, 256)
  assert m.n_bins == 189 and nw.count_parameters(m) == n_params
  bad = ccnn_spec(C)
  del bad["params"]["fs"]
  with pytest.raises(ValueError, match="fs"):
    nw.model_builder(bad)


def test_ccnn_spectrum_layout_real_then_imag_divided_by_T():
  """Known answer: for x = cos(2 pi 10 t) on every channel (256 samples, 256 Hz, nfft 1024), the
  spectrum map holds Re at position k and Im at n_bins + k; at 10 Hz Re = 0.5, Im ~ 0."""
  torch = _torch()
  from eegpipe.ssvep.ccnn import CCNN
  m = CCNN(5, 3, 256, 256.0, 3.0, 50.0, 0.25, 6, 10, 0.0)
  tt = torch.arange(256) / 256.0
  x = torch.cos(2 * np.pi * 10 * tt).repeat(1, 3, 1)
  s = m.spectrum(x)[0, 0, 0]
  k = int(np.argmin(np.abs(m.bins_hz - 10.0)))
  assert abs(float(s[k]) - 0.5) < 1e-6 and abs(float(s[m.n_bins + k])) < 1e-6


def test_fusion_parameter_count_and_packing_known_answer():
  """Known answer ([M] R-8): a 4 x 8 harmonic map and 5 FBCCA scores give 10,005 parameters; the
  packed model hands the network exactly the (1, 4, 8) map and the 5 scores; harmonic targets are
  f * m * h; the harmonic map picks the periodogram bin nearest each target; a target at Nyquist is
  refused."""
  torch = _torch()
  from eegpipe import networks as nw
  from eegpipe.ssvep import fusion as fu
  m = fu.DualBranchFusionCNN(5, 4, 8, 5, 0.3)
  assert nw.count_parameters(m) == 10005
  rng = np.random.default_rng(0)
  sp, sc = rng.normal(size=(3, 4, 8)), rng.normal(size=(3, 5))
  P = fu.pack(sp, sc)
  pm = nw.model_builder({"class": "PackedFusion", "params": {"n_spatial_channels": 4, "n_harmonic_bins": 8,
                                                             "n_fbcca": 5, "dropout": 0.3}})(5, 1, P.shape[2])
  seen = {}
  orig = pm.net.forward
  pm.net.forward = lambda a, b: (seen.update(a=a, b=b), orig(a, b))[1]
  pm.eval()
  assert pm(torch.from_numpy(P).float()).shape == (3, 5)
  assert np.allclose(seen["a"].numpy()[:, 0], sp, atol=1e-6) and np.allclose(seen["b"].numpy(), sc, atol=1e-6)
  assert fu.harmonic_targets([8.0, 10.0], 2) == [8.0, 16.0, 10.0, 20.0]
  assert fu.harmonic_targets([7.5], 1, response_multiple=2) == [15.0]
  tt = np.arange(256) / 256.0
  x = np.sin(2 * np.pi * 12.0 * tt)[None, None, :] * np.ones((1, 2, 1))
  hm = fu.harmonic_map(x, 256.0, [8.0, 12.0, 20.0])
  assert hm[0, 0].argmax() == 1 and hm[0, 0, 1] > 100 * hm[0, 0, 0]
  with pytest.raises(ValueError, match="Nyquist"):
    fu.harmonic_map(x, 256.0, [128.0])


def test_ccnn_and_fusion_learn_five_planted_frequencies_under_grouped_folds():
  """Known answer (5 classes, label-balanced grouped folds by trial): CCNN on the band epochs and the
  fusion network on packed (harmonic map, FBCCA scores) inputs reach BA >= 0.6 on planted
  sinusoids (chance 0.2) with 10 epochs [own bounds, a priori]."""
  _torch()
  from eegpipe import networks as nw
  from eegpipe.ssvep import ccnn, fusion as fu  # noqa: F401
  names = [f"{f:g}Hz" for f in SSVEP_FREQS]
  sess, _ = ssvep_session(70)
  ul = np.array([sess["y"][sess["unit_uid"] == u][0] for u in np.unique(sess["unit_uid"])])
  splits = fo.fold_splits(sess["unit_uid"], fo.assign_unit_folds(sess["unit_file"], 4, 1, unit_label=ul), 4)
  ncfg = {"trainer": {**{k: v for k, v in PROFILE["networks"]["trainer"].items()
                         if not isinstance(v, str) or k == "class_weights"}, "max_epochs": 10, "batch_size": 16},
          "augmentation": {"enabled": False, "p_scale": 0, "scale_range": [1, 1], "p_noise": 0, "noise_std_frac": 0}}
  Xb = sess["X_fb"][:, 0]                                    # first Chebyshev band, (n, C, T)
  pred, _, _, _ = nw.cv_network(Xb, sess["y"], sess["unit_uid"], splits, ccnn_spec(Xb.shape[1], fs=256.0)
                                | {"params": {**ccnn_spec(Xb.shape[1], fs=256.0)["params"], "resolution_hz": 0.5}},
                                1, ncfg, "cpu", names)
  assert evl.class_metrics(sess["y"], pred, names)["ba"] >= 0.6
  scores = fb.fbcca_scores(sess["X_fb"], fb.reference_bases(256.0, sess["X_fb"].shape[-1], SSVEP_FREQS, 3), W3)
  hm = fu.harmonic_map(Xb, 256.0, fu.harmonic_targets(SSVEP_FREQS, 2))
  P = fu.pack(hm, scores)
  spec = {"class": "PackedFusion", "params": {"n_spatial_channels": hm.shape[1], "n_harmonic_bins": hm.shape[2],
                                              "n_fbcca": 5, "dropout": 0.3}}
  pred, _, _, _ = nw.cv_network(P, sess["y"], sess["unit_uid"], splits, spec, 1, ncfg, "cpu", names,
                                norm={"kind": "per_feature", "std_floor": 1e-8})
  assert evl.class_metrics(sess["y"], pred, names)["ba"] >= 0.6
