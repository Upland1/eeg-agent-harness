"""Token and time log per agent call (SubagentStop) and per orchestrator session (Stop).

As a hook (stdin = the hook event), appends one JSON line to the run's `cost.jsonl`:
  SubagentStop  {"kind": "agent", "agent_type", "agent_id", ...totals of that agent's transcript}
  Stop          {"kind": "session", "session_id", ...running totals of the main transcript}
The run folder is the `agent_runs/<YYYY-MM-DD>_<slug>/` named in the agent's first prompt,
else the most recently changed run folder; without one, `agent_runs/cost_unassigned.jsonl`
(control arm: `.claude/cost.jsonl`). The hook never blocks and never prints on success.

Totals per transcript: API responses are counted once per message id (a response split
into several transcript rows repeats the same usage); tokens are summed per field;
wall time is last minus first timestamp of the transcript.

An agent that is resumed (sent back for a revision) stops again with its transcript's
cumulative totals, so the summary keeps the last line per agent id (and per session). The hook
runs before an agent's final response is written to its transcript, so these are running
numbers for log.md; the numbers for reporting come from the kit's cost_report.py, run on the
transcripts after the run (the same method for both evaluation arms).

Summary for log.md (G11: the numbers come from this script):
  python .claude/hooks/log_cost.py --summary agent_runs/<run>
Per agent call and orchestrator turn, the increment over the previous line of the same agent id or
session (0.6.0, L45: the lines are running totals, so adding them up counts the same tokens again):
  python .claude/hooks/log_cost.py --rounds agent_runs/<run>
"""

import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

FIELDS = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
RUN = re.compile(r"agent_runs/(\d{4}-\d{2}-\d{2}_[A-Za-z0-9._-]+)")


def _ts(s):
  try:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
  except (AttributeError, ValueError):
    return None


def summarize_transcript(path) -> dict:
  usage = {f: 0 for f in FIELDS}
  seen, models, stamps, first_prompt = set(), set(), [], None
  with open(path, errors="ignore") as fh:
    for line in fh:
      try:
        row = json.loads(line)
      except ValueError:
        continue
      t = _ts(row.get("timestamp"))
      if t is not None:
        stamps.append(t)
      msg = row.get("message") or {}
      if row.get("type") == "user" and first_prompt is None:
        c = msg.get("content")
        first_prompt = c if isinstance(c, str) else " ".join(
          b.get("text", "") for b in (c or []) if isinstance(b, dict) and b.get("type") == "text")
      if row.get("type") != "assistant" or not isinstance(msg.get("usage"), dict):
        continue
      key = msg.get("id") or row.get("requestId") or row.get("uuid")
      if key in seen:
        continue
      seen.add(key)
      if msg.get("model"):
        models.add(msg["model"])
      for f in FIELDS:
        usage[f] += int(msg["usage"].get(f) or 0)
  return {**usage, "total_tokens": sum(usage.values()), "api_responses": len(seen),
          "models": sorted(models),
          "wall_s": round(max(stamps) - min(stamps), 1) if len(stamps) > 1 else 0.0,
          "first_prompt": first_prompt or ""}


def run_folder(root: Path, prompt: str):
  runs = root / "agent_runs"
  m = RUN.search(prompt or "")
  if m and (runs / m.group(1)).is_dir():
    return runs / m.group(1)
  cands = [d for d in runs.glob("*_*") if d.is_dir() and re.match(r"\d{4}-\d{2}-\d{2}_", d.name)]
  if not cands:
    return None
  return max(cands, key=lambda d: max([f.stat().st_mtime for f in d.iterdir()] + [d.stat().st_mtime]))


