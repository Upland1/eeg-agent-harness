"""Known-answer tests for the eegpipe gaps found by the ssvep-apply plan audit and development run (2026-11-07).
Each test fails on v0.4-dev @ df717c2 (shown in the commit that added it) and passes after the fix:
  1. FBCSP has its own filter bank (``ssvep.filterbank.fbcsp_bank``) and the union input keeps both banks;
  2. FBCCA references may combine several response multiples (on-off f and checkerboard 2f), with harmonics at or
     above Nyquist dropped instead of refusing the study;
  3. the ssvep profile's F1 primary is the flagship FBCSP + FBCCA it names as its source;
  4. the network input window may start after the event (e.g. [0.5, 4.5) s);
  5. cv_network reports training accuracy on the un-augmented training fold (G18);
  6. the union step fbcsp+fbcca registers the SSVEP steps in a fresh interpreter (spawned permutation workers)."""

import copy
import json
import sys
from pathlib import Path

import numpy as np
import pytest
from scipy.signal import sosfiltfilt

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
import eegpipe.ssvep  # noqa: E402,F401
from eegpipe import classical as cl  # noqa: E402
from eegpipe import epochs as ep  # noqa: E402
from eegpipe import filtering as flt  # noqa: E402
from eegpipe.runner import methods as rm  # noqa: E402
from eegpipe.ssvep import fbcca as fb  # noqa: E402
from eegpipe.ssvep import fbcsp as csp  # noqa: E402
from eegpipe.ssvep import filterbank as fbank  # noqa: E402
from eegpipe.testing import synth  # noqa: E402

PROFILES = TOOLS / "eegpipe" / "profiles"
FS = 256.0


def _ssvep_cfg():
  p = json.loads((PROFILES / "ssvep.json").read_text())
  f1 = copy.deepcopy(p["f1"])
  for spec in f1["models"].values():
    if "priors" in spec["params"]:
      spec["params"]["priors"] = cl.uniform_priors(5)
  f1["fbcca"].update(fs_hz=FS, stimulus_freqs_hz=[8.0, 10.0, 12.0, 15.0, 20.0], n_bands=3)
  sv = copy.deepcopy(p["ssvep"])
  sv["stimulus_freqs_hz"] = [8.0, 10.0, 12.0, 15.0, 20.0]
  sv["filterbank"]["window_s"] = [0.0, 1.0]
  return {"f1": f1, "ssvep": sv, "fs_hz": FS, "baseline": None,
          "epochs": {"fallback": {"margin_s": 1.0}}}


# ------------------------------------------------------------------ 1. FBCSP bank
def test_fbcsp_uses_its_own_bank_and_the_union_keeps_both_banks():
  """Known answer: with a 3-band FBCCA bank and a 5-band FBCSP bank, FBCSP methods read 5-band epochs, FBCCA
  methods 3-band epochs, the union 3 + 5 bands; the union's FBCSP block equals FBCSPTransformer on the Butterworth
  bands alone (1e-9) and its FBCCA block equals FBCCAFeatures on the Chebyshev bands alone. (df717c2: every
  filter-bank method read the FBCCA bank.)"""
  cfg = _ssvep_cfg()
  data, events, _ = synth.recording(3, fs=FS, n_channels=4, n_units=10, n_epochs=2, isi=256, rest=600, tail=400,
                                    scheme="per_unit", n_classes=5, effect="ssvep", freqs=[8.0, 10.0, 12.0, 15.0, 20.0])
  s = synth.erp_settings(FS)
  s["rejection"]["enabled"] = False
  r = ep.prepare_file(data, FS, events, s)
  inp = rm.filterbank_inputs([(None, data, FS, events, r)], cfg)
  assert inp["fb"].shape[1] == 3 and inp["fb_csp"].shape[1] == 5 and inp["fb_both"].shape[1] == 8
  assert rm.input_kind("f1/fbcsp/Shrinkage-LDA lsqr") == "fb_csp" and rm.input_kind("ssvep/fbcca") == "fb"
  assert rm.input_kind("f1/fbcsp+fbcca/Shrinkage-LDA lsqr") == "fb_both" and rm.input_kind("f1/fbcca/LDA svd") == "fb"
  y = r["y"]
  est = cl.make_method("f1/fbcsp+fbcca/Shrinkage-LDA lsqr", cfg).fit(inp["fb_both"], y)
  Z = est.named_steps["fbcsp+fbcca"].transform(inp["fb_both"])
  ref_csp = csp.FBCSPTransformer(1, 1e-6, 1e-12).fit(inp["fb_csp"], y).transform(inp["fb_csp"])
  ref_cca = fb.FBCCAFeatures(FS, [8.0, 10.0, 12.0, 15.0, 20.0], 3).fit(inp["fb"]).transform(inp["fb"])
  assert Z.shape == (len(y), 5 * 5 * 2 + 5)
  assert np.allclose(Z[:, :50], ref_csp, atol=1e-9) and np.allclose(Z[:, 50:], ref_cca, atol=1e-9)


