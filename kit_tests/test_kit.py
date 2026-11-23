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


def _kit_copy(tmp_path, tag):
  """A committed copy of the kit, tagged or not (the real kit's state must not decide the test)."""
  import shutil
  k = tmp_path / "kit"
  shutil.copytree(KIT, k, ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache"))
  g = ["git", "-C", str(k), "-c", "user.name=t", "-c", "user.email=t@t"]
  for c in (["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-q", "-m", "kit"]) + ((["tag", "v0"],) if tag else ()):
    subprocess.run(g + c, check=True, capture_output=True)
  return k


@pytest.mark.parametrize("tag", [False, True])
def test_eval_requires_frozen_kit_without_allow_dirty(tmp_path, tag):
  """Known answer: an evaluation project from an untagged kit is refused; from a clean tagged kit it is made."""
  k = _kit_copy(tmp_path, tag)
  ev = tmp_path / "eval"
  ev.mkdir()
  r = subprocess.run([sys.executable, str(k / "new_project.py"), str(tmp_path / "p"), "--name", "p", "--eval-dir", str(ev)],
                     capture_output=True, text=True)
  assert (r.returncode == 0) == tag, r.stderr


def test_vendored_package_conftest_and_first_commit(made):
  """Known answer: eegharness/ is an exact copy of tools/eegharness, committed with the skeleton on main;
  the tree is clean; tests/conftest.py never puts .harness on the path; cost hooks registered."""
  _, h, c = made
  src = KIT / "tools" / "eegharness"
  for f in src.glob("*.py"):
    assert (h / "eegharness" / f.name).read_bytes() == f.read_bytes()
  psrc = KIT / "tools" / "eegpipe"
  for f in psrc.rglob("*"):
    if f.is_file() and "__pycache__" not in f.parts:
      assert (h / "eegpipe" / f.relative_to(psrc)).read_bytes() == f.read_bytes(), f
  tracked = subprocess.run(["git", "-C", str(h), "ls-files"], capture_output=True, text=True).stdout.split()
  assert {"eegharness/outputs.py", "eegharness/splits.py", "eegharness/permutation.py", "eegharness/chance.py",
          "eegharness/seeds.py", "eegharness/folds.py", "tests/conftest.py", ".gitignore", "docs/DECISIONS.md",
          "docs/COMPUTE.md", "eegpipe/__init__.py", "eegpipe/runner/stage.py", "eegpipe/profiles/erp.json",
          "eegpipe/ssvep/fbcca.py"} <= set(tracked)
  assert subprocess.run(["git", "-C", str(h), "status", "--porcelain"], capture_output=True, text=True).stdout == ""
  assert ".harness" not in (h / "tests" / "conftest.py").read_text().split('"""')[2]
  hooks = json.loads((h / ".claude" / "settings.json").read_text())["hooks"]
  assert "SubagentStop" in hooks and "Stop" in hooks and (h / ".claude" / "hooks" / "log_cost.py").exists()
  hooks_c = json.loads((c / ".claude" / "settings.json").read_text())["hooks"]
  assert set(hooks_c) == {"PreToolUse"} and not (c / ".claude" / "hooks" / "log_cost.py").exists()  # cost: after the run
  assert not (c / "eegharness").exists() and not (c / "eegpipe").exists()


def test_templates_carry_v03_rules_and_files():
  """Known answer: CLAUDE.md defines G1-G27 (G26 from 0.5.0, L34; G27 from 0.6.0, L40); run templates include the plan audit and the human-contact log."""
  claude = (KIT / "template" / "CLAUDE.md").read_text()
  assert all(f"**G{n}." in claude for n in range(1, 28)) and "**G28." not in claude
  tpl = KIT / "template" / "agent_runs" / "_templates"
  assert (tpl / "02b_plan_audit.md").exists()
  head = (tpl / "human_contacts.md").read_text()
  for col in ("Sources checked", "Proposed category", "Confirmed category", "should-have-found", "human-only fact"):
    assert col in head
  auditor = (KIT / "template" / ".claude" / "agents" / "methods-auditor.md").read_text()
  assert "Bash" in auditor.split("---")[1] and "G1–G27" in auditor and "## Results check" in auditor


def test_v03_checklists_rows_and_compute_limits():
  """Known answer: the three method checklists exist and are named in CLAUDE.md and the agents that
  apply them; plan/audit templates carry G17-G23 rows; COMPUTE.md has the three limits; no agent
  or template still points at the v0.2 'What Sebastian will run' section."""
  t = KIT / "template"
  claude = (t / "CLAUDE.md").read_text()
  for name in ("deep-learning", "connectivity", "compute-jobs"):
    skill = (t / ".claude" / "skills" / name / "SKILL.md").read_text()
    assert skill.startswith("---\nname: " + name + "\n")
    assert f".claude/skills/{name}/SKILL.md" in claude
  for agent in ("pipeline-engineer", "synthetic-tester", "methods-auditor"):
    assert "deep-learning/SKILL.md" in (t / ".claude" / "agents" / f"{agent}.md").read_text()
  results = (t / ".claude" / "agents" / "results-analyst.md").read_text()
  assert "G23" in results and "outside" in results and "L27" in results
  tpl = t / "agent_runs" / "_templates"
  plan_audit, audit = (tpl / "02b_plan_audit.md").read_text(), (tpl / "05_audit.md").read_text()
  for n in (17, 18, 19, 20, 21, 22):
    assert f"| G{n} " in plan_audit and f"| G{n} " in audit
  assert "| G23 " in audit and "## Results check" in audit
  plan = (tpl / "02_plan.md").read_text()
  assert "## Runs (G22)" in plan and "## Significance budget (G19)" in plan and "Development data" in plan
  compute = (t / "docs" / "COMPUTE.md").read_text()
  for key in ("cpu_max_minutes:", "gpu_max_minutes:", "gpu_device:"):
    assert key in compute
  stale = [str(f.relative_to(KIT)) for f in t.rglob("*.md") if "What Sebastian will run" in f.read_text()]
  assert stale == []


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


def test_v04_apply_pipeline_skill_templates_and_rules():
  """Known answer: the /apply-pipeline skill and its four templates exist; G24 and G25 are in CLAUDE.md
  and in the plan-audit and audit templates; PARADIGM.md asks for the pipeline settings; the skill
  names every runner step and both stop points."""
  t = KIT / "template"
  skill = (t / ".claude" / "skills" / "apply-pipeline" / "SKILL.md").read_text()
  assert skill.startswith("---\nname: apply-pipeline\n")
  for step in ("eegpipe.runner.select", "eegpipe.runner.stage", "eegpipe.runner.collect", "eegpipe.settings.validate",
               "STOP: Sebastian approves the plan", "STOP: Sebastian approves the freeze", "--interim"):
    assert step in skill, step
  tpl = t / "agent_runs" / "_templates"
  for f in ("00_assignment.md", "02_plan_pipeline.md", "02b_audit_rows.md", "06_results_pipeline.md"):
    assert (tpl / "apply_pipeline" / f).exists()
  for n in (24, 25):
    assert f"| G{n} " in (tpl / "02b_plan_audit.md").read_text() and f"| G{n} " in (tpl / "05_audit.md").read_text()
  assert "Pipeline settings this study needs" in (tpl / "onboarding" / "PARADIGM.md").read_text()
  assert "/apply-pipeline" in (t / "CLAUDE.md").read_text()


def test_guard_protects_vendored_eegpipe(made):
  """Known answer (G24): writing into eegpipe/ by Edit/Write, sed -i, cp, a redirect or from inside
  the folder is blocked (exit 2) with the G24 message; reading it, importing it and running its
  modules pass (exit 0)."""
  _, h, _ = made
  for tool, inp in (("Write", {"file_path": str(h / "eegpipe" / "x.py"), "content": "x"}),
                    ("Edit", {"file_path": str(h / "eegpipe" / "settings.py"), "old_string": "a", "new_string": "b"}),
                    ("Bash", {"command": "sed -i s/a/b/ eegpipe/settings.py"}),
                    ("Bash", {"command": "cp /tmp/x.py eegpipe/runner/stage.py"}),
                    ("Bash", {"command": "echo x > eegpipe/x.py"}),
                    ("Bash", {"command": "cd eegpipe && rm settings.py"})):
    assert guard(h, tool, inp) == 2, (tool, inp)
  for tool, inp in (("Read", {"file_path": str(h / "eegpipe" / "settings.py")}),
                    ("Bash", {"command": "cat eegpipe/settings.py"}),
                    ("Bash", {"command": "python -m eegpipe.runner.stage --config configs/pipeline.json --out outputs/s --dry-run"})):
    assert guard(h, tool, inp) == 0, (tool, inp)
