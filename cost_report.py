"""Tokens and time of a finished project, from its Claude Code transcripts (both arms).

  python cost_report.py <project dir> [--transcripts <dir>] [--json out.json]

Run by the evaluator after a run, outside the agents: nothing in the project changes, so a
control arm's instructions and behaviour are untouched. Transcripts are read from
``~/.claude/projects/<project path with every non-alphanumeric character as '-'>/``:
main sessions ``<session>.jsonl`` and their subagents
``<session>/subagents/agent-<id>.jsonl`` (agent type from ``agent-<id>.meta.json``).

Counting is the same function the harness arm's ``log_cost.py`` hook uses
(``template/.claude/hooks/log_cost.py: summarize_transcript``): one count per API response
(message id), tokens summed per field, wall time = last minus first timestamp.
Prints a Markdown table (one row per session and per agent) and the totals.
"""

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("log_cost", KIT / "template" / ".claude" / "hooks" / "log_cost.py")
log_cost = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(log_cost)
FIELDS = log_cost.FIELDS


def transcripts_dir(project: Path) -> Path:
  return Path.home() / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(project.resolve()))


def report(folder: Path) -> dict:
  rows = []
  for main in sorted(folder.glob("*.jsonl")):
    s = log_cost.summarize_transcript(main)
    s.pop("first_prompt")
    rows.append({"kind": "session", "session_id": main.stem, "agent_type": "main", **s})
    for sub in sorted((folder / main.stem / "subagents").glob("agent-*.jsonl")):
      meta = sub.with_suffix(".meta.json")
      try:
        agent_type = json.loads(meta.read_text()).get("agentType", "unknown")
      except (OSError, ValueError):
        agent_type = "unknown"
      a = log_cost.summarize_transcript(sub)
      a.pop("first_prompt")
      rows.append({"kind": "agent", "session_id": main.stem, "agent_id": sub.stem, "agent_type": agent_type, **a})
  totals = {f: sum(r[f] for r in rows) for f in (*FIELDS, "total_tokens", "api_responses")}
  totals["sessions"] = sum(r["kind"] == "session" for r in rows)
  totals["agent_calls"] = sum(r["kind"] == "agent" for r in rows)
  totals["session_wall_s"] = round(sum(r["wall_s"] for r in rows if r["kind"] == "session"), 1)
  totals["agent_wall_s"] = round(sum(r["wall_s"] for r in rows if r["kind"] == "agent"), 1)
  return {"transcripts": str(folder), "rows": rows, "totals": totals}


def markdown(rep: dict) -> str:
  out = [f"Transcripts: `{rep['transcripts']}`", "",
         "| Session | Agent | In | Out | Cache write | Cache read | Total | Responses | Wall (s) |",
         "|---|---|---|---|---|---|---|---|---|"]
  for r in rep["rows"]:
    out.append(f"| {r['session_id'][:8]} | {r['agent_type']} | {r['input_tokens']} | {r['output_tokens']} | "
               f"{r['cache_creation_input_tokens']} | {r['cache_read_input_tokens']} | {r['total_tokens']} | "
               f"{r['api_responses']} | {r['wall_s']} |")
  t = rep["totals"]
  out += ["", f"Totals: {t['total_tokens']} tokens (in {t['input_tokens']}, out {t['output_tokens']}, cache write "
          f"{t['cache_creation_input_tokens']}, cache read {t['cache_read_input_tokens']}); {t['api_responses']} API "
          f"responses; {t['sessions']} sessions ({t['session_wall_s']} s wall); {t['agent_calls']} agent calls "
          f"({t['agent_wall_s']} s wall, overlapping the sessions)."]
  return "\n".join(out)


def main(argv=None) -> int:
  ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  ap.add_argument("project")
  ap.add_argument("--transcripts", help="transcript folder (default: derived from the project path)")
  ap.add_argument("--json", help="also write the full report as JSON (refuses to overwrite)")
  a = ap.parse_args(argv)
  folder = Path(a.transcripts) if a.transcripts else transcripts_dir(Path(a.project))
  if not folder.is_dir():
    print(f"no transcripts at {folder}", file=sys.stderr)
    return 2
  rep = report(folder)
  print(markdown(rep))
  if a.json:
    with open(a.json, "x") as f:
      json.dump(rep, f, indent=1)
  return 0


if __name__ == "__main__":
  sys.exit(main())
