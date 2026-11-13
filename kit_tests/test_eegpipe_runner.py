"""Known-answer tests for eegpipe.runner (select, stage, methods, collect) and eegpipe.settings, moved
from the P300 project (tests @ d833264, ``tests/test_stage2.py`` runner and selection tests,
``tests/test_stage2_review.py`` selection and refusal tests) onto a synthetic study: a throwaway
git project with the vendored packages, a synthetic adapter and recordings written as .npz."""

import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
from eegpipe import settings as st  # noqa: E402
from eegpipe.runner import collect as col  # noqa: E402
from eegpipe.runner import select as sel  # noqa: E402
from eegpipe.runner import stage as stg  # noqa: E402
from eegpipe.testing import synth  # noqa: E402

PROFILE = json.loads((TOOLS / "eegpipe" / "profiles" / "erp.json").read_text())
FS = 256.0
ADAPTER = '''
import numpy as np
from pathlib import Path

def dataset_parts(root):
  root = Path(root)
  out = []
  for p in sorted(d.name for d in root.iterdir() if d.is_dir()):
    for s in sorted(d.name for d in (root / p).iterdir() if d.is_dir()):
      out.append({"participant": p, "part": f"{p}/{s}", "files": sorted(f"{p}/{s}/{f.name}" for f in (root / p / s).glob("*.npz"))})
  return out

def read(path):
  z = np.load(path)
  return z["data"], float(z["fs"]), [str(c) for c in z["ch"]]

def events(path, data, fs, ch, settings):
  z = np.load(path)
  return {k: z[k] for k in ("onset", "unit", "label", "unit_start", "unit_end", "code", "unit_target")}

def condition_of(path):
  return Path(path).stem
'''


def write_recording(path, seed, amp):
  data, events, info = synth.recording(seed, fs=FS, n_channels=4, n_units=6, n_epochs=24, isi=64, rest=1200, amp=amp,
                                       unit_targets=np.arange(6) % 4)
  path.parent.mkdir(parents=True, exist_ok=True)
  np.savez(path, data=data, fs=FS, ch=np.array(info["ch_names"]), unit_target=info["unit_targets"],
           **{k: v for k, v in events.items()})


def settings_for(selection_output=None, n_perm=4):
  epochs = synth.erp_settings(FS)
  epochs["rejection"]["enabled"] = False
  epochs.pop("classes")
  f1 = copy.deepcopy(PROFILE["f1"])
  f1["feature_spaces"], f1["model_order"] = ["raw"], ["Shrinkage-LDA lsqr"]
  stats = copy.deepcopy(PROFILE["statistics"])
  stats["holm_family"], stats["min_n"] = ["f1/raw/Shrinkage-LDA lsqr"], 3
  stats["bootstrap"]["n_resamples"] = 200
  return {
    "settings_version": 1, "classes": ["nontarget", "target"], "fs_hz": FS, "channels": ["C0", "C1", "C2", "C3"],
    "adapter": "adapter", "data_root": "data/raw", "label_scheme": "unit_target", "epochs": epochs,
    "folds": {"n_folds": 4, "seed": 20261107}, "baseline": copy.deepcopy(PROFILE["baseline"]), "f1": f1,
    "permutation": {"methods": ["baseline"], "n_permutations": n_perm, "seed": 20261105, "alpha": 0.05,
                    "critical_value_percentile": 95.0, "percentile_method": "linear", "n_jobs": 1, "chunk_size": 8},
    "statistics": stats, "comparator": "baseline",
    "selection": {"seed": 20261111, "development_participants": ["P1"], "excluded_files": ["P3/s2/f0.npz"],
                  "reported_separately": ["P6"]},
    "stage": {"name": "confirmation", "scope": "primaries", "scopes": {"primaries": {}}, "job_timeout_hours": 0.2,
              "retry": {"max_attempts": 2}, "tracked": ["eegpipe", "eegharness", "configs", "adapter.py"],
              "selection_output": selection_output},
  }


