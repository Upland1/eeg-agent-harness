"""Print the text of a written document (lab log, README, protocol sheet, table); refuse recordings.

  python .harness/tools/read_document.py <path> [--offset N] [--max-chars N]

For the paradigm-analyst (CLAUDE.md G16): documents in the data folder are read through this
script, never with a file-reading tool. It reads only document formats (the profiler's
DOCUMENT_EXTS: .txt .md .rst .pdf .docx .odt .rtf .html .csv .tsv .json .xlsx .ods .log
.ini .yaml ...) and refuses:
  - any other extension, every extension MNE reads, and every extension a project reader
    plugin in readers/ declares (recording formats);
  - a text-type file containing NUL bytes, and a .docx/.odt/.xlsx/.ods that is not a
    zip document, or a .pdf without a PDF header (a recording with a document name);
  - files over 50 MB.
Output: one header line (path, type, size, SHA-256), then the text. Long text is cut at
--max-chars; the last line says how to read on with --offset. Exit 0 on success, 3 when
refused, 4 when the document could not be converted.
"""

import argparse
import hashlib
import re
import subprocess
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))

from eegprofile.formats import DOCUMENT_EXTS, MNE_EXTENSIONS as MNE_EXTS  # noqa: E402  (no numpy needed)

TEXT_EXTS = {".txt", ".md", ".rst", ".csv", ".tsv", ".json", ".log", ".ini", ".yaml", ".yml", ".html", ".htm"}
MAX_BYTES = 50 * 1024 * 1024
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
TEXT_NS = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"


class Refused(Exception):
  pass


def plugin_extensions(folders) -> set:
  """Extensions declared by reader plugins (read as text, never imported)."""
  exts = set()
  for folder in folders:
    for f in Path(folder).glob("*.py"):
      m = re.search(r"EXTENSIONS\s*=\s*[\(\[]([^\)\]]*)[\)\]]", f.read_text(errors="ignore"))
      if m:
        exts |= {e.lower() for e in re.findall(r"['\"](\.[^'\"]+)['\"]", m.group(1))}
  return exts


def check(path: Path, plugin_dirs) -> str:
  if not path.is_file():
    raise Refused(f"not a file: {path}")
  ext = path.suffix.lower()
  recording_exts = set(MNE_EXTS) | plugin_extensions(plugin_dirs)
  if ext in recording_exts:
    raise Refused(f"{ext} is a recording format; recordings are read only by project code.")
  if ext not in DOCUMENT_EXTS:
    raise Refused(f"{ext or '(no extension)'} is not a document format this reader accepts "
                  f"({' '.join(sorted(DOCUMENT_EXTS))}).")
  if path.stat().st_size > MAX_BYTES:
    raise Refused(f"{path.stat().st_size} bytes is over the {MAX_BYTES} byte limit for a document.")
  head = path.read_bytes()[:65536]
  if ext in TEXT_EXTS and b"\x00" in head:
    raise Refused(f"{path.name} has a text extension but binary content; it may be a recording.")
  if ext in (".docx", ".odt", ".xlsx", ".ods") and not zipfile.is_zipfile(path):
    raise Refused(f"{path.name} is not a {ext} document (not a zip container).")
  if ext == ".pdf" and not head.startswith(b"%PDF"):
    raise Refused(f"{path.name} has no PDF header.")
  return ext


def _docx(path: Path) -> str:
  with zipfile.ZipFile(path) as z:
    root = ET.fromstring(z.read("word/document.xml"))
  lines = []
  body = root.find(f"{W}body")
  for el in (body if body is not None else []):
    if el.tag == f"{W}p":
      lines.append("".join(t.text or "" for t in el.iter(f"{W}t")))
    elif el.tag == f"{W}tbl":
      for row in el.iter(f"{W}tr"):
        cells = ["".join(t.text or "" for t in c.iter(f"{W}t")) for c in row.iter(f"{W}tc")]
        lines.append(" | ".join(cells))
  return "\n".join(lines)


