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


# L45 + L47: audit rounds (wording-only round, auditor errors, hard limit of 4) and cost per round.

L45 = ("The auditor labels each required fix *code/test* or *wording*. A failure whose fixes are all wording gets one "
       "fix round, limited to the named lines and checked by diff. That round does not count toward the two-round "
       "limit. The run log records each round's tokens and wall time as differences of running totals. Cost figures "
       "come only from `cost_report.py`, `run_cost.py` or the `log_cost.py` summary, never from adding up rows.")
L47 = ("A suggested wording in a required fix is held to G7/G26: any number in it is quoted from printed output with "
       "its line, or it gives none. A failure on text the auditor proposed is recorded as an auditor error and is not "
       "counted as a round against the agent. An auditor error is not counted against the agent, but every round "
       "counts toward a hard limit of 4 rounds per step, whoever caused the failure; at the limit, stop and ask "
       "Sebastian.")


@pytest.mark.parametrize("skill", ["onboard", "assignment", "apply-pipeline"])
def test_l45_l47_audit_rounds_in_every_workflow_skill(skill):
  text = read(f".claude/skills/{skill}/SKILL.md")
  assert f"**Audit rounds (L45, L47).** {L45} {L47}" in text
  assert "log_cost.py --rounds agent_runs/<run>" in text


def test_l45_l47_auditor_labels_fixes_and_holds_its_own_wording_to_g7_g26():
  auditor = read(".claude/agents/methods-auditor.md")
  assert "Label each required fix *code/test* or *wording* (L45)" in auditor and L47 in auditor
  audit = read("agent_runs/_templates/05_audit.md")
  assert "| Kind (code/test, wording, auditor error) |" in audit and "hard limit of 4 per step (L45, L47)" in audit
  assert "its kind (code/test, wording, auditor error)" in read("agent_runs/_templates/02b_plan_audit.md")


def _log_cost():
  import importlib.util
  spec = importlib.util.spec_from_file_location("log_cost_v06", T / ".claude" / "hooks" / "log_cost.py")
  m = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(m)
  return m


def test_l45_cost_per_round_from_running_totals_on_the_real_onboarding_log(tmp_path):
  # imagined-speech-eeg onboarding, the first 20 lines of cost.jsonl (to 2026-11-17T18:51:45): the orchestrator
  # reported 31.0 M by adding rows; the lines are running totals and the true total is 11,590,942.
  run = tmp_path / "run"
  run.mkdir()
  (run / "cost.jsonl").write_text((KIT / "kit_tests" / "golden" / "l45_onboarding_cost.jsonl").read_text())
  lines = [json.loads(l) for l in (run / "cost.jsonl").read_text().splitlines()]
  assert len(lines) == 20 and sum(l["total_tokens"] for l in lines) == 35_234_426  # the wrong method
  m = _log_cost()
  rows, total = m.rounds(run)
  assert total == 11_590_942
  assert "Total tokens: 11590942." in m.summary(run)
  assert rows[0]["tokens"] == 1_040_191 and rows[2]["tokens"] == 1_258_285 - 1_040_191  # orchestrator turn 2
  assert all(r["tokens"] >= 0 for r in rows)
  out = subprocess.run([sys.executable, str(T / ".claude" / "hooks" / "log_cost.py"), "--rounds", str(run)],
                       capture_output=True, text=True, check=True).stdout
  assert "Total tokens: 11590942 (the increments" in out


# L42 + L46: /onboard does not start while inputs/ holds a template placeholder or an unquoted report of a
# person's words. Fixtures: imagined-speech-eeg inputs/request.md at e147a9a (whole file, template text only),
# b71401a and 4c72438 (header lines only; the professor's notes are not copied into the kit).

INPUTS = KIT / "kit_tests" / "golden" / "l42_l46_inputs"


def _inputs_project(tmp_path, fixture, names=("Sebastian",)):
  p = tmp_path / "proj"
  new_project.main([str(p), "--name", "p"])
  (p / "inputs" / "request.md").write_text((INPUTS / fixture).read_text())
  hj = json.loads((p / ".claude" / "harness.json").read_text())
  hj["sources"] = {"names": list(names)}
  (p / ".claude" / "harness.json").write_text(json.dumps(hj))
  return p


def _check_inputs(p):
  r = subprocess.run([sys.executable, str(p / ".harness" / "tools" / "check_inputs.py"), "--root", str(p)],
                     capture_output=True, text=True)
  return r.returncode, r.stdout


