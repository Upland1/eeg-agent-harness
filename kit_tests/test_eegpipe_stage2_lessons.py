"""Known-answer tests for two lessons from the P300 Stage-2 run (ended 2026-11-09), checked in the v0.4 method
library. Each test fails on v0.4-dev @ 01d9573 (shown in the commit that added it) and passes after the fix:
  1. a file with 0 used epochs (every epoch rejected) gets a per-file test row with status no_used_epochs and
     BA NaN, enters Holm as p = 1, and the Holm family stays equal to all files (P300 D-018). The number of
     files is never taken from max(file_idx) + 1, and the null's width is checked explicitly, so an empty
     file can neither drop out nor shift the other files onto the wrong null column (with an empty last file,
     the session-level pooled column could be read as that file's null);
  2. a file whose used epochs are all one class has a NaN BA; it is untestable and enters Holm as p = 1
     instead of permutation_p(NaN) = 1 / (n + 1), the minimum p (P300 DEV-2). permutation_p refuses a
     non-finite observed value."""

import copy
import csv
import json
import sys
from pathlib import Path

import numpy as np
import pytest

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
from eegpipe import dataset as ds  # noqa: E402
from eegpipe import evaluate as evl  # noqa: E402
from eegpipe.runner import methods as rm  # noqa: E402
from eegpipe.testing import synth  # noqa: E402

BIN = ["nontarget", "target"]
FS = 256.0


def _null19():
  """The hand-derived null of test_per_stratum_tests_known_answer: column 0 gives p = 0.05 at 0.9,
  column 1 gives p = 0.5 at 0.5 (n_perm 19)."""
  null = np.zeros((19, 2))
  null[:, 0] = 0.40 + 0.01 * np.arange(19)
  null[:, 1] = [0.5] * 9 + [0.4] * 10
  return null


# ------------------------------------------------------------------ 2. one-class file, permutation_p(NaN)
def test_permutation_p_refuses_a_nan_observed_value():
  """Known answer: permutation_p(NaN, null) used to return 1 / (n + 1) (no null value is >= NaN), the
  minimum p; it now refuses."""
  with pytest.raises(ValueError, match="not finite"):
    evl.permutation_p(float("nan"), np.linspace(0.3, 0.7, 19))


def test_one_class_file_is_untestable_and_enters_holm_as_one():
  """Known answer: strata (p 0.05, one class only, p 0.5): the one-class stratum has status missing_class,
  p NaN, p entering Holm 1, no decision; Holm over m = 3: (0.15, 1, 1). Without the rule the NaN BA would
  get p = 0.05 and Holm (0.15, 0.15, 0.5)."""
  null = np.column_stack([_null19()[:, 0], np.full(19, 0.5), _null19()[:, 1]])
  counts = np.array([[30, 10], [0, 12], [30, 10]])
  rows = evl.per_stratum_tests(np.array([0.9, np.nan, 0.5]), null, [10, 1, 1000], 0.05, 95.0, "linear",
                               class_counts=counts)
  assert [r["status"] for r in rows] == ["ok", "missing_class", "ok"]
  assert np.isnan(rows[1]["perm_p_monte_carlo"]) and rows[1]["perm_p_entering_holm"] == 1.0
  assert [r["perm_p_holm"] for r in rows] == pytest.approx([0.15, 1.0, 1.0], abs=1e-12)
  assert [r["holm_m"] for r in rows] == [3, 3, 3]
  assert not any(r["above_chance_holm"] for r in rows)
  assert rows[0]["perm_p_monte_carlo"] == pytest.approx(0.05) and rows[2]["perm_p_monte_carlo"] == pytest.approx(0.5)


def test_nan_ba_without_class_counts_is_refused():
  """A NaN observed BA needs the class counts to say why it is NaN; without them the call refuses."""
  null = np.column_stack([_null19()[:, 0], np.full(19, 0.5)])
  with pytest.raises(ValueError, match="class_counts"):
    evl.per_stratum_tests(np.array([0.9, np.nan]), null, [10, 1], 0.05, 95.0, "linear")


# ------------------------------------------------------------------ 1. empty file, width check
def test_empty_file_gets_a_row_and_the_family_keeps_every_file():
  """Known answer (D-018): strata (p 0.05, 0 used epochs, p 0.5): status no_used_epochs, BA NaN, p entering
  Holm 1, null mean and critical value NaN; Holm over m = 3: (0.15, 1, 1)."""
  null = np.column_stack([_null19()[:, 0], np.full(19, np.nan), _null19()[:, 1]])
  counts = np.array([[30, 10], [0, 0], [30, 10]])
  rows = evl.per_stratum_tests(np.array([0.9, np.nan, 0.5]), null, [10, 1, 1000], 0.05, 95.0, "linear",
                               class_counts=counts)
  assert [r["status"] for r in rows] == ["ok", "no_used_epochs", "ok"]
  assert rows[1]["n_used_epochs"] == 0 and rows[1]["perm_p_entering_holm"] == 1.0
  assert np.isnan(rows[1]["null_ba_mean"]) and np.isnan(rows[1]["null_ba_critical"])
  assert [r["perm_p_holm"] for r in rows] == pytest.approx([0.15, 1.0, 1.0], abs=1e-12)


