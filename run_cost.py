"""Cost of a finished run: agent cost in USD, tokens, and CPU and GPU time per phase (evaluator-side).

  python run_cost.py --project <project dir> [--streams '<eval>/apply_*.stream.jsonl'] \
      --run-log confirmatory=<path> [--run-log <label>=<path> ...] [--suspends <journal excerpt>] \
      --out <eval>/run_cost

Run by the evaluator after the run, outside the agents (like ``cost_report.py``). Writes a new versioned
folder (``eegharness.outputs``: provenance with the kit commit, the SHA-256 of every input, compute time)
with ``run_cost.json`` and ``run_cost.md``. Nothing in the project changes.

Agent cost. Each headless invocation (``claude -p --output-format stream-json``) ends with a ``result``
line whose ``total_cost_usd`` is cumulative over the session (it never decreases across ``--resume``);
the session's cost is its last value, and each invocation adds the difference to the previous one. An
invocation without a result line (stopped) is listed with no figure: its cost is inside the next value.
Without ``--streams`` (a run driven in interactive sessions) no USD figure is given: the transcripts do not
record one, and none is estimated. Tokens come from the project's transcripts through ``cost_report.report``
(one count per API response), in total and per agent type: calls (one per subagent transcript, one per main
session), API responses, tokens and wall time (an agent's wall time overlaps its session's).

Compute time. A run log is the text the job wrappers write, one ``END <job> rc <rc> seconds <s>`` line per
job, each line starting with an ISO time (``2026-11-12T21:09:40Z``) or a time of day (``21:42:40``,
UTC, the date taken from the log's file name ``..._YYYYMMDDTHHMMSSZ...`` and advanced when the time goes
back). A run log may instead be a job table: tab-separated, a header line starting ``job<TAB>start_utc``,
then one row per job with ``job``, ``start_utc``, ``end_utc`` (``YYYYMMDDTHHMMSSZ``), ``wall_s`` and
``exit`` columns (the step H driver of the cold-pressor run). A job ran from end - seconds to end. Device, by job name (``device_of``): a name with ``__gpu``,
``f2__``, ``eegnet``, ``shallowconvnet``, ``shallow_convnet`` or ``gnn`` is a network job, on CUDA; anything else
(classical, statistics) is CPU. Wall time includes the time the machine was suspended; ``--suspends``
reads the kernel's ``PM: suspend entry`` / ``PM: suspend exit`` lines (``journalctl -o short-iso``) and
subtracts their overlap with each job, giving active time. CPU time here is the wall time of CPU jobs,
not CPU seconds summed over cores. Failed jobs (rc != 0) are counted: they used the machine.
"""

import argparse
import glob
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

KIT = Path(__file__).resolve().parent
sys.path.insert(0, str(KIT / "tools"))
sys.path.insert(0, str(KIT))
from eegharness import outputs as eo  # noqa: E402

END = re.compile(r"^(?P<ts>\S+) END (?P<job>.+?) rc (?P<rc>\d+) seconds (?P<s>\d+)\b")
STAMP = re.compile(r"(\d{8}T\d{6}Z)")
SUSPEND = re.compile(r"^(?P<ts>\S+) .*PM: suspend (?P<what>entry|exit)")
NETWORK = re.compile(r"__gpu|f2__|eegnet|shallowconvnet|shallow_convnet|gnn", re.IGNORECASE)
TABLE_HEADER = "job\tstart_utc"


def device_of(job):
  return "cuda" if NETWORK.search(job) else "cpu"


def parse_job_table(path):
  """The same records from a tab-separated job table (header ``job<TAB>start_utc...``)."""
  lines = Path(path).read_text().splitlines()
  head = lines[0].split("\t")
  missing = {"job", "end_utc", "wall_s", "exit"} - set(head)
  if missing:
    raise ValueError(f"{path}: job table without column(s) {sorted(missing)}")
  jobs = []
  for line in lines[1:]:
    if not line.strip():
      continue
    r = dict(zip(head, line.split("\t")))
    end = datetime.strptime(r["end_utc"], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    s = int(r["wall_s"])
    jobs.append({"job": r["job"], "rc": int(r["exit"]), "seconds": s, "start": end - timedelta(seconds=s), "end": end,
                 "device": device_of(r["job"])})
  return jobs


def parse_run_log(path):
  """[{job, rc, seconds, start, end (aware UTC datetimes), device}] from END lines (or a job table)."""
  text = Path(path).read_text().splitlines()
  if text and text[0].startswith(TABLE_HEADER):
    return parse_job_table(path)
  m = STAMP.search(Path(path).name)
  day = datetime.strptime(m.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc) if m else None
  last, jobs = None, []
  for line in text:
    e = END.match(line)
    if not e:
      continue
    ts = e["ts"]
    if "T" in ts:
      end = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)
    else:
      if day is None:
        raise ValueError(f"{path}: time-of-day lines need a UTC stamp YYYYMMDDTHHMMSSZ in the file name")
      t = datetime.strptime(ts, "%H:%M:%S").time()
      end = datetime.combine(day.date(), t, tzinfo=timezone.utc)
      if last is not None and end < last:
        day += timedelta(days=1)
        end += timedelta(days=1)
      last = end
    s = int(e["s"])
    jobs.append({"job": e["job"], "rc": int(e["rc"]), "seconds": s, "start": end - timedelta(seconds=s), "end": end,
                 "device": device_of(e["job"])})
  return jobs


