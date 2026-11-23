"""Derived report numbers from a committed spec, with a stable key per number (G11, G23). Standard library only.

    python -m eegharness.numbers derive --spec reports/numbers_spec.json --out outputs/numbers [--root .]
    python -m eegharness.numbers check --numbers outputs/numbers/<run>/numbers.json --report agent_runs/<run>/06_results.md

Every number a write-up derives from result tables (a difference, a percentage-point
conversion, a count, a percentage, a mean) is declared once in a JSON spec committed to the
project, computed here, and written to a new versioned folder (G9) as ``numbers.json`` and
``numbers.csv``. The report cites the key, never a retyped value: ``4.2 pp [num:gain_pp]``.
``check`` verifies every citation: the key exists and the text just before it is the number's
text. Nothing is computed in a scratch script or in the write-up.

Spec::

  {"numbers": [
    {"key": "ba_f1", "op": "value", "decimals": 3,
     "a": {"csv": "outputs/stats/<run>/tests.csv", "where": {"method": "f1/raw/Shrinkage-LDA lsqr"}, "column": "ba"}},
    {"key": "gain_pp", "op": "pp_difference", "a": {"key": "ba_f1"}, "b": {"key": "ba_base"}, "decimals": 1, "unit": "pp"},
    {"key": "n_above", "op": "count",
     "rows": {"csv": "...", "where": {"method": "baseline", "p_holm": {"<": 0.05}}}},
    {"key": "pct_above", "op": "percent", "a": {"key": "n_above"}, "b": {"key": "n_files"}, "decimals": 1, "unit": "%"}
  ]}

Operands: ``{"key": k}`` (an earlier number) or ``{"csv", "where", "column"}`` selecting exactly ONE row
(zero or several rows refuse). ``rows`` selects every matching row (``column`` for the aggregates).
``where``: a column name -> a string (exact match, so identifiers with spaces, slashes, '+' and
hyphens are matched as written) or {op: value} with op in <, <=, >, >=, ==, != (numeric), or
{"in": [strings]}. An empty or non-numeric cell refuses; NaN refuses unless the number sets
``"nan": "drop"`` (aggregates only; the count dropped is recorded).
Ops: value, pp (100 a), difference (a - b), pp_difference (100 (a - b)), ratio (a / b),
percent (100 a / b), count, sum, mean, sd (ddof 1), median, min, max; scale (a x ``factor``, or a /
``divisor``: seconds to hours is ``"divisor": 3600, "unit": "h"``); all_equal (1 if every selected value of
``column`` is the same, else 0; the distinct values are recorded).
Sources (0.6.0, L53): ``"delimiter": "\t"`` on a csv operand or selection (``.tsv`` files are tab-separated by
default); ``{"glob": "outputs/stage2/*/parts/*/classical/*/gates.csv", "where", "column"}`` selects the rows of
every matching file (sorted; each row gets a ``_file`` column; zero files refuse); ``{"json": <path or glob>,
"field": "a.b"}`` reads one dotted field per JSON file as one row (a single operand needs exactly one file).
Text: ``decimals`` (default 3; count and all_equal 0), then the unit (``%`` without a space).
Rules: keys are unique and match [A-Za-z0-9_.-]+; the spec and every file read lie inside ``--root``;
the spec is tracked by git and unmodified (committed); numbers.json records each file's SHA-256.
"""

import argparse
import csv
import hashlib
import json
import math
import re
import statistics
import subprocess
import sys
from pathlib import Path

from eegharness import __version__

KEY = re.compile(r"[A-Za-z0-9_.-]+")
CITE = re.compile(r"\[num:([^\]\s]*)\]")
BINARY = {"difference": lambda a, b: a - b, "pp_difference": lambda a, b: 100.0 * (a - b),
          "ratio": lambda a, b: a / b, "percent": lambda a, b: 100.0 * a / b}
UNARY = {"value": lambda a: a, "pp": lambda a: 100.0 * a}
AGG = {"sum": math.fsum, "mean": statistics.fmean, "sd": statistics.stdev, "median": statistics.median,
       "min": min, "max": max}
CMP = {"<": lambda x, v: x < v, "<=": lambda x, v: x <= v, ">": lambda x, v: x > v, ">=": lambda x, v: x >= v,
       "==": lambda x, v: x == v, "!=": lambda x, v: x != v}


class SpecError(ValueError):
  """The spec, a source table or a selection is not usable; nothing is written."""


