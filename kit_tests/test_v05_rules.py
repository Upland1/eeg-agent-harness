"""Known-answer tests for the rule wordings Sebastian approved for 0.5.0 on 2026-11-16 ("Approved, all
seven as worded"): L37 (G22), L29 (skills), L32 (G10), L33 (Data handling), L34 (new G26), L35 (G16),
L36 (paradigm-analyst Edit for docs/PARADIGM.md only). Each fails on 03c00f6 (the 0.5.0 candidate before
them): the wording is absent there, the paradigm-analyst has no Edit, and check_frozen_text.py does not exist.
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

WORDING = {
  "L37": "Every measurement and reporting output records its compute time (`record_compute_time`; no computation: "
         "null with a reason); the auditor runs `python -m eegharness.outputs check` on the outputs a result cites.",
  "L29": "Run each agent in the foreground and wait for its handoff before the next step or the end of the turn; a "
         "subagent still running when the turn ends is stopped.",
  "L32": "A frozen check states its decision rule (statistic, resampling unit, α, windows), its sidedness with a "
         "reason, and what each outcome changes in the plan; a check without them is descriptive and gates nothing.",
  "L33": "Committed files never quote or paraphrase a participant's own answers, comments or free text, or personal "
         "details from forms; protocol facts from such documents are stated in the agent's own words, without "
         "per-participant content; the paradigm-analyst and the auditor check it.",
  "L34": "Evidence for a design decision is a check that would have come out differently if the decision were wrong; "
         "a decision that cites a test states exactly what the test asserts (the alternatives it rules out and the "
         "limits it checks) and nothing beyond; the auditor compares the entry with the test's assertions.",
  "L35": "Only an explicit answer is logged as an answer; template text, placeholders or suggested defaults are "
         "logged as 'no answer', and the agent asks once more, grouped.",
  "L36": "The paradigm-analyst has Edit for `docs/PARADIGM.md` only and appends its own revisions; frozen text stays "
         "unchanged and is checked by diff; a correction goes back to the analyst, never made by the orchestrator.",
}


def norm(text):
  return re.sub(r"\s+", " ", text)


def read(rel):
  return norm((T / rel).read_text())


def rule(n):
  """The text of rule Gn in template/CLAUDE.md, up to the next rule or section."""
  s = (T / "CLAUDE.md").read_text()
  m = re.search(rf"\*\*G{n}\. .*?(?=\n\*\*G\d+\. |\n\*\*Rules grow|\n## |\n\nRules G17)", s, re.S)
  assert m, f"G{n} not found"
  return norm(m.group(0))


def section(title):
  s = (T / "CLAUDE.md").read_text()
  return norm(s.split(f"## {title}\n", 1)[1].split("\n## ", 1)[0])


def test_l37_compute_time_in_g22_and_in_the_auditors_results_check():
  assert WORDING["L37"] in rule(22)
  auditor = read(".claude/agents/methods-auditor.md")
  results = auditor.split("## Results check", 1)[1].split("## Output", 1)[0]
  assert WORDING["L37"] in results and "`python -m eegharness.outputs check <folder>`" in results


@pytest.mark.parametrize("skill", ["onboard", "assignment", "apply-pipeline"])
def test_l29_foreground_agents_in_every_workflow_skill(skill):
  assert f"**Agents.** {WORDING['L29']}" in read(f".claude/skills/{skill}/SKILL.md")


def test_l32_frozen_check_states_its_rule_in_g10():
  assert WORDING["L32"] in rule(10) and "(L32)" in rule(10)


def test_l33_participants_free_text_in_data_handling_analyst_and_auditor():
  assert WORDING["L33"] in section("Data handling")
  assert WORDING["L33"] in read(".claude/agents/paradigm-analyst.md")
  assert WORDING["L33"] in read(".claude/agents/methods-auditor.md")


def test_l34_g26_is_a_kit_rule_checked_by_the_auditor_and_the_audit_template():
  g26 = rule(26)
  assert g26.startswith("**G26. Evidence must be able to fail.** ") and WORDING["L34"] in g26
  assert f"9. G26: {WORDING['L34']}" in read(".claude/agents/methods-auditor.md")
  assert "| G26 " in (T / "agent_runs" / "_templates" / "05_audit.md").read_text()
  assert "proposes a new rule (G28, G29, …)" in norm((T / "CLAUDE.md").read_text())  # G27 is a kit rule from 0.6.0 (L40)


def test_l35_only_explicit_answers_are_logged_in_g16():
  assert WORDING["L35"] in rule(16) and "(L35)" in rule(16)


def test_l36_wording_tools_and_onboard_step():
  analyst = (T / ".claude" / "agents" / "paradigm-analyst.md").read_text()
  tools = re.search(r"^tools: (.*)$", analyst, re.M).group(1).split(", ")
  assert "Edit" in tools and "Write" in tools
  assert WORDING["L36"] in norm(analyst)
  onboard = read(".claude/skills/onboard/SKILL.md")
  assert WORDING["L36"] in onboard and "check_frozen_text.py docs/PARADIGM.md --base" in onboard


# ---------------------------------------------------------------- L36: guard and frozen-text check

@pytest.fixture()
def proj(tmp_path):
  h = tmp_path / "proj"
  new_project.main([str(h), "--name", "proj", "--allow-dirty"])
  (h / "docs" / "PARADIGM.md").write_text("# Paradigm\n\nStatus: READY\n")
  return h


def guard(project, tool, inp, agent):
  ev = {"tool_name": tool, "tool_input": inp, "cwd": str(project), "agent_type": agent}
  r = subprocess.run([sys.executable, str(project / ".claude" / "hooks" / "guard.py")], input=json.dumps(ev),
                     capture_output=True, text=True, env={"CLAUDE_PROJECT_DIR": str(project), "PATH": "/usr/bin:/bin"})
  return r.returncode


def _git(root, *a):
  subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", *a], check=True,
                 capture_output=True)


def test_guard_paradigm_analyst_edits_paradigm_only_and_appends_once_committed(proj):
  par = str(proj / "docs" / "PARADIGM.md")
  edit = {"file_path": par, "old_string": "Status: READY\n", "new_string": "Status: READY\n\n## Revision 1\n"}
  assert guard(proj, "Edit", edit, "paradigm-analyst") == 0
  for other in ("docs/DECISIONS.md", "adapter.py", "docs/COMPUTE.md"):
    assert guard(proj, "Edit", {"file_path": str(proj / other), "old_string": "a", "new_string": "b"},
                 "paradigm-analyst") == 2, other
  assert guard(proj, "Write", {"file_path": par, "content": "x"}, "paradigm-analyst") == 0  # first draft, not committed
  _git(proj, "add", "docs/PARADIGM.md")
  _git(proj, "commit", "-qm", "paradigm draft")
  assert guard(proj, "Write", {"file_path": par, "content": "x"}, "paradigm-analyst") == 2  # would rewrite frozen text
  assert guard(proj, "Edit", edit, "paradigm-analyst") == 0
  assert guard(proj, "Edit", {"file_path": str(proj / "docs" / "DECISIONS.md"), "old_string": "a", "new_string": "b"},
               None) == 0  # other agents are not restricted by L36


# The cold-pressor incident in miniature (Revision 3, R3.4): the orchestrator appended the analyst's block and
# reworded one of its sentences after it was committed.
R3 = "## Revision 3\n\nR3.4 The rest windows are measured from the cue.\n"
R3_REWORDED = "## Revision 3\n\nR3.4 The rest windows are measured from the end of the cue.\n"


def test_frozen_text_check_known_answers(tmp_path, capsys):
  import check_frozen_text as cft
  root = tmp_path / "p"
  (root / "docs").mkdir(parents=True)
  f = root / "docs" / "PARADIGM.md"
  f.write_text("# Paradigm\n\nApproved by Sebastian: [ ]\n\n" + R3)
  _git(root, "init", "-q", "-b", "main")
  _git(root, "add", "-A")
  _git(root, "commit", "-qm", "r3")
  args = ["docs/PARADIGM.md", "--base", "HEAD", "--root", str(root)]
  assert cft.main(args) == 0
  f.write_text(f.read_text() + "\n## Revision 4\n\nR4.1 New text.\n")  # appended revision
  assert cft.main(args) == 0
  f.write_text("# Paradigm\n\nApproved by Sebastian, 2026-11-12, Revision 4\nApproved by Sebastian: [ ]\n\n" + R3)
  assert cft.main(args) == 0  # an inserted approval line
  f.write_text("# Paradigm\n\nApproved by Sebastian: [ ]\n\n" + R3_REWORDED)
  assert cft.main(args) == 1
  assert "l.7: R3.4 The rest windows are measured from the cue." in capsys.readouterr().out
  f.write_text("# Paradigm\n\nApproved by Sebastian: [ ]\n\n## Revision 3\n")  # a deleted frozen line
  assert cft.main(args) == 1
  f.write_text("# Paradigm\n\nApproved by Sebastian: [x]\n\n" + R3)  # ticking the box changes a frozen line too
  assert cft.main(args) == 1
  assert cft.main(["docs/MISSING.md", "--base", "HEAD", "--root", str(root)]) == 1


def test_frozen_text_check_ships_in_dot_harness(proj):
  assert (proj / ".harness" / "tools" / "check_frozen_text.py").is_file()
