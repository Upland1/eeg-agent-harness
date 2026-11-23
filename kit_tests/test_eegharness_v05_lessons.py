"""Known-answer tests for two lessons from cold-pressor onboarding (BACKLOG L37, L38; v0.5-dev).

L37: every measurement and reporting output records its compute time (``compute_time`` in
provenance.json; an output without computation records null with a reason). Fails on v0.4.1: no
writer recorded it and nothing checked it (cold-pressor audit C5: "runtimes are not measured").

L38: a source that is an orchestrator's or human's instruction is quoted in a committed file, never
cited only from git-ignored ``agent_runs/``. Fails on v0.4.1: no check existed; G15 alone (a
search for ``agent_runs/``) misses a bare "contact #3", as committed in cold-pressor's PARADIGM.md.
"""

import json
import math
import subprocess
import sys
import time
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
from eegharness import compare_runs  # noqa: E402
from eegharness import outputs as eo  # noqa: E402
from eegharness import sources as src  # noqa: E402


# ---------------------------------------------------------------- L37: compute time

def _busy(seconds):
  t = time.process_time()
  x = 0
  while time.process_time() - t < seconds:
    x += 1
  return x


def test_timer_known_answer_wall_cpu_and_children(tmp_path):
  """A 0.3 s sleep, 0.3 s of own CPU and a child process burning 0.3 s of CPU: wall >= 0.9 s,
  own CPU >= 0.25 s, children's CPU >= 0.25 s (a timer that reads only wall time, or only this
  process, fails)."""
  out = eo.new_output_dir(tmp_path / "m", root=tmp_path, argv=["x"])
  t = eo.ComputeTimer(device="cpu")
  time.sleep(0.3)
  _busy(0.3)
  subprocess.run([sys.executable, "-c", "import time\nt=time.process_time()\nwhile time.process_time()-t<0.3: pass"],
                 check=True)
  prov = eo.record_compute_time(out, t)
  ct = prov["compute_time"]
  assert ct["wall_s"] >= 0.9 and ct["wall_s"] < 30
  assert ct["cpu_s"] >= 0.25 and ct["cpu_children_s"] >= 0.25
  assert ct["device"] == "cpu" and len(ct["utc_end"]) == 16
  assert eo.check_compute_time(out) == []
  assert json.loads((out / "provenance.json").read_text())["compute_time"] == ct


def test_unrecorded_output_fails_and_nothing_is_written_by_default(tmp_path):
  """new_output_dir writes no compute_time (a default of null would make every forgotten output look
  like 'no compute'), so a folder that never recorded it fails the check."""
  out = eo.new_output_dir(tmp_path / "m", root=tmp_path, argv=["x"])
  assert "compute_time" not in json.loads((out / "provenance.json").read_text())
  probs = eo.check_compute_time(out)
  assert len(probs) == 1 and "not recorded" in probs[0]


def test_no_compute_is_null_with_a_reason(tmp_path):
  out = eo.new_output_dir(tmp_path / "r", root=tmp_path, argv=["x"])
  with pytest.raises(ValueError, match="reason"):
    eo.record_no_compute(out, "  ")
  eo.record_no_compute(out, "copies a committed table; nothing computed")
  prov = json.loads((out / "provenance.json").read_text())
  assert prov["compute_time"] is None and prov["compute_time_reason"].startswith("copies")
  assert eo.check_compute_time(out) == []
  with pytest.raises(ValueError, match="once"):
    eo.record_compute_time(out, eo.ComputeTimer())


def test_recorded_once_and_values_checked(tmp_path):
  out = eo.new_output_dir(tmp_path / "m", root=tmp_path, argv=["x"])
  eo.record_compute_time(out, eo.ComputeTimer())
  with pytest.raises(ValueError, match="once"):
    eo.record_compute_time(out, eo.ComputeTimer())
  with pytest.raises(ValueError, match="wall_s"):
    eo.record_compute_time(eo.new_output_dir(tmp_path / "m", root=tmp_path, argv=["x"]), {"wall_s": -1, "cpu_s": 0})
  bad = {"null without reason": None, "negative": {"wall_s": -0.1, "cpu_s": 0.0}, "nan": {"wall_s": math.nan, "cpu_s": 0.0},
         "string": {"wall_s": "12 s", "cpu_s": 0.0}, "bool": {"wall_s": True, "cpu_s": 0.0}, "list": [1.0]}
  for name, value in bad.items():
    d = tmp_path / "bad" / name
    d.mkdir(parents=True)
    (d / "provenance.json").write_text(json.dumps({"compute_time": value}))
    assert eo.check_compute_time(d), name


