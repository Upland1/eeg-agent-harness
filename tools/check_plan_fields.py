"""Every quantity a plan's gate or decision rule uses is recorded by a named code path and output field (L56).

    python .harness/tools/check_plan_fields.py agent_runs/<run>/02_plan.md [--root .] [--final]
        [--output <folder> ...]

Reads the table of the plan's section "Gate and rule inputs" (header ``| Quantity | Used by | Code path |
Output field |``). For each row:

  OK       the code path (``file.py`` or ``file.py:first-last``) exists and writes the field: the field name
           appears in it, within the line range if one is given, as a quoted key ('t_e', "t_e") or a
           ``.field`` attribute written with ``=``;
  MISSING  the code path exists but does not write the field (a rule relying on a value no output records);
  NEW      the code path does not exist yet (code the plan will add): reported, not a failure at plan audit;
           with ``--final`` (the change audit, after the code is written) it is a failure;
  INCOMPLETE  the row names no code path or no field.

With ``--output <folder>`` (a real output of that code, e.g. the smoke's), each field must also appear as a
key in a JSON file or a column of a CSV/TSV file under one of the folders, else MISSING.
Prints one line per row, then PASS or FAIL; exit 1 on FAIL. Standard library only.
"""

import argparse
import csv
import json
import re
import sys
from pathlib import Path

SECTION = "## Gate and rule inputs"
HEADER = ("quantity", "used by", "code path", "output field")


def _cells(line):
  body = line.strip().strip("|")
  return [c.strip() for c in body.split("|")]


def table_rows(plan_text):
  """[(line_no, {quantity, used by, code path, output field})] of the section's table."""
  lines = plan_text.splitlines()
  try:
    start = next(i for i, l in enumerate(lines) if l.strip().lower().startswith(SECTION.lower()))
  except StopIteration:
    return None
  rows, head = [], None
  for i in range(start + 1, len(lines)):
    l = lines[i]
    if l.startswith("## "):
      break
    if not l.strip().startswith("|"):
      continue
    cells = _cells(l)
    if head is None:
      head = [c.lower() for c in cells]
      continue
    if all(re.fullmatch(r":?-{3,}:?", c) for c in cells if c):
      continue
    if not any(cells):
      continue
    rows.append((i + 1, dict(zip(head, cells))))
  if head is None or tuple(head[:4]) != HEADER:
    raise ValueError(f"'{SECTION}' table header must be | Quantity | Used by | Code path | Output field |")
  return rows


def _strip_code(s):
  return s.strip().strip("`").strip()


def written_in(text, field):
  f = re.escape(field)
  return bool(re.search(rf"""(['"]){f}\1|\.{f}\s*=(?!=)""", text))


def in_outputs(folders, field):
  for folder in folders:
    for p in Path(folder).rglob("*"):
      if p.suffix.lower() == ".json":
        try:
          if f'"{field}"' in p.read_text():
            json.loads(p.read_text())
            return True
        except (OSError, ValueError):
          continue
      elif p.suffix.lower() in (".csv", ".tsv"):
        try:
          with open(p, newline="") as fh:
            head = next(csv.reader(fh, delimiter="\t" if p.suffix.lower() == ".tsv" else ","), [])
        except (OSError, StopIteration):
          continue
        if field in head:
          return True
  return False


def check(plan, root=".", final=False, outputs=()):
  root = Path(root)
  rows = table_rows(Path(plan).read_text())
  if rows is None:
    return [(None, "MISSING", f"no '{SECTION}' section: every quantity a gate or decision rule uses must be "
                              "named with its code path and output field (L56)")], False
  if not rows:
    return [(None, "INCOMPLETE", f"'{SECTION}' has no rows")], False
  out, ok = [], True
  for n, r in rows:
    q, path, field = r.get("quantity", ""), _strip_code(r.get("code path", "")), _strip_code(r.get("output field", ""))
    if not path or not field or path in ("—", "-") or field in ("—", "-"):
      out.append((n, "INCOMPLETE", f"{q}: no code path or no output field"))
      ok = False
      continue
    m = re.fullmatch(r"(.+?)(?::(\d+)(?:-(\d+))?)?", path)
    rel, a, b = m.group(1), m.group(2), m.group(3)
    f = root / rel
    if not f.is_file():
      out.append((n, "NEW", f"{q}: {rel} does not exist yet (the change audit checks `{field}` there)"))
      ok = ok and not final
      continue
    text = f.read_text(errors="replace")
    if a:
      lines = text.splitlines()
      text = "\n".join(lines[int(a) - 1:int(b or a)])
    if not written_in(text, field):
      out.append((n, "MISSING", f"{q}: `{field}` is not written in {path} (a rule relying on a value no output records)"))
      ok = False
      continue
    if outputs and not in_outputs(outputs, field):
      out.append((n, "MISSING", f"{q}: `{field}` is in {path} but in no JSON key or CSV column of {', '.join(map(str, outputs))}"))
      ok = False
      continue
    out.append((n, "OK", f"{q}: `{field}` written in {path}"))
  return out, ok


def main(argv=None):
  ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  ap.add_argument("plan")
  ap.add_argument("--root", default=".")
  ap.add_argument("--final", action="store_true", help="change audit: code the plan names must exist")
  ap.add_argument("--output", action="append", default=[], help="an output folder that must hold each field")
  a = ap.parse_args(argv)
  try:
    rows, ok = check(a.plan, a.root, a.final, a.output)
  except ValueError as e:
    print(f"FAIL: {e}")
    return 1
  for n, status, msg in rows:
    print(f"{a.plan}:{n}: {status}: {msg}" if n else f"{status}: {msg}")
  print("PASS" if ok else "FAIL")
  return 0 if ok else 1


if __name__ == "__main__":
  sys.exit(main())