def _sha256(path):
  return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _inside(root, rel, what):
  p = (Path(root) / rel).resolve()
  if not p.is_relative_to(Path(root).resolve()):
    raise SpecError(f"{what} {rel!r} lies outside the project root (G23: no scratch files)")
  if not p.is_file():
    raise SpecError(f"{what} {rel!r} not found")
  return p


def _number(text, where):
  try:
    x = float(text)
  except (TypeError, ValueError):
    raise SpecError(f"{where}: {text!r} is not a number") from None
  return x


def _matches(row, where, path):
  for col, cond in where.items():
    if col not in row:
      raise SpecError(f"{path}: no column {col!r} (columns: {list(row)})")
    cell = row[col]
    if isinstance(cond, dict):
      for op, v in cond.items():
        if op == "in":
          if cell not in [str(s) for s in v]:
            return False
        elif op in CMP:
          if cell in ("", None) or not CMP[op](_number(cell, f"{path} column {col}"), float(v)):
            return False
        else:
          raise SpecError(f"unknown comparison {op!r} (known: {sorted(CMP)} and 'in')")
    elif cell != str(cond):
      return False
  return True


GLOB_CHARS = re.compile(r"[*?\[]")


def _dotted(obj, field, where):
  for k in str(field).split("."):
    if isinstance(obj, list) and k.isdigit() and int(k) < len(obj):
      obj = obj[int(k)]
    elif isinstance(obj, dict) and k in obj:
      obj = obj[k]
    else:
      raise SpecError(f"{where}: no field {field!r}")
  return obj


class _Tables:
  def __init__(self, root):
    self.root, self.cache, self.used = root, {}, {}

  def files(self, pattern, what):
    """The files a path or glob names, sorted, all inside the root; zero refuse."""
    if not GLOB_CHARS.search(pattern):
      return [(pattern, _inside(self.root, pattern, what))]
    base = Path(self.root).resolve()
    out = []
    for p in sorted(Path(self.root).glob(pattern)):
      if p.is_file():
        rp = p.resolve()
        if not rp.is_relative_to(base):
          raise SpecError(f"{what} {pattern!r} matches {p}, outside the project root (G23)")
        out.append((str(p.relative_to(self.root)), rp))
    if not out:
      raise SpecError(f"{what} {pattern!r} matches no file")
    return out

  def _table(self, rel, path, delimiter):
    ck = (rel, delimiter)
    if ck not in self.cache:
      with open(path, newline="") as f:
        self.cache[ck] = list(csv.DictReader(f, delimiter=delimiter))
      self.used[rel] = _sha256(path)
    return self.cache[ck]

  def select(self, sel, ctx):
    """Rows of a selection: {"csv"} or {"glob"} (tables) or {"json", "field"} (one row per file)."""
    if not isinstance(sel, dict):
      raise SpecError(f"{ctx}: a selection must be an object")
    where = sel.get("where") or {}
    if "json" in sel:
      field = sel.get("field") or sel.get("column")
      if not field:
        raise SpecError(f"{ctx}: a json source needs \"field\"")
      rows = []
      for rel, p in self.files(sel["json"], "json file"):
        if rel not in self.used:
          self.used[rel] = _sha256(p)
        try:
          v = _dotted(json.loads(p.read_text()), field, f"{ctx}: {rel}")
        except ValueError as e:
          raise SpecError(f"{ctx}: {rel} is not JSON ({e})") from None
        rows.append({field: v if isinstance(v, str) else json.dumps(v) if isinstance(v, (dict, list)) else
                     ("" if v is None else repr(v) if isinstance(v, float) else str(v)), "_file": rel})
      return [r for r in rows if _matches(r, where, sel["json"])]
    pattern = sel.get("glob") or sel.get("csv")
    if not pattern:
      raise SpecError(f"{ctx}: a selection needs \"csv\", \"glob\" or \"json\"")
    if "csv" in sel and GLOB_CHARS.search(sel["csv"]):
      raise SpecError(f"{ctx}: {sel['csv']!r} is a pattern; use \"glob\" for several files")
    out = []
    for rel, p in self.files(pattern, "table"):
      delim = sel.get("delimiter", "\t" if rel.lower().endswith(".tsv") else ",")
      rows = self._table(rel, p, delim)
      out += [{**r, "_file": rel} if "glob" in sel else r for r in rows if _matches(r, where, rel)]
    return out

  def rows(self, rel, where):  # earlier API, one CSV
    return self.select({"csv": rel, "where": where}, rel)


