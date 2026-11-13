"""Versioned output folders: every run writes a new folder and never overwrites (G9).

    from eegharness.outputs import new_output_dir
    out = new_output_dir("outputs/first_result", inputs=[cfg_path], params=vars(args))
    (out / "scores.csv").write_text(...)

``new_output_dir`` creates ``<out>/<UTC time>_<commit>[_dirty]/`` (``exist_ok=False``) and
writes ``provenance.json`` into it before anything else (two runs started in the same second
get ``_2``, ``_3``, … appended; an existing folder is never reused): the command, working directory,
commit, whether tracked files were modified, UTC start time, Python, platform, versions of
the scientific packages that are imported, torch's device and determinism settings if torch
is imported (``compute``, else null), the parameters given, and the size and SHA-256
of every input file (folders are expanded to their files, sorted).

Compute time (0.5.0, BACKLOG L37): every measurement or reporting output records how long it took.
Start a ``ComputeTimer`` before the work, then ``record_compute_time(out, timer)`` when the outputs are
written; it adds ``compute_time`` to ``provenance.json``: wall seconds, CPU seconds of this process and of
its finished child processes, the device given, and the UTC end. An output that involved no computation
records ``compute_time: null`` with a reason (``record_no_compute``). Nothing is written by default, so an
output that never recorded it fails the check:

    python -m eegharness.outputs check outputs/            # every provenance.json below; exit 1 on a problem
"""

import hashlib
import argparse
import json
import math
import os
import platform
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

from . import __version__
from .seeds import torch_state

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
    "compute": torch_state(),
    "eegharness": __version__,
    "params": params or {},
    "inputs": described,
  }
  with open(folder / "provenance.json", "x") as f:
    json.dump(prov, f, indent=1, default=str)
    f.write("\n")
  return folder


COMPUTE_KEY = "compute_time"


class ComputeTimer:
  """Wall and CPU time from creation to ``stop()``; start it before the work the output reports."""

  def __init__(self, device=None):
    self.device = device
    self._wall0 = time.perf_counter()
    self._t0 = os.times()

  def stop(self) -> dict:
    t1, wall = os.times(), time.perf_counter() - self._wall0
    return {"wall_s": round(wall, 3),
            "cpu_s": round((t1.user - self._t0.user) + (t1.system - self._t0.system), 3),
            "cpu_children_s": round((t1.children_user - self._t0.children_user)
                                    + (t1.children_system - self._t0.children_system), 3),
            "device": self.device,
            "utc_end": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")}


def _update_provenance(folder, fields: dict) -> dict:
  path = Path(folder) / "provenance.json"
  prov = json.loads(path.read_text())
  if COMPUTE_KEY in prov:
    raise ValueError(f"{path} already records {COMPUTE_KEY}; an output records it once (G9)")
  prov.update(fields)
  tmp = path.with_name("provenance.json.tmp")
  tmp.write_text(json.dumps(prov, indent=1, default=str) + "\n")
  os.replace(tmp, path)
  return prov


def record_compute_time(folder, timer) -> dict:
  """Add ``compute_time`` (from a ``ComputeTimer``, or its ``stop()`` dict) to the folder's provenance."""
  ct = timer.stop() if isinstance(timer, ComputeTimer) else dict(timer)
  probs = _compute_problems(ct, None)
  if probs:
    raise ValueError("; ".join(probs))
  return _update_provenance(folder, {COMPUTE_KEY: ct})


def record_no_compute(folder, reason: str) -> dict:
  """Record ``compute_time: null`` for an output that involved no computation, with the reason."""
  if not str(reason or "").strip():
    raise ValueError("record_no_compute needs a reason")
  return _update_provenance(folder, {COMPUTE_KEY: None, "compute_time_reason": str(reason).strip()})


def _compute_problems(ct, prov) -> list:
  if ct is None:
    return [] if str((prov or {}).get("compute_time_reason", "")).strip() else ["compute_time is null without a compute_time_reason"]
  if not isinstance(ct, dict):
    return [f"compute_time is {type(ct).__name__}, not an object or null"]
  probs = []
  for k in ("wall_s", "cpu_s"):
    v = ct.get(k)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0:
      probs.append(f"compute_time.{k} is {v!r}, not a finite number >= 0")
  return probs


def check_compute_time(folder) -> list:
  """Problems of one output folder's ``compute_time`` (empty list: it is recorded)."""
  path = Path(folder) / "provenance.json"
  if not path.is_file():
    return [f"{folder}: no provenance.json"]
  prov = json.loads(path.read_text())
  if COMPUTE_KEY not in prov:
    return [f"{folder}: compute_time not recorded (record_compute_time, or record_no_compute with a reason)"]
  return [f"{folder}: {p}" for p in _compute_problems(prov[COMPUTE_KEY], prov)]


def main(argv=None) -> int:
  ap = argparse.ArgumentParser(description="Check that output folders record their compute time.")
  sub = ap.add_subparsers(dest="cmd", required=True)
  c = sub.add_parser("check", help="every provenance.json under the given folders")
  c.add_argument("paths", nargs="+")
  a = ap.parse_args(argv)
  folders = []
  for p in map(Path, a.paths):
    folders += sorted({f.parent for f in ([p / "provenance.json"] if (p / "provenance.json").is_file()
                                          else p.rglob("provenance.json"))})
  problems = [x for f in folders for x in check_compute_time(f)]
  for x in problems:
    print(x)
  print(f"{len(folders)} output folder(s), {len(problems)} problem(s)")
  return 1 if problems or not folders else 0


if __name__ == "__main__":
  sys.exit(main())
