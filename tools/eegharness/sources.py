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
                     same paragraph;
  unquoted_attribution  a paragraph that attributes something to a named person with a date
                     ("Sebastian 2026-11-10: ...", "(Sebastian, 2026-11-13)": the name and an ISO
                     date within ``ATTRIBUTION_SPAN`` characters, either order) without quoting
                     them, as above. Only with names configured; a paragraph already reported as
                     unquoted_contact is not reported again;
  committed_names    the names list is in a git-tracked ``.claude/harness.json`` (it is meant to
                     stay local).

Names are not in the code: they come from the project's local, uncommitted ``.claude/harness.json``
(``{"sources": {"names": ["Sebastian"]}}``; none by default, so the attribution check is off) and
from ``--name`` on the command line.

A paragraph is a block of lines between blank lines. In a JSON file every string value is checked
on its own (the JSON quotes themselves do not count as a quotation). Untracked and ignored files
are not read: they are not committed; nor are git's own files (``.gitignore`` names ``agent_runs/`` to
ignore it). The vendored copies ``eegpipe/`` and ``eegharness/`` are
skipped by default.

    python -m eegharness.sources check [--root .] [--min-quote-words 3] [--name N ...] [paths ...]   # exit 1 on a finding
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
DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
ATTRIBUTION_SPAN = 60  # characters between the name and the date, either order, in the paragraph's text
HARNESS_JSON = ".claude/harness.json"


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


def _name_pattern(names):
  names = [n.strip() for n in names or () if n and n.strip()]
  if not names:
    return None
  return re.compile(r"\b(?:%s)(?:'s)?\b" % "|".join(re.escape(n) for n in names))


def _attribution(par, name_re):
  """Offset of the first name that has an ISO date within ATTRIBUTION_SPAN characters, else None."""
  dates = [(m.start(), m.end()) for m in DATE.finditer(par)]
  for m in name_re.finditer(par):
    if any(-ATTRIBUTION_SPAN <= ds - m.end() <= ATTRIBUTION_SPAN or -ATTRIBUTION_SPAN <= m.start() - de <= ATTRIBUTION_SPAN
           for ds, de in dates):
      return m.start()
  return None


def check_text(text, path="<text>", min_quote_words=3, line_offset=0, names=()):
  """Findings in one text: dicts with path, line, kind, excerpt."""
  found = []
  name_re = _name_pattern(names)
  for start, par in _paragraphs(text):
    for m in UNCOMMITTED.finditer(par):
      line = start + par[:m.start()].count("\n") + line_offset
      found.append({"path": str(path), "line": line, "kind": "uncommitted_path",
                    "excerpt": par.splitlines()[par[:m.start()].count("\n")].strip()[:160]})
    if _has_quote(par, min_quote_words):
      continue
    m = CONTACT.search(par)
    at, kind = (m.start(), "unquoted_contact") if m else (None, None)
    if at is None and name_re is not None:
      at, kind = _attribution(par, name_re), "unquoted_attribution"
    if at is not None:
      k = par[:at].count("\n")
      found.append({"path": str(path), "line": start + k + line_offset, "kind": kind,
                    "excerpt": par.splitlines()[k].strip()[:160]})
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


def check_file(path, rel=None, min_quote_words=3, names=()):
  rel = rel or str(path)
  text = Path(path).read_text(errors="replace")
  if str(path).endswith(".json"):
    try:
      obj = json.loads(text)
    except ValueError:
      return check_text(text, rel, min_quote_words, names=names)
    found = []
    for where, s in _json_strings(obj):
      for f in check_text(s, f"{rel}:{where}", min_quote_words, names=names):
        f["line"] = None
        found.append(f)
    return found
  return check_text(text, rel, min_quote_words, names=names)


def config_names(root="."):
  """The names list from the project's local .claude/harness.json (``sources.names``); [] if absent."""
  p = Path(root) / HARNESS_JSON
  if not p.is_file():
    return []
  try:
    names = json.loads(p.read_text()).get("sources", {}).get("names", [])
  except (ValueError, AttributeError):
    raise ValueError(f"{p}: not a JSON object with sources.names")
  if not isinstance(names, list) or not all(isinstance(n, str) and n.strip() for n in names):
    raise ValueError(f"{p}: sources.names must be a list of non-empty strings")
  return names


def _tracked(root, rel):
  r = subprocess.run(["git", "-C", str(root), "ls-files", "--error-unmatch", "--", rel], capture_output=True, text=True)
  return r.returncode == 0


def tracked_files(root, paths=(), skip=DEFAULT_SKIP):
  """Git-tracked text files under ``paths`` (default: the whole tree), minus ``skip`` prefixes."""
  r = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--", *paths], capture_output=True, text=True, check=True)
  files = [f for f in r.stdout.split("\0") if f]
  return [f for f in files if not f.startswith(tuple(skip)) and Path(f).suffix in TEXT_SUFFIXES
          and Path(f).name not in GIT_CONFIG
          and (Path(root) / f).is_file()]


def check_repo(root=".", paths=(), min_quote_words=3, skip=DEFAULT_SKIP, names=None):
  """Findings in the committed files. ``names=None`` reads the local .claude/harness.json list."""
  root = Path(root)
  found = []
  if names is None:
    names = config_names(root)
    if names and _tracked(root, HARNESS_JSON):
      found.append({"path": HARNESS_JSON, "line": None, "kind": "committed_names",
                    "excerpt": "the sources.names list is in a committed file; keep .claude/harness.json local"})
  return found + [f for rel in tracked_files(root, paths, skip)
                  for f in check_file(root / rel, rel, min_quote_words, names)]


def main(argv=None) -> int:
  ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  sub = ap.add_subparsers(dest="cmd", required=True)
  c = sub.add_parser("check", help="committed files of the project")
  c.add_argument("paths", nargs="*", help="limit to these paths (default: every tracked file)")
  c.add_argument("--root", default=".")
  c.add_argument("--min-quote-words", type=int, default=3)
  c.add_argument("--include-vendored", action="store_true", help="also read eegpipe/ and eegharness/")
  c.add_argument("--name", action="append", default=[],
                 help="a person's name for the attribution check, added to .claude/harness.json sources.names")
  a = ap.parse_args(argv)
  names = config_names(a.root) + a.name
  found = check_repo(a.root, a.paths, a.min_quote_words, () if a.include_vendored else DEFAULT_SKIP, names=names)
  if config_names(a.root) and _tracked(a.root, HARNESS_JSON):
    found.insert(0, {"path": HARNESS_JSON, "line": None, "kind": "committed_names",
                     "excerpt": "the sources.names list is in a committed file; keep .claude/harness.json local"})
  for f in found:
    loc = f"{f['path']}:{f['line']}" if f["line"] else f["path"]
    print(f"{loc}: {f['kind']}: {f['excerpt']}")
  print(f"{len(found)} finding(s)")
  return 1 if found else 0


if __name__ == "__main__":
  sys.exit(main())