def _operand(op, tables, done, ctx):
  if not isinstance(op, dict):
    raise SpecError(f"{ctx}: operand must be an object")
  if "key" in op:
    if op["key"] not in done:
      raise SpecError(f"{ctx}: key {op['key']!r} is not defined earlier in the spec")
    return done[op["key"]]["value"], {"key": op["key"]}
  if "glob" in op:
    raise SpecError(f"{ctx}: a single operand reads one file; use rows with an aggregate for a glob")
  rows = tables.select(op, ctx)
  src = op.get("csv") or op.get("json")
  col = op.get("column") or op.get("field")
  if len(rows) != 1:
    raise SpecError(f"{ctx}: {src} where {op.get('where')} matches {len(rows)} rows; exactly 1 needed")
  x = _number(rows[0].get(col), f"{ctx}: {src} column {col!r}")
  if math.isnan(x):
    raise SpecError(f"{ctx}: {src} column {col!r} is NaN")
  return x, {k: op[k] for k in ("csv", "json", "where", "column", "field", "delimiter") if k in op}


def text_of(value, decimals, unit):
  s = f"{value:.{int(decimals)}f}"
  if unit:
    s += unit if unit == "%" else f" {unit}"
  return s


def derive(spec, root="."):
  """spec (dict) -> list of number records, in spec order. Raises SpecError."""
  tables, done, out = _Tables(Path(root)), {}, []
  for i, n in enumerate(spec.get("numbers", [])):
    key = n.get("key", "")
    ctx = f"number {i} ({key!r})"
    if not isinstance(key, str) or not KEY.fullmatch(key):
      raise SpecError(f"{ctx}: a key is letters, digits, '_', '.', '-'")
    if key in done:
      raise SpecError(f"{ctx}: duplicate key")
    op = n.get("op")
    rec = {"key": key, "op": op, "unit": n.get("unit", "")}
    if op in UNARY:
      a, sa = _operand(n.get("a"), tables, done, ctx)
      value, rec["sources"] = UNARY[op](a), [sa]
    elif op in BINARY:
      a, sa = _operand(n.get("a"), tables, done, ctx)
      b, sb = _operand(n.get("b"), tables, done, ctx)
      if op in ("ratio", "percent") and b == 0:
        raise SpecError(f"{ctx}: division by zero")
      value, rec["sources"] = BINARY[op](a, b), [sa, sb]
    elif op == "scale":
      a, sa = _operand(n.get("a"), tables, done, ctx)
      if ("factor" in n) == ("divisor" in n):
        raise SpecError(f"{ctx}: scale needs exactly one of \"factor\" and \"divisor\"")
      f = n.get("factor", n.get("divisor"))
      if isinstance(f, bool) or not isinstance(f, (int, float)) or f == 0:
        raise SpecError(f"{ctx}: the scale must be a non-zero number")
      value = a * f if "factor" in n else a / f
      rec["sources"], rec["factor" if "factor" in n else "divisor"] = [sa], f
    elif op == "count" or op in AGG or op == "all_equal":
      sel = n.get("rows") or {}
      rows = tables.select(sel, ctx)
      rec["sources"] = [{**{k: sel[k] for k in ("csv", "glob", "json", "field", "delimiter") if k in sel},
                         "where": sel.get("where"), "column": sel.get("column"), "n_rows": len(rows),
                         **({"n_files": len({r.get("_file") for r in rows})} if ("glob" in sel or "json" in sel) else {})}]
      col = sel.get("column") or sel.get("field")
      if op == "count":
        value = len(rows)
      elif op == "all_equal":
        if not rows:
          raise SpecError(f"{ctx}: all_equal over 0 rows")
        if any(col not in r for r in rows):
          raise SpecError(f"{ctx}: no column {col!r}")
        distinct = sorted({r[col] for r in rows})
        value, rec["distinct_values"] = (1 if len(distinct) == 1 else 0), distinct[:10]
      else:
        xs = [_number(r.get(col), f"{ctx}: {r.get('_file') or sel.get('csv')} column {col!r}") for r in rows]
        nan = [x for x in xs if math.isnan(x)]
        if nan and n.get("nan") != "drop":
          raise SpecError(f"{ctx}: {len(nan)} NaN value(s); set \"nan\": \"drop\" to drop them (recorded)")
        xs = [x for x in xs if not math.isnan(x)]
        rec["n_nan_dropped"] = len(nan)
        if len(xs) < (2 if op == "sd" else 1):
          raise SpecError(f"{ctx}: {len(xs)} value(s) for {op}")
        value = float(AGG[op](xs))
    else:
      raise SpecError(f"{ctx}: unknown op {op!r} (known: {sorted([*UNARY, *BINARY, *AGG, 'count', 'scale', 'all_equal'])})")
    rec["value"] = value
    rec["decimals"] = int(n.get("decimals", 0 if op in ("count", "all_equal") else 3))
    rec["text"] = text_of(value, rec["decimals"], rec["unit"])
    done[key] = rec
    out.append(rec)
  return out, tables.used


