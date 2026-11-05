"""Versioned output folders: every run writes a new folder and never overwrites (G9).

    from eegharness.outputs import new_output_dir
    out = new_output_dir("outputs/first_result", inputs=[cfg_path], params=vars(args))
    (out / "scores.csv").write_text(...)

``new_output_dir`` creates ``<out>/<UTC time>_<commit>[_dirty]/`` (``exist_ok=False``) and
writes ``provenance.json`` into it before anything else (two runs started in the same second
get ``_2``, ``_3``, … appended; an existing folder is never reused): the command, working directory,
commit, whether tracked files were modified, UTC start time, Python, platform, versions of
the scientific packages that are imported, the parameters given, and the size and SHA-256
of every input file (folders are expanded to their files, sorted).
"""

import hashlib
import json
import platform
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

from . import __version__

PACKAGES = ("numpy", "scipy", "scikit-learn", "mne", "pandas", "torch", "pyriemann", "braindecode")
_MODULE_OF = {"scikit-learn": "sklearn"}


def sha256_file(path, chunk: int = 1 << 20) -> str:
  h = hashlib.sha256()
  with open(path, "rb") as f:
    for block in iter(lambda: f.read(chunk), b""):
      h.update(block)
  return h.hexdigest()


def _git(root: Path, *args) -> str | None:
  try:
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=30)
  except (OSError, subprocess.TimeoutExpired):
    return None
  return r.stdout.strip() if r.returncode == 0 else None


def git_state(root=".") -> dict:
  """Commit (full and short) and whether tracked files differ from it. Untracked files are ignored."""
  root = Path(root)
  full = _git(root, "rev-parse", "HEAD")
  if full is None:
    return {"commit": None, "commit_short": "nogit", "tracked_files_dirty": None}
  status = _git(root, "status", "--porcelain", "--untracked-files=no")
  return {"commit": full, "commit_short": full[:7], "tracked_files_dirty": bool(status)}


def package_versions() -> dict:
  """Versions of the listed packages that this process has imported (others are not loaded)."""
  out = {}
  for dist in PACKAGES:
    if _MODULE_OF.get(dist, dist) in sys.modules:
      try:
        out[dist] = metadata.version(dist)
      except metadata.PackageNotFoundError:
        out[dist] = "unknown"
  return out


def describe_inputs(inputs) -> list:
  """Size and SHA-256 of every input file; a folder is expanded to its files, sorted."""
  rows = []
  for item in inputs:
    p = Path(item)
    files = sorted(f for f in p.rglob("*") if f.is_file()) if p.is_dir() else [p]
    if not p.exists():
      raise FileNotFoundError(f"input not found: {p}")
    for f in files:
      rows.append({"path": str(f), "bytes": f.stat().st_size, "sha256": sha256_file(f)})
  return rows


def new_output_dir(out, *, inputs=(), params=None, root=".", argv=None, now=None) -> Path:
  """Create ``<out>/<UTC>_<commit>[_dirty]/`` and write its ``provenance.json``.

  out     parent folder of all runs of this script (created if missing)
  inputs  files or folders whose SHA-256 identifies what the run read
  params  JSON-serializable parameters of the run (e.g. ``vars(args)``)
  root    the git working tree whose commit identifies the code (default: current folder)
  argv    the command (default ``sys.argv``); now: a datetime, for tests
  """
  now = now or datetime.now(timezone.utc)
  stamp = now.strftime("%Y%m%dT%H%M%SZ")
  git = git_state(root)
  base = f"{stamp}_{git['commit_short']}{'_dirty' if git['tracked_files_dirty'] else ''}"
  described = describe_inputs(inputs)  # before mkdir: a missing input leaves no empty folder
  Path(out).mkdir(parents=True, exist_ok=True)
  for n in range(1, 1000):
    folder = Path(out) / (base if n == 1 else f"{base}_{n}")
    try:
      folder.mkdir(exist_ok=False)  # G9: never reuse a folder
      break
    except FileExistsError:
      continue
  else:
    raise FileExistsError(f"999 output folders named {base}* already exist in {out}")
  prov = {
    "command": shlex.join(argv if argv is not None else [sys.executable, *sys.argv]),
    "cwd": str(Path.cwd()),
    **git,
    "utc_start": stamp,
    "output_dir": str(folder),
    "python": platform.python_version(),
    "platform": platform.platform(),
    "packages": package_versions(),
    "eegharness": __version__,
    "params": params or {},
    "inputs": described,
  }
  with open(folder / "provenance.json", "x") as f:
    json.dump(prov, f, indent=1, default=str)
    f.write("\n")
  return folder
