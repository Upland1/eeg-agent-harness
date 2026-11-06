"""Known-answer tests for the document reader and the paradigm-analyst's access to the data folder
(G16, L25): documents are read through a reader that refuses recordings; the guard enforces it."""

import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

KIT = Path(__file__).resolve().parents[1]
READER = KIT / "tools" / "read_document.py"
sys.path.insert(0, str(KIT))
import new_project  # noqa: E402


def read(path, *opts, plugins=None, cwd=None):
  args = [sys.executable, "-I", str(READER), str(path), *opts]
  if plugins is not None:
    args += ["--plugins", str(plugins)]
  return subprocess.run(args, capture_output=True, text=True, cwd=cwd)


def make_docx(path: Path, paragraphs, table):
  w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
  p = "".join(f"<w:p><w:r><w:t>{x}</w:t></w:r></w:p>" for x in paragraphs)
  rows = "".join("<w:tr>" + "".join(f"<w:tc><w:p><w:r><w:t>{c}</w:t></w:r></w:p></w:tc>" for c in r) + "</w:tr>"
                 for r in table)
  with zipfile.ZipFile(path, "w") as z:
    z.writestr("[Content_Types].xml", "<Types/>")
    z.writestr("word/document.xml", f'<w:document xmlns:w="{w}"><w:body>{p}<w:tbl>{rows}</w:tbl></w:body></w:document>')


def test_docx_with_table(tmp_path):
  """Known answer: paragraphs in order, then table rows as 'a | b'; header names type and size."""
  f = tmp_path / "Bitácora.docx"
  make_docx(f, ["Session log", "S3: Pz noisy"], [["Subject", "Code 2 means"], ["all", "target"]])
  r = read(f)
  assert r.returncode == 0, r.stderr
  assert r.stdout.splitlines()[1:] == ["Session log", "S3: Pz noisy", "Subject | Code 2 means", "all | target"]
  assert r.stdout.startswith(f"document: {f} (docx, {f.stat().st_size} bytes")


def test_text_types_and_offset(tmp_path):
  """Known answer: a CSV is printed verbatim; --max-chars cuts and names the offset to continue; latin-1 decodes."""
  f = tmp_path / "log.csv"
  f.write_text("subject,session,note\nS1,1,ok\n")
  assert read(f).stdout.splitlines()[1:3] == ["subject,session,note", "S1,1,ok"]
  r = read(f, "--max-chars", "7")
  assert r.stdout.splitlines()[1] == "subject" and "continue with --offset 7" in r.stdout
  assert read(f, "--offset", "7", "--max-chars", "8").stdout.splitlines()[1] == ",session"
  g = tmp_path / "notes.txt"
  g.write_bytes("Bit\xe1cora".encode("latin-1"))
  assert "Bitácora" in read(g).stdout


@pytest.mark.parametrize("name,content,why", [
  ("a.edf", b"0       ", "recording format"),
  ("a.vhdr", b"Brain Vision", "recording format"),
  ("a.xyz", b"raw", "recording format"),            # declared by a project reader plugin
  ("a.bin", b"\x00\x01", "not a document format"),
  ("a.txt", b"DATA\x00\x00\x01\x02", "binary content"),  # a recording renamed .txt
  ("a.docx", b"not a zip", "not a zip"),
  ("a.pdf", b"\x00\x01\x02", "no PDF header"),
])
def test_refuses_recordings_and_disguised_files(tmp_path, name, content, why):
  """Known answer: recording formats (MNE, plugins), unknown formats and recordings with a document name are refused (exit 3)."""
  plugins = tmp_path / "readers"
  plugins.mkdir()
  (plugins / "xyz.py").write_text('EXTENSIONS = (".xyz",)\n\ndef read(path):\n  raise NotImplementedError\n')
  f = tmp_path / name
  f.write_bytes(content)
  r = read(f, plugins=plugins)
  assert r.returncode == 3 and why in r.stderr and r.stdout == "", r.stderr


