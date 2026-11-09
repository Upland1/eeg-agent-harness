"""Every parser and matcher of the kit tested with REAL identifiers (P300 Stage-2 lesson, 2026-11-09).

A pre-declared check in the P300 project parsed log lines with ``^(?P<method>\\S+): pooled BA``; the real F1 id
``f1/raw/Shrinkage-LDA lsqr`` has a space, so the check failed on real data, while its synthetic tests had used a
made-up id without one. Here the kit's matchers see the names real studies use: method ids with slashes, spaces,
hyphens and '+' (``f1/raw/Shrinkage-LDA lsqr``, ``f1/fbcsp+fbcca/...``), data parts with spaces
(``Sub-01/Session 1``) and file names like ``Training 5 - F.ebr`` (with a comma for CSV quoting).

Fails on v0.4-dev @ bed106f: ``eegharness.folds`` refused a fold key made from a real file or method name."""

import copy
import csv
import json
import sys
from pathlib import Path

import numpy as np
import pytest

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
from eegharness.folds import FoldStore  # noqa: E402
from eegpipe import classical as cl  # noqa: E402
from eegpipe.paired import natural_key  # noqa: E402
from eegpipe.runner import collect as col  # noqa: E402
from eegpipe.runner import methods as rm  # noqa: E402
from eegpipe.runner import select as sel  # noqa: E402
from eegpipe.runner import stage as stg  # noqa: E402
from eegpipe.testing import synth  # noqa: E402

FS = 256.0
F1 = "f1/raw/Shrinkage-LDA lsqr"
PART = "Sub-01/Session 1"
FILES = ["Training 5 - F.ebr", "Training 6 - F.ebr", "Training 7, repeat - F.ebr"]
REAL_KEYS = ["Training 5 - F.ebr", "Sub-01 Session 1 Training 5 - F", "f1__raw__Shrinkage-LDA lsqr",
             "fbcsp+fbcca seed=3", "Training 7, repeat - F (fold 2)"]


# ------------------------------------------------------------------ eegharness.folds
def test_fold_keys_accept_real_file_and_method_names(tmp_path):
  """Known answer: every real name in REAL_KEYS saves, is done, loads back with its meta and is listed by
  keys(). (bed106f: refused as 'invalid fold key', the regex allowed letters, digits, -_.= only.)"""
  store = FoldStore(tmp_path / "folds", {"m": 1})
  for i, k in enumerate(REAL_KEYS):
    store.save(k, meta={"i": i}, y=np.arange(3))
    assert store.done(k)
    arrays, meta = store.load(k)
    assert meta == {"i": i} and arrays["y"].tolist() == [0, 1, 2]
  assert sorted(store.keys()) == sorted(REAL_KEYS)


@pytest.mark.parametrize("key", ["", ".", "..", ".hidden", "a/b", "a\\b", "C:x", " lead", "trail ", "a*b", "a\nb"])
def test_fold_keys_still_refuse_paths_and_unsafe_names(tmp_path, key):
  with pytest.raises(ValueError, match="invalid fold key"):
    FoldStore(tmp_path / "folds", {"m": 1}).save(key, y=np.arange(2))


# ------------------------------------------------------------------ eegpipe id parsing
def test_method_ids_with_spaces_slashes_and_plus_parse():
  """The F1 id splits into family / space / model with the model's space kept; the union space keeps its '+'."""
  assert F1.split("/", 2) == ["f1", "raw", "Shrinkage-LDA lsqr"]
  assert rm.input_kind("f1/fbcsp+fbcca/Shrinkage-LDA lsqr") == "fb_both"
  assert rm.input_kind(F1) == "clf"
  prof = json.loads((TOOLS / "eegpipe" / "profiles" / "erp.json").read_text())
  est = cl.make_method(F1, {"f1": prof["f1"], "baseline": prof["baseline"]})
  assert hasattr(est, "fit")


def test_stage_slug_and_collect_part_names_with_spaces():
  assert stg.slug(PART) == "Sub-01__Session 1"
  assert col.part_methods({}, "f2__Shallow ConvNet v2") == ["f2/Shallow ConvNet v2"]


def test_selection_with_real_participant_part_and_file_names():
  """Known answer: excluded files are matched by the full name with spaces, either as '<part>/<file>' or as
  the file; participants sort naturally (Sub-2 < Sub-10); the draw uses the last digit run (Sub-01 -> 1)."""
  parts = [{"participant": "Sub-01", "part": "Sub-01/Session 1", "files": FILES[:2]},
           {"participant": "Sub-01", "part": "Sub-01/Session 2", "files": [FILES[2]]},
           {"participant": "Sub-10", "part": "Sub-10/Session 1", "files": FILES[:1]},
           {"participant": "Sub-2", "part": "Sub-2/Session 1", "files": FILES[1:2]}]
  rows = sel.evaluate(parts, {"excluded_files": ["Sub-01/Session 2/Training 7, repeat - F.ebr"],
                              "development_participants": []})
  bad = {r["part"]: r for r in rows}
  assert not bad["Sub-01/Session 2"]["eligible"] and "Training 7, repeat - F.ebr" in bad["Sub-01/Session 2"]["reasons"]
  assert all(r["eligible"] for r in rows if r["part"] != "Sub-01/Session 2")
  assert sorted(["Sub-10", "Sub-2", "Sub-01"], key=natural_key) == ["Sub-01", "Sub-2", "Sub-10"]
  assert sel.participant_number("Sub-01", []) == 1


