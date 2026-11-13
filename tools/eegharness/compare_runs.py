"""Regression check: compare two output folders file by file (read-only on both).

  python -m eegharness.compare_runs --a <old run folder> --b <new run folder> --out <folder>
      [--exclude-columns time_s wall_clock] [--ignore '*.log' 'figures/*'] [--rtol 0 --atol 0]

Definitions:
  Files are matched by their path relative to A and B. Files matching --ignore are skipped;
    provenance.json is always skipped (it differs between any two runs by design). Files
    present on one side only are listed and count as differences.
  CSV/TSV: rows are compared in file order (row i of A with row i of B) over the columns
    present in both headers, except --exclude-columns. With --rtol = --atol = 0 (default)
    cells are compared as the strings written, so a change in the last printed digit counts.
    With a tolerance, cells that parse as numbers on both sides are equal when
    |a - b| <= atol + rtol * |b| (NaN equals NaN); other cells are compared as strings.
    Extra rows and columns present on one side only are counted separately.
  NPY/NPZ: arrays differ if a key is missing on one side, or shape or dtype differ, or the
    values differ (NaN equals NaN; ``numpy.allclose`` with the same tolerance, exact when 0).
    Loaded with ``allow_pickle=False``.
  JSON: compared as parsed values, reported as the list of differing key paths.
  Any other file: equal if its SHA-256 is equal.

Exit status: 0 if nothing differs, 1 if anything differs, 2 on a usage error.
Output: a new folder ``<out>/<UTC>_<commit>[_dirty]/`` (G9) with ``compare.txt`` (one line
per file) and ``compare.json`` (every count and each differing cell, up to --max-cells per
file), plus ``provenance.json`` with the SHA-256 of every compared file.
"""

import argparse
import csv
import fnmatch
import json
import math
import sys
from pathlib import Path

import numpy as np

from .outputs import new_output_dir, sha256_file

ALWAYS_IGNORED = ("provenance.json",)


def _num(s):
  try:
    return float(s)
  except (TypeError, ValueError):
    return None


def _cells_equal(a: str, b: str, rtol: float, atol: float) -> bool:
  if rtol == 0 and atol == 0:
    return a == b
  x, y = _num(a), _num(b)
  if x is None or y is None:
    return a == b
  if math.isnan(x) or math.isnan(y):
    return math.isnan(x) and math.isnan(y)
  return abs(x - y) <= atol + rtol * abs(y)


def compare_table(fa: Path, fb: Path, exclude, rtol, atol, max_cells) -> dict:
  delim = "\t" if fa.suffix.lower() == ".tsv" else ","
  with open(fa, newline="") as f:
    ra = list(csv.reader(f, delimiter=delim))
  with open(fb, newline="") as f:
    rb = list(csv.reader(f, delimiter=delim))
  ha, hb = (ra[0] if ra else []), (rb[0] if rb else [])
  cols = [c for c in ha if c in hb and c not in exclude]
  ia, ib = {c: ha.index(c) for c in cols}, {c: hb.index(c) for c in cols}
  n = min(len(ra), len(rb)) - 1 if ra and rb else 0
  diffs, n_diff = [], 0
  for i in range(1, n + 1):
    for c in cols:
      va = ra[i][ia[c]] if ia[c] < len(ra[i]) else ""
      vb = rb[i][ib[c]] if ib[c] < len(rb[i]) else ""
      if not _cells_equal(va, vb, rtol, atol):
        n_diff += 1
        if len(diffs) < max_cells:
          diffs.append({"row": i, "column": c, "a": va, "b": vb})
  r = {"kind": "table", "rows_compared": n, "columns_compared": len(cols),
       "cells_compared": n * len(cols), "cells_differing": n_diff,
       "rows_only_in_a": max(0, len(ra) - len(rb)), "rows_only_in_b": max(0, len(rb) - len(ra)),
       "columns_only_in_a": [c for c in ha if c not in hb], "columns_only_in_b": [c for c in hb if c not in ha],
       "differences": diffs}
  r["equal"] = (n_diff == 0 and not r["rows_only_in_a"] and not r["rows_only_in_b"]
                and not r["columns_only_in_a"] and not r["columns_only_in_b"])
  return r


