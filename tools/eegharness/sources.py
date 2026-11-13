"""Committed files quote the instructions they cite (0.5.0, BACKLOG L38; extends G15).

A source that is an orchestrator's or a human's instruction lives in git-ignored files
(``agent_runs/<run>/human_contacts.md``, ``log.md``, briefs), so a committed file that cites it only
by a contact number or a path points at something nobody else can read. This check reads the
committed (git-tracked) text files of a project and reports:

  uncommitted_path   a reference to ``agent_runs/`` (G15: committed files cite committed things;
                     a quote does not make the path readable);
  unquoted_contact   a paragraph that cites a human contact (``contact #N``, ``contact N``,
                     ``human_contacts``) without quoting it: no quoted span of at least
                     ``min_quote_words`` words ("...", “...”, or a ``>`` block-quote line) in the
                     same paragraph.

A paragraph is a block of lines between blank lines. In a JSON file every string value is checked
on its own (the JSON quotes themselves do not count as a quotation). Untracked and ignored files
are not read: they are not committed; nor are git's own files (``.gitignore`` names ``agent_runs/`` to
ignore it). The vendored copies ``eegpipe/`` and ``eegharness/`` are
skipped by default.

    python -m eegharness.sources check [--root .] [--min-quote-words 3] [paths ...]   # exit 1 on a finding
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

UNCOMMITTED = re.compile(r"agent_runs/")
CONTACT = re.compile(r"\bcontacts?\s*(?:#\s*|no\.\s*)?\d+\b|\bhuman_contacts\b", re.IGNORECASE)
QUOTED = re.compile(r'"([^"]+)"|“([^”]+)”')
TEXT_SUFFIXES = {".md", ".txt", ".py", ".json", ".sh", ".toml", ".cfg", ".ini", ".yaml", ".yml", ".csv", ".rst", ""}
DEFAULT_SKIP = ("eegpipe/", "eegharness/")
GIT_CONFIG = {".gitignore", ".gitattributes", ".gitmodules"}  # name agent_runs/ to ignore it, not to cite it


def _paragraphs(text):
  """(first line number, paragraph text) for blocks separated by blank lines."""
  out, buf, start = [], [], 1
  for i, line in enumerate(text.splitlines(), 1):
    if line.strip():
      if not buf:
        start = i
      buf.append(line)
    elif buf:
      out.append((start, "\n".join(buf)))
      buf = []
  if buf:
    out.append((start, "\n".join(buf)))
  return out


def _has_quote(par, min_words):
  spans = [a or b for a, b in QUOTED.findall(par)]
  spans += [ln.lstrip()[1:] for ln in par.splitlines() if ln.lstrip().startswith(">")]
  return any(len(s.split()) >= min_words for s in spans)


def check_text(text, path="<text>", min_quote_words=3, line_offset=0):
  """Findings in one text: dicts with path, line, kind, excerpt."""
  found = []
  for start, par in _paragraphs(text):
    for m in UNCOMMITTED.finditer(par):
      line = start + par[:m.start()].count("\n") + line_offset
      found.append({"path": str(path), "line": line, "kind": "uncommitted_path",
                    "excerpt": par.splitlines()[par[:m.start()].count("\n")].strip()[:160]})
    m = CONTACT.search(par)
    if m and not _has_quote(par, min_quote_words):
      line = start + par[:m.start()].count("\n") + line_offset
      found.append({"path": str(path), "line": line, "kind": "unquoted_contact",
                    "excerpt": par.splitlines()[par[:m.start()].count("\n")].strip()[:160]})
  return found


def _json_strings(obj, where=""):
  if isinstance(obj, str):
    yield where, obj
  elif isinstance(obj, dict):
    for k, v in obj.items():
      yield from _json_strings(v, f"{where}.{k}" if where else str(k))
  elif isinstance(obj, list):
    for i, v in enumerate(obj):
      yield from _json_strings(v, f"{where}[{i}]")


def check_file(path, rel=None, min_quote_words=3):
  rel = rel or str(path)
  text = Path(path).read_text(errors="replace")
  if str(path).endswith(".json"):
    try:
      obj = json.loads(text)
    except ValueError:
      return check_text(text, rel, min_quote_words)
    found = []
    for where, s in _json_strings(obj):
      for f in check_text(s, f"{rel}:{where}", min_quote_words):
        f["line"] = None
        found.append(f)
    return found
  return check_text(text, rel, min_quote_words)


def tracked_files(root, paths=(), skip=DEFAULT_SKIP):
  """Git-tracked text files under ``paths`` (default: the whole tree), minus ``skip`` prefixes."""
  r = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--", *paths], capture_output=True, text=True, check=True)
  files = [f for f in r.stdout.split("\0") if f]
  return [f for f in files if not f.startswith(tuple(skip)) and Path(f).suffix in TEXT_SUFFIXES
          and Path(f).name not in GIT_CONFIG
          and (Path(root) / f).is_file()]


def check_repo(root=".", paths=(), min_quote_words=3, skip=DEFAULT_SKIP):
  root = Path(root)
  return [f for rel in tracked_files(root, paths, skip) for f in check_file(root / rel, rel, min_quote_words)]


def main(argv=None) -> int:
  ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  sub = ap.add_subparsers(dest="cmd", required=True)
  c = sub.add_parser("check", help="committed files of the project")
  c.add_argument("paths", nargs="*", help="limit to these paths (default: every tracked file)")
  c.add_argument("--root", default=".")
  c.add_argument("--min-quote-words", type=int, default=3)
  c.add_argument("--include-vendored", action="store_true", help="also read eegpipe/ and eegharness/")
  a = ap.parse_args(argv)
  found = check_repo(a.root, a.paths, a.min_quote_words, () if a.include_vendored else DEFAULT_SKIP)
  for f in found:
    loc = f"{f['path']}:{f['line']}" if f["line"] else f["path"]
    print(f"{loc}: {f['kind']}: {f['excerpt']}")
  print(f"{len(found)} finding(s)")
  return 1 if found else 0


if __name__ == "__main__":
  sys.exit(main())
