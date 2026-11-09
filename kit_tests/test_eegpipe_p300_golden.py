"""Regression against the FROZEN P300 pipeline (spec v0.4 §4, decision D3): with the P300 settings, eegpipe
reproduces the P300 code's outputs bit for bit on a fixed synthetic P300 study.

The golden files ``kit_tests/golden/p300_<commit>.{npz,json}`` were written once by
``kit_tests/golden/make_p300_goldens.py`` from a read-only export of the P300 repository at the frozen commit
(the study, its inputs and every compared output are described there). Each test below is one module of the port;
"bit for bit" means ``np.array_equal`` on float64 arrays and ``==`` on numbers, never a tolerance."""

import copy
import json
import sys
from pathlib import Path

import numpy as np
import pytest

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
from eegpipe import classical as cl  # noqa: E402
from eegpipe import dataset as ds  # noqa: E402
from eegpipe import epochs as ep  # noqa: E402
from eegpipe import evaluate as evl  # noqa: E402
from eegpipe import folds as fo  # noqa: E402
from eegpipe import graphstats as gs  # noqa: E402
from eegpipe import network_input as ni  # noqa: E402
from eegpipe import paired as pr  # noqa: E402
from eegpipe.testing import synth  # noqa: E402

COMMIT = "d833264"
GOLD = Path(__file__).resolve().parent / "golden"
PROFILE = json.loads((TOOLS / "eegpipe" / "profiles" / "erp.json").read_text())
FS = 256.0
BIN = ["nontarget", "target"]
EVENT_KEYS = ("onset", "unit", "label", "unit_start", "unit_end", "code", "unit_target")


@pytest.fixture(scope="module", autouse=True)
def one_thread():
  """The goldens were made with one BLAS/OpenMP thread and one torch thread (see the generator): the summation
  order of the connectivity matrix products and of torch's CPU reductions depends on the thread count."""
  from threadpoolctl import threadpool_limits
  try:
    import torch
    saved = torch.get_num_threads()
    torch.set_num_threads(1)
  except ImportError:
    torch = None
  with threadpool_limits(1):
    yield
  if torch is not None:
    torch.set_num_threads(saved)


@pytest.fixture(scope="module")
def gold():
  z = np.load(GOLD / f"p300_{COMMIT}.npz")
  arrays = {k: z[k] for k in z.files}
  meta = json.loads((GOLD / f"p300_{COMMIT}.json").read_text())
  assert meta["p300_commit"] == COMMIT
  return arrays, meta


@pytest.fixture(scope="module")
def kit(gold):
  """eegpipe on the golden inputs: per-file epochs, the session, folds and splits."""
  G, meta = gold
  s = synth.erp_settings(FS)
  files = []
  for f in range(3):
    evs = {k: G[f"in{f}__{k}"] for k in EVENT_KEYS}
    files.append((G[f"in{f}__data"], evs, ep.prepare_file(G[f"in{f}__data"], FS, evs, s)))
  sess = ds.assemble([r for _, _, r in files])
  ufold = fo.assign_unit_folds(sess["unit_file"], 8, 20261107)
  splits = fo.fold_splits(sess["unit_uid"], ufold, 8)
  cfg = {"f1": copy.deepcopy(PROFILE["f1"]), "baseline": copy.deepcopy(PROFILE["baseline"])}
  return {"files": files, "sess": sess, "ufold": ufold, "splits": splits, "cfg": cfg}


GATE_MAP = {"gate_i_4_14__span_samples": "span__bandpass__span_samples",
            "gate_i_4_14__min_gap_samples": "span__bandpass__min_gap_samples",
            "gate_i_4_14__passes": "span__bandpass__passes",
            "gate_i_4_14__gap_exceeds_2x_span": "span__bandpass__gap_exceeds_2x_span",
            "gate_i_1_40_resample__span_samples": "span__network_input__span_samples",
            "gate_i_1_40_resample__min_gap_samples": "span__network_input__min_gap_samples",
            "gate_i_1_40_resample__passes": "span__network_input__passes",
            "gate_ii_window__min_gap_samples": "window__connectivity__min_gap_samples",
            "gate_ii_window__passes": "window__connectivity__passes",
            "filtering_4_14": "filtering",
            "n_used_epochs_near_fallback_segment_edge": "n_used_epochs_near_fallback_segment_edge",
            "n_used_epochs_near_fallback_segment_edge_half_reach": "n_used_epochs_near_fallback_segment_edge_half_reach"}


