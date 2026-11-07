"""Known-answer tests for eegpipe.paired, moved from the P300 project (tests @ d833264):
``tests/test_stage2.py`` (statistics tests) and ``tests/test_stage2_review.py`` (the independent
hand-derived review tests). Statistics settings = the erp profile (the P300 Stage-2 values).
Every known answer is derived in the docstring, as in the source tests."""

import copy
import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pytest
from scipy import stats

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
from eegpipe import paired as pr  # noqa: E402

PROFILE = json.loads((TOOLS / "eegpipe" / "profiles" / "erp.json").read_text())


def SC():
  return copy.deepcopy(PROFILE["statistics"])


PRIMS = SC()["holm_family"]
D12 = np.array([0.031, 0.012, -0.004, 0.027, 0.045, -0.019, 0.008, 0.022, 0.015, -0.007, 0.036, 0.051])


def exact_two_sided_p(d):
  d = np.asarray(d, float)
  ranks = stats.rankdata(np.abs(d))
  t = ranks[d > 0].sum()
  ts = np.array([sum(r for r, s in zip(ranks, signs) if s) for signs in itertools.product((0, 1), repeat=d.size)])
  return min(1.0, 2 * min(np.mean(ts <= t), np.mean(ts >= t)))


def test_profile_holds_the_p300_stage2_statistics():
  sc = SC()
  assert sc["alpha"] == 0.05 and sc["min_n"] == 12 and sc["holm_missing_p"] == 1.0 and len(PRIMS) == 4
  assert sc["wilcoxon_exact"] == {"zero_method": "wilcox", "method": "exact"}
  assert sc["bootstrap"]["seed"] == 20261110 and sc["bootstrap"]["n_resamples"] == 10000


def test_exact_wilcoxon_p_equals_full_enumeration_and_is_not_the_approximation():
  r = pr.paired_test(D12, SC())
  ref = exact_two_sided_p(D12)
  assert r["test_path"].startswith("exact") and abs(r["p"] - ref) < 1e-12
  assert abs(stats.wilcoxon(D12, method="approx").pvalue - ref) > 1e-4
  assert r["n"] == 12 and r["n_zero_differences"] == 0 and not r["tied_abs_differences"]
  assert r["sign_test_p"] == pytest.approx(stats.binomtest(9, 12, 0.5).pvalue, abs=1e-15)
  assert r["wilcoxon_direction"] == 1 and r["sign_test_direction"] == 1 and r["directions_agree"]


def test_exact_wilcoxon_p_by_hand_enumeration():
  """Ranks {1..5}: R- = 3 -> 5 of 32 subsets -> p 0.3125; R- = 4 -> 7 -> 0.4375; all positive ->
  0.0625; sign test 4/1 -> 0.375, 5/0 -> 0.0625."""
  r = pr.paired_test(np.array([.1, .2, -.3, .4, .5]), SC())
  assert r["test_path"].startswith("exact") and r["wilcoxon_statistic"] == 3.0
  assert r["p"] == pytest.approx(0.3125, abs=1e-15) and r["sign_test_p"] == pytest.approx(0.375, abs=1e-15)
  r = pr.paired_test(np.array([.1, .2, .3, -.4, .5]), SC())
  assert r["p"] == pytest.approx(0.4375, abs=1e-15)
  r = pr.paired_test(np.array([.1, .2, .3, .4, .5]), SC())
  assert r["p"] == pytest.approx(0.0625, abs=1e-15) and r["sign_test_p"] == pytest.approx(0.0625, abs=1e-15)


def test_pratt_normal_approximation_with_two_zeros_by_hand():
  """N = 12 with 2 zeros: mean 37.5, var 161.25, no correction -> p = 0.003145774928543661."""
  d = np.array([0, 0] + [0.01 * k for k in range(1, 11)])
  r = pr.paired_test(d, SC())
  assert r["n"] == 12 and r["n_zero_differences"] == 2
  assert "zero_method=pratt" in r["test_path"] and "method=approx" in r["test_path"]
  assert r["p"] == pytest.approx(0.003145774928543661, abs=1e-9)
  assert r["p"] != pytest.approx(2 / 1024, abs=1e-4)


