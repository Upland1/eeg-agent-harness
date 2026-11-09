"""Known-answer tests for eegharness.numbers: derived report numbers from a committed spec, one stable key per
number, cited in the report as ``<text> [num:key]`` and verified by ``check`` (G11, G23; P300 Stage-2 lesson
2026-11-09: the results analyst computed pp conversions, counts and percentages in uncommitted /tmp scripts).
Fails on v0.4-dev @ bed106f: the tool did not exist. Identifiers are the real ones (spaces, slashes, '+',
hyphens, a comma in a file name)."""

import csv
import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
from eegharness import numbers as nb  # noqa: E402

F1 = "f1/raw/Shrinkage-LDA lsqr"
UNION = "f1/fbcsp+fbcca/Shrinkage-LDA lsqr"
ROWS = [  # method, file, ba, p_holm
  ("baseline", "Training 5 - F.ebr", "0.70", "0.20"),
  ("baseline", "Training 6, repeat - F.ebr", "0.74", "0.04"),
  (F1, "Training 5 - F.ebr", "0.75", "0.01"),
  (F1, "Training 6, repeat - F.ebr", "nan", "1.0"),
  (UNION, "Training 5 - F.ebr", "0.81", "0.03"),
  (UNION, "Training 6, repeat - F.ebr", "0.79", "0.002"),
]


def _table(root):
  p = root / "outputs" / "stats" / "run1" / "per_file_tests.csv"
  p.parent.mkdir(parents=True)
  with open(p, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["method", "file", "ba", "p_holm"])
    w.writerows(ROWS)
  return "outputs/stats/run1/per_file_tests.csv"


def _one(t, method, file, column="ba"):
  return {"csv": t, "where": {"method": method, "file": file}, "column": column}


def _spec(t):
  return {"numbers": [
    {"key": "ba_f1_t5", "op": "value", "a": _one(t, F1, "Training 5 - F.ebr")},
    {"key": "ba_base_t5", "op": "value", "a": _one(t, "baseline", "Training 5 - F.ebr")},
    {"key": "gain_f1_t5_pp", "op": "pp_difference", "a": {"key": "ba_f1_t5"}, "b": {"key": "ba_base_t5"},
     "decimals": 1, "unit": "pp"},
    {"key": "n_rows_union", "op": "count", "rows": {"csv": t, "where": {"method": UNION}}},
    {"key": "n_sig_union", "op": "count", "rows": {"csv": t, "where": {"method": UNION, "p_holm": {"<": 0.05}}}},
    {"key": "n_sig_all", "op": "count", "rows": {"csv": t, "where": {"p_holm": {"<": 0.05}}}},
    {"key": "pct_sig_union", "op": "percent", "a": {"key": "n_sig_union"}, "b": {"key": "n_rows_union"},
     "decimals": 0, "unit": "%"},
    {"key": "mean_ba_f1", "op": "mean", "rows": {"csv": t, "where": {"method": F1}, "column": "ba"}, "nan": "drop"},
    {"key": "sd_ba_union", "op": "sd", "rows": {"csv": t, "where": {"method": UNION}, "column": "ba"}, "decimals": 4},
    {"key": "ba_union_t6_pct", "op": "pp", "a": _one(t, UNION, "Training 6, repeat - F.ebr"), "decimals": 1,
     "unit": "%"},
  ]}


def test_derive_known_answers_with_real_identifiers(tmp_path):
  """Known answers (hand-derived): F1 - baseline on 'Training 5 - F.ebr' = 0.75 - 0.70 = 5.0 pp; UNION rows 2,
  both p_holm < 0.05; all rows with p_holm < 0.05: 4 (0.04, 0.01, 0.03, 0.002); 100%; mean F1 BA with the NaN
  row dropped = 0.75 (1 dropped); SD of (0.81, 0.79) = 0.0141; UNION on the comma file 79.0%."""
  t = _table(tmp_path)
  recs, used = nb.derive(_spec(t), tmp_path)
  v = {r["key"]: r for r in recs}
  assert v["gain_f1_t5_pp"]["value"] == pytest.approx(5.0) and v["gain_f1_t5_pp"]["text"] == "5.0 pp"
  assert v["n_rows_union"]["value"] == 2 and v["n_sig_union"]["value"] == 2 and v["n_sig_all"]["value"] == 4
  assert v["n_sig_all"]["text"] == "4" and v["pct_sig_union"]["text"] == "100%"
  assert v["mean_ba_f1"]["value"] == pytest.approx(0.75) and v["mean_ba_f1"]["n_nan_dropped"] == 1
  assert v["sd_ba_union"]["text"] == f"{math.sqrt(0.0002):.4f}" == "0.0141"
  assert v["ba_union_t6_pct"]["text"] == "79.0%"
  assert list(used) == [t] and len(used[t]) == 64
  assert [r["key"] for r in recs] == [n["key"] for n in _spec(t)["numbers"]]


