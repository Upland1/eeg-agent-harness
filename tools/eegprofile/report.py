"""Readable Markdown view of a profile. Same numbers as the JSON, no interpretation."""


def _f(x, nd=1):
  return "—" if x is None else (f"{x:.{nd}f}" if isinstance(x, float) else str(x))


def to_markdown(p: dict) -> str:
  s, st = p["summary"], p["structure"]
  out = [
    "# Data profile",
    "",
    f"Measured by the harness profiler v{p['profiler_version']} on {p['created']} "
    f"(runtime {p['runtime_s']} s). Root: `{p['root']}`. Plugins: "
    f"{', '.join(f'`{x}`' for x in p['plugins']) or 'none'}. "
    f"Every number below is computed from the files; nothing is interpreted. "
    f"Full detail: `DATA_PROFILE.json`.",
    "",
    "## Overview",
    "",
    "| Item | Value |", "|---|---|",
    f"| Files found | {s['n_files']} |",
    f"| Profiled | {s['n_profiled']} |",
    f"| No reader for the format | {s['n_no_reader']} |",
    f"| Reader errors | {s['n_unreadable']} |",
    f"| Extensions | {', '.join(f'`{k}` {v}' for k, v in st['extensions'].items())} |",
    f"| Sampling rates (Hz: files) | {', '.join(f'{k}: {v}' for k, v in s['sampling_rates_hz'].items()) or '—'} |",
    f"| Duration per file (s) | min {_f(s['duration_s'].get('min'))}, median {_f(s['duration_s'].get('median'))}, max {_f(s['duration_s'].get('max'))} |",
    "",
    "## Folder structure",
    "",
    "Digits are shown as `#`.",
    "",
    "| Depth | Distinct folders | Name shape | Files below | Examples |", "|---|---|---|---|---|",
  ]
  for lvl in st["folder_levels"]:
    for sh in lvl["name_shapes"]:
      out.append(f"| {lvl['depth']} | {lvl['n_distinct_folders']} | `{sh['shape']}` | "
                 f"{sh['n_files_below']} | {', '.join(f'`{e}`' for e in sh['examples'])} |")
  out += ["", "## File names", "", "| Name (without extension) | Files |", "|---|---|"]
  out += [f"| `{k}` | {v} |" for k, v in st["file_stems"].items()]
  if st["spelling_variants"]:
    out += ["", "Names that differ only in case, spaces, `-` or `_`:", ""]
    out += ["- " + " · ".join(f"`{n}`" for n in g) for g in st["spelling_variants"]]
  out += ["", "## Channels", "", "| Channel set | Files |", "|---|---|"]
  out += [f"| {', '.join(c['channels'])} | {c['n_files']} |" for c in s["channel_sets"]]
  out += ["", "## Event codes (all profiled files)", "",
          "| Code | Files containing it | Total count | Median interval between two events of this code (ms) |",
          "|---|---|---|---|"]
  out += [f"| {c} | {e['n_files']} | {e['total_count']} | {_f(e['median_of_file_medians_same_code_interval_ms'])} |"
          for c, e in s["codes"].items()]
  out += ["", "## Code sets", "", "| Codes present | Files |", "|---|---|"]
  out += [f"| {', '.join(c['codes'])} | {c['n_files']} |" for c in s["distinct_code_sets"]]
  out += ["", "## Transitions (code followed by code; top 40)", "",
          "| Transition | Count | Median gap (ms) |", "|---|---|---|"]
  out += [f"| {t['transition']} | {t['count']} | {_f(t['median_of_file_medians_gap_ms'])} |"
          for t in s["transitions"][:40]]
  out += ["", "## Events per file, by file-name shape", "", "| Name shape | Events per file: files |", "|---|---|"]
  out += [f"| `{k}` | {', '.join(f'{n}: {c}' for n, c in sorted(v.items()))} |"
          for k, v in s["n_events_by_file_name_shape"].items()]
  out += ["", "## Per file", "",
          "| File | Reader | fs | Channels | Duration (s) | Events | Codes | Flat / NaN channels | Error |",
          "|---|---|---|---|---|---|---|---|---|"]
  for f in p["files"]:
    pr = f.get("profile")
    if pr:
      bad = [c["name"] for c in pr["channels"] if c["flat"] or c["n_nan"]]
      out.append(f"| `{f['path']}` | {f['reader']} | {_f(pr['fs'], 2)} | {pr['n_channels']} | "
                 f"{_f(pr['duration_s'])} | {pr['n_events']} | {len(pr['codes'])} | "
                 f"{', '.join(bad) or '—'} | |")
    else:
      out.append(f"| `{f['path']}` | {f['reader'] or 'none'} | | | | | | | {f.get('error', 'not read')} |")
  return "\n".join(out) + "\n"
