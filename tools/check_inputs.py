"""The inputs are the human's own words before onboarding starts (0.6.0, L42, L46).

    python .harness/tools/check_inputs.py [--root .]   # exit 1 on a finding; /onboard does not start then

Reads every text file in ``inputs/`` (tracked or not; .md, .txt, .rst, .tex, .csv, .json, .yaml, .yml, .html)
and reports:

  placeholder         a template placeholder ``<...>`` (e.g. ``Goal: <what the requester wants: ...>``): a
                      template filled in only partly is not the requester's request, and an example in it is
                      not something anyone said (L42). HTML comments, autolinks (``<https://...>``), e-mail
                      addresses and common HTML tags are not placeholders;
  unquoted_contact /  text that reports a named person's words without quoting them, the check of
  unquoted_attribution  ``eegharness.sources`` (G15) with the names in the local ``.claude/harness.json``
                      (``sources.names``): a text in inputs/ that reports a human's words quotes them
                      verbatim with the date (L46).

Prints every finding as ``path:line: kind: excerpt``, then the count, or PASS. Standard library only.
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eegharness import sources  # noqa: E402

TEXT_EXTS = {".md", ".txt", ".rst", ".tex", ".csv", ".json", ".yaml", ".yml", ".html", ".htm", ""}
HTML_TAGS = {"a", "b", "i", "u", "p", "br", "hr", "em", "strong", "sub", "sup", "span", "div", "img", "code", "pre",
             "table", "tr", "td", "th", "ul", "ol", "li", "details", "summary", "small", "kbd"}
ANGLE = re.compile(r"<([^<>\n]+)>")


TAG = re.compile(r"/?([A-Za-z][A-Za-z0-9]*)(\s[^<>]*)?/?")


def placeholders(text):
  """[(line, excerpt)] of every ``<...>`` that is a template placeholder."""
  out = []
  for n, line in enumerate(text.splitlines(), 1):
    for m in ANGLE.finditer(line):
      if m.group(1) != m.group(1).strip():
        continue  # "p < 0.05 and q > 1": a comparison has spaces inside the brackets, a placeholder does not
      inner = m.group(1)
      tag = TAG.fullmatch(inner)
      if (inner.startswith(("!", "?"))                                   # <!-- comment -->, <!doctype>, <?xml?>
          or re.match(r"^[a-z][a-z0-9+.-]*://", inner)                   # <https://...>
          or re.fullmatch(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}", inner)       # <name@host.org>
          or (tag and tag.group(1).lower() in HTML_TAGS)                  # <br>, </sub>, <img src=...>
          or not re.search(r"[A-Za-z]", inner)):                         # "<0.05>"
        continue
      out.append((n, m.group(0)[:160]))
  return out


def check(root):
  root = Path(root)
  folder = root / "inputs"
  names = sources.config_names(root)
  found = []
  if not folder.is_dir():
    return [{"path": "inputs/", "line": None, "kind": "missing", "excerpt": "no inputs/ folder"}]
  for f in sorted(p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in TEXT_EXTS):
    rel = f.relative_to(root).as_posix()
    try:
      text = f.read_text()
    except UnicodeDecodeError:
      continue
    found += [{"path": rel, "line": n, "kind": "placeholder", "excerpt": e} for n, e in placeholders(text)]
    found += [x for x in sources.check_text(text, rel, names=names)
              if x["kind"] in ("unquoted_contact", "unquoted_attribution", "undated_approval")]
  return found


def main(argv=None):
  ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  ap.add_argument("--root", default=".")
  a = ap.parse_args(argv)
  found = check(a.root)
  if not sources.config_names(a.root):
    print("note: no names in .claude/harness.json sources.names, so reported words of a person are not checked (L46)")
  for f in found:
    print(f"{f['path']}:{f['line']}: {f['kind']}: {f['excerpt']}" if f["line"] else f"{f['path']}: {f['kind']}: {f['excerpt']}")
  print(f"{len(found)} finding(s)" if found else "PASS")
  return 1 if found else 0


if __name__ == "__main__":
  sys.exit(main())