# ------------------------------------------------------------------ 2. response multiples
def test_fbcca_union_of_response_multiples_with_harmonics_above_nyquist_dropped():
  """Known answer: f = 24 Hz at 256 Hz, H 3, multiples (1, 2): reference frequencies 24, 48, 72, 96 (144 Hz is above
  Nyquist and dropped, 48 counted once); a checkerboard response at 48 Hz and an on-off response at 24 Hz both
  score > 0.9 of sum(w) for that target and win; (df717c2: multiple 2 with H 3 raised 'rank deficient')."""
  T = 256
  t = np.arange(T) / FS
  freqs = [24.0, 20.0, 15.0]
  assert fb.reference_frequencies(24.0, 3, (1, 2), FS) == [24.0, 48.0, 72.0, 96.0]
  bases = fb.reference_bases(FS, T, freqs, 3, response_multiple=[1, 2])
  w = fb.weights(3)
  for f_resp in (24.0, 48.0):
    x = np.stack([np.sin(2 * np.pi * f_resp * t + 0.4 * c) for c in range(4)])
    s = fb.fbcca_scores(np.stack([x] * 3)[None], bases, w)
    assert s.argmax() == 0 and s[0, 0] > 0.9 * w.sum()
  with pytest.raises(ValueError):
    fb.reference_bases(FS, T, [200.0], 1)                 # nothing below Nyquist: refused


# ------------------------------------------------------------------ 3. profile
def test_ssvep_profile_primary_is_the_flagship_it_cites():
  p = json.loads((PROFILES / "ssvep.json").read_text())
  assert p["f1"]["primary"]["features"] == "fbcsp+fbcca" and "flagship" in p["f1"]["source"]
  assert "fbcsp+fbcca" in p["f1"]["feature_spaces"]


# ------------------------------------------------------------------ 4. network input window
def test_network_input_window_may_start_after_the_event():
  """Known answer: window [0.25, 0.65) s at 256 Hz -> 128 Hz: 51 samples starting at floor((onset + 64) / 2); equal
  to filtfilt + resample_poly of the whole record cut there (1e-12). (df717c2: refused 'does not start at 0'.)"""
  from eegpipe import network_input as ni
  data, events, _ = synth.recording(7, fs=FS, n_channels=4, n_units=3, n_epochs=12, isi=64, rest=2400, tail=256)
  s = synth.erp_settings(FS)
  kept = ep.prepare_file(data, FS, events, s)
  prof = json.loads((PROFILES / "erp.json").read_text())["network_input"]
  g = {**prof, "epoch_window_s": [0.25, 0.65], "epoch_samples_out": 51}
  out = ni.network_epochs(data, FS, events, kept, g, 1.0)
  taps = flt.design_bandpass(FS, g["band_hz"], g["numtaps"], g["window"], scale=g["firwin_scale"])
  ref = flt.resample(flt.bandpass_continuous(data, taps, g["padtype"], g["padlen"]), 1, 2, g["resample_window"],
                     g["resample_padtype"])
  want = flt.cut_resampled(ref, kept["onset"] + 64, 2, 51)
  assert out["X"].shape[-1] == 51 and np.abs(out["X"] - want).max() < 1e-12


