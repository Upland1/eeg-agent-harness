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
  assert "set cpu_working_threads and memory_max_gb in" in capsys.readouterr().out


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


# L54 + L44: memory limit and data present before each batch; where the recordings are stored.

def _batch_project(tmp_path, memory, n_files=3, link=True):
  p = tmp_path / "proj"
  rec = tmp_path / "drive" / "Habla imaginada con 5 palabras"
  for i in range(n_files):
    (rec / f"S{i + 1}").mkdir(parents=True, exist_ok=True)
    (rec / f"S{i + 1}" / "1_HI.ebr").write_bytes(b"\0" * 8)
  (p / "docs").mkdir(parents=True)
  (p / "data").mkdir()
  (p / "data" / "raw").symlink_to(rec) if link else None
  text = (T / "docs" / "COMPUTE.md").read_text().replace("cpu_working_threads:\n", "cpu_working_threads: 8\n")
  if memory is not None:
    text = text.replace("memory_max_gb:\n", f"memory_max_gb: {memory}\n")
  (p / "docs" / "COMPUTE.md").write_text(text)
  (p / "docs" / "DATA_PROFILE.json").write_text(json.dumps({"files": [{"path": f"S{i + 1}/1_HI.ebr"} for i in range(3)]}))
  return p, rec


MEMINFO = "MemTotal:       23000000 kB\nMemAvailable:   {} kB\n"


def test_l54_batch_size_and_memory_limit(tmp_path, compute):
  assert compute.batch_size(5.7, 18) == 3
  p, _ = _batch_project(tmp_path, 18)
  ok = MEMINFO.format(30_000_000)  # 30.7 GB available: only the limit refuses 4 parts
  assert compute.precheck(p, 3, 5.7, meminfo=ok) == []
  assert compute.precheck(p, 4, 5.7, meminfo=ok) == ["4 parts x 5.7 GB = 22.80 GB > memory_max_gb = 18 (at most 3 parts, L54)"]
  low = compute.precheck(p, 3, 5.7, meminfo=MEMINFO.format(6_000_000))
  assert low == ["available memory 6.14 GB < 17.10 GB needed; wait or stop (L54)"]


def test_l54_unset_memory_limit_refuses_and_template_has_no_default(tmp_path, compute):
  assert compute.parse_limits((T / "docs" / "COMPUTE.md").read_text())["memory_max_gb"] is None
  p, _ = _batch_project(tmp_path, None)
  assert compute.precheck(p, 1, 5.7, meminfo=MEMINFO.format(20_000_000)) == [
    "docs/COMPUTE.md: memory_max_gb is not set (Sebastian sets it, L54)"]
  r = subprocess.run([sys.executable, "-m", "eegharness.compute", "precheck", "--parts", "1", "--peak-gb", "5.7",
                      "--root", str(p)], capture_output=True, text=True, cwd=KIT / "tools")
  assert r.returncode == 1 and "STOP: docs/COMPUTE.md: memory_max_gb is not set" in r.stdout
  skill = read(".claude/skills/compute-jobs/SKILL.md")
  assert "| `memory_max_gb` |" in skill and "python -m eegharness.compute precheck --parts <b> --peak-gb <peak>" in skill
  assert "`memory_max_gb` (memory the jobs may use together)" in read("CLAUDE.md")


def test_l44_data_raw_must_resolve_with_every_profiled_file(tmp_path, compute):
  p, rec = _batch_project(tmp_path, 18)
  ok = MEMINFO.format(20_000_000)
  rec.rename(rec.with_name("unmounted"))  # the drive is gone: the symlink dangles
  probs = compute.precheck(p, 1, 5.7, meminfo=ok)
  assert len(probs) == 1 and probs[0].startswith("data/raw -> ") and "does not resolve" in probs[0]
  p2, rec2 = _batch_project(tmp_path / "b", 18, n_files=2)  # one profiled file absent
  assert compute.precheck(p2, 1, 5.7, meminfo=ok) == [
    "1 of 3 profiled files missing under data/raw (first: S3/1_HI.ebr); stop (L44)"]