def record(event: dict, root: Path) -> tuple:
  name = event.get("hook_event_name")
  if name == "SubagentStop":
    s = summarize_transcript(event["agent_transcript_path"])
    rec = {"kind": "agent", "agent_type": event.get("agent_type"), "agent_id": event.get("agent_id")}
  elif name == "Stop":
    s = summarize_transcript(event["transcript_path"])
    rec = {"kind": "session", "agent_type": "orchestrator"}
  else:
    return None, None
  prompt = s.pop("first_prompt")
  rec.update({"session_id": event.get("session_id"), "logged_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **s})
  try:
    mode = json.loads((root / ".claude" / "harness.json").read_text()).get("mode")
  except (OSError, ValueError):
    mode = None
  if mode == "control":
    return rec, root / ".claude" / "cost.jsonl"
  run = run_folder(root, prompt if name == "SubagentStop" else "")
  if run is not None:
    rec["run"] = run.name
  return rec, (run / "cost.jsonl") if run else (root / "agent_runs" / "cost_unassigned.jsonl")


def summary(run: Path) -> str:
  rows = [json.loads(l) for l in (run / "cost.jsonl").read_text().splitlines() if l.strip()]
  last = {}
  for i, r in enumerate(rows):
    if r["kind"] == "agent":
      key = r.get("agent_id") or f"row{i}"
      last[key] = {**r, "stops": last.get(key, {}).get("stops", 0) + 1}
  agents = list(last.values())
  sessions = {}
  for r in rows:
    if r["kind"] == "session":
      sessions[r["session_id"]] = r  # running totals: the last line per session is the total
  out = ["| # | Agent | Rounds | Tokens (in / out / cache write / cache read) | Total | Wall time (s) |",
         "|---|---|---|---|---|---|"]
  for i, r in enumerate(agents, 1):
    out.append(f"| {i} | {r['agent_type']} | {r['stops']} | {r['input_tokens']} / {r['output_tokens']} / "
               f"{r['cache_creation_input_tokens']} / {r['cache_read_input_tokens']} | {r['total_tokens']} | {r['wall_s']} |")
  for sid, r in sessions.items():
    out.append(f"| — | orchestrator ({(sid or '')[:8]}) | — | {r['input_tokens']} / {r['output_tokens']} / "
               f"{r['cache_creation_input_tokens']} / {r['cache_read_input_tokens']} | {r['total_tokens']} | {r['wall_s']} |")
  tot = sum(r["total_tokens"] for r in agents) + sum(r["total_tokens"] for r in sessions.values())
  out += ["", f"Agents: {len(agents)} ({sum(r['stops'] for r in agents)} rounds). Orchestrator sessions: "
          f"{len(sessions)}. Total tokens: {tot}. Agent wall time: {round(sum(r['wall_s'] for r in agents), 1)} s. "
          "Running numbers; report the kit's cost_report.py totals."]
  return "\n".join(out)


def rounds(run: Path) -> tuple:
  """(rows, total): each line's increment over the previous line of the same agent id or session.
  The increments add up to the summary's total; the lines themselves do not (they are running totals)."""
  prev, out = {}, []
  for i, l in enumerate((run / "cost.jsonl").read_text().splitlines()):
    if not l.strip():
      continue
    r = json.loads(l)
    key = (r["kind"], r.get("agent_id") or r.get("session_id") or f"row{i}")
    p = prev.get(key, {"total_tokens": 0, "wall_s": 0.0})
    out.append({"kind": r["kind"], "agent_type": r.get("agent_type"), "logged_at": r.get("logged_at"),
                "tokens": r["total_tokens"] - p["total_tokens"], "wall_s": round(r["wall_s"] - p["wall_s"], 1)})
    prev[key] = r
  return out, sum(r["tokens"] for r in out)


def rounds_table(run: Path) -> str:
  rows, total = rounds(run)
  out = ["| # | Logged at | Agent | Tokens (this round) | Wall time (s, this round) |", "|---|---|---|---|---|"]
  out += [f"| {i} | {r['logged_at']} | {r['agent_type']} | {r['tokens']} | {r['wall_s']} |" for i, r in enumerate(rows, 1)]
  return "\n".join(out + ["", f"Total tokens: {total} (the increments; never the sum of the lines)."])


def main(argv) -> int:
  if len(argv) == 2 and argv[0] == "--summary":
    print(summary(Path(argv[1])))
    return 0
  if len(argv) == 2 and argv[0] == "--rounds":
    print(rounds_table(Path(argv[1])))
    return 0
  try:
    event = json.load(sys.stdin)
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR", event.get("cwd", ".")))
    rec, dest = record(event, root)
    if rec is not None:
      dest.parent.mkdir(parents=True, exist_ok=True)
      with open(dest, "a") as fh:
        fh.write(json.dumps(rec) + "\n")
  except Exception as exc:  # logging must never stop the session
    print(f"log_cost.py: not logged ({type(exc).__name__}: {exc})", file=sys.stderr)
  return 0


if __name__ == "__main__":
  sys.exit(main(sys.argv[1:]))