def _load_arrays(p: Path) -> dict:
  if p.suffix.lower() == ".npy":
    return {"": np.load(p, allow_pickle=False)}
  with np.load(p, allow_pickle=False) as z:
    return {k: z[k] for k in z.files}


def _arrays_equal(x, y, rtol, atol) -> bool:
  if x.shape != y.shape or x.dtype != y.dtype:
    return False
  numeric = np.issubdtype(x.dtype, np.number) or np.issubdtype(x.dtype, np.bool_)
  if not numeric:
    return bool(np.array_equal(x, y))
  if rtol == 0 and atol == 0:
    nan_ok = np.issubdtype(x.dtype, np.inexact)
    return bool(np.array_equal(x, y, equal_nan=nan_ok))
  return bool(np.allclose(x, y, rtol=rtol, atol=atol, equal_nan=True))


def compare_arrays(fa: Path, fb: Path, rtol, atol) -> dict:
  a, b = _load_arrays(fa), _load_arrays(fb)
  keys = sorted(set(a) | set(b))
  per = {}
  for k in keys:
    if k not in a or k not in b:
      per[k] = "missing in " + ("a" if k not in a else "b")
    elif a[k].shape != b[k].shape:
      per[k] = f"shape {a[k].shape} vs {b[k].shape}"
    elif a[k].dtype != b[k].dtype:
      per[k] = f"dtype {a[k].dtype} vs {b[k].dtype}"
    elif not _arrays_equal(a[k], b[k], rtol, atol):
      per[k] = "values differ"
  return {"kind": "arrays", "arrays_compared": len(keys), "arrays_differing": len(per),
          "differences": per, "equal": not per}


def _json_diff(x, y, path="", out=None, limit=1000):
  out = [] if out is None else out
  if len(out) >= limit:
    return out
  if isinstance(x, dict) and isinstance(y, dict):
    for k in sorted(set(x) | set(y), key=str):
      if k not in x or k not in y:
        out.append(f"{path}/{k}: missing in {'a' if k not in x else 'b'}")
      else:
        _json_diff(x[k], y[k], f"{path}/{k}", out, limit)
  elif isinstance(x, list) and isinstance(y, list):
    if len(x) != len(y):
      out.append(f"{path}: length {len(x)} vs {len(y)}")
    for i, (u, v) in enumerate(zip(x, y)):
      _json_diff(u, v, f"{path}[{i}]", out, limit)
  elif x != y and not (isinstance(x, float) and isinstance(y, float) and math.isnan(x) and math.isnan(y)):
    out.append(f"{path}: {x!r} vs {y!r}")
  return out


def compare_json(fa: Path, fb: Path, max_cells) -> dict:
  d = _json_diff(json.loads(fa.read_text()), json.loads(fb.read_text()), limit=max_cells)
  return {"kind": "json", "differences": d, "equal": not d}


def compare_file(fa: Path, fb: Path, a) -> dict:
  suf = fa.suffix.lower()
  if suf in (".csv", ".tsv"):
    return compare_table(fa, fb, set(a.exclude_columns), a.rtol, a.atol, a.max_cells)
  if suf in (".npy", ".npz"):
    return compare_arrays(fa, fb, a.rtol, a.atol)
  if suf == ".json":
    return compare_json(fa, fb, a.max_cells)
  same = sha256_file(fa) == sha256_file(fb)
  return {"kind": "bytes", "equal": same}


def files_of(root: Path, ignore) -> dict:
  out = {}
  for f in sorted(root.rglob("*")):
    rel = f.relative_to(root).as_posix()
    if f.is_file() and f.name not in ALWAYS_IGNORED and not any(fnmatch.fnmatch(rel, g) for g in ignore):
      out[rel] = f
  return out