# ------------------------------------------------------------------ filtering, gates, epochs
@pytest.mark.parametrize("f", [0, 1, 2])
def test_epochs_counts_and_gates_equal_p300(gold, kit, f):
  """Per file (1 = the block-wise fallback file): retained epochs X, labels, codes, units and onsets bit for
  bit; every count (per class and per rejection criterion) and every gate value equal."""
  G, meta = gold
  _, _, r = kit["files"][f]
  for k, gk in (("X", "X"), ("y", "y"), ("code", "code"), ("unit", "block"), ("onset", "onset")):
    assert np.array_equal(r[k], G[f"ep{f}__{gk}"]), k
  assert r["X"].dtype == G[f"ep{f}__X"].dtype == np.float64
  c, pc = meta[f"ep{f}__counts"], r["counts"]["per_class"]
  for cls, name in enumerate(BIN):
    for what in ("labelled", "out_of_bounds", "rejected", "used", "rejected_by_ptp", "rejected_by_sd",
                 "rejected_by_power_ratio"):
      p300_key = f"n_{name}_{what}" if not what.startswith("rejected_by") else f"n_{name}_{what}"
      assert pc[cls][what] == c[p300_key], (name, what)
  assert r["counts"]["n_samples"] == c["n_samples"] and r["counts"]["n_units"] == c["n_blocks"]
  assert r["counts"]["n_used_epochs_within_filter_span_of_file_edge"] == c["n_used_epochs_within_filter_span_of_file_edge"]
  for pk, kk in GATE_MAP.items():
    want = meta[f"ep{f}__gates"][pk]
    got = r["gates"][kk]
    assert (got == "unitwise_fallback" and want == "blockwise_fallback") or got == want, (pk, got, want)


def test_the_fallback_file_is_the_one_p300_filtered_block_by_block(gold, kit):
  G, meta = gold
  assert [meta[f"ep{f}__gates"]["filtering_4_14"] for f in range(3)] == ["continuous", "blockwise_fallback", "continuous"]
  assert kit["files"][1][2]["gates"]["filtering"] != "continuous"


# ------------------------------------------------------------------ network input
@pytest.mark.parametrize("f", [0, 1, 2])
def test_network_input_equals_p300(gold, kit, f):
  """The 1-40 Hz, 128 Hz network epochs bit for bit; file 1 (rests of 250 samples) is refused by both, because
  its unit-wise segments are shorter than padlen 2535."""
  G, meta = gold
  data, evs, r = kit["files"][f]
  if "error" in meta[f"nn{f}"]:
    with pytest.raises(ValueError, match="padlen"):
      ni.network_epochs(data, FS, evs, r, PROFILE["network_input"], 1.0)
    return
  out = ni.network_epochs(data, FS, evs, r, PROFILE["network_input"], 1.0)
  assert np.array_equal(out["X"], G[f"nn{f}__X"])
  assert out["filtering"] == meta[f"nn{f}"]["filtering"] and int(out["n_edge"]) == meta[f"nn{f}"]["n_edge"]
  for k, v in meta[f"nn{f}"]["gate"].items():
    assert out["gate"][k] == v, k


# ------------------------------------------------------------------ dataset, folds
def test_session_and_folds_equal_p300(gold, kit):
  G, _ = gold
  sess = kit["sess"]
  assert np.array_equal(sess["unit_uid"], G["sess__block_uid"]) and np.array_equal(sess["file_idx"], G["sess__file_idx"])
  assert np.array_equal(kit["ufold"], G["sess__block_fold"])