@pytest.mark.parametrize("width", [1, 3])
def test_null_width_must_equal_the_number_of_strata(width):
  """The null must have one column per stratum: a null that still holds the pooled column (width 3 for two
  strata) or lacks a stratum (width 1) is refused instead of read by position."""
  null = np.full((19, width), 0.5)
  with pytest.raises(ValueError, match="columns"):
    evl.per_stratum_tests(np.array([0.9, 0.5]), null, [10, 10], 0.05, 95.0, "linear")


def _session_with_empty_file(pos):
  """Three files of 2 units x 8 epochs (unit_target), the file at ``pos`` with every epoch rejected."""
  rng = np.random.default_rng(7)
  res = []
  for f in range(3):
    n = 0 if f == pos else 16
    unit = np.repeat([0, 1], 8)[:n]
    res.append({"X": rng.normal(size=(n, 4, 20)), "y": np.tile([0, 0, 0, 1], 4)[:n], "unit": unit,
                "onset": np.arange(n) * 64, "unit_start": np.array([0, 600]), "unit_end": np.array([500, 1100]),
                "code": np.tile([0, 1, 2, 3], 4)[:n]})
  return ds.assemble(res)


@pytest.mark.parametrize("pos", [0, 2])
def test_assembled_session_counts_files_not_max_file_idx(pos, monkeypatch):
  """Known answer: three files, one with 0 used epochs (first or last): the session has n_files 3 and
  per_stratum_ba (oracle predictions) returns 3 BAs, NaN at the empty file and 1.0 elsewhere. (01d9573: no
  n_files; max(file_idx) + 1 gives 2 BAs for an empty last file, so the pooled column of the null became
  that file's column.)"""
  sess = _session_with_empty_file(pos)
  assert sess["n_files"] == 3 and evl.n_strata(sess) == 3
  y = sess["y"]
  monkeypatch.setattr(evl, "cv_predict", lambda X, yy, splits, make_est, names: (yy.copy(), None, []))
  ba, pooled = evl.per_stratum_ba(sess, y, [], None, BIN)
  assert ba.shape == (3,) and np.isnan(ba[pos]) and np.all(ba[np.arange(3) != pos] == 1.0) and pooled == 1.0


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
  return {k: z[k] for k in ("onset", "unit", "label", "unit_start", "unit_end", "code", "unit_target")}

def condition_of(path):
  return Path(path).stem