MOUNTINFO = ("22 1 259:4 / / rw,relatime shared:1 - ext4 /dev/nvme1n1p4 rw\n"
             "481 22 8:1 / /media/user/USBDRIVE rw,nosuid,nodev,relatime shared:250 - exfat /dev/sda1 rw,uid=1000\n"
             "482 22 8:17 / /media/user/My\\040Disk rw - vfat /dev/sdb1 rw\n")


def test_l44_profile_records_the_mount_of_the_resolved_data_folder(tmp_path):
  from eegprofile.storage import storage
  sysfs = tmp_path / "sys"
  (sysfs / "class" / "block" / "sda").mkdir(parents=True)
  (sysfs / "class" / "block" / "sda" / "removable").write_text("1\n")
  st = storage("/media/user/USBDRIVE/Habla imaginada con 5 palabras", mountinfo=MOUNTINFO, sys_root=sysfs)
  assert (st["mount_point"], st["fs_type"], st["source"], st["removable"], st["under_media"]) == (
    "/media/user/USBDRIVE", "exfat", "/dev/sda1", True, True)
  assert storage("/media/user/My Disk/x", mountinfo=MOUNTINFO, sys_root=sysfs)["mount_point"] == "/media/user/My Disk"
  home = storage("/home/u/proj", mountinfo=MOUNTINFO, sys_root=sysfs)
  assert (home["mount_point"], home["fs_type"], home["removable"], home["under_media"]) == ("/", "ext4", None, False)
  target = tmp_path / "rec"
  target.mkdir()
  (tmp_path / "raw").symlink_to(target)
  assert storage(tmp_path / "raw", mountinfo=MOUNTINFO)["resolved"] == str(target.resolve())


def test_l44_data_profile_json_and_md_carry_the_storage(tmp_path):
  from eegprofile.profile import profile_dataset
  from eegprofile.report import to_markdown
  (tmp_path / "rec").mkdir()
  (tmp_path / "rec" / "notes.txt").write_text("x")
  prof = profile_dataset(tmp_path / "rec", use_mne=False)
  assert set(prof["storage"]) == {"path", "resolved", "mount_point", "fs_type", "source", "removable", "under_media"}
  assert "Storage: `" in to_markdown(prof) and "filesystem `" in to_markdown(prof)


# L49: an attempt killed from outside (the stage process stopped mid-job) is recorded and counted.

DRIVER = '''
import json, sys, pathlib
sys.path.insert(0, {tools!r}); sys.path.insert(0, {kit_tests!r})
import eegpipe.runner.stage as stg
from test_eegpipe_runner import STG_COMMIT

def command(cpath, pdir, root):
  code = """
import json, os, sys, time, pathlib
pdir = pathlib.Path(%r)
(pdir / "child.pid").write_text(str(os.getpid()))
if pathlib.Path(%r).exists():
  time.sleep(60)
cfg = json.loads(pathlib.Path(%r).read_text())
n = len([d for d in pdir.iterdir() if d.is_dir()])
out = pdir / f"run{{n}}"; out.mkdir()
(out / "config_used.json").write_text(json.dumps(cfg))
(out / "results.json").write_text(json.dumps({{"commit": %r, "tracked_files_dirty": False, "epochs_sha256": "e", "folds_sha256": "f"}}))
(out / "pooled.csv").write_text("method,seed,status,ba\\\\nbaseline,,ok,0.6\\\\n")
(out / "summary.txt").write_text("ok\\\\n")
""" % (str(pdir), {flag!r}, str(cpath), STG_COMMIT)
  return [sys.executable, "-c", code]

try:
  stg.main({argv!r}, git=lambda: (STG_COMMIT, False), command=command)
except SystemExit as e:
  sys.exit(e.code)
'''


def _stage_driver(tmp_path, max_attempts=2):
  sys.path.insert(0, str(KIT / "kit_tests"))
  from test_eegpipe_runner import _stage_world
  argv, _ = _stage_world(tmp_path, "ok")
  cp = Path(argv[1])
  cfg = json.loads(cp.read_text())
  cfg["stage"]["retry"]["max_attempts"] = max_attempts
  cp.write_text(json.dumps(cfg))
  flag = tmp_path / "sleep.flag"
  code = DRIVER.format(tools=str(KIT / "tools"), kit_tests=str(KIT / "kit_tests"), flag=str(flag), argv=argv)
  return code, flag