def test_zeros_and_ties_take_the_pratt_approx_path():
  d = np.array([0.0, 0.1 + 0.2, 0.3, -0.05, 0.12, 0.2, 0.07, 0.15, -0.02, 0.09, 0.11, 0.25, 0.04])
  r = pr.paired_test(d, SC())
  assert r["n"] == 13 and r["n_zero_differences"] == 1 and r["tied_abs_differences"]
  ref = stats.wilcoxon(np.round(d, 12), zero_method="pratt", method="approx", correction=False).pvalue
  assert r["p"] == pytest.approx(ref, abs=1e-15)
  d2 = d.copy()
  d2[0] = 0.013
  assert "pratt" in pr.paired_test(d2, SC())["test_path"]


def test_hodges_lehmann_and_bootstrap_interval():
  d = np.array([0.01, 0.02, 0.03, 0.10])
  assert pr.hodges_lehmann(d) == pytest.approx(0.0275, abs=1e-15)
  assert pr.hodges_lehmann([-.02, .01, .03]) == pytest.approx(0.0075, abs=1e-15)
  assert pr.hodges_lehmann([1, 2]) == pytest.approx(1.5, abs=1e-15)
  rng = np.random.default_rng(20261110)
  hl = []
  for _ in range(10000):
    x = d[rng.integers(0, 4, size=4)]
    hl.append(np.median([(x[i] + x[j]) / 2 for i in range(4) for j in range(i, 4)]))
  lo, hi = np.quantile(hl, [0.025, 0.975], method="linear")
  assert pr.bootstrap_hl(d, 10000, 20261110, 0.95) == pytest.approx((lo, hi), abs=1e-15)
  lo, hi = pr.bootstrap_hl(np.full(5, .02), 200, 1, .95)
  assert lo == pytest.approx(.02, abs=1e-15) and hi == pytest.approx(.02, abs=1e-15)


def test_holm_known_values_and_boundaries():
  assert pr.holm([0.01, 0.04, 0.03, 0.005]) == pytest.approx([0.03, 0.06, 0.06, 0.02], abs=1e-15)
  cases = [([1, 1, 1, 1], [1, 1, 1, 1]), ([.001, 1, 1, 1], [.004, 1, 1, 1]), ([.012, 1, 1, .012], [.048, 1, 1, .048]),
           ([1, .01, 1, 1], [1, .04, 1, 1]), ([.0125, 1, 1, 1], [.05, 1, 1, 1]), ([.3, 1, 1, 1], [1, 1, 1, 1])]
  for p, want in cases:
    assert pr.holm(p) == pytest.approx(want, abs=1e-15), p
  assert pr.holm([.0125, 1, 1, 1])[0] == 0.05


def test_direction_disagreement_is_not_robust():
  d = np.array([0.10, 0.11, 0.12, 0.13] + [-0.001 * k for k in range(1, 10)])
  r = pr.paired_test(d, SC())
  assert r["wilcoxon_direction"] == 1 and r["sign_test_direction"] == -1 and not r["directions_agree"]
  assert pr.verdict({**r, "p_holm": 0.01, "hodges_lehmann": 0.002}, SC()).startswith("not robust")


def _row(n=12, p_holm=0.01, hl=0.01, agree=True):
  return {"n": n, "p_holm": p_holm, "hodges_lehmann": hl, "directions_agree": agree}


def test_success_rule_boundaries():
  v = lambda **k: pr.verdict(_row(**k), SC())  # noqa: E731
  assert v(p_holm=0.05) == "no evidence of a difference"
  assert v(p_holm=0.0499999999) == "beats the baseline"
  assert v(hl=0.0) == "no evidence of a difference" and v(hl=-1e-9) == "worse than the baseline"
  assert v(n=12).startswith("beats") and v(n=11, p_holm=1e-6).startswith("descriptive only")
  assert v(agree=False).startswith("not robust") and v(p_holm=0.05, agree=False) == "no evidence of a difference"
  assert pr.verdict(_row(), SC(), comparator_label="FBCCA") == "beats the FBCCA"