@pytest.mark.parametrize("bad,match", [
  ({"key": "x", "op": "value", "a": {"csv": "T", "where": {"method": "baseline"}, "column": "ba"}}, "matches 2 rows"),
  ({"key": "x", "op": "value", "a": {"csv": "T", "where": {"method": "f1/raw/Shrinkage-LDA"}, "column": "ba"}},
   "matches 0 rows"),
  ({"key": "x", "op": "value", "a": _one("T", F1, "Training 6, repeat - F.ebr")}, "NaN"),
  ({"key": "x", "op": "mean", "rows": {"csv": "T", "where": {"method": F1}, "column": "ba"}}, "nan.*drop"),
  ({"key": "x", "op": "value", "a": {"key": "later"}}, "not defined earlier"),
  ({"key": "x y", "op": "count", "rows": {"csv": "T"}}, "a key is"),
  ({"key": "x", "op": "value", "a": {"csv": "../outside.csv", "column": "ba"}}, "outside the project root"),
  ({"key": "x", "op": "median3", "a": {"key": "x"}}, "unknown op"),
  ({"key": "x", "op": "count", "rows": {"csv": "T", "where": {"subject": "S1"}}}, "no column 'subject'"),
])
def test_derive_refuses(tmp_path, bad, match):
  t = _table(tmp_path)
  (tmp_path.parent / "outside.csv").write_text("ba\n0.5\n")
  bad = json.loads(json.dumps(bad).replace('"T"', json.dumps(t)))
  with pytest.raises(nb.SpecError, match=match):
    nb.derive({"numbers": [bad]}, tmp_path)


def test_duplicate_key_is_refused(tmp_path):
  t = _table(tmp_path)
  n = {"key": "n", "op": "count", "rows": {"csv": t}}
  with pytest.raises(nb.SpecError, match="duplicate"):
    nb.derive({"numbers": [n, n]}, tmp_path)


def test_check_report_citations():
  """A citation is verified when the text right before it is the number's text; a retyped or rounded value, a
  value that only ends like it (14.2 vs 4.2) and an unknown key are each reported with the line."""
  nums = {"gain": {"text": "4.2 pp"}, "n": {"text": "4"}, "pct": {"text": "80%"}}
  ok = "F1 beat the baseline by 4.2 pp [num:gain] in 4 [num:n] files (80% [num:pct])."
  assert nb.check_report(ok, nums) == []
  bad = "by 4.3 pp [num:gain]\nby 14.2 pp [num:gain]\nin 4 [num:nfiles]\n80 % [num:pct]"
  probs = nb.check_report(bad, nums)
  assert [p.split(":")[0] for p in probs] == ["line 1", "line 2", "line 3", "line 4"]
  assert "unknown key 'nfiles'" in probs[2]


def _git(root, *a):
  subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", *a], check=True,
                 capture_output=True)


def test_cli_derive_needs_a_committed_spec_and_writes_a_versioned_output(tmp_path, capsys):
  """End to end: an uncommitted spec is refused (exit 2); committed, it writes <out>/<UTC>_<commit>/ with
  numbers.json (tool, version, spec SHA-256, the table's SHA-256, every number) and numbers.csv; a modified
  spec is refused again; check passes on a report citing the keys and fails (exit 1) on a retyped value."""
  root = tmp_path / "proj"
  root.mkdir()
  t = _table(root)
  spec = root / "reports" / "numbers_spec.json"
  spec.parent.mkdir()
  spec.write_text(json.dumps(_spec(t), indent=1))
  _git(root, "init", "-q", "-b", "main")
  argv = ["derive", "--spec", str(spec), "--out", str(root / "outputs" / "numbers"), "--root", str(root)]
  assert nb.main(argv) == 2 and "not committed" in capsys.readouterr().err
  (root / ".gitignore").write_text("outputs/\n")
  _git(root, "add", ".gitignore", "reports/numbers_spec.json")
  _git(root, "commit", "-qm", "spec")
  assert nb.main(argv) == 0
  out = sorted((root / "outputs" / "numbers").iterdir())
  assert len(out) == 1 and (out[0] / "provenance.json").is_file()
  data = json.loads((out[0] / "numbers.json").read_text())
  assert data["tool"] == "eegharness.numbers" and data["spec"] == "reports/numbers_spec.json"
  assert set(data["tables"]) == {t} and len(data["numbers"]) == 10
  rows = list(csv.DictReader(open(out[0] / "numbers.csv")))
  assert rows[2]["key"] == "gain_f1_t5_pp" and rows[2]["text"] == "5.0 pp"
  report = root / "06_results.md"
  report.write_text("F1 gained 5.0 pp [num:gain_f1_t5_pp]; 4 [num:n_sig_all] rows below 0.05.\n")
  assert nb.main(["check", "--numbers", str(out[0]), "--report", str(report)]) == 0
  report.write_text("F1 gained 5 pp [num:gain_f1_t5_pp].\n")
  assert nb.main(["check", "--numbers", str(out[0] / "numbers.json"), "--report", str(report)]) == 1
  spec.write_text(spec.read_text().replace('"decimals": 1', '"decimals": 2'))
  assert nb.main(argv) == 2 and "uncommitted changes" in capsys.readouterr().err
  outside = tmp_path / "scratch_spec.json"
  outside.write_text(json.dumps(_spec(t)))
  assert nb.main(["derive", "--spec", str(outside), "--out", str(root / "outputs" / "numbers"),
                  "--root", str(root)]) == 2