def test_cli_check_finds_every_folder_below(tmp_path, capsys):
  good = eo.new_output_dir(tmp_path / "outputs" / "a", root=tmp_path, argv=["x"])
  eo.record_compute_time(good, eo.ComputeTimer())
  assert eo.main(["check", str(tmp_path / "outputs")]) == 0
  eo.new_output_dir(tmp_path / "outputs" / "b", root=tmp_path, argv=["x"])
  assert eo.main(["check", str(tmp_path / "outputs")]) == 1
  assert "2 output folder(s), 1 problem(s)" in capsys.readouterr().out
  assert eo.main(["check", str(good)]) == 0
  (tmp_path / "empty").mkdir()
  assert eo.main(["check", str(tmp_path / "empty")]) == 1


def test_compare_runs_records_compute_time(tmp_path):
  """A kit writer end to end (the stage, select, collect and numbers writers are checked in their own
  end-to-end tests)."""
  a, b = tmp_path / "a", tmp_path / "b"
  for d in (a, b):
    d.mkdir()
    (d / "t.csv").write_text("x\n1\n")
  assert compare_runs.main(["--a", str(a), "--b", str(b), "--out", str(tmp_path / "cmp")]) == 0
  out = next((tmp_path / "cmp").iterdir())
  assert eo.check_compute_time(out) == []


# ---------------------------------------------------------------- L38: instruction sources

CP_PARADIGM = ("- Sidedness: **two-sided, by Sebastian's decision** (onboarding contact #3, 2026-11-11). Reasoning\n"
               "  follows below.\n")  # cold-pressor docs/PARADIGM.md l.908 @ a558941, as committed
SSVEP_D015 = ("- Date: 2026-11-10. Plan revision 5 (`agent_runs/2026-11-07_apply-pipeline/02_plan.md`, git-excluded)\n"
              "  holds it; its text is copied here verbatim.\n")  # ssvep-apply D-015 @ d0e8ee9 (Round 7 R5)


def kinds(text, **kw):
  return sorted(f["kind"] for f in src.check_text(text, **kw))


def test_real_incidents_are_found_and_g15_alone_misses_the_first():
  assert kinds(CP_PARADIGM) == ["unquoted_contact"]
  assert not src.UNCOMMITTED.search(CP_PARADIGM)  # a G15-only check (agent_runs/ paths) passes it
  assert kinds(SSVEP_D015) == ["uncommitted_path"]


def test_quoted_instruction_passes_and_short_or_missing_quotes_fail():
  ok = ('Sidedness: two-sided (Sebastian, onboarding contact #3, 2026-11-11: "two-sided, because a reversal\n'
        'would also tell us something").\n')
  assert kinds(ok) == []
  assert kinds('Two-sided (contact #3: "two-sided").') == ["unquoted_contact"]
  assert kinds('Two-sided (contact 3: “yes, two sided please”).') == []
  assert kinds("As decided in human_contacts.md, two-sided.") == ["unquoted_contact"]
  assert kinds("Approved (contact #8):\n> Approved: freeze a1130b3, and start the run.\n") == []
  assert kinds('Two-sided (contact #3: "two-sided").', min_quote_words=1) == []
  # the quote must be in the same paragraph as the citation
  assert kinds('"two-sided, because a reversal matters"\n\nTwo-sided (contact #3).') == ["unquoted_contact"]


def test_agent_runs_path_is_found_even_when_quoted():
  assert kinds('Per `agent_runs/x/log.md`: "use n_jobs 3 for classical".') == ["uncommitted_path"]
  assert kinds("no reference here, and a contacts list of 3 items is not a contact") == []


def test_json_values_are_checked_one_by_one_and_json_quotes_do_not_count(tmp_path):
  p = tmp_path / "pipeline.json"
  p.write_text(json.dumps({"permutation": {"n_jobs": 3, "n_jobs_source": "Sebastian, contact 5, 2026-11-10"},
                           "ok_source": 'Sebastian, contact 6: "Classical at n_jobs 3; I will keep it ventilated."',
                           "plan": ["see agent_runs/run/02_plan.md"]}))
  found = src.check_file(p, "configs/pipeline.json")
  assert sorted((f["path"], f["kind"]) for f in found) == [
    ("configs/pipeline.json:permutation.n_jobs_source", "unquoted_contact"),
    ("configs/pipeline.json:plan[0]", "uncommitted_path")]


def _git(root, *a):
  subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", *a], check=True, capture_output=True)