def parse_suspends(path):
  """[(entry, exit)] in UTC; an entry without an exit is refused."""
  out, entry = [], None
  for line in Path(path).read_text().splitlines():
    m = SUSPEND.match(line)
    if not m:
      continue
    t = datetime.fromisoformat(m["ts"]).astimezone(timezone.utc)
    if m["what"] == "entry":
      entry = t
    elif entry is not None:
      out.append((entry, t))
      entry = None
  if entry is not None:
    raise ValueError(f"{path}: a suspend entry at {entry.isoformat()} has no exit")
  return out


def overlap_s(a0, a1, intervals):
  return sum(max(0.0, (min(a1, b1) - max(a0, b0)).total_seconds()) for b0, b1 in intervals)


def agent_cost(stream_files):
  """Per session: invocations (file, cumulative USD or None, increment) and the session total."""
  sessions = {}
  for f in sorted(stream_files, key=lambda p: Path(p).stat().st_mtime):
    sid, usd, ok = None, None, False
    for line in Path(f).read_text().splitlines():
      try:
        d = json.loads(line)
      except ValueError:
        continue
      sid = d.get("session_id") or sid
      if d.get("type") == "result":
        usd, ok = d.get("total_cost_usd"), d.get("subtype") == "success"
    s = sessions.setdefault(sid, {"invocations": [], "usd": None})
    prev = s["usd"]
    if usd is not None and prev is not None and usd + 1e-9 < prev:
      raise ValueError(f"{f}: total_cost_usd {usd} is below the session's previous {prev}; not cumulative")
    s["invocations"].append({"stream": Path(f).name, "cumulative_usd": usd, "result": ok,
                             "added_usd": None if usd is None else usd - (prev or 0.0)})
    if usd is not None:
      s["usd"] = usd
  return {"sessions": sessions, "total_usd": sum(s["usd"] or 0.0 for s in sessions.values())}


def compute(run_logs, suspends):
  phases, totals = [], {}
  for label, path in run_logs:
    jobs = parse_run_log(path)
    by = {}
    for j in jobs:
      sus = overlap_s(j["start"], j["end"], suspends)
      d = by.setdefault(j["device"], {"jobs": 0, "failed": 0, "wall_s": 0, "suspended_s": 0.0})
      d["jobs"] += 1
      d["failed"] += j["rc"] != 0
      d["wall_s"] += j["seconds"]
      d["suspended_s"] += sus
    for dev, d in by.items():
      d["active_s"] = d["wall_s"] - d["suspended_s"]
      t = totals.setdefault(dev, {"jobs": 0, "wall_s": 0, "suspended_s": 0.0, "active_s": 0.0})
      for k in t:
        t[k] += d[k]
    phases.append({"label": label, "log": str(path), "first_start": min(j["start"] for j in jobs).isoformat() if jobs else None,
                   "last_end": max(j["end"] for j in jobs).isoformat() if jobs else None, "by_device": by})
  return {"phases": phases, "totals": totals}


def by_agent(rows):
  """cost_report rows summed per agent type (main sessions as ``main``)."""
  out = {}
  for r in rows:
    d = out.setdefault(r["agent_type"], {"calls": 0, "api_responses": 0, "total_tokens": 0, "output_tokens": 0,
                                         "wall_s": 0.0})
    d["calls"] += 1
    for k in ("api_responses", "total_tokens", "output_tokens", "wall_s"):
      d[k] += r[k]
  return dict(sorted(out.items(), key=lambda kv: -kv[1]["total_tokens"]))


def hours(s):
  return f"{s / 3600:.2f} h"