# ------------------------------------------------------------------ runner end to end with real names
ADAPTER = '''
import numpy as np
from pathlib import Path

def dataset_parts(root):
  d = Path(root) / "Sub-01" / "Session 1"
  return [{"participant": "Sub-01", "part": "Sub-01/Session 1", "files": sorted(f"Sub-01/Session 1/{f.name}" for f in d.glob("*.ebr"))}]

def read(path):
  z = np.load(path)
  return z["data"], float(z["fs"]), [str(c) for c in z["ch"]]

def events(path, data, fs, ch, settings):
  z = np.load(path)
  return {k: z[k] for k in ("onset", "unit", "label", "unit_start", "unit_end", "code", "unit_target")}

def condition_of(path):
  return Path(path).stem.split(" - ")[-1]
'''


def test_runner_end_to_end_with_real_names(tmp_path):
  """Known answer: data part 'Sub-01/Session 1' with files 'Training 5 - F.ebr', 'Training 6 - F.ebr' and
  'Training 7, repeat - F.ebr' (the last excluded by its full name): per_file_tests.csv and per_file.csv name
  the two used files exactly (the comma survives CSV quoting), pooled.csv names the F1 method with its space."""
  d = tmp_path / "proj" / "data" / "raw" / "Sub-01" / "Session 1"
  d.mkdir(parents=True)
  for i, f in enumerate(FILES):
    data, events, info = synth.recording(700 + i, fs=FS, n_channels=4, n_units=6, n_epochs=24, isi=64, rest=1200,
                                         amp=2.0, unit_targets=np.arange(6) % 4)
    with open(d / f, "wb") as fh:   # np.savez to a handle keeps the real extension
      np.savez(fh, data=data, fs=FS, ch=np.array(info["ch_names"]), unit_target=info["unit_targets"], **events)
  (tmp_path / "proj" / "adapter_realnames.py").write_text(ADAPTER)
  epochs = synth.erp_settings(FS)
  epochs.pop("classes")
  epochs["rejection"]["enabled"] = False
  prof = json.loads((TOOLS / "eegpipe" / "profiles" / "erp.json").read_text())
  f1 = copy.deepcopy(prof["f1"])
  f1["feature_spaces"], f1["model_order"] = ["raw"], ["Shrinkage-LDA lsqr"]
  cfg = {
    "settings_version": 1, "classes": ["nontarget", "target"], "fs_hz": FS, "channels": ["C0", "C1", "C2", "C3"],
    "adapter": "adapter_realnames", "data_root": "data/raw", "label_scheme": "unit_target", "epochs": epochs,
    "folds": {"n_folds": 4, "seed": 20261107}, "baseline": copy.deepcopy(prof["baseline"]), "f1": f1,
    "permutation": {"methods": [F1], "n_permutations": 4, "seed": 20261105, "alpha": 0.05,
                    "critical_value_percentile": 95.0, "percentile_method": "linear", "n_jobs": 1, "chunk_size": 8},
    "statistics": copy.deepcopy(prof["statistics"]), "comparator": "baseline",
    "selection": {"seed": 1, "development_participants": ["Sub-00"], "reported_separately": [],
                  "excluded_files": [f"{PART}/{FILES[2]}"]},
    "stage": {"name": "confirmation", "scope": "primaries", "scopes": {"primaries": {}}, "job_timeout_hours": 0.2,
              "retry": {"max_attempts": 1}, "tracked": [], "selection_output": None,
              "part": "classical", "dataset_part": PART},
  }
  out = tmp_path / "out"
  out.mkdir()
  (out / "provenance.json").write_text(json.dumps({"commit_short": "test", "tracked_files_dirty": False}))
  res = rm.run(cfg, out, tmp_path / "proj")
  used = [f"{PART}/{f}" for f in FILES[:2]]
  assert res["files"] == used and res["methods"][F1].startswith("ok")
  tests = list(csv.DictReader(open(out / "per_file_tests.csv")))
  assert [(r["method"], r["file"]) for r in tests] == [(F1, used[0]), (F1, used[1])]
  assert {r["file"] for r in csv.DictReader(open(out / "per_file.csv"))} == set(used)
  assert F1 in {r["method"] for r in csv.DictReader(open(out / "pooled.csv"))}
  assert {r["condition"] for r in csv.DictReader(open(out / "per_condition.csv"))} == {"F"}