def _scores_from(deltas, base=0.6):
  n = len(next(iter(deltas.values())))
  out = {f"S{i + 1}": {"baseline": base + 0.01 * i, **{m: base + 0.01 * i + deltas[m][i] for m in PRIMS}} for i in range(n)}
  return out, {p: "confirmatory" for p in out}


def test_n_12_counts_zero_differences_and_pratt_is_used():
  d = [0.0, 0.0] + [0.01 * k for k in range(1, 11)]
  sc, roles = _scores_from({m: d for m in PRIMS})
  rows, _ = pr.analyse(sc, roles, "baseline", SC())
  for r in rows:
    assert r["n"] == 12 and r["n_zero_differences"] == 2 and "pratt" in r["test_path"]
    assert r["p_holm"] == pytest.approx(4 * 0.003145774928543661, abs=1e-8) and r["verdict"] == "beats the baseline"
  sc11 = {p: v for p, v in sc.items() if p != "S12"}
  rows, _ = pr.analyse(sc11, {p: roles[p] for p in sc11}, "baseline", SC())
  assert all(r["n"] == 11 and r["verdict"].startswith("descriptive only") for r in rows)


def test_missing_p_enters_holm_as_one_keeping_the_family_at_four():
  pos = [0.01 * k for k in range(1, 13)]
  zero = [0.0] * 12
  sc, roles = _scores_from({PRIMS[0]: pos, PRIMS[1]: zero, PRIMS[2]: zero, PRIMS[3]: zero})
  rows, _ = pr.analyse(sc, roles, "baseline", SC())
  assert rows[0]["p"] == pytest.approx(2 / 4096, abs=1e-15)
  assert rows[0]["p_holm"] == pytest.approx(0.001953125, abs=1e-15) and rows[0]["holm_m"] == 4
  for r in rows[1:]:
    assert r["p"] is None and r["p_entering_holm"] == 1.0 and r["p_holm"] == 1.0
  sc, roles = _scores_from({PRIMS[0]: pos, PRIMS[1]: pos, PRIMS[2]: pos, PRIMS[3]: zero})
  rows, _ = pr.analyse(sc, roles, "baseline", SC())
  assert [r["p_holm"] for r in rows[:3]] == pytest.approx([8 / 4096] * 3, abs=1e-15)


def test_separately_reported_participant_never_in_a_test_even_with_extreme_scores():
  pos = [0.01 * k for k in range(1, 13)]
  sc, roles = _scores_from({m: pos for m in PRIMS})
  base_rows, _ = pr.analyse(sc, roles, "baseline", SC())
  for ext in (0.4, -0.4):
    sc2 = {**sc, "S18": {"baseline": 0.5, **{m: 0.5 + ext for m in PRIMS}}}
    rows, drows = pr.analyse(sc2, {**roles, "S18": "reported_separately"}, "baseline", SC())
    assert rows == base_rows
    s18 = [r for r in drows if r["participant"] == "S18"]
    assert len(s18) == 4 and not any(r["in_test"] for r in s18)
  sc11 = {p: v for p, v in sc.items() if p != "S12"}
  sc11["S18"] = {"baseline": 0.5, **{m: 0.9 for m in PRIMS}}
  rows, _ = pr.analyse(sc11, {**{p: "confirmatory" for p in sc11}, "S18": "reported_separately"}, "baseline", SC())
  assert all(r["n"] == 11 and r["verdict"].startswith("descriptive only") for r in rows)


def test_missing_scores_count_as_missing_not_as_zero():
  pos = [0.01 * k for k in range(1, 13)]
  sc, roles = _scores_from({m: pos for m in PRIMS})
  sc["S3"][PRIMS[1]] = None
  rows, _ = pr.analyse(sc, roles, "baseline", SC())
  assert rows[1]["n"] == 11 and rows[1]["n_missing_confirmatory"] == 1 and "S3" not in rows[1]["participants"].split()
  assert pr.natural_key("S2") < pr.natural_key("S10")