def test_repo_check_reads_only_committed_files_and_skips_vendored(tmp_path, capsys):
  root = tmp_path / "proj"
  (root / "docs").mkdir(parents=True)
  (root / "eegpipe").mkdir()
  (root / "docs" / "DECISIONS.md").write_text("## D-001\n\n- Window 4 s (contact #2).\n")
  (root / "docs" / "notes.md").write_text('- Window 4 s (contact #2: "use the four second window").\n')
  (root / "eegpipe" / "x.py").write_text("# see agent_runs/ for the handoff\n")
  (root / ".gitignore").write_text("agent_runs/\n")
  _git(root, "init", "-q", "-b", "main")
  _git(root, "add", ".")
  _git(root, "commit", "-qm", "c")
  (root / "docs" / "draft.md").write_text("Per contact #4, change it.\n")  # untracked: not committed, not read
  (root / "agent_runs").mkdir()
  (root / "agent_runs" / "log.md").write_text("contact #1\n")  # ignored
  found = src.check_repo(root)
  assert [(f["path"], f["line"], f["kind"]) for f in found] == [("docs/DECISIONS.md", 3, "unquoted_contact")]
  assert src.main(["check", "--root", str(root)]) == 1
  assert "docs/DECISIONS.md:3: unquoted_contact" in capsys.readouterr().out
  assert [f["path"] for f in src.check_repo(root, skip=())] == ["docs/DECISIONS.md", "eegpipe/x.py"]
  (root / "docs" / "DECISIONS.md").write_text('## D-001\n\n- Window 4 s (contact #2: "use the four second window").\n')
  _git(root, "commit", "-qam", "quote it")
  assert src.main(["check", "--root", str(root)]) == 0


# ---------------------------------------------------------------- L38: attributions by name and date
# Real lines, as committed: ssvep-apply configs/pipeline.json "primary_source" @ f2e7f68 (a JSON string
# value) and cold-pressor docs/DECISIONS.md l.521 and docs/COMPUTE.md l.14 @ its HEAD of 2026-11-15.
SSVEP_PRIMARY_SOURCE = ("Decision 3 = B (Sebastian 2026-11-07): his MAS flagship, FBCSP + FBCCA features -> shrinkage LDA. "
                        "Chosen from his earlier pipeline: this study is a reproduction, not a blind test")
CP_CHOICE = "- **Choice (Sebastian, 2026-11-13).** 8 cores per job; GPU allowed through the CUDA build of torch\n"
CP_COMPUTE = "The SSVEP study's run has finished (Sebastian, 2026-11-13); the 2-core cap of 2026-11-10 is\n"
SSVEP_NO_DATE = "MAS (Sebastian's earlier pipeline, commit f725369) shallow_conv_net.py l.26-28"


def test_attribution_needs_configured_names_and_is_found_on_real_lines():
  for t in (SSVEP_PRIMARY_SOURCE, CP_CHOICE, CP_COMPUTE):
    assert kinds(t) == []  # no names configured: the check is off (the 0.5-dev default)
    assert kinds(t, names=["Sebastian"]) == ["unquoted_attribution"], t
  assert kinds(SSVEP_NO_DATE, names=["Sebastian"]) == []  # a name without a date is not an attribution
  assert kinds(CP_CHOICE, names=["Someone"]) == []


def test_attribution_window_order_and_quote():
  n = ["Sebastian"]
  assert kinds("Set on 2026-11-13 by Sebastian.", names=n) == ["unquoted_attribution"]  # date before the name
  far = "Sebastian " + "x" * (src.ATTRIBUTION_SPAN + 5) + " 2026-11-13"
  assert kinds(far, names=n) == []
  assert kinds("Sebastian, 2026-11-13:\n> 8 cores per job, and the GPU is allowed.\n", names=n) == []
  assert kinds('Sebastian 2026-11-07: "his MAS flagship, FBCSP plus FBCCA".', names=n) == []
  assert kinds("Sebastiano 2026-11-13 chose it.", names=n) == []  # whole names only
  # a contact citation in the same paragraph is reported once, as unquoted_contact
  assert kinds("Sebastian's decision (onboarding contact #3, 2026-11-11).", names=n) == ["unquoted_contact"]


def _project(tmp_path, harness_json=None, commit_config=False):
  root = tmp_path / "proj"
  (root / "docs").mkdir(parents=True)
  (root / "docs" / "COMPUTE.md").write_text(CP_COMPUTE)
  (root / ".gitignore").write_text("agent_runs/\n")
  if harness_json is not None:
    (root / ".claude").mkdir()
    (root / ".claude" / "harness.json").write_text(json.dumps(harness_json))
  _git(root, "init", "-q", "-b", "main")
  _git(root, "add", "docs", ".gitignore", *([".claude/harness.json"] if commit_config else []))
  _git(root, "commit", "-qm", "c")
  return root