# ------------------------------------------------------------------ 5. training accuracy
def test_cv_network_reports_training_accuracy_on_the_unaugmented_training_fold(monkeypatch):
  """Known answer: every fold row carries train_ba = balanced accuracy of the fitted model's predictions on the
  fold's training epochs WITHOUT augmentation (recomputed here from a spy on fit_network, 1e-12), also when
  augmentation is on. (df717c2: no training accuracy, G18.)"""
  torch = pytest.importorskip("torch")  # noqa: F841
  from eegpipe import evaluate as evl
  from eegpipe import folds as fo
  from eegpipe import networks as nw
  rng = np.random.default_rng(0)
  X = rng.normal(size=(96, 4, 64))
  y = np.tile([0, 1], 48)
  X[y == 1, :, 20:30] += 1.0
  uid = np.repeat(np.arange(24), 4)
  splits = fo.fold_splits(uid, fo.assign_unit_folds(np.zeros(24, int), 3, 0), 3)
  prof = json.loads((PROFILES / "erp.json").read_text())["networks"]
  tr = {k: v for k, v in prof["trainer"].items() if not isinstance(v, str) or k == "class_weights"}
  tr.update(max_epochs=2)
  aug = {**prof["augmentation"], "enabled": True, "p_scale": 1.0, "p_noise": 1.0}
  spec = {"class": "ShallowConvNet", "params": {"F1": 4, "temporal_kernel_length": 5, "pool_kernel_length": 10,
                                                "pool_stride": 5, "dropout_rate": 0.5}}
  fits = []
  real = nw.fit_network
  monkeypatch.setattr(nw, "fit_network", lambda *a, **k: (fits.append((a[0], a[1], real(*a, **k))), fits[-1][2])[1])
  _, _, rows, _ = nw.cv_network(X, y, uid, splits, spec, 1, {"trainer": tr, "augmentation": aug}, "cpu", ["a", "b"])
  for row, (Xtr, ytr, f) in zip(rows, fits):
    pred, _ = nw.predict(f, Xtr, "cpu", 256)
    assert row["train_ba"] == pytest.approx(evl.class_metrics(ytr, pred, ["a", "b"])["ba"], abs=1e-12)


def test_settings_refuse_an_fbcca_band_count_that_does_not_match_the_bank():
  from eegpipe import settings as st
  sys.path.insert(0, str(Path(__file__).resolve().parent))
  from test_eegpipe_runner import settings_for
  cfg = settings_for()
  cfg["ssvep"] = {"enabled": True, "stimulus_freqs_hz": [8.0, 10.0], "filterbank": {"bank": [{}, {}, {}]}}
  cfg["f1"]["fbcca"] = {"n_bands": 3}
  st.validate(cfg, require_sources=False)
  cfg["f1"]["fbcca"]["n_bands"] = 4
  with pytest.raises(st.SettingsError, match="n_bands"):
    st.validate(cfg, require_sources=False)


def test_union_feature_step_registers_itself_in_a_fresh_interpreter():
  """Gap 6 (found by the ssvep-apply development run): a spawned permutation worker imports only
  eegpipe.classical, so ``fbcsp+fbcca`` must register the SSVEP steps the way ``fbcsp`` and ``fbcca`` do."""
  import subprocess
  code = ("import json, sys; sys.path.insert(0, sys.argv[1]); from eegpipe import classical as cl; "
          "p = json.loads(open(sys.argv[2]).read()); print(cl.feature_step('fbcsp+fbcca', p['f1'])[0])")
  out = subprocess.run([sys.executable, "-I", "-c", code, str(TOOLS), str(PROFILES / "ssvep.json")],
                       capture_output=True, text=True)
  assert out.returncode == 0, out.stderr
  assert out.stdout.strip() == "fbcsp+fbcca"
