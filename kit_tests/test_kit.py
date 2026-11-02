"""Known-answer tests for the kit: project creation, guard decisions, paradigm neutrality."""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT))
import new_project  # noqa: E402


@pytest.fixture()
def made(tmp_path):
  ev = tmp_path / "eval"
  (ev / "cases" / "c1" / "inputs").mkdir(parents=True)
  (ev / "cases" / "c1" / "inputs" / "notes.md").write_text("professor notes")
  (ev / "blocklist.json").write_text(json.dumps({"terms": ["secret-repo-name"]}))
  h, c = tmp_path / "proj_h", tmp_path / "proj_c"
  common = ["--eval-dir", str(ev), "--case", str(ev / "cases" / "c1"), "--allow-dirty"]
  new_project.main([str(h), "--name", "proj-h", *common])
  new_project.main([str(c), "--name", "proj-c", "--control", *common])
  return ev, h, c


def guard(project: Path, tool: str, inp: dict, agent=None) -> int:
  ev = {"tool_name": tool, "tool_input": inp, "cwd": str(project)}
  if agent:
    ev["agent_type"] = agent
  r = subprocess.run([sys.executable, str(project / ".claude" / "hooks" / "guard.py")],
                     input=json.dumps(ev), capture_output=True, text=True,
                     env={"CLAUDE_PROJECT_DIR": str(project), "PATH": "/usr/bin:/bin"})
  return r.returncode


def test_harness_project_layout(made):
  """Known answer: placeholders substituted, inputs copied, eval folder denied, private paths excluded."""
  ev, h, _ = made
  claude = (h / "CLAUDE.md").read_text()
  assert "{{" not in claude and "proj-h" in claude
  assert (h / "inputs" / "notes.md").read_text() == "professor notes"
  assert (h / ".harness" / "tools" / "run_profile.py").exists()
  assert not (h / ".harness" / "tools" / "tests").exists()
  deny = json.loads((h / ".claude" / "settings.json").read_text())["permissions"]["deny"]
  assert f"Read(/{ev.resolve()}/**)" in deny
  cfg = json.loads((h / ".claude" / "harness.json").read_text())
  assert cfg["mode"] == "harness" and cfg["eval_dir"] == str(ev.resolve())
  excl = (h / ".git" / "info" / "exclude").read_text().splitlines()
  assert {"CLAUDE.md", ".claude/", ".harness/", "agent_runs/"} <= set(excl)
  assert len(list((h / ".claude" / "agents").glob("*.md"))) == 6


def test_control_project_has_no_harness(made):
  """Known answer: control arm gets only the guard, the inputs and the eval deny rules."""
  _, _, c = made
  assert not (c / "CLAUDE.md").exists() and not (c / ".claude" / "agents").exists()
  assert not (c / ".harness").exists()
  assert (c / "inputs" / "notes.md").exists()
  s = json.loads((c / ".claude" / "settings.json").read_text())
  assert "PostToolUse" not in s["hooks"] and s["permissions"]["deny"]


@pytest.mark.parametrize("arm", ["h", "c"])
def test_guard_blocks_evaluation_material_in_both_arms(made, arm):
  """Known answer: eval path, answer keys and blocklist terms are blocked (exit 2); ordinary reads pass (0)."""
  ev, h, c = made
  p = h if arm == "h" else c
  assert guard(p, "Read", {"file_path": str(ev / "answer_keys" / "x.md")}) == 2
  assert guard(p, "Bash", {"command": "cat ../eval/answer_keys/x.md"}) == 2
  assert guard(p, "WebFetch", {"url": "https://github.com/someone/secret-repo-name"}) == 2
  assert guard(p, "WebSearch", {"query": "secret-repo-name results"}) == 2
  assert guard(p, "Read", {"file_path": str(p / "inputs" / "notes.md")}) == 0
  assert guard(p, "Bash", {"command": "ls data/raw"}) == 0
  assert guard(p, "Bash", {"command": "rm -rf data/raw/S1"}) == 2
  assert guard(p, "Bash", {"command": "git push origin main"}) == 2


def test_guard_workflow_rules_only_in_harness(made):
  """Known answer: the auditor is read-only and .harness/ is frozen in the harness arm; control has no such rules."""
  _, h, c = made
  assert guard(h, "Write", {"file_path": str(h / "src" / "a.py")}, agent="methods-auditor") == 2
  assert guard(h, "Write", {"file_path": str(h / "agent_runs" / "r" / "05_audit.md")}, agent="methods-auditor") == 0
  assert guard(h, "Edit", {"file_path": str(h / ".harness" / "VERSION")}) == 2
  assert guard(h, "Bash", {"command": "git add CLAUDE.md"}) == 2
  assert guard(c, "Write", {"file_path": str(c / "src" / "a.py")}, agent="methods-auditor") == 0


def test_eval_requires_frozen_kit_without_allow_dirty(tmp_path):
  """Known answer: an evaluation project from an untagged kit is refused."""
  ev = tmp_path / "eval"
  ev.mkdir()
  with pytest.raises(SystemExit):
    new_project.main([str(tmp_path / "p"), "--name", "p", "--eval-dir", str(ev)])


def test_kit_is_paradigm_neutral():
  """Known answer: no paradigm or lab-specific term in the kit outside the paradigm-analyst's list of families."""
  pat = re.compile(r"p300|ssvep|motor imagery|\.ebr|happy smile|ssvep-eeg-xai|sebastian.s ssvep", re.I)
  allowed = {"paradigm-analyst.md", "PARADIGM.md"}
  hits = []
  for f in (KIT / "template").rglob("*"):
    if f.is_file() and f.name not in allowed:
      hits += [f"{f.relative_to(KIT)}: {m.group(0)}" for m in pat.finditer(f.read_text(errors="ignore"))]
  assert hits == []


def test_sibling_runs_blocked_own_folder_allowed(tmp_path):
  """Known answer: run r-h1 may use its own path but not r-h2's."""
  ev = tmp_path / "eval"
  ev.mkdir()
  (ev / "blocklist.json").write_text(json.dumps({"terms": ["r-h1", "r-h2"]}))
  p = tmp_path / "runs" / "r-h1"
  new_project.main([str(p), "--name", "r-h1", "--eval-dir", str(ev), "--allow-dirty"])
  assert guard(p, "Read", {"file_path": str(p / "inputs" / "x.md")}) == 0
  assert guard(p, "Read", {"file_path": str(tmp_path / "runs" / "r-h2" / "docs" / "x.md")}) == 2