def _odf(path: Path) -> str:
  with zipfile.ZipFile(path) as z:
    root = ET.fromstring(z.read("content.xml"))
  return "\n".join("".join(p.itertext()) for p in root.iter() if p.tag in (f"{TEXT_NS}p", f"{TEXT_NS}h"))


def _xlsx(path: Path) -> str:
  with zipfile.ZipFile(path) as z:
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
      shared = ["".join(t.text or "" for t in si.iter(f"{S}t"))
                for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(f"{S}si")]
    out = []
    for name in sorted(n for n in z.namelist() if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n)):
      out.append(f"## {Path(name).stem}")
      for row in ET.fromstring(z.read(name)).iter(f"{S}row"):
        vals = []
        for c in row.iter(f"{S}c"):
          v = c.find(f"{S}v")
          txt = "" if v is None else (v.text or "")
          if c.get("t") == "s" and txt.isdigit():
            txt = shared[int(txt)]
          elif c.get("t") == "inlineStr":
            txt = "".join(t.text or "" for t in c.iter(f"{S}t"))
          vals.append(txt)
        out.append("\t".join(vals))
  return "\n".join(out)


def _pdf(path: Path) -> str:
  try:
    r = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True, timeout=120)
  except FileNotFoundError:
    raise RuntimeError("pdftotext (poppler-utils) is not installed; ask the orchestrator for a text copy.")
  if r.returncode != 0:
    raise RuntimeError(f"pdftotext failed: {r.stderr.strip()[:300]}")
  return r.stdout


def _rtf(path: Path) -> str:
  s = path.read_text(errors="replace")
  s = re.sub(r"\\'[0-9a-fA-F]{2}", "", s)
  s = re.sub(r"\\par[d]?\b", "\n", s)
  s = re.sub(r"\\[a-zA-Z]+-?\d* ?|[{}]", "", s)
  return s


def text_of(path: Path, ext: str) -> str:
  if ext == ".docx":
    return _docx(path)
  if ext in (".odt", ".ods"):
    return _odf(path)
  if ext == ".xlsx":
    return _xlsx(path)
  if ext == ".pdf":
    return _pdf(path)
  if ext == ".rtf":
    return _rtf(path)
  if ext in (".doc", ".xls"):
    raise RuntimeError(f"{ext} (legacy binary Office) cannot be converted here; ask the orchestrator for a "
                       "text, .docx or .pdf copy.")
  raw = path.read_bytes()
  for enc in ("utf-8", "latin-1"):
    try:
      return raw.decode(enc)
    except UnicodeDecodeError:
      continue
  return raw.decode("utf-8", errors="replace")


def main(argv=None) -> int:
  ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  ap.add_argument("path")
  ap.add_argument("--offset", type=int, default=0, help="first character to print")
  ap.add_argument("--max-chars", type=int, default=40000)
  ap.add_argument("--plugins", action="append", default=None,
                  help="folder of reader plugins whose extensions are refused (default: ./readers)")
  a = ap.parse_args(argv)
  path = Path(a.path)
  try:
    ext = check(path, a.plugins if a.plugins is not None else ["readers"])
  except Refused as exc:
    print(f"refused: {exc}", file=sys.stderr)
    return 3
  try:
    text = text_of(path, ext)
  except (RuntimeError, KeyError, ET.ParseError, zipfile.BadZipFile) as exc:
    print(f"could not convert {path}: {exc}", file=sys.stderr)
    return 4
  sha = hashlib.sha256(path.read_bytes()).hexdigest()
  chunk = text[a.offset:a.offset + a.max_chars]
  print(f"document: {path} ({ext[1:]}, {path.stat().st_size} bytes, {len(text)} characters, sha256 {sha})")
  print(chunk)
  if a.offset + a.max_chars < len(text):
    print(f"[cut at character {a.offset + a.max_chars} of {len(text)}; continue with --offset {a.offset + a.max_chars}]")
  return 0


if __name__ == "__main__":
  sys.exit(main())
