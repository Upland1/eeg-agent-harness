"""The worked example (examples/ssvep_synthetic/run_example.py) end to end, outputs pinned.

Known answer: with the defaults the example builds its project, freezes, runs the stage in child
processes, collects and derives the cited numbers; the numbers check passes (10 citations, 0
problems); per-participant balanced accuracies are exactly the golden ones (they are multiples of
1/80), the test row equals the golden one (floats to 1e-9), and every cited number's text is the
golden text. The development participant P00 never appears. Every output folder records its
compute time (L37). About 30 s on a laptop CPU.
"""

import csv
import json
import math
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT / "examples" / "ssvep_synthetic"))
sys.path.insert(0, str(KIT / "tools"))
import run_example  # noqa: E402
from eegharness.outputs import check_compute_time  # noqa: E402

GOLDEN = json.loads((KIT / "kit_tests" / "golden" / "worked_example_ssvep.json").read_text())


def test_worked_example_end_to_end_matches_golden(tmp_path, capsys):
  proj = tmp_path / "example"
  assert run_example.main([str(proj)]) == 0
  out = capsys.readouterr().out
  assert "check: 10 citation(s), 0 problem(s)" in out
  stats = next((proj / "outputs" / "stats").rglob("tests.csv")).parent
  part = sorted([r["participant"], r["method"], r["ba"]] for r in csv.DictReader(open(stats / "participants.csv")))
  assert part == GOLDEN["participants_ba"]
  assert "P00" not in {p for p, _, _ in part}
  row = next(csv.DictReader(open(stats / "tests.csv")))
  for k, v in GOLDEN["test"].items():
    try:
      assert math.isclose(float(row[k]), float(v), rel_tol=0, abs_tol=1e-9), k
    except ValueError:
      assert row[k] == v, k
  numbers = next((proj / "outputs" / "numbers").iterdir())
  assert {r["key"]: r["text"] for r in csv.DictReader(open(numbers / "numbers.csv"))} == GOLDEN["numbers_text"]
  stage_parts = [p.parent for p in (proj / "outputs" / "stage").rglob("results.json")]
  assert len(stage_parts) == 8
  for folder in [*stage_parts, stats, numbers]:
    assert check_compute_time(folder) == [], folder
