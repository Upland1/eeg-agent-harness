"""Known-answer tests for run_cost.py, on the real formats and job names of the ssvep-apply logs (G12):
confirmatory ``S01__cpu`` / ``S01__gpu`` / ``stats__collect`` with ISO times, development logs with times of
day and a midnight, names with spaces (``S019__classical (D-008 bank)``, ``try S09 eegnet M``,
``p20 S09 shallowconvnet``), the kit session's rerun log (``original shallow_convnet``), and the kernel's
suspend lines as ``journalctl -o short-iso`` prints them."""

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