def compare_dirs(da: Path, db: Path, a) -> dict:
  fa, fb = files_of(da, a.ignore), files_of(db, a.ignore)
  per = {rel: compare_file(fa[rel], fb[rel], a) for rel in sorted(set(fa) & set(fb))}
  only_a, only_b = sorted(set(fa) - set(fb)), sorted(set(fb) - set(fa))
  return {"files_compared": len(per), "files_differing": sum(not r["equal"] for r in per.values()),
          "only_in_a": only_a, "only_in_b": only_b, "per_file": per,
          "equal": all(r["equal"] for r in per.values()) and not only_a and not only_b}


def _line(rel: str, r: dict) -> str:
  tag = "SAME" if r["equal"] else "DIFF"
  if r["kind"] == "table":
    extra = (f"{r['cells_differing']}/{r['cells_compared']} cells differ; rows only in a/b: "
             f"{r['rows_only_in_a']}/{r['rows_only_in_b']}; columns only in a/b: "
             f"{len(r['columns_only_in_a'])}/{len(r['columns_only_in_b'])}")
  elif r["kind"] == "arrays":
    extra = f"{r['arrays_differing']}/{r['arrays_compared']} arrays differ"
  elif r["kind"] == "json":
    extra = f"{len(r['differences'])} key paths differ"
  else:
    extra = "sha256 " + ("equal" if r["equal"] else "differs")
  return f"{tag} {rel}: {extra}"


def main(argv=None) -> int:
  ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  ap.add_argument("--a", required=True, help="reference output folder")
  ap.add_argument("--b", required=True, help="new output folder")
  ap.add_argument("--out", required=True, help="parent folder for this comparison's versioned output")
  ap.add_argument("--exclude-columns", nargs="*", default=[], help="table columns not compared (e.g. wall-clock time)")
  ap.add_argument("--ignore", nargs="*", default=[], help="glob patterns of relative paths not compared")
  ap.add_argument("--rtol", type=float, default=0.0)
  ap.add_argument("--atol", type=float, default=0.0)
  ap.add_argument("--max-cells", type=int, default=200, help="differences listed per file in compare.json")
  try:
    a = ap.parse_args(argv)
  except SystemExit as e:
    return 2 if e.code else 0
  from eegharness.outputs import ComputeTimer, record_compute_time
  timer = ComputeTimer()
  da, db = Path(a.a), Path(a.b)
  for d in (da, db):
    if not d.is_dir():
      print(f"not a folder: {d}", file=sys.stderr)
      return 2
  if a.rtol < 0 or a.atol < 0:
    print("tolerances must be >= 0", file=sys.stderr)
    return 2
  result = compare_dirs(da, db, a)
  inputs = [p for p in (*files_of(da, a.ignore).values(), *files_of(db, a.ignore).values())]
  params = {k: v for k, v in vars(a).items()}
  out = new_output_dir(a.out, inputs=inputs, params=params,
                       argv=[sys.executable, "-m", "eegharness.compare_runs", *(argv if argv is not None else sys.argv[1:])])
  lines = [f"A: {da}", f"B: {db}", f"tolerance: rtol={a.rtol} atol={a.atol}",
           *(_line(rel, r) for rel, r in result["per_file"].items()),
           *(f"ONLY_A {rel}" for rel in result["only_in_a"]),
           *(f"ONLY_B {rel}" for rel in result["only_in_b"]),
           f"RESULT: {'equal' if result['equal'] else 'different'} "
           f"({result['files_differing']} of {result['files_compared']} files differ, "
           f"{len(result['only_in_a'])} only in A, {len(result['only_in_b'])} only in B)"]
  (out / "compare.txt").write_text("\n".join(lines) + "\n")
  (out / "compare.json").write_text(json.dumps({"a": str(da), "b": str(db), "params": params, **result},
                                               indent=1, default=str) + "\n")
  record_compute_time(out, timer)
  print("\n".join(lines[-1:]) + f"\noutput: {out}")
  return 0 if result["equal"] else 1


if __name__ == "__main__":
  sys.exit(main())
