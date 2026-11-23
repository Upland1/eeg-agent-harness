"""Compute limits of a project (``docs/COMPUTE.md``, set by Sebastian) and the checks around long jobs (G22).

0.6.0, BACKLOG L39: a core limit is not a thermal limit. ``cpu_working_threads`` is the number of threads the
jobs of a long run use (below the per-job core limit), enforced on the settings before freeze 1
(``thread_problems``, called by ``eegpipe.settings.validate``); every long-run driver logs CPU and GPU
temperature next to its job table (``templog``).

    python -m eegharness.compute limits [--root .]                       # the parsed limits
    python -m eegharness.compute temps                                   # one sample: utc, cpu_c, gpu_c
    python -m eegharness.compute templog --out <file.tsv> [--interval 60] [--pid PID]
        # appends one row per interval (utc, cpu_c, gpu_c) until PID exits (or until stopped)

Temperatures are read from ``/sys/class/thermal`` and ``/sys/class/hwmon`` (CPU: the package sensor if there is
one, else the maximum) and ``nvidia-smi`` (GPU); an absent source is written as ``not available``, never
guessed. Standard library only.
"""

import argparse
import datetime as dt
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

COMPUTE_MD = Path("docs") / "COMPUTE.md"
NOT_AVAILABLE = "not available"
# settings keys that set a number of worker processes or threads
THREAD_KEYS = {"n_jobs", "num_threads", "n_threads", "threads", "torch_threads", "torch_num_threads",
               "num_workers", "omp_num_threads"}
KEY_LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):[ \t]*(.*?)\s*$")


def parse_limits(text):
  """{key: value} from the ``key: value`` lines of COMPUTE.md (HTML comments ignored). A number is returned as
  int or float, an empty value as None, anything else as the string."""
  text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
  out = {}
  for line in text.splitlines():
    m = KEY_LINE.match(line)
    if not m:
      continue
    v = m.group(2)
    if v == "":
      out[m.group(1)] = None
    elif re.fullmatch(r"-?\d+", v):
      out[m.group(1)] = int(v)
    elif re.fullmatch(r"-?\d+\.\d*|-?\d*\.\d+", v):
      out[m.group(1)] = float(v)
    else:
      out[m.group(1)] = v
  return out


def read_limits(root="."):
  """The limits of ``<root>/docs/COMPUTE.md``, or None when the file does not exist."""
  p = Path(root) / COMPUTE_MD
  return parse_limits(p.read_text()) if p.is_file() else None


def _walk(obj, path=""):
  if isinstance(obj, dict):
    for k, v in obj.items():
      yield from _walk(v, f"{path}.{k}" if path else str(k))
  elif isinstance(obj, list):
    for i, v in enumerate(obj):
      yield from _walk(v, f"{path}[{i}]")
  else:
    yield path, obj


def thread_problems(cfg, limits):
  """Problems with the worker/thread settings of ``cfg`` under ``limits`` (L39). ``limits`` None (no
  COMPUTE.md) checks nothing. Unset ``cpu_working_threads`` is a problem: Sebastian sets it."""
  if limits is None:
    return []
  w = limits.get("cpu_working_threads")
  if not isinstance(w, int) or w < 1:
    return ["docs/COMPUTE.md: cpu_working_threads is not set (Sebastian sets it, L39)"]
  probs = []
  for path, v in _walk(cfg):
    last = path.rsplit(".", 1)[-1]
    key = None if "[" in last else last
    if key not in THREAD_KEYS or v is None or isinstance(v, bool):
      continue
    try:
      n = int(v)
    except (TypeError, ValueError):
      probs.append(f"{path} = {v!r}: not a number of threads")
      continue
    if n < 1:
      probs.append(f"{path} = {n}: all cores, at most cpu_working_threads = {w} (docs/COMPUTE.md, L39)")
    elif n > w:
      probs.append(f"{path} = {n} > cpu_working_threads = {w} (docs/COMPUTE.md, L39)")
  return probs


# Temperatures --------------------------------------------------------------------------------------------

def _read(p):
  try:
    return Path(p).read_text().strip()
  except OSError:
    return None


