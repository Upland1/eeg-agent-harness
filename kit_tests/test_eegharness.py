"""Known-answer tests for the vendored package: versioned outputs (G9) and compare_runs."""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT / "tools"))
import eegharness  # noqa: E402
from eegharness import compare_runs  # noqa: E402
from eegharness.outputs import new_output_dir  # noqa: E402

T0 = datetime(2026, 11, 5, 4, 21, 42, tzinfo=timezone.utc)
SHA_ABC = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"  # FIPS 180-2 "abc"


def git(repo, *a):
  return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *a],
                        check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture()
def repo(tmp_path):
  r = tmp_path / "repo"
  r.mkdir()
  git(r, "init", "-q", "-b", "main")
  (r / "code.py").write_text("x = 1\n")
  git(r, "add", "code.py")
  git(r, "commit", "-q", "-m", "init")
  return r


def test_package_version_matches_kit():
  """Known answer: the vendored package reports the kit VERSION."""
  assert eegharness.__version__ == (KIT / "VERSION").read_text().strip()


def test_new_output_dir_name_provenance_and_no_overwrite(repo, tmp_path):
  """Known answer: <UTC>_<short commit>/, provenance with commit, params and SHA-256("abc"); second call in the same second gets _2 and leaves the first untouched."""
  inp = tmp_path / "in.txt"
  inp.write_bytes(b"abc")
  commit = git(repo, "rev-parse", "HEAD")
  out = new_output_dir(tmp_path / "outs", inputs=[inp], params={"alpha": 0.05}, root=repo, argv=["s.py", "--x"], now=T0)
  assert out.name == f"20261105T042142Z_{commit[:7]}"
  p = json.loads((out / "provenance.json").read_text())
  assert p["commit"] == commit and p["tracked_files_dirty"] is False and p["command"] == "s.py --x"
  assert p["params"] == {"alpha": 0.05} and p["eegharness"] == eegharness.__version__
  assert p["inputs"] == [{"path": str(inp), "bytes": 3, "sha256": SHA_ABC}]
  before = (out / "provenance.json").read_bytes()
  again = new_output_dir(tmp_path / "outs", root=repo, now=T0)  # same second: a new folder, never the old one
  assert again.name == out.name + "_2" and (out / "provenance.json").read_bytes() == before


def test_new_output_dir_dirty_untracked_folder_inputs_and_missing(repo, tmp_path):
  """Known answer: an untracked file is not dirty; a modified tracked file is (_dirty); a folder input expands to its files sorted; a missing input leaves no folder."""
  (repo / "untracked.txt").write_text("u")
  assert not new_output_dir(tmp_path / "o", root=repo, now=T0).name.endswith("_dirty")
  (repo / "code.py").write_text("x = 2\n")
  d = tmp_path / "indir"
  (d / "sub").mkdir(parents=True)
  (d / "sub" / "b.txt").write_bytes(b"abc")
  (d / "a.txt").write_bytes(b"")
  out = new_output_dir(tmp_path / "o2", inputs=[d], root=repo, now=T0)
  assert out.name.endswith("_dirty")
  rows = json.loads((out / "provenance.json").read_text())["inputs"]
  assert [Path(r["path"]).name for r in rows] == ["a.txt", "b.txt"] and rows[1]["sha256"] == SHA_ABC
  with pytest.raises(FileNotFoundError):
    new_output_dir(tmp_path / "o3", inputs=[tmp_path / "nope"], root=repo, now=T0)
  assert not (tmp_path / "o3").exists() or not any((tmp_path / "o3").iterdir())


def test_new_output_dir_without_git(tmp_path):
  """Known answer: outside a git repository the commit is 'nogit' and dirtiness unknown (None)."""
  out = new_output_dir(tmp_path / "o", root=tmp_path, now=T0)
  assert out.name == "20261105T042142Z_nogit"
  assert json.loads((out / "provenance.json").read_text())["tracked_files_dirty"] is None


def make_run(root: Path, rows, arrays=None, extra=None):
  root.mkdir(parents=True)
  (root / "scores.csv").write_text("participant,auc,time_s\n" + "".join(f"{p},{a},{t}\n" for p, a, t in rows))
  np.savez(root / "arrays.npz", **(arrays or {"w": np.array([1.0, np.nan, 3.0])}))
  (root / "summary.json").write_text(json.dumps({"n": len(rows), "ok": True}))
  (root / "provenance.json").write_text(json.dumps({"utc_start": str(root)}))  # always differs, always ignored
  for name, text in (extra or {}).items():
    (root / name).write_text(text)
  return root