def markdown(rep):
  a, c = rep["agent"], rep["compute"]
  lines = [f"# Run cost: {rep['project']}", "", "## Agent cost", ""]
  if a is None:
    lines.append("USD: not available (no headless stream files: the run was driven in interactive sessions, whose "
                 "transcripts record no cost; none is estimated).")
  else:
    lines += ["| Session | Invocations | With result | USD |", "|---|---|---|---|"]
    for sid, s in a["sessions"].items():
      n_ok = sum(i["result"] for i in s["invocations"])
      lines.append(f"| {sid} | {len(s['invocations'])} | {n_ok} | {s['usd']:.2f} |")
    lines += ["", f"Total: {a['total_usd']:.2f} USD."]
  t = rep["tokens"]
  lines += ["", f"Tokens {t['total_tokens']:,} in {t['api_responses']:,} API responses (main sessions and subagents, "
            "from the transcripts).", "", "| Agent | Calls | API responses | Tokens | Output tokens | Wall |",
            "|---|---|---|---|---|---|"]
  for name, d in rep["tokens_by_agent"].items():
    lines.append(f"| {name} | {d['calls']} | {d['api_responses']:,} | {d['total_tokens']:,} | {d['output_tokens']:,} | "
                 f"{hours(d['wall_s'])} |")
  lines += ["", "Calls: one per subagent transcript; main = sessions. Agent wall time overlaps the session's.", "",
            "## Compute time", "",
            "| Phase | Device | Jobs (failed) | Wall | Suspended | Active |", "|---|---|---|---|---|---|"]
  for p in c["phases"]:
    for dev, d in sorted(p["by_device"].items()):
      lines.append(f"| {p['label']} | {dev} | {d['jobs']} ({d['failed']}) | {hours(d['wall_s'])} | "
                   f"{hours(d['suspended_s'])} | {hours(d['active_s'])} |")
  for dev, d in sorted(c["totals"].items()):
    lines.append(f"| **total** | {dev} | {d['jobs']} | {hours(d['wall_s'])} | {hours(d['suspended_s'])} | "
                 f"{hours(d['active_s'])} |")
  lines += ["", "CPU time = wall time of CPU jobs (not core-seconds). Device by job name (run_cost.device_of). "
            f"Suspend intervals subtracted: {len(rep['suspend_intervals'])}."]
  return "\n".join(lines) + "\n"


def main(argv=None):
  ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  ap.add_argument("--project", required=True)
  ap.add_argument("--streams", help="glob of the headless invocations' stream-json files (none: no USD figure)")
  ap.add_argument("--run-log", action="append", default=[], metavar="LABEL=PATH")
  ap.add_argument("--suspends", help="journalctl -o short-iso excerpt with 'PM: suspend entry/exit' lines")
  ap.add_argument("--transcripts", help="transcript folder (default: derived from the project path)")
  ap.add_argument("--out", required=True)
  a = ap.parse_args(argv)
  import cost_report
  timer = eo.ComputeTimer(device="cpu")
  streams = sorted(glob.glob(a.streams)) if a.streams else []
  if a.streams and not streams:
    raise SystemExit(f"no stream files match {a.streams}")
  logs = [tuple(x.split("=", 1)) for x in a.run_log]
  if any(len(x) != 2 for x in logs):
    raise SystemExit("--run-log takes LABEL=PATH")
  suspends = parse_suspends(a.suspends) if a.suspends else []
  project = Path(a.project).resolve()
  tdir = Path(a.transcripts) if a.transcripts else cost_report.transcripts_dir(project)
  cr = cost_report.report(tdir)
  rep = {"project": str(project), "agent": agent_cost(streams) if streams else None, "tokens": cr["totals"],
         "tokens_by_agent": by_agent(cr["rows"]), "transcripts": str(tdir),
         "compute": compute(logs, suspends),
         "suspend_intervals": [[s.isoformat(), e.isoformat()] for s, e in suspends],
         "device_rule": "cuda if the job name matches " + NETWORK.pattern + ", else cpu"}
  inputs = [*streams, *(p for _, p in logs), *([a.suspends] if a.suspends else [])]
  out = eo.new_output_dir(a.out, inputs=inputs, params=vars(a), root=KIT, argv=["run_cost.py", *(argv or sys.argv[1:])])
  (out / "run_cost.json").write_text(json.dumps(rep, indent=1, default=str))
  (out / "run_cost.md").write_text(markdown(rep))
  eo.record_compute_time(out, timer)
  print(markdown(rep))
  print(out)
  return 0


if __name__ == "__main__":
  sys.exit(main())
