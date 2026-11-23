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