def _kill_during_job(tmp_path, code):
  import os
  import signal
  import time
  before = set((tmp_path / "out").rglob("attempt_*.log")) if (tmp_path / "out").exists() else set()
  proc = subprocess.Popen([sys.executable, "-c", code], start_new_session=True)
  for _ in range(300):
    logs = set((tmp_path / "out").rglob("attempt_*.log")) - before if (tmp_path / "out").exists() else set()
    pids = list((tmp_path / "out").rglob("child.pid")) if (tmp_path / "out").exists() else []
    if logs and pids and pids[0].read_text().strip():
      child_pid = int(pids[0].read_text())
      if pids[0].stat().st_mtime >= max([l.stat().st_mtime for l in logs]) - 1:
        break
    time.sleep(0.1)
  else:
    proc.kill()
    raise AssertionError("the job did not start")
  os.killpg(proc.pid, signal.SIGKILL)  # the stage shell is stopped from outside (as for low memory)
  proc.wait()
  try:
    os.killpg(child_pid, signal.SIGKILL)  # and its job
  except ProcessLookupError:
    pass
  pids[0].unlink()


def _status(tmp_path):
  return json.loads(next((tmp_path / "out").rglob("part_status.json")).read_text())


def test_l49_killed_attempt_is_recorded_and_counted(tmp_path):
  code, flag = _stage_driver(tmp_path)
  flag.write_text("sleep")
  _kill_during_job(tmp_path, code)
  assert _status(tmp_path)["status"] == "running" and _status(tmp_path)["n_attempts"] == 1
  flag.unlink()
  r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
  assert r.returncode == 0, r.stdout + r.stderr
  st = _status(tmp_path)
  assert (st["status"], st["n_attempts"], st["n_interrupted"]) == ("done", 2, 1)
  pdir = next((tmp_path / "out").rglob("part_status.json")).parent
  assert sorted(l.name.rsplit("_", 1)[1] for l in pdir.glob("attempt_*.log")) == ["1.log", "2.log"]
  events = [json.loads(l)["event"] if "event" in json.loads(l) else json.loads(l)["status"]
            for l in (pdir.parents[2] / "attempts.jsonl").read_text().splitlines()]
  assert events == ["started", "interrupted", "started", "done"]
  index = (pdir.parents[2] / "index.csv").read_text().splitlines()
  assert "n_interrupted" in index[0] and index[1].split(",")[index[0].split(",").index("n_interrupted")] == "1"


def test_l49_two_kills_with_max_attempts_2_make_the_part_terminal(tmp_path):
  code, flag = _stage_driver(tmp_path, max_attempts=2)
  flag.write_text("sleep")
  _kill_during_job(tmp_path, code)
  _kill_during_job(tmp_path, code)
  flag.unlink()
  r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
  assert r.returncode == 1 and "skip (failed after 2 attempts)" in r.stdout
  st = _status(tmp_path)
  assert (st["status"], st["n_attempts"], st["n_interrupted"]) == ("interrupted", 2, 2)


# L52: outputs check reads a paths file (one folder per line, spaces kept) and records its own result.

def _output_with_time(parent, name):
  from eegharness import outputs as eo
  t = eo.ComputeTimer()
  d = parent / name
  d.mkdir(parents=True)
  (d / "provenance.json").write_text(json.dumps({"command": "x"}))
  eo.record_compute_time(d, t)
  return d


def test_l52_paths_file_keeps_spaces_and_a_whitespace_split_fails(tmp_path, capsys):
  from eegharness import outputs as eo
  good = _output_with_time(tmp_path / "run with spaces", "20261123T000000Z_abc1234")
  lst = tmp_path / "paths.txt"
  lst.write_text(f"{good}\n\n")
  assert eo.main(["check", "--paths-file", str(lst)]) == 0
  assert capsys.readouterr().out.splitlines()[-1] == "1 output folder(s), 0 problem(s)"
  assert eo.read_paths_file(lst) == [str(good)]
  # the project wrapper's reading (46f18c9: read_text().split()) gives two paths that do not exist
  assert eo.main(["check", *lst.read_text().split()]) == 1
  assert capsys.readouterr().out.splitlines()[-1] == "0 output folder(s), 0 problem(s)"