def test_l42_template_request_with_placeholders_is_refused(tmp_path):
  rc, out = _check_inputs(_inputs_project(tmp_path, "e147a9a_request.md"))
  assert rc == 1
  assert "inputs/request.md:2: placeholder: <what the professor wants: e.g. decode which of the 5 words" in out
  assert "inputs/request.md:3: placeholder: <anything known about how it was recorded" in out


def test_l46_paraphrase_refused_verbatim_quote_passes(tmp_path):
  rc, out = _check_inputs(_inputs_project(tmp_path / "a", "b71401a_request_header.md"))
  assert rc == 1 and "inputs/request.md:3: unquoted_attribution:" in out
  rc, out = _check_inputs(_inputs_project(tmp_path / "b", "4c72438_request_header.md"))
  assert rc == 0 and out.strip().endswith("PASS")


def test_l42_not_placeholders():
  import importlib.util
  spec = importlib.util.spec_from_file_location("check_inputs_v06", KIT / "tools" / "check_inputs.py")
  m = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(m)
  text = ("See <https://doi.org/10.1/x> or write to <lab@uni.edu>.<br> H<sub>2</sub>\n"
          "<!-- a comment --> p < 0.05 and q > 1\n<img src=\"a.png\">\n")
  assert m.placeholders(text) == []
  assert m.placeholders("Goal: <the goal>\n") == [(1, "<the goal>")]


def test_l42_l46_onboard_runs_the_check_before_set_up():
  onboard = read(".claude/skills/onboard/SKILL.md")
  assert "0. **Inputs are the human's own words (L42, L46).** Run `python .harness/tools/check_inputs.py`. Do not start while it reports a finding" in onboard
  assert onboard.index("0. **Inputs are the human's own words") < onboard.index("1. **Set up.**")


# L55 (option a): a `slow` marker, left out of the default run; the full suite with -m "".

def test_l55_slow_tests_left_out_by_default_and_run_in_the_full_suite(tmp_path):
  p = tmp_path / "proj"
  new_project.main([str(p), "--name", "p"])
  (p / "tests" / "test_speed.py").write_text(
    "import pytest\n\ndef test_fast():\n  assert True\n\n@pytest.mark.slow\ndef test_slow():\n  assert True\n")
  run = lambda *a: subprocess.run([sys.executable, "-m", "pytest", "tests/", "-q", "-p", "no:cacheprovider",
                                   "-W", "error::pytest.PytestUnknownMarkWarning", *a],
                                  cwd=p, capture_output=True, text=True)
  default, full = run(), run("-m", "")
  assert default.returncode == 0 and "1 passed, 1 deselected" in default.stdout
  assert full.returncode == 0 and "2 passed" in full.stdout and "deselected" not in full.stdout
  assert "PytestUnknownMarkWarning" not in default.stdout + default.stderr


def test_l55_g2_names_both_runs():
  g2 = read("CLAUDE.md").split("**G2. ", 1)[1].split("**G3. ", 1)[0]
  assert "`pytest tests/` (the default run, which leaves out tests marked `slow`) runs on CPU in about a minute" in g2
  assert "the full suite, `pytest tests/ -m \"\"`, runs before every freeze and commit and in the auditor's check (L55)" in g2
  assert "-p no:cacheprovider -m \"\"` (the full suite" in read(".claude/agents/methods-auditor.md")


# L39: working threads below the core limit, enforced on the settings; a temperature log next to the job table.

from eegpipe import settings as eeg_settings  # noqa: E402


def _cfg(n_jobs=1):
  from test_eegpipe_runner import settings_for  # a complete settings dict that validates
  cfg = settings_for()
  cfg["permutation"]["n_jobs"] = n_jobs
  return cfg


@pytest.fixture()
def compute():
  from eegharness import compute as c
  return c


def _compute_md(root, threads):
  (root / "docs").mkdir(parents=True, exist_ok=True)
  text = (T / "docs" / "COMPUTE.md").read_text()
  if threads is not None:
    text = text.replace("cpu_working_threads:\n", f"cpu_working_threads: {threads}\n")
  (root / "docs" / "COMPUTE.md").write_text(text)


def _thread_refusals(cfg, root):
  try:
    assert eeg_settings.validate(cfg, require_sources=False, root=root) == []
    return []
  except eeg_settings.SettingsError as e:
    return [p for p in str(e).split("; ") if "cpu_working_threads" in p]