ROWS = [("S1", "0.8123", "10.1"), ("S2", "0.7001", "11.4")]


def run_cmp(tmp_path, a, b, *opts):
  code = compare_runs.main(["--a", str(a), "--b", str(b), "--out", str(tmp_path / "cmp"), *opts])
  outs = sorted((tmp_path / "cmp").iterdir()) if (tmp_path / "cmp").exists() else []
  return code, (json.loads((outs[-1] / "compare.json").read_text()) if outs else None)


def test_compare_identical_runs_exit_0_with_nan(tmp_path):
  """Known answer: two identical runs (NaN in an array, different provenance.json) compare equal, exit 0; output is a versioned folder with provenance."""
  a, b = make_run(tmp_path / "a", ROWS), make_run(tmp_path / "b", ROWS)
  code, res = run_cmp(tmp_path, a, b)
  assert code == 0 and res["equal"] and res["files_compared"] == 3
  out = next((tmp_path / "cmp").iterdir())
  assert (out / "provenance.json").exists() and "RESULT: equal" in (out / "compare.txt").read_text()


def test_compare_detects_one_cell_extra_row_and_excludes_columns(tmp_path):
  """Known answer: one changed last digit = 1 differing cell (exit 1); a changed excluded column is ignored (exit 0); an extra row counts."""
  a = make_run(tmp_path / "a", ROWS)
  b = make_run(tmp_path / "b", [("S1", "0.8124", "10.1"), ROWS[1]])
  code, res = run_cmp(tmp_path, a, b)
  t = res["per_file"]["scores.csv"]
  assert code == 1 and t["cells_differing"] == 1 and t["differences"] == [{"row": 1, "column": "auc", "a": "0.8123", "b": "0.8124"}]
  c = make_run(tmp_path / "c", [(p, au, "99.9") for p, au, _ in ROWS])
  assert run_cmp(tmp_path, a, c, "--exclude-columns", "time_s")[0] == 0
  d = make_run(tmp_path / "d", ROWS + [("S3", "0.5", "1")])
  code, res = run_cmp(tmp_path, a, d)
  assert code == 1 and res["per_file"]["scores.csv"]["rows_only_in_b"] == 1 and res["per_file"]["summary.json"]["differences"] == ["/n: 2 vs 3"]


def test_compare_tolerance(tmp_path):
  """Known answer: 0.8123 vs 0.81230001 differs exactly, is equal at rtol=1e-6."""
  a = make_run(tmp_path / "a", ROWS)
  b = make_run(tmp_path / "b", [("S1", "0.81230001", "10.1"), ROWS[1]])
  assert run_cmp(tmp_path, a, b)[0] == 1
  assert run_cmp(tmp_path, a, b, "--rtol", "1e-6")[0] == 0


@pytest.mark.parametrize("arrays,why", [
  ({"w": np.array([1.0, np.nan, 3.5])}, "values differ"),
  ({"w": np.array([1.0, np.nan])}, "shape (3,) vs (2,)"),
  ({"w": np.array([1.0, np.nan, 3.0], dtype=np.float32)}, "dtype float64 vs float32"),
  ({"w": np.array([1.0, np.nan, 3.0]), "v": np.zeros(2)}, "missing in a"),
])
def test_compare_arrays(tmp_path, arrays, why):
  """Known answer: a changed value, shape, dtype or an extra key is reported with its reason."""
  a = make_run(tmp_path / "a", ROWS)
  b = make_run(tmp_path / "b", ROWS, arrays=arrays)
  code, res = run_cmp(tmp_path, a, b)
  assert code == 1 and why in res["per_file"]["arrays.npz"]["differences"].values()


def test_compare_files_on_one_side_ignore_and_usage_errors(tmp_path):
  """Known answer: a file only in B differs (exit 1) unless ignored (exit 0); a missing folder is a usage error (exit 2)."""
  a = make_run(tmp_path / "a", ROWS)
  b = make_run(tmp_path / "b", ROWS, extra={"run.log": "took 3 s"})
  code, res = run_cmp(tmp_path, a, b)
  assert code == 1 and res["only_in_b"] == ["run.log"]
  assert run_cmp(tmp_path, a, b, "--ignore", "*.log")[0] == 0
  assert compare_runs.main(["--a", str(a), "--b", str(tmp_path / "nope"), "--out", str(tmp_path / "x")]) == 2