def git(proj, *args):
  return subprocess.run(["git", "-C", str(proj), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                        capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture(scope="module")
def project(tmp_path_factory):
  proj = tmp_path_factory.mktemp("proj")
  for pkg in ("eegpipe", "eegharness"):
    shutil.copytree(TOOLS / pkg, proj / pkg, ignore=shutil.ignore_patterns("__pycache__"))
  (proj / "adapter.py").write_text(ADAPTER)
  (proj / ".gitignore").write_text("data/\noutputs/\n__pycache__/\n")
  for i, p in enumerate(["P1", "P2", "P3", "P4", "P5", "P6"]):
    for s in ("s1", "s2"):
      for f in range(2):
        write_recording(proj / "data" / "raw" / p / s / f"f{f}.npz", 1000 + 10 * i + 2 * (s == "s2") + f, 2.0)
  (proj / "configs").mkdir()
  (proj / "configs" / "pipeline.json").write_text(json.dumps(settings_for()))
  git(proj, "init", "-q", "-b", "main")
  git(proj, "add", "-A")
  git(proj, "commit", "-qm", "project")
  return proj


def run_select(proj):
  cfg = json.loads((proj / "configs" / "pipeline.json").read_text())
  sys.path.insert(0, str(proj))
  try:
    import importlib
    adapter = importlib.import_module("adapter")
    importlib.reload(adapter)
    return sel.select(cfg, adapter, proj)
  finally:
    sys.path.remove(str(proj))


def test_selection_never_picks_development_or_excluded_and_is_reproducible(project):
  """Known answer: P1 (development) never drawn; P3/s2 (excluded file) ineligible so P3 gets s1; each
  participant's draw = sorted(eligible)[default_rng([seed, number]).integers(0, n)], independent of the
  others; P6 is 'reported_separately'; the same inputs give the same selection."""
  a = run_select(project)
  b = run_select(project)
  assert a == b and "P1" not in {s["participant"] for s in a["stage2_parts"]}
  assert {s["part"] for s in a["stage2_parts"] if s["participant"] == "P3"} == {"P3/s1"}
  for d in a["draws"]:
    if d["chosen"]:
      k = int(np.random.default_rng([20261111, int(d["participant"][1:])]).integers(0, len(d["eligible_sorted"])))
      assert d["chosen"] == d["eligible_sorted"][k]
  assert {s["participant"]: s["role"] for s in a["stage2_parts"]}["P6"] == "reported_separately"
  assert "development participant" in a["excluded"]["P1/s1"]


def test_settings_validation_refuses_and_lists_unconfirmed_profile_defaults():
  """Known answer: a complete settings dict validates (no sources required) ; missing a required key,
  an unknown key, priors of the wrong length, the comparator inside the Holm family, an SSVEP section
  without one frequency per class, fewer than 3 network seeds, and a missing source each raise;
  profile defaults are listed until confirmed in the plan."""
  cfg = settings_for()
  assert st.validate(cfg, require_sources=False) == []
  for mutate, msg in ((lambda c: c.pop("folds"), "folds"), (lambda c: c.update(bogus=1), "bogus"),
                      (lambda c: c["f1"]["models"]["LDA svd"]["params"].update(priors=[1.0]), "priors"),
                      (lambda c: c["statistics"].update(holm_family=["baseline"]), "comparator"),
                      (lambda c: c.update(ssvep={"enabled": True, "stimulus_freqs_hz": [8.0]}), "stimulus_freqs"),
                      (lambda c: c.update(networks={"enabled": True, "seeds": [1, 2]}), "3 seeds")):
    c = copy.deepcopy(cfg)
    mutate(c)
    with pytest.raises(st.SettingsError, match=msg):
      st.validate(c, require_sources=False)
  with pytest.raises(st.SettingsError, match="no source"):
    st.validate(cfg, require_sources=True)
  c = copy.deepcopy(cfg)
  c["sources"] = {k: "plan" for k in st.required_sources(c)}
  c["sources"]["folds.seed"] = "profile:erp"
  assert st.validate(c) == ["folds.seed"]
  c["sources"]["folds.seed"] = "profile:erp, confirmed in plan"
  assert st.validate(c) == []
  assert "| `classes` |" in st.table(c)


def freeze(project, tmp):
  """Selection written into the project, settings pointing at it, committed (the freeze)."""
  from eegharness.outputs import new_output_dir
  res = run_select(project)
  out = new_output_dir(project / "configs" / "selection", inputs=[project / "configs" / "pipeline.json"], root=project)
  (out / "selection.json").write_text(json.dumps(res, indent=1))
  cfg = settings_for(str(out.relative_to(project)))
  (project / "configs" / "pipeline.json").write_text(json.dumps(cfg))
  git(project, "add", "-A")
  git(project, "commit", "-qm", "freeze")
  return cfg


def test_stage_end_to_end_resume_and_collect(project, tmp_path):
  """Known answer: the stage runner runs the classical part for every selected data part through
  real child processes, each done with matching provenance and identical epochs/folds hashes; a
  second invocation skips every terminal part; collect gives a confirmatory analysis whose test
  row has n = number of confirmatory participants with valid scores (P6 separate); a dirty tree is
  refused."""
  freeze(project, tmp_path)
  out = tmp_path / "stage"
  argv = ["--config", str(project / "configs" / "pipeline.json"), "--out", str(out), "--root", str(project)]
  root = stg.main(argv)
  idx = json.loads((root / "index.json").read_text())["parts"]
  assert idx and all(r["status"] == "done" for r in idx), idx
  first = {r["data_part"]: r["outdir"] for r in idx}
  root2 = stg.main(argv)
  assert root2 == root and {r["data_part"]: r["outdir"] for r in json.loads((root / "index.json").read_text())["parts"]} == first
  outdir = col.main(["--stage", str(root), "--out", str(tmp_path / "stats"), "--root", str(project)])
  tests = list(__import__("csv").DictReader(open(outdir / "tests.csv")))
  n_conf = sum(r["role"] == "confirmatory" for r in idx)
  assert len(tests) == 1 and int(tests[0]["n"]) == n_conf and tests[0]["run_status"].startswith("confirmatory")
  res = json.loads((Path(first[idx[0]["data_part"]]) / "results.json").read_text())
  assert res["methods"]["baseline"].startswith("ok") and res["tracked_files_dirty"] is False
  pft = list(__import__("csv").DictReader(open(Path(first[idx[0]["data_part"]]) / "per_file_tests.csv")))
  assert len(pft) == 2 and all(float(r["perm_p_monte_carlo"]) >= 1 / 5 - 1e-12 for r in pft)
  from eegharness.outputs import check_compute_time  # 0.5.0 (L37): every kit writer records its compute time
  sel_out = sel.main(["--config", str(project / "configs" / "pipeline.json"), "--out", str(tmp_path / "sel"),
                      "--root", str(project)])
  for folder in [*first.values(), outdir, sel_out]:
    assert check_compute_time(folder) == [], folder
    ct = json.loads((Path(folder) / "provenance.json").read_text())["compute_time"]
    assert ct["wall_s"] > 0 and ct["device"] == "cpu"
  (project / "adapter.py").write_text(ADAPTER + "\n# edit\n")
  with pytest.raises(SystemExit, match="clean, frozen commit"):
    stg.main(argv)
  git(project, "checkout", "--", "adapter.py")


STG_COMMIT = "abc1234"


def _fake_child(behaviour, commit=STG_COMMIT):
  """A stage child that writes a complete or failing part per ``behaviour``; it reports ``commit``."""
  def command(cpath, pdir, root):
    code = f'''
import json, sys, time, pathlib, hashlib
cfg = json.loads(pathlib.Path({str(cpath)!r}).read_text())
mode = {behaviour!r}
pdir = pathlib.Path({str(pdir)!r})
n = len([d for d in pdir.iterdir() if d.is_dir()])
n_logs = len(list(pdir.glob("attempt_*.log")))
if mode == "fail" or (mode == "fail_once" and n_logs == 1):
  sys.exit(3)
if mode == "sleep":
  time.sleep(30)
out = pdir / f"run{{n}}"
out.mkdir()
canon = json.dumps(cfg, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
(out / "config_used.json").write_text(json.dumps(cfg))
commit = {commit!r}
(out / "results.json").write_text(json.dumps({{"commit": commit, "tracked_files_dirty": False,
   "epochs_sha256": "e" if mode != "hash" else "x", "folds_sha256": "f"}}))
(out / "pooled.csv").write_text("method,seed,status,ba\\nbaseline,,ok,0.6\\n")
(out / "summary.txt").write_text("ok\\n")
'''
    return [sys.executable, "-c", code]
  return command



def _stage_world(tmp_path, behaviour, timeout_h=0.2):
  sel_dir = tmp_path / "sel"
  sel_dir.mkdir(parents=True)
  (sel_dir / "selection.json").write_text(json.dumps({"chosen_parts": ["P2/s1"], "stage2_parts": [
    {"participant": "P2", "part": "P2/s1", "role": "confirmatory", "files": ["P2/s1/f0.npz"]}]}))
  cfg = settings_for(str(sel_dir))
  cfg["stage"]["job_timeout_hours"] = timeout_h
  cp = tmp_path / "pipeline.json"
  cp.write_text(json.dumps(cfg))
  return ["--config", str(cp), "--out", str(tmp_path / "out"), "--root", str(tmp_path)], _fake_child(behaviour)


def test_runner_isolates_a_failure_retries_once_and_then_never_again(tmp_path):
  argv, child = _stage_world(tmp_path, "fail")
  with pytest.raises(SystemExit):
    stg.main(argv, git=lambda: (STG_COMMIT, False), command=child)
  st0 = json.loads(next((tmp_path / "out").rglob("part_status.json")).read_text())
  assert st0["status"] == "failed" and st0["n_attempts"] == 2
  with pytest.raises(SystemExit):
    stg.main(argv, git=lambda: (STG_COMMIT, False), command=child)
  assert json.loads(next((tmp_path / "out").rglob("part_status.json")).read_text())["n_attempts"] == 2   # terminal


def test_runner_retry_succeeds(tmp_path):
  argv, child = _stage_world(tmp_path, "fail_once")
  root = stg.main(argv, git=lambda: (STG_COMMIT, False), command=child)
  st0 = json.loads(next(root.rglob("part_status.json")).read_text())
  assert st0["status"] == "done" and st0["n_attempts"] == 2


def test_runner_timeout_is_retried_once_and_kills_the_job(tmp_path):
  argv, child = _stage_world(tmp_path, "sleep", timeout_h=1.0 / 3600)
  with pytest.raises(SystemExit):
    stg.main(argv, git=lambda: (STG_COMMIT, False), command=child)
  st0 = json.loads(next((tmp_path / "out").rglob("part_status.json")).read_text())
  assert st0["status"] == "timeout" and st0["n_attempts"] == 2 and st0["seconds"] < 25


def test_runner_stops_on_a_changed_tree_and_on_provenance_mismatch(tmp_path):
  argv, child = _stage_world(tmp_path, "ok")
  calls = iter([(STG_COMMIT, False), (STG_COMMIT, False), ("zzz9999", False)])
  with pytest.raises(RuntimeError, match="tree changed"):
    stg.main(argv, git=lambda: next(calls), command=child)
  with pytest.raises(SystemExit, match="provenance failure"):
    stg.main(argv, git=lambda: (STG_COMMIT, False), command=child)
  argv2, _ = _stage_world(tmp_path / "b", "ok")
  child_bad = _fake_child("ok", commit="other00")
  with pytest.raises(RuntimeError, match="provenance check failed"):
    stg.main(argv2, git=lambda: (STG_COMMIT, False), command=child_bad)


def test_runner_refuses_development_participant_excluded_file_and_dirty_tree(tmp_path):
  argv, child = _stage_world(tmp_path, "ok")
  with pytest.raises(SystemExit, match="clean, frozen"):
    stg.main(argv, git=lambda: (STG_COMMIT, True), command=child)
  s = json.loads((tmp_path / "sel" / "selection.json").read_text())
  s["stage2_parts"][0]["participant"] = "P1"
  (tmp_path / "sel" / "selection.json").write_text(json.dumps(s))
  with pytest.raises(ValueError, match="development participant"):
    stg.main(argv, git=lambda: (STG_COMMIT, False), command=child)
  s["stage2_parts"][0].update(participant="P2", files=["P3/s2/f0.npz"])
  (tmp_path / "sel" / "selection.json").write_text(json.dumps(s))
  with pytest.raises(ValueError, match="excluded file"):
    stg.main(argv, git=lambda: (STG_COMMIT, False), command=child)


def test_scopes_override_only_existing_keys():
  cfg = settings_for()
  cfg["stage"]["scopes"]["primaries"] = {"f1.model_order": ["LDA svd"]}
  assert stg.scoped_config(cfg)["f1"]["model_order"] == ["LDA svd"]
  cfg["stage"]["scopes"]["primaries"] = {"f1.nope": 1}
  with pytest.raises(KeyError, match="not a key"):
    stg.scoped_config(cfg)