def test_l52_record_writes_output_list_exit_code_and_real_command(tmp_path, capsys):
  from eegharness import outputs as eo
  good = _output_with_time(tmp_path / "outs a", "20261123T000000Z_abc1234")
  bad = tmp_path / "outs b" / "20261123T000001Z_abc1234"
  bad.mkdir(parents=True)
  (bad / "provenance.json").write_text("{}")
  lst = tmp_path / "paths.txt"
  lst.write_text(f"{good}\n{bad}\n")
  rec = tmp_path / "outputs" / "outputs_check"
  assert eo.main(["check", "--paths-file", str(lst), "--record", str(rec), "--root", str(tmp_path)]) == 1
  folder = next(rec.iterdir())
  out = (folder / "check_output.txt").read_text().splitlines()
  assert out[-2:] == ["2 output folder(s), 1 problem(s)", "exit 1"] and out[0].startswith(f"{bad}: compute_time not recorded")
  assert (folder / "paths.txt").read_text() == lst.read_text()
  prov = json.loads((folder / "provenance.json").read_text())
  assert "eegharness.outputs check --paths-file" in json.dumps(prov["command"]) and prov["compute_time"]["wall_s"] >= 0


# L53 + L51: eegharness.numbers reads TSV, many files (glob), JSON fields, scales and compares across files;
# the orchestrator's derived numbers come from it, or are marked as hand counts.

def _derive(tmp_path, files, numbers):
  from eegharness import numbers as en
  for rel, text in files.items():
    (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / rel).write_text(text)
  recs, used = en.derive({"numbers": numbers}, tmp_path)
  return {r["key"]: r for r in recs}, used


def test_l53_tsv_rows(tmp_path):
  batches = "batch\tscope\ttemp_max\n" + "".join(f"{i:02d}\tB_loro\t{t}\n" for i, t in
                                                  enumerate([96, 93, 95, 94, 97, 92, 95], 1))
  r, used = _derive(tmp_path, {"outputs/stage2_logs/batches.tsv": batches}, [
    {"key": "n_hot", "op": "count", "rows": {"csv": "outputs/stage2_logs/batches.tsv", "where": {"temp_max": {">=": 95}}}},
    {"key": "t_max", "op": "max", "decimals": 0, "unit": "°C",
     "rows": {"csv": "outputs/stage2_logs/batches.tsv", "column": "temp_max"}}])
  assert r["n_hot"]["text"] == "4" and r["t_max"]["text"] == "97 °C"
  assert list(used) == ["outputs/stage2_logs/batches.tsv"]
  r, _ = _derive(tmp_path / "x", {"b.txt": batches}, [  # explicit delimiter on another extension
    {"key": "n", "op": "count", "rows": {"csv": "b.txt", "delimiter": "\t", "where": {"scope": "B_loro"}}}])
  assert r["n"]["value"] == 7


def test_l53_glob_over_many_files_and_a_first_file_only_variant_fails(tmp_path):
  files = {f"outputs/stage2/B/parts/S{i}_HI/classical/2026/gates.csv":
           "gate,passes\nspan,True\nwindow," + ("False" if i == 2 else "True") + "\n" for i in (1, 2, 3)}
  spec = [{"key": "n_rows", "op": "count", "rows": {"glob": "outputs/stage2/*/parts/*/classical/*/gates.csv"}},
          {"key": "n_fail", "op": "count",
           "rows": {"glob": "outputs/stage2/*/parts/*/classical/*/gates.csv", "where": {"passes": "False"}}}]
  r, used = _derive(tmp_path, files, spec)
  assert (r["n_rows"]["value"], r["n_fail"]["value"]) == (6, 1) and len(used) == 3
  assert r["n_rows"]["sources"][0]["n_files"] == 3
  first_only = sorted(files)[0]  # a variant that reads only the first file finds no failing gate
  r1, _ = _derive(tmp_path, {}, [{"key": "n_fail", "op": "count", "rows": {"csv": first_only, "where": {"passes": "False"}}}])
  assert r1["n_fail"]["value"] != r["n_fail"]["value"]
  from eegharness import numbers as en
  with pytest.raises(en.SpecError, match="matches no file"):
    en.derive({"numbers": [{"key": "n", "op": "count", "rows": {"glob": "outputs/none/*.csv"}}]}, tmp_path)