def test_l39_validate_refuses_n_jobs_above_working_threads(tmp_path):
  _compute_md(tmp_path, 8)
  assert _thread_refusals(_cfg(12), tmp_path) == ["permutation.n_jobs = 12 > cpu_working_threads = 8 (docs/COMPUTE.md, L39)"]
  assert _thread_refusals(_cfg(-1), tmp_path) == ["permutation.n_jobs = -1: all cores, at most cpu_working_threads = 8 (docs/COMPUTE.md, L39)"]
  assert _thread_refusals(_cfg(8), tmp_path) == [] and _thread_refusals(_cfg(None), tmp_path) == []
  cfg = _cfg(4)
  cfg.setdefault("networks", {})["torch_threads"] = 16
  assert _thread_refusals(cfg, tmp_path) == ["networks.torch_threads = 16 > cpu_working_threads = 8 (docs/COMPUTE.md, L39)"]


def test_l39_unset_working_threads_is_refused_and_no_compute_md_checks_nothing(tmp_path, compute):
  _compute_md(tmp_path / "p", None)
  assert compute.read_limits(tmp_path / "p")["cpu_working_threads"] is None
  assert _thread_refusals(_cfg(1), tmp_path / "p") == ["docs/COMPUTE.md: cpu_working_threads is not set (Sebastian sets it, L39)"]
  assert _thread_refusals(_cfg(12), tmp_path / "none") == []  # not a project: no COMPUTE.md


def test_l39_template_skill_and_new_project(tmp_path, capsys, compute):
  lim = compute.parse_limits((T / "docs" / "COMPUTE.md").read_text())
  assert "cpu_working_threads" in lim and lim["cpu_working_threads"] is None
  skill = read(".claude/skills/compute-jobs/SKILL.md")
  assert "| `cpu_working_threads` |" in skill and "python -m eegharness.compute templog" in skill
  assert "`OMP_NUM_THREADS`, `MKL_NUM_THREADS`, `OPENBLAS_NUM_THREADS`" in skill
  new_project.main([str(tmp_path / "p"), "--name", "p"])
  assert "set cpu_working_threads in" in capsys.readouterr().out


def _sys_tree(root, zones=(), hwmon=()):
  for i, (kind, milli) in enumerate(zones):
    z = root / "class" / "thermal" / f"thermal_zone{i}"
    z.mkdir(parents=True)
    (z / "type").write_text(kind + "\n")
    (z / "temp").write_text(f"{milli}\n")
  for i, (name, sensors) in enumerate(hwmon):
    h = root / "class" / "hwmon" / f"hwmon{i}"
    h.mkdir(parents=True)
    (h / "name").write_text(name + "\n")
    for j, (label, milli) in enumerate(sensors, 1):
      (h / f"temp{j}_label").write_text(label + "\n")
      (h / f"temp{j}_input").write_text(f"{milli}\n")
  return root


def test_l39_temperatures_from_planted_sysfs_and_nvidia_smi(tmp_path, compute):
  s = _sys_tree(tmp_path / "a", zones=[("acpitz", 51000), ("x86_pkg_temp", 95000)])
  assert compute.cpu_temperature(s) == 95.0  # the package sensor, not the hotter-or-colder other zone
  s = _sys_tree(tmp_path / "b", zones=[("acpitz", 40000)],
                hwmon=[("coretemp", [("Package id 0", 98000), ("Core 0", 99000)])])
  assert compute.cpu_temperature(s) == 98.0
  s = _sys_tree(tmp_path / "c", zones=[("acpitz", 40000), ("pch", 61000)])
  assert compute.cpu_temperature(s) == 61.0  # no package sensor: the maximum
  assert compute.gpu_temperature("87\n") == 87.0 and compute.gpu_temperature("54\n71\n") == 71.0
  row = compute.sample(tmp_path / "empty", nvidia_smi_output="")
  assert row["cpu_c"] == "not available" and row["gpu_c"] == "not available"


def test_l39_templog_writes_rows_until_the_driver_exits(tmp_path, compute):
  s = _sys_tree(tmp_path / "s", zones=[("x86_pkg_temp", 66000)])
  out = tmp_path / "logs" / "temperature.tsv"
  assert compute.templog(out, interval=0, n=3, sys_root=s, nvidia_smi_output="70") == 3
  lines = out.read_text().splitlines()
  assert lines[0] == "utc\tcpu_c\tgpu_c" and len(lines) == 4 and all(l.endswith("\t66.0\t70.0") for l in lines[1:])
  p = subprocess.Popen([sys.executable, "-c", "pass"])
  p.wait()
  assert compute.templog(tmp_path / "t2.tsv", interval=0, pid=p.pid, sys_root=s, nvidia_smi_output="") == 1