'''


def _write(path, seed, scale):
  data, events, info = synth.recording(seed, fs=FS, n_channels=4, n_units=6, n_epochs=24, isi=64, rest=1200, amp=2.0,
                                       unit_targets=np.arange(6) % 4)
  path.parent.mkdir(parents=True, exist_ok=True)
  np.savez(path, data=data * scale, fs=FS, ch=np.array(info["ch_names"]), unit_target=info["unit_targets"],
           **{k: v for k, v in events.items()})


def _cfg(scheme="unit_target"):
  epochs = synth.erp_settings(FS)
  epochs.pop("classes")
  prof = json.loads((TOOLS / "eegpipe" / "profiles" / "erp.json").read_text())
  f1 = copy.deepcopy(prof["f1"])
  f1["feature_spaces"], f1["model_order"] = ["raw"], ["Shrinkage-LDA lsqr"]
  return {
    "settings_version": 1, "classes": BIN, "fs_hz": FS, "channels": ["C0", "C1", "C2", "C3"],
    "adapter": "adapter_lessons", "data_root": "data/raw", "label_scheme": scheme, "epochs": epochs,
    "folds": {"n_folds": 4, "seed": 20261107}, "baseline": copy.deepcopy(prof["baseline"]), "f1": f1,
    "permutation": {"methods": ["baseline"], "n_permutations": 4, "seed": 20261105, "alpha": 0.05,
                    "critical_value_percentile": 95.0, "percentile_method": "linear", "n_jobs": 1, "chunk_size": 8},
    "statistics": copy.deepcopy(prof["statistics"]), "comparator": "baseline",
    "selection": {"seed": 1, "development_participants": ["P0"], "excluded_files": [], "reported_separately": []},
    "stage": {"name": "confirmation", "scope": "primaries", "scopes": {"primaries": {}}, "job_timeout_hours": 0.2,
              "retry": {"max_attempts": 1}, "tracked": [], "selection_output": None,
              "part": "classical", "dataset_part": "P1/s1"},
  }


def _out(tmp_path):
  out = tmp_path / "out"
  out.mkdir()
  (out / "provenance.json").write_text(json.dumps({"commit_short": "test", "tracked_files_dirty": False}))
  return out


@pytest.mark.parametrize("empty", ["f0", "f2"])
def test_runner_writes_a_row_for_a_file_with_every_epoch_rejected(tmp_path, empty):
  """Known answer (end to end, rm.run): three files, one (first or last) scaled x 1e4 so the artifact screen
  rejects every epoch: per_file_tests.csv has 3 rows in file order, the empty file has status no_used_epochs,
  BA NaN and p entering Holm 1, the others are ok with finite p; Holm m = 3 on every row; the empty file's
  per_file.csv row has n = 0. (01d9573: the shuffle refused the empty file's units, which have no codes, so
  the step stopped; behind it, an empty first file would have shifted every other file onto the previous
  file's null column, and an empty last file would have had no row and a family of 2.)"""
  root = tmp_path / "proj"
  for i, f in enumerate(["f0", "f1", "f2"]):
    _write(root / "data" / "raw" / "P1" / "s1" / f"{f}.npz", 500 + i, 1e4 if f == empty else 1.0)
  (root / "adapter_lessons.py").write_text(ADAPTER)
  cfg = _cfg()
  out = _out(tmp_path)
  rm.run(cfg, out, root)
  rows = list(csv.DictReader(open(out / "per_file_tests.csv")))
  assert [r["file"] for r in rows] == ["P1/s1/f0.npz", "P1/s1/f1.npz", "P1/s1/f2.npz"]
  for r in rows:
    assert int(r["holm_m"]) == 3
    if r["file"].endswith(f"{empty}.npz"):
      assert r["status"] == "no_used_epochs" and np.isnan(float(r["observed_ba"]))
      assert float(r["perm_p_entering_holm"]) == 1.0 and float(r["perm_p_holm"]) == 1.0
      assert r["above_chance_holm"] == "False"
    else:
      assert r["status"] == "ok" and np.isfinite(float(r["observed_ba"]))
      assert 1 / 5 - 1e-12 <= float(r["perm_p_monte_carlo"]) <= 1.0
  pf = {r["file"]: r for r in csv.DictReader(open(out / "per_file.csv")) if r["method"] == "baseline"}
  assert set(pf) == {r["file"] for r in rows}
  assert int(pf[f"P1/s1/{empty}.npz"]["n_target"]) == 0 and int(pf[f"P1/s1/{empty}.npz"]["n_nontarget"]) == 0


# ------------------------------------------------------------------ known broken in v0.4 (unit_label)
@pytest.mark.xfail(strict=True, raises=IndexError,
                   reason="KNOWN BROKEN in v0.4 (CHANGELOG): under label_scheme unit_label (SSVEP trials) a unit with "
                          "0 used epochs stops the run (its label is unknown: IndexError in the runner's unit labels "
                          "for fold balancing; evaluate.unit_values refuses it next); deferred by decision 2026-11-09")
def test_unit_label_unit_with_every_epoch_rejected_runs(tmp_path):
  """The failing case: two files of 8 two-class trials (unit_label), the first trial of f0 scaled x 1e4 so the
  artifact screen rejects all its epochs. Wanted: the run completes with one test row per file. Today it
  stops; strict xfail, so a fix makes this test fail until the marker is removed."""
  root = tmp_path / "proj"
  for i, f in enumerate(["f0", "f1"]):
    data, events, info = synth.recording(600 + i, fs=FS, n_channels=4, n_units=8, n_epochs=6, isi=64, rest=1200,
                                         amp=2.0, scheme="per_unit", unit_classes=[0, 1] * 4)
    if f == "f0":
      data[:, events["unit_start"][0] - 300:events["unit_end"][0] + 300] *= 1e4
    path = root / "data" / "raw" / "P1" / "s1" / f"{f}.npz"
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(path, data=data, fs=FS, ch=np.array(info["ch_names"]), unit_target=np.zeros(8, dtype=np.int64),
             **{k: v for k, v in events.items()})
  (root / "adapter_lessons.py").write_text(ADAPTER)
  out = _out(tmp_path)
  rm.run(_cfg("unit_label"), out, root)
  rows = list(csv.DictReader(open(out / "per_file_tests.csv")))
  assert len(rows) == 2 and all(r["status"] == "ok" for r in rows)
