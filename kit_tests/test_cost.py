"""Known-answer tests for the cost hook: tokens counted once per API response, wall time from
timestamps, records routed to the run named in the agent's prompt."""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

KIT = Path(__file__).resolve().parents[1]
HOOK = KIT / "template" / ".claude" / "hooks" / "log_cost.py"


def row(kind, t, msg_id=None, usage=None, text=None):
  r = {"type": kind, "timestamp": f"2026-11-06T10:00:{t:02d}.000Z", "uuid": f"u{t}"}
  if kind == "assistant":
    r["message"] = {"id": msg_id, "model": "m-1", "usage": usage, "content": [{"type": "text", "text": "x"}]}
  else:
    r["message"] = {"role": "user", "content": text}
  return r


U1 = {"input_tokens": 10, "output_tokens": 100, "cache_creation_input_tokens": 1000, "cache_read_input_tokens": 5000}
U2 = {"input_tokens": 2, "output_tokens": 20, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 6000}


def transcript(path: Path, prompt: str):
  rows = [row("user", 0, text=prompt),
          row("assistant", 3, "msg_A", U1), row("assistant", 4, "msg_A", U1),  # one response, two rows
          {"type": "attachment", "timestamp": "2026-11-06T10:00:20.000Z"},
          row("assistant", 42, "msg_B", U2)]
  path.write_text("\n".join(json.dumps(r) for r in rows) + "\nnot json\n")
  return path


def hook(project: Path, event: dict):
  return subprocess.run([sys.executable, str(HOOK)], input=json.dumps(event), capture_output=True, text=True,
                        env={"CLAUDE_PROJECT_DIR": str(project), "PATH": "/usr/bin:/bin"})


@pytest.fixture()
def project(tmp_path):
  p = tmp_path / "proj"
  for run in ("2026-11-05_old", "2026-11-06_first-result"):
    (p / "agent_runs" / run).mkdir(parents=True)
  return p


def test_agent_record_dedupes_and_routes_to_named_run(project, tmp_path):
  """Known answer: msg_A counted once -> input 12, output 120, cache write 1000, cache read 11000,
  total 12132, 2 responses, wall 42 s; written to the run named in the prompt (the older one)."""
  t = transcript(tmp_path / "agent.jsonl", "Audit agent_runs/2026-11-05_old/ please")
  r = hook(project, {"hook_event_name": "SubagentStop", "agent_type": "methods-auditor", "agent_id": "a1",
                     "agent_transcript_path": str(t), "session_id": "s1"})
  assert r.returncode == 0 and r.stdout == "" and r.stderr == ""
  rec = json.loads((project / "agent_runs" / "2026-11-05_old" / "cost.jsonl").read_text())
  assert (rec["input_tokens"], rec["output_tokens"], rec["cache_creation_input_tokens"],
          rec["cache_read_input_tokens"], rec["total_tokens"]) == (12, 120, 1000, 11000, 12132)
  assert rec["api_responses"] == 2 and rec["wall_s"] == 42.0 and rec["agent_type"] == "methods-auditor"
  assert rec["run"] == "2026-11-05_old" and rec["models"] == ["m-1"]


def test_session_record_goes_to_latest_run_and_summary(project, tmp_path):
  """Known answer: Stop logs running totals to the most recently changed run; the summary keeps the last line per session."""
  (project / "agent_runs" / "2026-11-06_first-result" / "log.md").write_text("x")
  t = transcript(tmp_path / "main.jsonl", "hello")
  hook(project, {"hook_event_name": "Stop", "transcript_path": str(t), "session_id": "sess-1"})
  hook(project, {"hook_event_name": "Stop", "transcript_path": str(t), "session_id": "sess-1"})
  a = transcript(tmp_path / "a.jsonl", "run agent_runs/2026-11-06_first-result")
  for _ in range(2):  # the same agent stops twice (resumed for a revision): cumulative totals, counted once
    hook(project, {"hook_event_name": "SubagentStop", "agent_type": "pipeline-engineer", "agent_id": "e1",
                   "agent_transcript_path": str(a)})
  run = project / "agent_runs" / "2026-11-06_first-result"
  assert len((run / "cost.jsonl").read_text().splitlines()) == 4
  out = subprocess.run([sys.executable, str(HOOK), "--summary", str(run)], capture_output=True, text=True).stdout
  assert "| 1 | pipeline-engineer | 2 | 12 / 120 / 1000 / 11000 | 12132 | 42.0 |" in out
  assert "Agents: 1 (2 rounds). Orchestrator sessions: 1. Total tokens: 24264." in out


def test_never_blocks_and_control_arm(project, tmp_path):
  """Known answer: a missing transcript exits 0 with a note; if the hook ever ran in a control project it would
  write to .claude/cost.jsonl (new_project no longer installs it there: cost_report.py is used instead)."""
  r = hook(project, {"hook_event_name": "SubagentStop", "agent_transcript_path": str(tmp_path / "nope.jsonl")})
  assert r.returncode == 0 and "not logged" in r.stderr
  (project / ".claude").mkdir()
  (project / ".claude" / "harness.json").write_text(json.dumps({"mode": "control"}))
  hook(project, {"hook_event_name": "Stop", "transcript_path": str(transcript(tmp_path / "m.jsonl", "x"))})
  assert json.loads((project / ".claude" / "cost.jsonl").read_text())["total_tokens"] == 12132


def test_cost_report_from_transcripts_after_the_run(tmp_path):
  """Known answer: a session (12132 tokens) with two subagents (12132 each, types from meta files) gives
  36396 tokens, 1 session, 2 agent calls; the folder is found from the project path."""
  sys.path.insert(0, str(KIT))
  import cost_report
  proj = tmp_path / "my_proj.v2"
  assert cost_report.transcripts_dir(proj).name == re.sub(r"[^A-Za-z0-9]", "-", str(proj.resolve()))
  folder = tmp_path / "tr"
  (folder / "sess1" / "subagents").mkdir(parents=True)
  transcript(folder / "sess1.jsonl", "/onboard")
  for i, kind in enumerate(("paradigm-analyst", "methods-auditor")):
    transcript(folder / "sess1" / "subagents" / f"agent-{i}.jsonl", "x")
    (folder / "sess1" / "subagents" / f"agent-{i}.meta.json").write_text(json.dumps({"agentType": kind}))
  rep = cost_report.report(folder)
  t = rep["totals"]
  assert (t["total_tokens"], t["sessions"], t["agent_calls"], t["api_responses"]) == (36396, 1, 2, 6)
  assert [r["agent_type"] for r in rep["rows"]] == ["main", "paradigm-analyst", "methods-auditor"]
  out = subprocess.run([sys.executable, str(KIT / "cost_report.py"), str(proj), "--transcripts", str(folder)],
                       capture_output=True, text=True).stdout
  assert "Totals: 36396 tokens" in out
