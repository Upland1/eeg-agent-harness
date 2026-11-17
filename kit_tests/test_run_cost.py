"""Known-answer tests for run_cost.py, on the real formats and job names of the ssvep-apply logs (G12):
confirmatory ``S01__cpu`` / ``S01__gpu`` / ``stats__collect`` with ISO times, development logs with times of
day and a midnight, names with spaces (``S019__classical (D-008 bank)``, ``try S09 eegnet M``,
``p20 S09 shallowconvnet``), the kit session's rerun log (``original shallow_convnet``), the kernel's
suspend lines as ``journalctl -o short-iso`` prints them, and the cold-pressor run's step H job table
(``h_jobs.tsv``: ``C2_stage``, ``C3_pooled_f4__gnn_bp_phase``, ``C3_sanity_classical_pooled``), driven in an
interactive session (no stream files)."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT))
import run_cost as rc  # noqa: E402

CONF = """2026-11-12T17:34:27Z BEGIN freeze a1130b3 root /x parts 35 sampler pid 1
2026-11-12T17:34:27Z START S01__cpu load 1.22 HEAD a1130b3
2026-11-12T21:09:40Z END S01__cpu rc 0 seconds 12913
2026-11-14T19:00:00Z END S01__gpu rc 0 seconds 600
2026-11-14T20:08:26Z END stats__collect rc 0 seconds 2
2026-11-14T20:08:28Z EXIT rc 0
"""
DEV = """23:26:18 START S040 load 2.0 HEAD 1b007ac
23:26:25 END S040 rc 143 seconds 7
00:11:34 END S040 (separate) rc 0 seconds 4160
23:30:18 END S019__classical (D-008 bank) rc 0 seconds 978
"""
SUSP = """2026-11-12T12:33:49-06:00 host kernel: PM: suspend entry (deep)
2026-11-12T15:09:34-06:00 host kernel: PM: suspend exit
"""


def test_device_rule_on_real_job_names():
  for job in ("S01__gpu", "S015__f2__eegnet", "try S09 eegnet M", "p20 S09 shallowconvnet", "original shallow_convnet",
              "smoke S015 f2__shallowconvnet"):
    assert rc.device_of(job) == "cuda", job
  for job in ("C3_pooled_f4__gnn_bp_phase", "C3_sanity_f4__gnn_bp_nodes", "C3_pooled_f2__eegnet"):
    assert rc.device_of(job) == "cuda", job
  for job in ("C1_primary", "C2_stage", "C3_pooled_classical_pooled", "C5_conn_group"):
    assert rc.device_of(job) == "cpu", job
  for job in ("S01__cpu", "stats__collect", "stats__seed_spread", "S09", "S040 (separate)", "S019__classical (D-008 bank)"):
    assert rc.device_of(job) == "cpu", job


def test_iso_log_and_suspend_overlap_known_answer(tmp_path):
  log = tmp_path / "run_log_20261112T173427Z.txt"
  log.write_text(CONF)
  sus = tmp_path / "suspends.txt"
  sus.write_text(SUSP)
  jobs = rc.parse_run_log(log)
  assert [(j["job"], j["device"], j["seconds"]) for j in jobs] == [("S01__cpu", "cpu", 12913), ("S01__gpu", "cuda", 600),
                                                                   ("stats__collect", "cpu", 2)]
  assert jobs[0]["start"] == datetime(2026, 11, 12, 17, 34, 27, tzinfo=timezone.utc)
  intervals = rc.parse_suspends(sus)
  assert intervals == [(datetime(2026, 11, 12, 18, 33, 49, tzinfo=timezone.utc), datetime(2026, 11, 12, 21, 9, 34, tzinfo=timezone.utc))]
  out = rc.compute([("confirmatory", log)], intervals)
  cpu = out["phases"][0]["by_device"]["cpu"]
  # S01__cpu 17:34:27-21:09:40 overlaps the suspend 18:33:49-21:09:34 by 9345 s; stats__collect not at all
  assert cpu["wall_s"] == 12915 and cpu["suspended_s"] == 9345.0 and cpu["active_s"] == 3570.0 and cpu["jobs"] == 2
  assert out["totals"]["cuda"] == {"jobs": 1, "wall_s": 600, "suspended_s": 0.0, "active_s": 600.0}


def test_time_of_day_log_rolls_over_midnight_and_counts_failed_jobs(tmp_path):
  log = tmp_path / "run_log_20261107T214240Z.txt"
  log.write_text(DEV)
  jobs = rc.parse_run_log(log)
  assert [j["end"].isoformat() for j in jobs] == ["2026-11-07T23:26:25+00:00", "2026-11-08T00:11:34+00:00",
                                                  "2026-11-08T23:30:18+00:00"]  # no wrap: same (later) day
  d = rc.compute([("dev", log)], [])["phases"][0]["by_device"]["cpu"]
  assert d["jobs"] == 3 and d["failed"] == 1 and d["wall_s"] == 7 + 4160 + 978
  two = tmp_path / "run_log_v040_20261109T225013Z.txt"  # two midnights: the day base must advance each time
  two.write_text("23:00:00 END a rc 0 seconds 1\n00:10:00 END b rc 0 seconds 1\n23:50:00 END c rc 0 seconds 1\n"
                 "00:20:00 END d rc 0 seconds 1\n")
  assert [j["end"].date().isoformat() for j in rc.parse_run_log(two)] == ["2026-11-09", "2026-11-10", "2026-11-10",
                                                                          "2026-11-11"]
  bad = tmp_path / "log_without_stamp.txt"
  bad.write_text(DEV)
  with pytest.raises(ValueError, match="UTC stamp"):
    rc.parse_run_log(bad)


def test_unclosed_suspend_is_refused(tmp_path):
  p = tmp_path / "s.txt"
  p.write_text(SUSP.splitlines()[0] + "\n")
  with pytest.raises(ValueError, match="no exit"):
    rc.parse_suspends(p)


def _stream(path, sid, usd, subtype="success"):
  lines = [{"type": "system", "session_id": sid}]
  if usd is not None:
    lines.append({"type": "result", "subtype": subtype, "session_id": sid, "total_cost_usd": usd})
  path.write_text("\n".join(json.dumps(x) for x in lines) + "\n")


def test_agent_cost_is_the_last_cumulative_value_per_session(tmp_path):
  import os
  files = []
  for i, usd in enumerate([None, 20.41, 38.12, 118.17]):  # a stopped first invocation, as ssvep-apply's apply_plan
    f = tmp_path / f"apply_{i}.stream.jsonl"
    _stream(f, "3395c6c0", usd)
    os.utime(f, (1000 + i, 1000 + i))
    files.append(str(f))
  a = rc.agent_cost(files)
  s = a["sessions"]["3395c6c0"]
  assert a["total_usd"] == 118.17 and s["usd"] == 118.17
  assert [i["added_usd"] for i in s["invocations"]] == [None, pytest.approx(20.41), pytest.approx(17.71),
                                                        pytest.approx(80.05)]
  _stream(tmp_path / "apply_9.stream.jsonl", "3395c6c0", 50.0)
  os.utime(tmp_path / "apply_9.stream.jsonl", (2000, 2000))
  with pytest.raises(ValueError, match="not cumulative"):
    rc.agent_cost([*files, str(tmp_path / "apply_9.stream.jsonl")])


def test_end_to_end_writes_a_versioned_folder_with_provenance(tmp_path, capsys):
  from eegharness.outputs import check_compute_time
  log = tmp_path / "run_log_20261112T173427Z.txt"
  log.write_text(CONF)
  _stream(tmp_path / "a.stream.jsonl", "s1", 3.5)
  (tmp_path / "transcripts").mkdir()
  assert rc.main(["--project", str(tmp_path), "--streams", str(tmp_path / "*.stream.jsonl"), "--run-log",
                  f"confirmatory={log}", "--transcripts", str(tmp_path / "transcripts"), "--out", str(tmp_path / "out")]) == 0
  out = next((tmp_path / "out").iterdir())
  rep = json.loads((out / "run_cost.json").read_text())
  assert rep["agent"]["total_usd"] == 3.5 and rep["compute"]["totals"]["cpu"]["wall_s"] == 12915
  assert check_compute_time(out) == []
  prov = json.loads((out / "provenance.json").read_text())
  assert len(prov["inputs"]) == 2
  assert "| confirmatory | cuda | 1 (0) | 0.17 h |" in (out / "run_cost.md").read_text()


TABLE = ("job\tstart_utc\tend_utc\twall_s\texit\tcommand\tlog\n"
         "C1_primary\t20261116T202653Z\t20261116T202752Z\t59\t0\t.venv/bin/python -m trialpair.primary --out a\tl1\n"
         "C2_stage\t20261116T202752Z\t20261117T035244Z\t26692\t0\tpython -m trialpair.stage --parts cpu\tl2\n"
         "C3_pooled_f4__gnn_bp_phase\t20261117T035947Z\t20261117T040221Z\t154\t0\tpython -m trialpair.pooled\tl3\n"
         "C3_sanity_classical_pooled\t20261117T051332Z\t20261117T051429Z\t57\t1\tpython -m trialpair.pooled\tl4\n")


def test_job_table_known_answer(tmp_path):
  t = tmp_path / "h_jobs.tsv"
  t.write_text(TABLE)
  jobs = rc.parse_run_log(t)
  assert [(j["job"], j["device"], j["seconds"], j["rc"]) for j in jobs] == [
    ("C1_primary", "cpu", 59, 0), ("C2_stage", "cpu", 26692, 0), ("C3_pooled_f4__gnn_bp_phase", "cuda", 154, 0),
    ("C3_sanity_classical_pooled", "cpu", 57, 1)]
  assert jobs[1]["start"] == datetime(2026, 11, 16, 20, 27, 52, tzinfo=timezone.utc)
  assert jobs[1]["end"] == datetime(2026, 11, 17, 3, 52, 44, tzinfo=timezone.utc)
  # a suspend inside C2_stage, 22:00-22:10 UTC, is subtracted from it alone
  sus = [(datetime(2026, 11, 16, 22, 0, tzinfo=timezone.utc), datetime(2026, 11, 16, 22, 10, tzinfo=timezone.utc))]
  out = rc.compute([("step H", t)], sus)["phases"][0]["by_device"]
  assert out["cpu"] == {"jobs": 3, "failed": 1, "wall_s": 59 + 26692 + 57, "suspended_s": 600.0,
                        "active_s": 59 + 26692 + 57 - 600.0}
  assert out["cuda"]["wall_s"] == 154 and out["cuda"]["jobs"] == 1
  bad = tmp_path / "b.tsv"
  bad.write_text("job\tstart_utc\tend_utc\n")
  with pytest.raises(ValueError, match="wall_s"):
    rc.parse_run_log(bad)


def _transcript(path, msgs):
  rows = [{"type": "user", "timestamp": "2026-11-16T10:00:00Z", "message": {"content": "go"}}]
  for i, (t, tok) in enumerate(msgs):
    rows.append({"type": "assistant", "timestamp": t, "message": {"id": f"m{i}", "model": "x",
                 "usage": {"input_tokens": 1, "output_tokens": tok}}})
  path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def test_without_streams_no_usd_and_tokens_per_agent(tmp_path):
  log = tmp_path / "h_jobs.tsv"
  log.write_text(TABLE)
  tr = tmp_path / "transcripts"
  sub = tr / "sess1" / "subagents"
  sub.mkdir(parents=True)
  _transcript(tr / "sess1.jsonl", [("2026-11-16T11:00:00Z", 100)])  # main: 1 response, 101 tokens, 3600 s
  for i, (agent, tok) in enumerate([("methods-auditor", 10), ("methods-auditor", 20), ("pipeline-engineer", 5)]):
    _transcript(sub / f"agent-a{i}.jsonl", [("2026-11-16T10:30:00Z", tok), ("2026-11-16T10:30:00Z", tok)])
    (sub / f"agent-a{i}.meta.json").write_text(json.dumps({"agentType": agent}))
  assert rc.main(["--project", str(tmp_path), "--run-log", f"step H={log}", "--transcripts", str(tr),
                  "--out", str(tmp_path / "out")]) == 0
  out = next((tmp_path / "out").iterdir())
  rep = json.loads((out / "run_cost.json").read_text())
  assert rep["agent"] is None
  assert rep["tokens_by_agent"] == {
    "main": {"calls": 1, "api_responses": 1, "total_tokens": 101, "output_tokens": 100, "wall_s": 3600.0},
    "methods-auditor": {"calls": 2, "api_responses": 4, "total_tokens": 64, "output_tokens": 60, "wall_s": 3600.0},
    "pipeline-engineer": {"calls": 1, "api_responses": 2, "total_tokens": 12, "output_tokens": 10, "wall_s": 1800.0}}
  md = (out / "run_cost.md").read_text()
  assert "USD: not available" in md and "| methods-auditor | 2 | 4 | 64 | 60 | 1.00 h |" in md
  assert "| step H | cuda | 1 (0) | 0.04 h |" in md
  assert len(json.loads((out / "provenance.json").read_text())["inputs"]) == 1
