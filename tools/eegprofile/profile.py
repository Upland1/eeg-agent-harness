"""Measure a dataset folder. Every value is computed from the files; nothing is interpreted."""

import re
import time
import traceback
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from . import __version__
from .registry import Registry

SKIP_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}
# Written documents (lab logs, READMEs, protocol sheets, spreadsheets): listed for the agents to
# read (CLAUDE.md G16), never counted as recordings without a reader. A reader plugin wins.
DOCUMENT_EXTS = {".txt", ".md", ".rst", ".pdf", ".doc", ".docx", ".odt", ".rtf", ".html", ".htm",
                 ".csv", ".tsv", ".json", ".xls", ".xlsx", ".ods", ".log", ".ini", ".yaml", ".yml"}


def shape_of(name: str) -> str:
  """Digits become '#', so 'S12' -> 'S##' and '06-19-19' -> '##-##-##'."""
  return re.sub(r"\d", "#", name)


def normalized(name: str) -> str:
  """Case-folded, with spaces, '-' and '_' removed: spellings that are probably the same name."""
  return re.sub(r"[\s_\-]+", "", name.casefold())


def _stats(x) -> dict:
  x = np.asarray(x, dtype=float)
  if x.size == 0:
    return {"n": 0}
  return {"n": int(x.size), "min": float(x.min()), "median": float(np.median(x)),
          "max": float(x.max()), "mean": float(x.mean())}


def profile_recording(rec) -> dict:
  rec.validate()
  fs = float(rec.fs)
  data = np.asarray(rec.data, dtype=float)
  ev = np.asarray(rec.events, dtype=int).reshape(-1, 2)
  ms = 1000.0 / fs
  channels = []
  for i, name in enumerate(rec.ch_names):
    row = data[i]
    finite = row[np.isfinite(row)]
    channels.append({
      "name": str(name), "n_nan": int(row.size - finite.size),
      "std": float(finite.std()) if finite.size else None,
      "min": float(finite.min()) if finite.size else None,
      "max": float(finite.max()) if finite.size else None,
      "flat": bool(finite.size and finite.std() == 0),
    })
  codes = {}
  for code in np.unique(ev[:, 1]) if len(ev) else []:
    onsets = ev[ev[:, 1] == code, 0]
    entry = {"count": int(onsets.size),
             "first_s": float(onsets[0] / fs), "last_s": float(onsets[-1] / fs),
             "interval_same_code_ms": _stats(np.diff(onsets) * ms)}
    if rec.durations is not None:
      entry["duration_ms"] = _stats(np.asarray(rec.durations)[ev[:, 1] == code] * ms)
    if int(code) in rec.event_labels:
      entry["label"] = rec.event_labels[int(code)]
    codes[str(int(code))] = entry
  transitions = defaultdict(list)
  for (s0, c0), (s1, c1) in zip(ev[:-1], ev[1:]):
    transitions[f"{int(c0)}->{int(c1)}"].append((s1 - s0) * ms)
  return {
    "fs": fs, "n_channels": int(data.shape[0]), "ch_names": [str(c) for c in rec.ch_names],
    "n_samples": int(data.shape[1]), "duration_s": float(data.shape[1] / fs),
    "channels": channels, "n_events": int(len(ev)), "codes": codes,
    "transitions": {k: {"count": len(v), "gap_ms": _stats(v)} for k, v in transitions.items()},
    "interval_any_event_ms": _stats(np.diff(ev[:, 0]) * ms) if len(ev) > 1 else {"n": 0},
    "meta": {k: v for k, v in rec.meta.items() if isinstance(v, (str, int, float, bool, list, dict))},
  }


def discover(root: Path):
  return sorted(p for p in root.rglob("*") if p.is_file() and p.name not in SKIP_NAMES)


