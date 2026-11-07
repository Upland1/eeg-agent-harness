"""Known-answer tests for eegpipe.filtering, gates, epochs, dataset and folds.

Moved from the P300 project (tests @ d833264, ``tests/test_ssvep_methods_step1.py`` sections 1-4
and ``step2`` input-path tests); P300 literals (256 Hz, 257 / 845 taps, 204 / 102 samples,
the 884-sample span) are kept as the parameters of each case, the event structure comes
from ``eegpipe.testing.synth`` instead of the study's .ebr files.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
from eegpipe import dataset as ds  # noqa: E402
from eegpipe import epochs as ep  # noqa: E402
from eegpipe import filtering as flt  # noqa: E402
from eegpipe import folds as fo  # noqa: E402
from eegpipe import gates as gt  # noqa: E402
from eegpipe.testing import synth  # noqa: E402
from eegharness.splits import LeakError  # noqa: E402

FS = 256.0
SEED_FOLDS = 20261107


# ------------------------------------------------------------------ folds
def test_folds_never_split_a_unit_are_balanced_and_reproducible():
  """Known answer (exact; moved from step1 ``test_folds_never_split_a_block_...``): 6+6+6 = 18
  units over 8 folds: every unit in exactly one test fold, per stratum and overall the unit
  counts per fold differ by at most 1, same seed same folds, another seed other folds; unequal
  strata (8, 9, 5) still within 1. Buggy variant: an epoch-level random k-fold splits units,
  and check_no_leak raises on it."""
  unit_stratum = np.repeat([0, 1, 2], 6)
  uf = fo.assign_unit_folds(unit_stratum, 8, SEED_FOLDS)
  unit_uid = np.repeat(np.arange(18), 5)
  splits = fo.fold_splits(unit_uid, uf, 8)
  te_all = np.concatenate([te for _, _, te in splits])
  assert sorted(te_all.tolist()) == list(range(unit_uid.size))
  for f in range(3):
    c = np.bincount(uf[unit_stratum == f], minlength=8)
    assert c.max() - c.min() <= 1
  c = np.bincount(uf, minlength=8)
  assert c.max() - c.min() <= 1 and c.sum() == 18
  assert np.array_equal(uf, fo.assign_unit_folds(unit_stratum, 8, SEED_FOLDS))
  assert not np.array_equal(uf, fo.assign_unit_folds(unit_stratum, 8, SEED_FOLDS + 1))
  bfile = np.repeat([0, 1, 2], [8, 9, 5])
  f2 = fo.assign_unit_folds(bfile, 8, SEED_FOLDS)
  for f in range(3):
    cc = np.bincount(f2[bfile == f], minlength=8)
    assert cc.max() - cc.min() <= 1
  rng = np.random.default_rng(1)
  bad_fold = rng.integers(0, 8, unit_uid.size)              # buggy: folds per epoch, not per unit
  te = np.flatnonzero(bad_fold == 0)
  tr = np.flatnonzero(bad_fold != 0)
  with pytest.raises(LeakError):
    from eegharness.splits import check_no_leak
    check_no_leak(tr, te, unit_uid)


def test_fold_assignment_is_bitwise_the_p300_algorithm():
  """Regression (exact): the folds equal an independent re-implementation of the P300
  algorithm (p300/session.py::assign_block_folds @ cd5db15) for the P300 seed."""
  unit_stratum = np.repeat(np.arange(7), [9, 9, 9, 9, 9, 9, 8])
  rng = np.random.default_rng(SEED_FOLDS)
  want = np.full(unit_stratum.size, -1)
  nxt = 0
  for f in range(7):
    uids = np.flatnonzero(unit_stratum == f)
    perm = rng.permutation(uids.size)
    for i, j in enumerate(perm):
      want[uids[j]] = (nxt + i) % 8
    nxt = (nxt + uids.size) % 8
  assert np.array_equal(fo.assign_unit_folds(unit_stratum, 8, SEED_FOLDS), want)


# ------------------------------------------------------------------ gates
def _gate_inputs(onset0, onset1, start, stop):
  f0, l0 = gt.epoch_extent(np.array(onset0), start, stop)
  f1, l1 = gt.epoch_extent(np.array(onset1), start, stop)
  return np.concatenate([f0, f1]), np.concatenate([l0, l1]), np.array([0] * len(onset0) + [1] * len(onset1))


@pytest.mark.parametrize("gap,passes", [(255, False), (256, False), (257, True), (400, True)])
def test_span_gate_boundary_257_taps(gap, passes):
  """Known answer (exact): span = numtaps - 1 = 256; passes iff min gap > 256."""
  last0 = 1000
  first_used_1 = last0 + 203 + gap
  first, last, u = _gate_inputs([800, last0], [first_used_1, first_used_1 + 400], 0, 204)
  g = gt.span_gate(first, last, u, 2, flt.filter_half_span(257))
  assert g["span_samples"] == 256 and g["min_gap_samples"] == gap and g["passes"] is passes


@pytest.mark.parametrize("gap,passes", [(882, False), (884, False), (886, True)])
def test_span_gate_boundary_resample_path_floor_onset(gap, passes):
  """Known answer (exact): span (845 - 1) + (41 - 1) = 884; floor(onset / 2) mapping: odd
  onset 1001 -> first 1000, last 1202 (a ceil/round rule would give 1002)."""
  f, l = gt.resampled_epoch_extent(np.array([1001]), 2, 102)
  assert (int(f[0]), int(l[0])) == (1000, 1202)
  last0 = 1202
  o1 = (last0 + gap) // 2 * 2 + 1
  f1, l1 = gt.resampled_epoch_extent(np.array([o1]), 2, 102)
  assert int(f1[0]) == last0 + gap
  g = gt.span_gate(np.concatenate([f, f1]), np.concatenate([l, l1]), np.array([0, 1]), 2,
                   flt.filter_half_span(845) + flt.resampler_numtaps(1, 2) - 1)
  assert g["span_samples"] == 884 and g["min_gap_samples"] == gap and g["passes"] is passes


def test_window_gate_overlap_and_boundary():
  """Known answer (exact): window [-51, 256) at 256 Hz for [-0.2, 1.0] s (round); gap 0 and
  -50 fail, gap 1 passes."""
  ws, wst = flt.window_bounds([-0.2, 1.0], FS, "round")
  assert (ws, wst) == (-51, 256)
  for gap, passes in [(-50, False), (0, False), (1, True)]:
    last_on = 2000
    end0 = last_on + wst - 1
    on1 = end0 + gap - ws
    first, last, u = _gate_inputs([1000, last_on], [on1, on1 + 400], ws, wst)
    g = gt.window_gate(first, last, u, 2, [990, on1 - 8], [last_on + 16, on1 + 416])
    assert g["min_gap_samples"] == gap and g["passes"] is passes


def test_edge_epoch_count_planted_case():
  """Known answer (exact): 4 of the 7 planted epochs lie within 128 samples of their segment edge."""
  first = [100, 400, 700, 128, 500, 400, 1000]
  last = [303, 603, 903, 331, 872, 871, 1203]
  u = [0, 0, 0, 0, 0, 0, 1]
  assert gt.count_edge_epochs(first, last, u, [(0, 999), (1000, 1999)], 128) == 4


def test_unitwise_segments_raise_on_overlap_and_not_one_sample_apart():
  with pytest.raises(ValueError, match="overlap"):
    gt.unitwise_segments([0, 500], [500, 900], [0, 500], [500, 900], 257, 256, 2000)
  gt.unitwise_segments([0, 501], [500, 900], [0, 501], [500, 900], 257, 256, 2000)


# ------------------------------------------------------------------ prepare_file
def _file(rest, seed=7, effect="erp", **kw):
  return synth.recording(seed, fs=FS, n_channels=4, n_units=3, n_epochs=12, isi=64, rest=rest, tail=256,
                         effect=effect, **kw)


def test_prepare_file_gate_drives_filtering_mode_and_epochs_are_one_to_one():
  """Known answer: units separated widely -> span gate passes and filtering is continuous;
  every kept epoch is the event of the same index (onset, unit, code carried through), and
  the epoch equals the scipy chain (filtfilt of the whole record, cut [0, 204), every 4th
  sample) to 1e-12. Rest 435: gap = rest + tail - 203 - ... reaches the boundary exactly."""
  data, events, _ = _file(rest=1200)
  s = synth.erp_settings(FS)
  r = ep.prepare_file(data, FS, events, s)
  assert r["gates"]["filtering"] == "continuous" and r["gates"]["span__bandpass__passes"] is True
  b = s["bandpass"]
  taps = flt.design_bandpass(FS, b["band_hz"], b["numtaps"], b["window"], scale=True)
  filt = flt.bandpass_continuous(data, taps, "odd", 771)
  kept = np.flatnonzero(r["keep"])
  want = flt.cut_epochs(filt, events["onset"][kept], 0, 204)[..., ::4]
  assert r["X"].shape == (kept.size, 4, 51)
  assert np.abs(r["X"] - want).max() < 1e-12
  assert np.array_equal(r["code"], events["code"][kept]) and np.array_equal(r["unit"], events["unit"][kept])


def test_fallback_isolates_units_and_equals_continuous_away_from_edges():
  """Known answer (moved from step1 fallback tests): with units close together (rest 150 +
  tail 256 -> used-sample gap 203 <= 256) the span gate fails, filtering is unit-wise, no
  segment contains another unit's used samples; epochs whose used samples are more than the
  filter's reach (numtaps - 1 = 256) from their segment edges equal continuous filtering to
  1e-9 (the others are the counted edge epochs); a 5000 uV step from unit 1's start on leaves
  unit-0 epochs unchanged (no leakage between segments), while continuous filtering of the
  same record changes them (the buggy variant: the used-sample gap 203 < 256)."""
  data, events, _ = _file(rest=150)
  s = synth.erp_settings(FS)
  r = ep.prepare_file(data, FS, events, s)
  assert r["gates"]["filtering"] == "unitwise_fallback" and r["gates"]["span__bandpass__passes"] is False
  first, last = gt.epoch_extent(events["onset"], 0, 204)
  for u, (a, z) in enumerate(r["segments"]):
    others = events["unit"] != u
    assert not np.any((first[others] <= z) & (last[others] >= a))
  b = s["bandpass"]
  taps = flt.design_bandpass(FS, b["band_hz"], b["numtaps"], b["window"], scale=True)
  filt = flt.bandpass_continuous(data, taps, "odd", 771)
  Xc = flt.cut_epochs(filt, r["onset"], 0, 204)[..., ::4]
  f_k, l_k = gt.epoch_extent(r["onset"], 0, 204)
  s_lo = np.array([r["segments"][u][0] for u in r["unit"]])
  s_hi = np.array([r["segments"][u][1] for u in r["unit"]])
  interior = (f_k - s_lo >= 256) & (s_hi - l_k >= 256)
  assert interior.sum() >= 6 and (~interior).sum() == r["gates"]["n_used_epochs_near_fallback_segment_edge"]
  assert np.abs(Xc[interior] - r["X"][interior]).max() < 1e-9
  d2 = data.copy()
  d2[:, events["unit_start"][1]:] += 5000.0
  r2 = ep.prepare_file(d2, FS, events, {**s, "rejection": {**s["rejection"], "enabled": False}})
  r1 = ep.prepare_file(data, FS, events, {**s, "rejection": {**s["rejection"], "enabled": False}})
  m0 = r1["unit"] == 0
  assert m0.sum() > 0 and np.allclose(r1["X"][m0], r2["X"][m0], atol=1e-9)
  # buggy variant: continuous filtering of the stepped record DOES change unit-0 epochs
  Xs = flt.cut_epochs(flt.bandpass_continuous(d2, taps, "odd", 771), r1["onset"][m0], 0, 204)[..., ::4]
  Xn = flt.cut_epochs(flt.bandpass_continuous(data, taps, "odd", 771), r1["onset"][m0], 0, 204)[..., ::4]
  assert not np.allclose(Xs, Xn, atol=1e-6)


def test_rejection_counts_per_class_and_criterion():
  """Known answer: a 400 uV spike planted in two label-1 epochs of unit 0 (ptp > 200) rejects
  exactly those two, counted under class 1 and criterion ptp."""
  data, events, _ = _file(rest=1200, amp=0.0)
  idx = np.flatnonzero((events["unit"] == 0) & (events["label"] == 1))[:2]
  for i in idx:
    data[:, events["onset"][i] + 100] += 400.0
  r = ep.prepare_file(data, FS, events, synth.erp_settings(FS))
  pc = r["counts"]["per_class"]
  assert pc[1]["rejected_by_ptp"] >= 2 and not r["keep"][idx].any()
  assert pc[0]["rejected"] + pc[1]["rejected"] == int((~r["keep"]).sum()) - pc[0]["out_of_bounds"] - pc[1]["out_of_bounds"]


def test_prepare_file_refuses_bad_event_tables():
  data, events, _ = _file(rest=1200)
  s = synth.erp_settings(FS)
  bad = dict(events)
  bad["unit_start"] = events["unit_start"][::-1]
  with pytest.raises(ValueError, match="time order"):
    ep.prepare_file(data, FS, bad, s)
  bad = {k: v for k, v in events.items() if k != "unit_end"}
  with pytest.raises(ValueError, match="lacks"):
    ep.prepare_file(data, FS, bad, s)


def test_window_gate_failure_is_reported():
  """Known answer: units 30 samples apart make the [-0.2, 1.0] s connectivity windows of
  consecutive units overlap: window gate fails and is reported (the runner stops on it)."""
  data, events, _ = _file(rest=30)
  s = synth.erp_settings(FS)
  s["rejection"]["enabled"] = False
  try:
    r = ep.prepare_file(data, FS, events, s)
  except ValueError:
    return  # used samples overlap: also a refusal
  assert r["gates"]["window__connectivity__passes"] is False


# ------------------------------------------------------------------ dataset
def _prep(rec, s):
  data, events, _ = rec
  return ep.prepare_file(data, FS, events, s)


def test_assembly_unit_uids_unique_across_files_and_hashes_detect_changes():
  """Known answer: three files of 3 units -> uids 0..8 (file f has 3f..3f+2); unit_file and
  unit_local_of_uid consistent; the epochs hash changes when one onset changes, the folds
  hash when one fold changes; the same inputs give the same hashes."""
  s = synth.erp_settings(FS)
  res = [_prep(synth.recording(seed, fs=FS, n_units=3, rest=1200), s) for seed in (1, 2, 3)]
  sess = ds.assemble(res)
  assert np.array_equal(np.unique(sess["unit_uid"]), np.arange(9))
  for i in range(len(sess["y"])):
    assert sess["unit_file"][sess["unit_uid"][i]] == sess["file_idx"][i]
    assert sess["unit_local_of_uid"][sess["unit_uid"][i]] == sess["unit_local"][i]
  names = ["a", "b", "c"]
  rows = ds.epoch_rows(sess, names)
  folds = fo.assign_unit_folds(sess["unit_file"], 3, 1).tolist()
  h1 = ds.epochs_and_folds_sha256(rows, [r["counts"] for r in res], names, folds)
  assert h1 == ds.epochs_and_folds_sha256(rows, [r["counts"] for r in res], names, folds)
  rows2 = [dict(r) for r in rows]
  rows2[5]["onset"] += 1
  assert ds.epochs_and_folds_sha256(rows2, [r["counts"] for r in res], names, folds)[0] != h1[0]
  f2 = list(folds)
  f2[0] = (f2[0] + 1) % 3
  assert ds.epochs_and_folds_sha256(rows, [r["counts"] for r in res], names, f2)[1] != h1[1]


def test_assembly_refuses_files_with_different_epoch_shapes():
  s = synth.erp_settings(FS)
  a = _prep(synth.recording(1, fs=FS, n_channels=4, rest=1200), s)
  b = _prep(synth.recording(2, fs=FS, n_channels=3, rest=1200), s)
  with pytest.raises(ValueError, match="shape"):
    ds.assemble([a, b])
