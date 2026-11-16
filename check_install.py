"""Install check: is this machine ready to build and run eeg-harness projects?

    python check_install.py            # versions, tools, a smoke subset of kit_tests, the worked example (~1 min)
    python check_install.py --quick    # versions and tools only

Checks, each printed as OK / MISSING / TOO OLD / FAILED:
  * Python >= 3.10;
  * required packages at the minimum versions in requirements.txt (numpy, scipy, scikit-learn,
    mne, pytest), read from the installed distributions;
  * optional: torch (networks; reports CPU or the CUDA device), pdftotext (read_document.py),
    git (projects are git repositories), claude (the Claude Code CLI that runs the agents);
  * a smoke subset of kit_tests (guard, project creation, eegharness, numbers, sources and compute
    time, the SSVEP methods, paired statistics, epochs, the profiler);
  * the worked example (examples/ssvep_synthetic) end to end against its pinned outputs.

Exit 0 when everything required is OK; optional items only warn.
"""

import argparse
import re
import shutil
import subprocess
import sys
import time
from importlib import metadata
from pathlib import Path

KIT = Path(__file__).resolve().parent
SMOKE = ["test_kit.py", "test_guard.py", "test_eegharness.py", "test_eegharness_numbers.py",
         "test_eegharness_v05_lessons.py", "test_eegpipe_paired.py", "test_eegpipe_ssvep.py", "test_eegpipe_epochs.py",
         "test_profile.py", "test_worked_example.py"]
DIST = {"numpy": "numpy", "scipy": "scipy", "scikit-learn": "scikit-learn", "mne": "mne", "pytest": "pytest"}


def _ver(v):
  return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


def requirements():
  """{distribution: minimum version} from the uncommented lines of requirements.txt."""
  out = {}
  for line in (KIT / "requirements.txt").read_text().splitlines():
    m = re.match(r"^\s*([A-Za-z0-9_.-]+)\s*>=\s*([0-9.]+)", line)
    if m:
      out[m.group(1)] = m.group(2)
  return out


def main(argv=None):
  ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  ap.add_argument("--quick", action="store_true", help="versions and tools only, no tests")
  a = ap.parse_args(argv)
  bad = []

  def line(status, what, detail=""):
    print(f"  {status:<8} {what}{(': ' + detail) if detail else ''}")
    if status in ("MISSING", "TOO OLD", "FAILED"):
      bad.append(what)

  print(f"eeg-harness {(KIT / 'VERSION').read_text().strip()} at {KIT}")
  print("required")
  py = sys.version_info
  line("OK" if py >= (3, 10) else "TOO OLD", "python", f"{py.major}.{py.minor}.{py.micro} (>= 3.10)")
  for dist, minimum in requirements().items():
    try:
      v = metadata.version(dist)
    except metadata.PackageNotFoundError:
      line("MISSING", dist, f"pip install '{dist}>={minimum}'")
      continue
    line("OK" if _ver(v) >= _ver(minimum) else "TOO OLD", dist, f"{v} (>= {minimum})")
  git = shutil.which("git")
  line("OK" if git else "MISSING", "git", git or "projects are git repositories")

  print("optional")
  try:
    import torch
    dev = f"CUDA {torch.cuda.get_device_name(0)}" if torch.cuda.is_available() else "CPU only (networks run on CPU)"
    print(f"  {'OK':<8} torch: {torch.__version__}, {dev}")
  except ImportError:
    print(f"  {'WARN':<8} torch: not installed; the network methods (EEGNet, ShallowConvNet, GNN, CCNN) are unavailable")
  for tool, why in (("pdftotext", "read_document.py reads PDFs with it"), ("claude", "the Claude Code CLI runs the agents")):
    w = shutil.which(tool)
    print(f"  {'OK' if w else 'WARN':<8} {tool}: {w or 'not found; ' + why}")

  if not a.quick and not bad:
    print("smoke tests and worked example")
    t = time.time()
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                        *[str(KIT / "kit_tests" / f) for f in SMOKE]], cwd=KIT, capture_output=True, text=True)
    last = (r.stdout.strip().splitlines() or ["no output"])[-1]
    line("OK" if r.returncode == 0 else "FAILED", "kit_tests smoke subset", f"{last} ({time.time() - t:.0f} s)")
    if r.returncode:
      print(r.stdout[-3000:], r.stderr[-2000:], sep="\n")

  print("ready" if not bad else f"NOT READY: {', '.join(bad)}")
  return 1 if bad else 0


if __name__ == "__main__":
  sys.exit(main())