@pytest.mark.skipif(shutil.which("pdftotext") is None, reason="pdftotext not installed")
def test_pdf(tmp_path):
  """Known answer: text drawn in a minimal hand-written PDF comes back through pdftotext."""
  stream = b"BT /F1 12 Tf 72 720 Td (Code 2 is the target) Tj ET"
  objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
          b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
          b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
          b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
  out, offs = b"%PDF-1.4\n", []
  for i, o in enumerate(objs, 1):
    offs.append(len(out))
    out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
  xref = len(out)
  out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + b"".join(b"%010d 00000 n \n" % o for o in offs)
  out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
  f = tmp_path / "protocol.pdf"
  f.write_bytes(out)
  r = read(f)
  assert r.returncode == 0 and "Code 2 is the target" in r.stdout, r.stderr


def test_guard_document_list_matches_profiler():
  """Known answer: the guard's DOCUMENT_EXTS equals the profiler's (they are kept as two copies)."""
  sys.path.insert(0, str(KIT / "tools"))
  from eegprofile.formats import DOCUMENT_EXTS
  g = (KIT / "template" / ".claude" / "hooks" / "guard.py").read_text()
  block = g[g.index("DOCUMENT_EXTS = {"):g.index("}", g.index("DOCUMENT_EXTS = {"))]
  assert set(re.findall(r'"(\.[a-z]+)"', block)) == DOCUMENT_EXTS


@pytest.fixture(scope="module")
def proj(tmp_path_factory):
  p = tmp_path_factory.mktemp("a") / "proj"
  new_project.main([str(p), "--name", "proj", "--allow-dirty"])
  (p / "data" / "raw" / "S1").mkdir(parents=True)
  make_docx(p / "data" / "raw" / "Bitácora.docx", ["log"], [["a", "b"]])
  (p / "data" / "raw" / "S1" / "a.edf").write_bytes(b"0")
  return p


def analyst(p, tool, inp):
  ev = {"tool_name": tool, "tool_input": inp, "cwd": str(p), "agent_type": "paradigm-analyst"}
  return subprocess.run([sys.executable, str(p / ".claude" / "hooks" / "guard.py")], input=json.dumps(ev),
                        capture_output=True, text=True,
                        env={"CLAUDE_PROJECT_DIR": str(p), "PATH": "/usr/bin:/bin"}).returncode


def test_analyst_reads_documents_only_through_the_reader(proj):
  """Known answer: the reader on a document passes; the reader on a recording, any other command, and
  Read/Grep under data/ are blocked; Read of inputs/ and docs/ passes."""
  p = proj
  ok = ["python3 .harness/tools/read_document.py 'data/raw/Bitácora.docx'",
        ".venv/bin/python .harness/tools/read_document.py data/raw/Bitácora.docx --offset 40000",
        "python3 .harness/tools/read_document.py inputs/notes.md 2>&1"]
  for cmd in ok:
    assert analyst(p, "Bash", {"command": cmd}) == 0, cmd
  bad = ["python3 .harness/tools/read_document.py data/raw/S1/a.edf",
         "cat data/raw/Bitácora.docx",
         "python3 -c 'print(1)'",
         "python3 .harness/tools/read_document.py data/raw/Bitácora.docx > docs/copy.txt",
         "python3 .harness/tools/read_document.py data/raw/Bitácora.docx && ls data/raw",
         "python3 /tmp/read_document.py data/raw/Bitácora.docx",
         "ls data/raw"]
  for cmd in bad:
    assert analyst(p, "Bash", {"command": cmd}) == 2, cmd
  assert analyst(p, "Read", {"file_path": str(p / "data" / "raw" / "Bitácora.docx")}) == 2
  assert analyst(p, "Read", {"file_path": str(p / "data" / "raw" / "S1" / "a.edf")}) == 2
  assert analyst(p, "Grep", {"pattern": "x", "path": str(p / "data")}) == 2
  assert analyst(p, "Read", {"file_path": str(p / "docs" / "DECISIONS.md")}) == 0
  assert analyst(p, "Glob", {"pattern": "**/*", "path": str(p / "data" / "raw")}) == 0  # names only