def structure(root: Path, files) -> dict:
  levels = defaultdict(Counter)
  examples = defaultdict(lambda: defaultdict(list))
  stems = Counter()
  for f in files:
    parts = f.relative_to(root).parts
    for depth, part in enumerate(parts[:-1]):
      s = shape_of(part)
      levels[depth][s] += 1
      if len(examples[depth][s]) < 5 and part not in examples[depth][s]:
        examples[depth][s].append(part)
    stems[f.stem] += 1
  dirs_per_level = defaultdict(set)
  for f in files:
    parts = f.relative_to(root).parts
    for depth in range(len(parts) - 1):
      dirs_per_level[depth].add(parts[:depth + 1])
  groups = defaultdict(set)
  for stem in stems:
    groups[normalized(stem)].add(stem)
  return {
    "folder_levels": [
      {"depth": d, "n_distinct_folders": len(dirs_per_level[d]),
       "name_shapes": [{"shape": s, "n_files_below": n, "examples": examples[d][s]}
                       for s, n in levels[d].most_common()]}
      for d in sorted(levels)],
    "file_depths": dict(Counter(len(f.relative_to(root).parts) - 1 for f in files)),
    "extensions": dict(Counter(f.suffix.lower() or "(none)" for f in files)),
    "file_stems": dict(stems.most_common()),
    "spelling_variants": [sorted(v) for v in groups.values() if len(v) > 1],
  }


def summarize(per_file) -> dict:
  ok = [p for p in per_file if "profile" in p]
  fs = Counter(p["profile"]["fs"] for p in ok)
  chsets = Counter(tuple(p["profile"]["ch_names"]) for p in ok)
  code_files = Counter()
  code_total = Counter()
  same_code = defaultdict(list)
  trans = defaultdict(lambda: [0, []])
  for p in ok:
    for code, e in p["profile"]["codes"].items():
      code_files[code] += 1
      code_total[code] += e["count"]
      if e["interval_same_code_ms"].get("n"):
        same_code[code].append(e["interval_same_code_ms"]["median"])
    for k, t in p["profile"]["transitions"].items():
      trans[k][0] += t["count"]
      trans[k][1].append(t["gap_ms"]["median"])
  code_sets = Counter(tuple(sorted(p["profile"]["codes"], key=int)) for p in ok)
  by_stem_shape = defaultdict(Counter)
  for p in ok:
    by_stem_shape[shape_of(Path(p["path"]).stem)][p["profile"]["n_events"]] += 1
  return {
    "n_files": len(per_file), "n_profiled": len(ok),
    "n_unreadable": sum(1 for p in per_file if "error" in p),
    "n_no_reader": sum(1 for p in per_file if p.get("reader") is None and p.get("kind") != "document"),
    "n_documents": sum(1 for p in per_file if p.get("kind") == "document"),
    "sampling_rates_hz": {str(k): v for k, v in fs.items()},
    "channel_sets": [{"channels": list(k), "n_files": v} for k, v in chsets.most_common()],
    "duration_s": _stats([p["profile"]["duration_s"] for p in ok]),
    "codes": {c: {"n_files": code_files[c], "total_count": code_total[c],
                  "median_of_file_medians_same_code_interval_ms":
                    float(np.median(same_code[c])) if same_code[c] else None}
              for c in sorted(code_files, key=int)},
    "distinct_code_sets": [{"codes": list(k), "n_files": v} for k, v in code_sets.most_common()],
    "transitions": sorted(({"transition": k, "count": v[0],
                            "median_of_file_medians_gap_ms": float(np.median(v[1]))}
                           for k, v in trans.items()), key=lambda r: -r["count"]),
    "n_events_by_file_name_shape": {s: dict(c) for s, c in by_stem_shape.items()},
  }


def profile_dataset(root, plugins=(), max_files=None, use_mne=True) -> dict:
  root = Path(root)
  registry = Registry(plugins=plugins, use_mne=use_mne)
  files = discover(root)
  t0 = time.time()
  per_file = []
  for i, f in enumerate(files):
    rel = str(f.relative_to(root))
    reader = registry.reader_for(f)
    entry = {"path": rel, "reader": Registry.name(reader) if reader else None}
    if reader is None and f.suffix.lower() in DOCUMENT_EXTS:
      entry["kind"] = "document"
      entry["size_bytes"] = f.stat().st_size
    if reader is not None and (max_files is None or i < max_files):
      try:
        entry["profile"] = profile_recording(reader.read(f))
      except Exception as exc:  # recorded, never hidden
        entry["error"] = f"{type(exc).__name__}: {exc}"
        entry["traceback_tail"] = traceback.format_exc().splitlines()[-3:]
    per_file.append(entry)
  return {
    "profiler_version": __version__,
    "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    "root": str(root), "plugins": [str(p) for p in plugins], "max_files": max_files,
    "runtime_s": round(time.time() - t0, 2),
    "structure": structure(root, files),
    "summary": summarize(per_file),
    "files": per_file,
  }