# ------------------------------------------------------------------ classical
def test_every_classical_method_predicts_as_p300(gold, kit):
  """Out-of-fold predictions of the baseline and all 20 F1 methods equal P300's; the two QDA methods fail with
  the same error type in both (rank-deficient class covariance)."""
  G, meta = gold
  sess, splits, cfg = kit["sess"], kit["splits"], kit["cfg"]
  ids = ["baseline"] + cl.method_ids(cfg)
  assert ids == meta["methods"]
  for mid in ids:
    if mid in meta["method_errors"]:
      with pytest.raises(Exception) as e:
        evl.cv_predict(sess["X"], sess["y"], splits, lambda m=mid: cl.make_method(m, cfg), BIN)
      assert meta["method_errors"][mid].startswith(type(e.value).__name__), (mid, e.value)
      continue
    pred, _, _ = evl.cv_predict(sess["X"], sess["y"], splits, lambda m=mid: cl.make_method(m, cfg), BIN)
    assert np.array_equal(pred, G[f"cl__{mid}__pred"]), mid


# ------------------------------------------------------------------ evaluate: draws, null, per-file tests
@pytest.fixture(scope="module")
def perm(gold, kit):
  G, meta = gold
  sess = dict(kit["sess"])
  vals = evl.unit_values(sess, "unit_target", [kit["files"][f][1]["unit_target"] for f in range(3)])
  codes = [evl.unit_code_sets_of_events(kit["files"][f][1]) for f in range(3)]
  shuffles = evl.draw_shuffles(vals, meta["n_perm"], 20261105, code_sets=codes)
  null = evl.permutation_null(sess, kit["splits"], meta["perm__methods"], cl.make_method, kit["cfg"], "unit_target",
                              BIN, shuffles, 1, 8)
  return vals, shuffles, null


def test_permutation_draws_equal_p300(gold, perm):
  G, meta = gold
  vals, shuffles, _ = perm
  for f in range(3):
    assert np.array_equal(shuffles[f], G[f"perm__shuffle{f}"]), f
  assert [evl.n_distinct_shuffles(v) for v in vals] == meta["perm__n_distinct"]


def test_permutation_null_and_per_file_tests_equal_p300(gold, kit, perm):
  """The null BAs (per file and pooled) bit for bit; the observed per-file BAs and every per-file test value
  (Monte Carlo p, floors, flag, null mean and critical value, Holm p, decision) equal."""
  G, meta = gold
  vals, _, null = perm
  assert np.array_equal(null, G["perm__null"])
  nd = [evl.n_distinct_shuffles(v) for v in vals]
  for mi, mid in enumerate(meta["perm__methods"]):
    obs, _ = evl.per_stratum_ba(kit["sess"], kit["sess"]["y"], kit["splits"], lambda m=mid: cl.make_method(m, kit["cfg"]),
                                BIN)
    assert np.array_equal(obs, G[f"perm__obs__{mid}"]), mid
    rows = evl.per_stratum_tests(obs, null[mi, :, :3], nd, 0.05, 95.0, "linear")
    for got, want in zip(rows, meta["perm__tests"][mid]):
      for k, v in want.items():
        assert got[k] == v, (mid, k, got[k], v)


# ------------------------------------------------------------------ graphstats
def test_bh_fdr_and_nbs_equal_p300(gold):
  G, meta = gold
  assert np.array_equal(np.asarray(gs.benjamini_hochberg(G["gs__p"].ravel(), 0.05)), G["gs__bh"])
  for d, want in meta["gs__nbs"].items():
    got = gs.nbs(G["gs__t_obs"], G["gs__t_null"], 3.0, 8, d)
    assert got["components"] == want["components"] and got["null_max"].tolist() == want["null_max"], d