def test_l53_scale_seconds_to_hours_and_ratio(tmp_path):
  r, _ = _derive(tmp_path, {"t.csv": "scope,cpu_s\nB_loro,7200\n"}, [
    {"key": "cpu_s", "op": "value", "a": {"csv": "t.csv", "where": {"scope": "B_loro"}, "column": "cpu_s"}, "decimals": 0},
    {"key": "cpu_h", "op": "scale", "a": {"key": "cpu_s"}, "divisor": 3600, "decimals": 1, "unit": "h"},
    {"key": "vs_plan", "op": "ratio", "a": {"key": "cpu_h"}, "b": {"key": "cpu_s"}, "decimals": 6}])
  assert r["cpu_h"]["text"] == "2.0 h" and r["cpu_h"]["divisor"] == 3600
  r, _ = _derive(tmp_path / "f", {"t.csv": "scope,cpu_s\nB_loro,7200\n"}, [
    {"key": "h", "op": "scale", "a": {"csv": "t.csv", "where": {"scope": "B_loro"}, "column": "cpu_s"},
     "factor": 0.5, "decimals": 0}])
  assert r["h"]["value"] == 3600


def test_l53_all_equal_over_json_files(tmp_path):
  files = {f"outputs/{root}/parts/S1_HI/classical/2026/results.json": json.dumps({"n_epochs": 200, "n": {"units": 200}})
           for root in ("B_loro", "cue_loro", "emg_loro")}
  spec = [{"key": "same_epochs", "op": "all_equal", "rows": {"json": "outputs/*/parts/*/classical/*/results.json",
                                                             "field": "n_epochs"}},
          {"key": "units", "op": "value", "a": {"json": "outputs/B_loro/parts/S1_HI/classical/2026/results.json",
                                                "field": "n.units"}, "decimals": 0}]
  r, used = _derive(tmp_path, files, spec)
  assert r["same_epochs"]["value"] == 1 and r["same_epochs"]["text"] == "1" and r["units"]["text"] == "200"
  assert len(used) == 3
  files["outputs/cue_loro/parts/S1_HI/classical/2026/results.json"] = json.dumps({"n_epochs": 199})
  r, _ = _derive(tmp_path / "d", files, spec[:1])
  assert r["same_epochs"]["value"] == 0 and r["same_epochs"]["distinct_values"] == ["199", "200"]


def test_l51_orchestrator_numbers_from_the_tool_or_marked_as_hand_counts(tmp_path):
  assert ("A number the orchestrator derives from outputs for `log.md` or for Sebastian comes from "
          "`eegharness.numbers` or a committed tool. Otherwise it is sent marked `(hand count, not derived)` with "
          "the tool gap named, and it is never corrected by another hand count (L51).") in read("CLAUDE.md")
  # the count the orchestrator made by hand (imagined-speech-eeg: pinned batches >= 95 °C), now derivable
  rows = [("B_loro", "01", "no", 96)] + [("B_loro", f"{i:02d}", "yes", t) for i, t in
          zip(range(2, 15), [93, 94, 92, 95, 93, 94, 96, 95, 94, 97, 93, 95, 94])]
  tsv = "scope\tbatch\tpinned\ttemp_max\n" + "".join("\t".join(map(str, r)) + "\n" for r in rows)
  r, _ = _derive(tmp_path, {"outputs/stage2_logs/batches.tsv": tsv}, [
    {"key": "n_pinned_hot", "op": "count",
     "rows": {"csv": "outputs/stage2_logs/batches.tsv", "where": {"pinned": "yes", "temp_max": {">=": 95}}}},
    {"key": "n_pinned", "op": "count", "rows": {"csv": "outputs/stage2_logs/batches.tsv", "where": {"pinned": "yes"}}}])
  assert (r["n_pinned_hot"]["value"], r["n_pinned"]["value"]) == (5, 13)
