"""Where the recordings are stored: mount point, filesystem and whether the device is removable (0.6.0, L44).

A long run depends on ``data/raw`` resolving to the same files for its whole duration; recordings on a
removable drive (e.g. an exFAT USB disk mounted under /media) can disappear mid-run. The profiler records
this in DATA_PROFILE; the pre-batch check (``eegharness.compute precheck``) confirms the files are there.
Linux: ``/proc/self/mountinfo`` and ``/sys/class/block/<dev>/removable``; elsewhere the fields are None.
Standard library only.
"""

import os
import re
from pathlib import Path


def _unescape(s):
  return re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), s)


def parse_mountinfo(text):
  """[(mount_point, fs_type, source)] from /proc/self/mountinfo text."""
  out = []
  for line in text.splitlines():
    if " - " not in line:
      continue
    left, right = line.split(" - ", 1)
    f, r = left.split(), right.split()
    if len(f) >= 5 and len(r) >= 2:
      out.append((_unescape(f[4]), r[0], _unescape(r[1])))
  return out


def _removable(source, sys_root):
  m = re.fullmatch(r"/dev/([A-Za-z0-9]+?)(p?\d+)?", source or "")
  if not m:
    return None
  for dev in (m.group(0)[5:], m.group(1)):
    p = Path(sys_root) / "class" / "block" / dev / "removable"
    try:
      v = p.read_text().strip()
    except OSError:
      continue
    if v in ("0", "1"):
      return v == "1"
  return None


def storage(path, mountinfo=None, sys_root="/sys"):
  """{"path", "resolved", "mount_point", "fs_type", "source", "removable", "under_media"} for ``path``."""
  resolved = os.path.realpath(path)
  if mountinfo is None:
    try:
      mountinfo = Path("/proc/self/mountinfo").read_text()
    except OSError:
      mountinfo = ""
  best = None
  for mp, fs, src in parse_mountinfo(mountinfo):
    if resolved == mp or resolved.startswith(mp.rstrip("/") + "/") or mp == "/":
      if best is None or len(mp) > len(best[0]):
        best = (mp, fs, src)
  mp, fs, src = best if best else (None, None, None)
  return {"path": str(path), "resolved": resolved, "mount_point": mp, "fs_type": fs, "source": src,
          "removable": _removable(src, sys_root) if src else None,
          "under_media": bool(mp and re.match(r"^(/media/|/run/media/|/mnt/|/Volumes/)", mp + "/"))}