# ------------------------------------------------------------------ paired (Stage-2 statistics)
def test_paired_statistics_equal_p300(gold):
  """Paired Wilcoxon / sign test / Hodges-Lehmann with bootstrap interval / Holm / verdicts on a fixed score
  table (14 participants, one reported separately, one missing network score): every field P300 wrote equals."""
  G, meta = gold
  rows, drows = pr.analyse(meta["paired__scores"], meta["paired__roles"], PROFILE["comparator"], PROFILE["statistics"])
  want_rows, want_drows = meta["paired__result"]
  assert len(rows) == len(want_rows) and len(drows) == len(want_drows)
  for got, want in zip(rows, want_rows):
    for k, v in want.items():
      assert k in got, k
      assert got[k] == v or (isinstance(v, float) and np.isnan(v) and np.isnan(got[k])), (want["method"], k, got[k], v)
  renamed = {"baseline_ba": "comparator_score", "method_ba": "method_score"}   # generic names (D5)
  for got, want in zip(drows, want_drows):
    assert {k: got[renamed.get(k, k)] for k in want} == want


# ------------------------------------------------------------------ phase (F3 classification), connectivity (F3 a)
def _kit_full_cfg():
  return {"fs_hz": FS, **{k: copy.deepcopy(PROFILE[k]) for k in ("f1", "baseline", "f3", "f4", "networks")}}


def test_phase_epochs_and_f3_classifiers_equal_p300(gold, kit):
  """Phase epochs ([-0.2, 1.0] s raw windows) bit for bit; out-of-fold predictions of every F3 phase-feature
  variant (label-free template fitted on the training fold) equal P300's."""
  from eegpipe import phase as ph
  G, meta = gold
  cfg = _kit_full_cfg()
  Xp = np.concatenate([ph.phase_epochs(d, FS, r["onset"], cfg["f3"]) for d, _, r in kit["files"]])
  assert np.array_equal(Xp, G["f3__X_phase"])
  assert ph.f3_method_ids(cfg) == meta["f3__methods"] and not meta["f3__errors"]
  for mid in meta["f3__methods"]:
    pred, _, _ = evl.cv_predict(Xp, kit["sess"]["y"], kit["splits"], lambda m=mid: ph.make_f3(m, cfg), BIN)
    assert np.array_equal(pred, G[f"f3__{mid}__pred"]), mid


def test_condition_level_connectivity_equals_p300(gold, kit):
  """Condition-level debiased wPLI (target - non-target, class mean subtracted per file, subsampled
  non-targets), 5 shuffles of the block targets: draws, observed statistics and both nulls bit for bit; every
  edge row (p, FDR decision, PLV) and NBS row equal."""
  from eegpipe import connectivity as cn
  G, meta = gold
  cfg = _kit_full_cfg()
  sess = kit["sess"]
  ccfg = cfg["f3"]["condition_level"]
  vals = [kit["files"][f][1]["unit_target"] for f in range(3)]
  codes = [evl.unit_code_sets_of_events(kit["files"][f][1]) for f in range(3)]
  sh = evl.draw_shuffles(vals, meta["f3a__n_perm"], ccfg["permutation_seed"], code_sets=codes)
  for f in range(3):
    assert np.array_equal(sh[f], G[f"f3a__shuffle{f}"])
  from eegpipe import phase as ph
  # the kit's own phase epochs (a strided view, as in P300), not the stored contiguous copy: the FFT rounds the
  # two memory layouts differently in the last bit
  Xp = np.concatenate([ph.phase_epochs(d, FS, r["onset"], cfg["f3"]) for d, _, r in kit["files"]])
  res = cn.condition_level(Xp, sess["y"], sess["unit_uid"],
                           lambda p: evl.labels_for(sess, [s[p] for s in sh], "unit_target"), meta["f3a__n_perm"],
                           FS, cfg, sess["file_idx"])
  assert np.array_equal(res["null_diff"], G["f3a__null_diff"]) and np.array_equal(res["null_t"], G["f3a__null_t"])
  for k, kk in (("diff", "diff"), ("dw_target", "dw_a"), ("dw_nontarget", "dw_b"), ("t", "t")):   # generic names (D5)
    assert np.array_equal(res["observed"][kk], G[f"f3a__obs__{k}"]), k
  renamed = {"dwpli_target": "dwpli_a", "dwpli_nontarget_subsample_mean": "dwpli_b_subsample_mean",
             "plv_target_comparison_only": "plv_a_comparison_only",
             "plv_nontarget_comparison_only": "plv_b_comparison_only", "t_blocks": "t_units"}
  assert len(res["edges"]) == len(meta["f3a__edges"])
  for got, want in zip(res["edges"], meta["f3a__edges"]):
    for k, v in want.items():
      gk = renamed.get(k, k) if renamed.get(k, k) in got else k
      assert got[gk] == v, (k, got.get(gk), v)
  assert len(res["nbs"]) == len(meta["f3a__nbs"])
  for got, want in zip(res["nbs"], meta["f3a__nbs"]):
    for k in ("band", "component", "size_edges", "p", "significant", "pairs", "threshold"):
      assert got[k] == want[k], k