def _committed(root, spec_path):
  rel = str(Path(spec_path).resolve().relative_to(Path(root).resolve()))
  tracked = subprocess.run(["git", "-C", str(root), "ls-files", "--error-unmatch", rel], capture_output=True)
  if tracked.returncode != 0:
    return f"the spec {rel} is not committed"
  dirty = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--", rel], capture_output=True, text=True)
  return f"the spec {rel} has uncommitted changes" if dirty.stdout.strip() else None


def load_numbers(path):
  p = Path(path)
  if p.is_dir():
    p = p / "numbers.json"
  return {r["key"]: r for r in json.loads(p.read_text())["numbers"]}


def check_report(text, numbers):
  """Problems with the [num:key] citations of a report (empty list = every citation verified)."""
  problems = []
  for line_no, line in enumerate(text.splitlines(), 1):
    for m in CITE.finditer(line):
      key = m.group(1)
      if key not in numbers:
        problems.append(f"line {line_no}: unknown key {key!r}")
        continue
      want = numbers[key]["text"]
      before = line[:m.start()].rstrip()
      if not before.endswith(want) or (len(before) > len(want) and re.match(r"[0-9.\-]", before[-len(want) - 1])):
        problems.append(f"line {line_no}: [num:{key}] is {want!r} in numbers.json, but the report has "
                        f"{before[-len(want) - 8:]!r} before it")
  return problems


def main(argv=None) -> int:
  ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  sub = ap.add_subparsers(dest="cmd", required=True)
  d = sub.add_parser("derive", help="compute the numbers of a committed spec into a new versioned folder")
  d.add_argument("--spec", required=True)
  d.add_argument("--out", required=True)
  d.add_argument("--root", default=".")
  c = sub.add_parser("check", help="verify every [num:key] citation of a report")
  c.add_argument("--numbers", required=True, help="numbers.json or its folder")
  c.add_argument("--report", required=True)
  a = ap.parse_args(argv)
  if a.cmd == "check":
    problems = check_report(Path(a.report).read_text(), load_numbers(a.numbers))
    n = len(CITE.findall(Path(a.report).read_text()))
    for p in problems:
      print(p)
    print(f"{n} citation(s), {len(problems)} problem(s)")
    return 1 if problems else 0
  from eegharness.outputs import ComputeTimer, new_output_dir, record_compute_time
  timer = ComputeTimer()
  root = Path(a.root).resolve()
  spec_path = Path(a.spec).resolve()
  if not spec_path.is_relative_to(root) or not spec_path.is_file():
    print(f"the spec {a.spec} is not a file inside the project root {root} (G23: no scratch files)", file=sys.stderr)
    return 2
  why = _committed(root, spec_path)
  if why:
    print(f"{why}: commit the spec first (G23)", file=sys.stderr)
    return 2
  spec = json.loads(spec_path.read_text())
  try:
    recs, used = derive(spec, root)
  except (SpecError, KeyError) as e:
    print(f"refused: {e}", file=sys.stderr)
    return 2
  out = new_output_dir(a.out, inputs=[spec_path, *[root / u for u in used]], params=vars(a), root=root)
  (out / "numbers.json").write_text(json.dumps(
    {"tool": "eegharness.numbers", "version": __version__, "spec": str(spec_path.relative_to(root.resolve())),
     "spec_sha256": _sha256(spec_path), "tables": used, "numbers": recs}, indent=1) + "\n")
  with open(out / "numbers.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["key", "text", "value", "op", "unit"])
    for r in recs:
      w.writerow([r["key"], r["text"], repr(r["value"]), r["op"], r["unit"]])
  record_compute_time(out, timer)
  print(f"written: {out} ({len(recs)} numbers)")
  return 0


if __name__ == "__main__":
  sys.exit(main())
