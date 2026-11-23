"""Known-answer tests for the 0.6.0 items Sebastian approved on 2026-11-23 ("Approved for v0.6: every item
marked Rec, as worded, with these edits and choices"), BACKLOG L39-L55. Each test fails on b361f81 (the
v0.6-dev commit before them) and passes with its item.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

KIT = Path(__file__).resolve().parents[1]
T = KIT / "template"
sys.path.insert(0, str(KIT))
sys.path.insert(0, str(KIT / "tools"))
import new_project  # noqa: E402


def norm(text):
  return re.sub(r"\s+", " ", text)


def read(rel):
  return norm((T / rel).read_text())


# L41: data/ and inputs/ exist in every project, with or without --case.

@pytest.mark.parametrize("arm", [[], ["--control"]])
def test_l41_data_and_inputs_exist_without_case(tmp_path, arm):
  p = tmp_path / "proj"
  new_project.main([str(p), "--name", "p", *arm])
  assert (p / "data").is_dir() and (p / "inputs").is_dir()
  (p / "data" / "raw").symlink_to(tmp_path)  # the documented `ln -s <recordings> <dir>/data/raw` now works
  assert (p / "data" / "raw").resolve() == tmp_path.resolve()


# L43 (reduced form): the per-project .venv is the documented interpreter.

def test_l43_per_project_venv_is_documented_and_printed(tmp_path, capsys):
  p = tmp_path / "proj"
  new_project.main([str(p), "--name", "p"])
  out = capsys.readouterr().out
  assert f"python3 -m venv {p / '.venv'}" in out and str(KIT / "requirements.txt") in out
  step1 = norm((KIT / "README.md").read_text()).split("## How a project runs", 1)[1].split("2. Open Claude Code", 1)[0]
  assert "<dir>/.venv" in step1 and "the test hook runs `.venv/bin/python`" in step1
  assert '".venv" / "bin" / "python"' in (T / ".claude" / "hooks" / "run_tests.py").read_text()


# L48: the template's approval box, ticked and dated, passes the sources check; the gates read the same form.

from eegharness import sources  # noqa: E402

BOX_FILES = ("agent_runs/_templates/onboarding/PARADIGM.md", "agent_runs/_templates/02_plan.md")


def _box(rel):
  return next(l for l in (T / rel).read_text().splitlines() if l.startswith("Approved by Sebastian"))


@pytest.mark.parametrize("rel", BOX_FILES)
def test_l48_ticked_dated_template_box_passes_and_others_are_reported(rel):
  box = _box(rel)
  assert box.startswith("Approved by Sebastian: [ ]") and box.rstrip().endswith("Date:")
  ticked = box.replace("[ ]", "[x]").rstrip() + " 2026-11-19"
  body = "# Title\n\n{}\n\nText.\n"
  assert sources.check_text(body.format(ticked), names=["Sebastian"]) == []
  unticked_dated = box.rstrip() + " 2026-11-19"
  assert [f["kind"] for f in sources.check_text(body.format(unticked_dated), names=["Sebastian"])] == ["unquoted_attribution"]
  ticked_undated = box.replace("[ ]", "[x]")
  assert [f["kind"] for f in sources.check_text(body.format(ticked_undated), names=["Sebastian"])] == ["undated_approval"]
  # an attribution elsewhere in the paragraph is still reported
  assert sources.check_text(body.format(ticked + "\nSebastian said on 2026-11-19 to keep it."), names=["Sebastian"])


def test_l48_ticked_box_in_a_committed_file_passes_the_repo_check(tmp_path):
  subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
  (tmp_path / "docs").mkdir()
  box = _box(BOX_FILES[0]).replace("[ ]", "[x]").rstrip() + " 2026-11-19"
  (tmp_path / "docs" / "PARADIGM.md").write_text(f"# Paradigm\n\n{box}\n")
  subprocess.run(["git", "-C", str(tmp_path), "add", "docs"], check=True)
  assert sources.check_repo(tmp_path, names=["Sebastian"]) == []


def test_l48_gates_read_the_template_box():
  gate = "Approved by Sebastian: [x]"
  for rel in BOX_FILES:
    assert _box(rel).replace("[ ]", "[x]").startswith(gate)
  for rel in ("skills/assignment/SKILL.md", "skills/apply-pipeline/SKILL.md", "skills/onboard/SKILL.md",
              "agents/pipeline-engineer.md"):
    assert gate in (T / ".claude" / rel).read_text()
  assert "the template's box ticked and dated" in read("CLAUDE.md")


# L40: kit rule G27, the wording the cold-pressor project approved (BACKLOG L40).

L40 = ("A group statistic takes only estimates that exist at that sample size. Extends G20 (a). A per-participant "
       "(or per-unit) estimate enters a group statistic only if its estimator is defined and non-degenerate at that "
       "unit's sample size; the minimum is derived from the estimator and tested (a test at the minimum and one "
       "below it), and inclusion is decided by the estimator's own criterion, never by another method's validity "
       "flag. Every unit left out is listed with its reason in that runner's output.")


def test_l40_g27_is_a_kit_rule_checked_by_the_auditor():
  claude = read("CLAUDE.md")
  g27 = claude.split("**G27. ", 1)[1].split("**Rules grow from experience.**", 1)[0]
  assert norm("**G27. " + g27).startswith("**G27. A group statistic takes only estimates that exist at that sample size.** ")
  assert L40.split(". ", 1)[1] in g27 and "(L40)" in g27
  assert "proposes a new rule (G28, G29, …)" in claude
  assert f"10. G27: {L40}" in read(".claude/agents/methods-auditor.md")
  assert "| G27 " in (T / "agent_runs" / "_templates" / "05_audit.md").read_text()
  assert "(G27)" in read(".claude/skills/connectivity/SKILL.md")
  assert L40 in norm((KIT / "BACKLOG.md").read_text())


# L50: the auditor's hook lets it run the checks G15 and G22 tell it to run, and nothing else of those modules.

@pytest.fixture()
def proj(tmp_path):
  h = tmp_path / "proj"
  new_project.main([str(h), "--name", "proj", "--allow-dirty"])
  return h


def guard(project, tool, inp, agent):
  ev = {"tool_name": tool, "tool_input": inp, "cwd": str(project), "agent_type": agent}
  r = subprocess.run([sys.executable, str(project / ".claude" / "hooks" / "guard.py")], input=json.dumps(ev),
                     capture_output=True, text=True, env={"CLAUDE_PROJECT_DIR": str(project), "PATH": "/usr/bin:/bin"})
  return r.returncode


def auditor(project, cmd):
  return guard(project, "Bash", {"command": cmd}, "methods-auditor")


@pytest.mark.parametrize("py", ["python", ".venv/bin/python", "python3"])
def test_l50_auditor_runs_outputs_and_sources_check(proj, py):
  assert auditor(proj, f"{py} -m eegharness.outputs check outputs/confirm/20261123T100355Z_ec60d9b") == 0
  assert auditor(proj, f"{py} -m eegharness.sources check") == 0
  assert auditor(proj, f"{py} -m eegharness.sources check docs/DECISIONS.md --min-quote-words 3") == 0


@pytest.mark.parametrize("cmd", [
  "python -m eegharness.outputs new outputs/x",
  "python -m eegharness.outputs",
  "python -m eegharness.sources",
  "python -m eegharness.outputs check outputs/x --record outputs/outputs_check",
  "python -m eegharness.outputs check outputs/x > agent_runs/r/check.txt",
  "python -m eegharness.sources check > docs/sources.txt",
  "python -m eegharness.folds check outputs/x",
])
def test_l50_auditor_refused_other_subcommands_records_and_redirects(proj, cmd):
  assert auditor(proj, cmd) == 2


def test_l50_every_check_named_for_the_auditor_passes_its_hook(proj):
  named = set()
  for rel in (".claude/agents/methods-auditor.md", "CLAUDE.md"):
    named |= set(re.findall(r"`(python -m [\w.]+ check)[^`]*`", (T / rel).read_text()))
  assert {"python -m eegharness.outputs check", "python -m eegharness.sources check",
          "python -m eegharness.numbers check"} <= named
  for cmd in named:
    assert auditor(proj, cmd + " x") == 0, cmd
  assert auditor(proj, "python -m pytest tests/ -q -p no:cacheprovider") == 0