# ------------------------------------------------------------------ networks (F2) and graph (F4), torch on CPU
def _short_ncfg():
  ncfg = copy.deepcopy(PROFILE["networks"])
  ncfg["trainer"]["max_epochs"] = 3
  return ncfg


@pytest.mark.parametrize("name", ["eegnet", "shallowconvnet"])
def test_networks_equal_p300_on_cpu(gold, kit, name):
  """EEGNet and ShallowConvNet, seed 20261107, 3 epochs, deterministic, CPU, on files 0 and 2 (4 folds):
  out-of-fold predictions and target probabilities bit for bit; per fold best epoch, epochs run, best
  validation loss and parameter count equal."""
  pytest.importorskip("torch")
  from eegpipe import networks as nw
  G, meta = gold
  ncfg = _short_ncfg()
  nw.set_determinism(ncfg["deterministic"])
  s02 = ds.assemble([kit["files"][0][2], kit["files"][2][2]])
  sp = fo.fold_splits(s02["unit_uid"], fo.assign_unit_folds(s02["unit_file"], 4, 20261107), 4)
  X = np.concatenate([G["nn0__X"], G["nn2__X"]])
  pred, proba, rows, _ = nw.cv_network(X, s02["y"], s02["unit_uid"], sp, ncfg["models"][name], 20261107, ncfg, "cpu",
                                       BIN)
  assert np.array_equal(pred, G[f"f2__{name}__pred"])
  assert np.array_equal(np.asarray(proba)[:, 1], G[f"f2__{name}__p_target"])
  for got, want in zip(rows, meta[f"f2__{name}__folds"]):
    for k, v in want.items():
      assert got[k] == v, (k, got[k], v)


def test_gnn_equals_p300_on_cpu(gold, kit):
  """The F4 primary (edge-gated GNN on phase edges), seed 20261107, 3 epochs, CPU, 8 folds of the whole session:
  predictions, target probabilities and fold rows equal P300's."""
  pytest.importorskip("torch")
  from eegpipe import graph as gr
  from eegpipe import networks as nw
  G, meta = gold
  cfg = _kit_full_cfg()
  ncfg = _short_ncfg()
  nw.set_determinism(ncfg["deterministic"])
  from eegpipe import phase as ph
  name = meta["f4__model"]
  Xp = np.concatenate([ph.phase_epochs(d, FS, r["onset"], cfg["f3"]) for d, _, r in kit["files"]])
  pred, proba, rows, _ = gr.cv_gnn(kit["sess"]["X"], Xp, kit["sess"]["y"], kit["sess"]["unit_uid"],
                                   kit["splits"], cfg["f4"]["models"][name], 20261107, ncfg, cfg["f4"]["normalisation"],
                                   cfg, "cpu", BIN)
  assert np.array_equal(pred, G[f"f4__{name}__pred"])
  assert np.array_equal(np.asarray(proba)[:, 1], G[f"f4__{name}__p_target"])
  for got, want in zip(rows, meta[f"f4__{name}__folds"]):
    for k, v in want.items():
      assert got[k] == v, (k, got[k], v)