def cpu_temperature(sys_root="/sys"):
  """CPU temperature in °C: the package sensor (x86_pkg_temp, coretemp 'Package', k10temp Tctl/Tdie) if present,
  else the maximum of the thermal zones; None if nothing can be read."""
  sys_root = Path(sys_root)
  package, others = [], []
  for z in sorted((sys_root / "class" / "thermal").glob("thermal_zone*")):
    t, kind = _read(z / "temp"), (_read(z / "type") or "")
    if t and re.fullmatch(r"-?\d+", t):
      (package if kind in ("x86_pkg_temp",) else others).append(int(t) / 1000.0)
  for h in sorted((sys_root / "class" / "hwmon").glob("hwmon*")):
    name = _read(h / "name") or ""
    if name not in ("coretemp", "k10temp", "zenpower"):
      continue
    for inp in sorted(h.glob("temp*_input")):
      t, label = _read(inp), (_read(inp.with_name(inp.name.replace("_input", "_label"))) or "")
      if t and re.fullmatch(r"-?\d+", t):
        (package if label.startswith(("Package", "Tctl", "Tdie")) else others).append(int(t) / 1000.0)
  vals = package or others
  return max(vals) if vals else None


def gpu_temperature(nvidia_smi_output=None):
  """GPU temperature in °C (the hottest GPU) from ``nvidia-smi``; None without one."""
  if nvidia_smi_output is None:
    if not shutil.which("nvidia-smi"):
      return None
    r = subprocess.run(["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"],
                       capture_output=True, text=True)
    if r.returncode:
      return None
    nvidia_smi_output = r.stdout
  vals = [float(x) for x in nvidia_smi_output.split() if re.fullmatch(r"\d+(\.\d+)?", x)]
  return max(vals) if vals else None


def sample(sys_root="/sys", nvidia_smi_output=None):
  """One row: utc, cpu_c, gpu_c (a missing source as 'not available')."""
  c, g = cpu_temperature(sys_root), gpu_temperature(nvidia_smi_output)
  return {"utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
          "cpu_c": NOT_AVAILABLE if c is None else f"{c:.1f}", "gpu_c": NOT_AVAILABLE if g is None else f"{g:.1f}"}


def _alive(pid):
  try:
    os.kill(pid, 0)
    return True
  except OSError:
    return False


def templog(out, interval=60.0, pid=None, n=None, sys_root="/sys", nvidia_smi_output=None):
  """Append one row per ``interval`` seconds to ``out`` (tab-separated, header utc/cpu_c/gpu_c) until ``pid``
  exits, ``n`` rows are written, or the process is stopped."""
  out = Path(out)
  out.parent.mkdir(parents=True, exist_ok=True)
  if not out.exists():
    out.write_text("utc\tcpu_c\tgpu_c\n")
  k = 0
  while True:
    s = sample(sys_root, nvidia_smi_output)
    with open(out, "a") as f:
      f.write(f"{s['utc']}\t{s['cpu_c']}\t{s['gpu_c']}\n")
    k += 1
    if (n is not None and k >= n) or (pid is not None and not _alive(pid)):
      return k
    time.sleep(interval)


def main(argv=None) -> int:
  ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  sub = ap.add_subparsers(dest="cmd", required=True)
  li = sub.add_parser("limits")
  li.add_argument("--root", default=".")
  sub.add_parser("temps")
  tl = sub.add_parser("templog")
  tl.add_argument("--out", required=True)
  tl.add_argument("--interval", type=float, default=60.0)
  tl.add_argument("--pid", type=int)
  tl.add_argument("--n", type=int)
  a = ap.parse_args(argv)
  if a.cmd == "limits":
    lim = read_limits(a.root)
    if lim is None:
      print(f"{Path(a.root) / COMPUTE_MD}: not found")
      return 1
    for k, v in lim.items():
      print(f"{k}: {'(not set)' if v is None else v}")
    return 0
  if a.cmd == "temps":
    s = sample()
    print(f"{s['utc']}\t{s['cpu_c']}\t{s['gpu_c']}")
    return 0
  templog(a.out, a.interval, a.pid, a.n)
  return 0


if __name__ == "__main__":
  sys.exit(main())
