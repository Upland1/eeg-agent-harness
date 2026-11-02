"""Known-answer tests for the profiler. Synthetic files only; answers fixed before the code runs."""

import json
import sys
import textwrap
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from eegprofile.profile import normalized, profile_dataset, shape_of  # noqa: E402
from eegprofile.recording import Recording  # noqa: E402
import run_profile  # noqa: E402

FS = 128.0
PLUGIN = textwrap.dedent('''
  import numpy as np
  from eegprofile.recording import Recording
  EXTENSIONS = (".syn",)
  def read(path):
    z = np.load(path, allow_pickle=False)
    return Recording(data=z["data"], fs=float(z["fs"]), ch_names=list(z["ch"]),
                     events=z["events"], durations=z["dur"])
''')


def write_syn(path, events, n=1280, fs=FS, nch=3, flat=None):
  rng = np.random.default_rng(0)
  data = rng.normal(size=(nch, n))
  if flat is not None:
    data[flat] = 0.0
  path.parent.mkdir(parents=True, exist_ok=True)
  ev = np.asarray(events, dtype=int)
  with open(path, "wb") as fh:
    np.savez(fh, data=data, fs=fs, ch=np.array([f"C{i}" for i in range(nch)]),
             events=ev, dur=np.full(len(ev), 13))


@pytest.fixture()
def dataset(tmp_path):
  root = tmp_path / "raw"
  # Known answer: code 1 every 32 samples (250 ms at 128 Hz), code 9 once at sample 0.
  ev = [(0, 9)] + [(64 + 32 * k, 1) for k in range(10)]
  write_syn(root / "S1" / "06-19-19" / "Run 5.syn", ev)
  write_syn(root / "S2" / "07-01-19" / "run 5.syn", ev, flat=1)
  write_syn(root / "S10" / "02-17-2020" / "Run 5-F.syn", ev)
  (root / "S10" / "02-17-2020" / "notes.xyz").write_text("not a recording")
  (root / "S2" / "07-01-19" / "Broken 5.syn").write_bytes(b"garbage")
  plug = tmp_path / "plugins" / "syn.py"
  plug.parent.mkdir()
  plug.write_text(PLUGIN)
  return root, plug


def test_shapes_and_normalization():
  """Known answer: digits -> '#'; case, spaces, '-' and '_' are ignored by normalized()."""
  assert shape_of("S12") == "S##" and shape_of("02-17-2020") == "##-##-####"
  assert normalized("Training 5-F") == normalized("training 5 - F")


def test_event_counts_intervals_transitions(dataset):
  """Known answer: 10 events of code 1, 250 ms apart; 9->1 gap 500 ms; durations 13 samples = 101.5625 ms."""
  root, plug = dataset
  prof = profile_dataset(root, plugins=[plug], use_mne=False)
  f = next(x for x in prof["files"] if x["path"].endswith("Run 5.syn") and "S1" in x["path"])
  c1 = f["profile"]["codes"]["1"]
  assert c1["count"] == 10
  assert c1["interval_same_code_ms"]["median"] == pytest.approx(250.0)
  assert c1["duration_ms"]["median"] == pytest.approx(13 * 1000 / FS)
  t = f["profile"]["transitions"]
  assert t["9->1"]["count"] == 1 and t["9->1"]["gap_ms"]["median"] == pytest.approx(500.0)
  assert t["1->1"]["count"] == 9
  assert f["profile"]["fs"] == FS and f["profile"]["duration_s"] == pytest.approx(10.0)


def test_structure_spelling_and_failures(dataset):
  """Known answer: 3 profiled, 1 reader error, 1 file without reader; shapes S#/S##; spelling variants Run 5 / run 5 found; flat channel flagged."""
  root, plug = dataset
  prof = profile_dataset(root, plugins=[plug], use_mne=False)
  s = prof["summary"]
  assert (s["n_files"], s["n_profiled"], s["n_unreadable"], s["n_no_reader"]) == (5, 3, 1, 1)
  lvl0 = {x["shape"] for x in prof["structure"]["folder_levels"][0]["name_shapes"]}
  lvl1 = {x["shape"] for x in prof["structure"]["folder_levels"][1]["name_shapes"]}
  assert lvl0 == {"S#", "S##"} and lvl1 == {"##-##-##", "##-##-####"}
  assert prof["structure"]["spelling_variants"] == [["Run 5", "run 5"]]  # "Run 5-F" is a different name
  s2 = next(x for x in prof["files"] if x["path"].endswith("run 5.syn"))
  assert [c["flat"] for c in s2["profile"]["channels"]] == [False, True, False]
  assert s["codes"]["1"] == {"n_files": 3, "total_count": 30,
                             "median_of_file_medians_same_code_interval_ms": 250.0}


def test_validate_rejects_bad_events():
  """Known answer: an event beyond the last sample and unsorted events are rejected."""
  rec = Recording(data=np.zeros((2, 100)), fs=100.0, ch_names=["a", "b"], events=np.array([[150, 1]]))
  with pytest.raises(ValueError):
    rec.validate()
  rec.events = np.array([[50, 1], [10, 2]])
  with pytest.raises(ValueError):
    rec.validate()


def test_mne_fif_round_trip(tmp_path):
  """Known answer: a FIF file written by MNE at 200 Hz with stim pulses at samples 100 and 300 (code 5)."""
  mne = pytest.importorskip("mne")
  data = np.zeros((3, 1000))
  data[2, 100:103] = 5
  data[2, 300:303] = 5
  info = mne.create_info(["Cz", "Pz", "STI"], 200.0, ["eeg", "eeg", "stim"])
  root = tmp_path / "raw"
  root.mkdir()
  mne.io.RawArray(data, info, verbose="error").save(root / "x_raw.fif", verbose="error")
  prof = profile_dataset(root)
  f = prof["files"][0]["profile"]
  assert f["fs"] == 200.0
  assert f["codes"]["5"]["count"] == 2
  assert f["codes"]["5"]["interval_same_code_ms"]["median"] == pytest.approx(1000.0)


def test_cli_writes_outputs_and_refuses_inside_data(dataset, tmp_path):
  """Known answer: JSON and MD are written outside the data folder; an output inside it is refused."""
  root, plug = dataset
  out = tmp_path / "docs" / "DATA_PROFILE"
  assert run_profile.main(["--data", str(root), "--out", str(out), "--plugin", str(plug), "--no-mne"]) == 0
  assert json.loads(out.with_suffix(".json").read_text())["summary"]["n_profiled"] == 3
  assert "| 1 | 3 | 30 | 250.0 |" in out.with_suffix(".md").read_text()
  with pytest.raises(SystemExit):
    run_profile.main(["--data", str(root), "--out", str(root / "p"), "--no-mne"])