def test_names_come_from_the_local_harness_json_and_the_command_line(tmp_path, capsys):
  root = _project(tmp_path)  # no harness.json: off
  assert src.main(["check", "--root", str(root)]) == 0
  assert src.main(["check", "--root", str(root), "--name", "Sebastian"]) == 1
  root = _project(tmp_path / "b", {"mode": "harness", "sources": {"names": ["Sebastian"]}})
  assert [f["kind"] for f in src.check_repo(root)] == ["unquoted_attribution"]
  assert src.main(["check", "--root", str(root)]) == 1
  out = capsys.readouterr().out
  assert "docs/COMPUTE.md:1: unquoted_attribution" in out and "committed_names" not in out
  bad = _project(tmp_path / "c", {"sources": {"names": "Sebastian"}})
  with pytest.raises(ValueError, match="list"):
    src.check_repo(bad)


def test_a_committed_names_list_is_reported(tmp_path, capsys):
  root = _project(tmp_path, {"sources": {"names": ["Sebastian"]}}, commit_config=True)
  assert sorted(f["kind"] for f in src.check_repo(root)) == ["committed_names", "unquoted_attribution"]
  assert src.main(["check", "--root", str(root)]) == 1
  assert ".claude/harness.json: committed_names" in capsys.readouterr().out


def test_new_project_update_keeps_the_names_list(tmp_path):
  sys.path.insert(0, str(TOOLS.parent))
  import new_project
  dest = tmp_path / "p"
  (dest / ".claude").mkdir(parents=True)
  (dest / ".claude" / "harness.json").write_text(json.dumps({"mode": "harness", "sources": {"names": ["Sebastian"]}}))
  new_project.write_build(dest, {"version": "0.5.0"}, "harness", None, None)
  cfg = json.loads((dest / ".claude" / "harness.json").read_text())
  assert cfg["sources"] == {"names": ["Sebastian"]} and cfg["harness"] == {"version": "0.5.0"}
  fresh = tmp_path / "q"
  fresh.mkdir()
  new_project.write_build(fresh, {"version": "0.5.0"}, "harness", None, None)
  assert "sources" not in json.loads((fresh / ".claude" / "harness.json").read_text())


# Approval lines in the standard form "Approved by <name>, <date>[, <what>]" (Sebastian, 2026-11-15).
# Real lines: cold-pressor docs/PARADIGM.md l.7-8 (standard form) and l.6 (not), @ its HEAD of 2026-11-15.
CP_APPROVED_R4 = "Approved by Sebastian, 2026-11-12, Revision 4\n"
CP_APPROVED_R5 = "Approved by Sebastian, 2026-11-13, Revision 5\n"
CP_APPROVED_BOX = "Approved by Sebastian: [x]   Date: 2026-11-12\n"


def test_standard_approval_lines_pass_and_an_unquoted_instruction_is_still_flagged():
  n = ["Sebastian"]
  assert kinds(CP_APPROVED_R4, names=n) == [] and kinds(CP_APPROVED_R5, names=n) == []
  assert kinds("Approved by Sebastian, 2026-11-12\n", names=n) == []          # <what> is optional
  assert kinds("- Approved by Sebastian, 2026-11-12, Revision 4\n", names=n) == []
  # 0.6.0 (L48, approved 2026-11-23): the template's box ticked and dated is a record too; unticked it is not
  assert kinds(CP_APPROVED_BOX, names=n) == []
  assert kinds(CP_APPROVED_BOX.replace("[x]", "[ ]"), names=n) == ["unquoted_attribution"]
  # an approval line does not hide an unquoted instruction in the same paragraph
  assert kinds(CP_APPROVED_R4 + CP_CHOICE, names=n) == ["unquoted_attribution"]
  assert kinds(CP_APPROVED_R4 + CP_COMPUTE, names=n) == ["unquoted_attribution"]
  # the form is the whole line: an approval sentence inside an instruction is not exempt
  assert kinds("Set to 8 cores. Approved by Sebastian, 2026-11-13, on the call.\n", names=n) == ["unquoted_attribution"]
  assert kinds("Approved by Someone, 2026-11-12, Revision 4\n" + CP_COMPUTE, names=n) == ["unquoted_attribution"]
  assert kinds("Approved by Sebastian, 2026-11-13 to use 8 cores per job.\n", names=n) == ["unquoted_attribution"]
  # only the configured person's own approval line is exempt
  assert kinds("Approved by the lab manager, 2026-11-13, as Sebastian asked\n", names=n) == ["unquoted_attribution"]
