"""Frozen text stays unchanged: a file may only gain lines after a committed version (L36).

    python .harness/tools/check_frozen_text.py docs/PARADIGM.md --base <commit>   # exit 1 on a change

Compares the file as committed at ``--base`` with the file in the working tree, line by line. Lines
may be inserted anywhere (a new revision, an approval line); no committed line may be deleted or
changed. Prints PASS, or FAIL with every changed or deleted line of the base (number and text).
Standard library only.
"""

import argparse
import difflib
import subprocess
import sys
from pathlib import Path


def changed_lines(old, new):
  """[(base line number, base text)] of base lines deleted or replaced in ``new``."""
  a, b = old.splitlines(), new.splitlines()
  out = []
  for tag, i1, i2, _, _ in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
    if tag in ("delete", "replace"):
      out += [(i + 1, a[i]) for i in range(i1, i2)]
  return out


def main(argv=None):
  ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  ap.add_argument("path")
  ap.add_argument("--base", required=True, help="the commit whose version of the file is frozen")
  ap.add_argument("--root", default=".")
  a = ap.parse_args(argv)
  rel = Path(a.path).as_posix()
  r = subprocess.run(["git", "-C", a.root, "show", f"{a.base}:{rel}"], capture_output=True, text=True)
  if r.returncode:
    print(f"FAIL: {rel} not found at {a.base}: {r.stderr.strip()}")
    return 1
  bad = changed_lines(r.stdout, (Path(a.root) / rel).read_text())
  if bad:
    print(f"FAIL: {len(bad)} frozen line(s) of {rel} @ {a.base} changed or deleted:")
    for n, t in bad:
      print(f"  l.{n}: {t[:160]}")
    return 1
  print(f"PASS: every line of {rel} @ {a.base} is unchanged")
  return 0


if __name__ == "__main__":
  sys.exit(main())
