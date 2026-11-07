"""Known-answer tests for eegpipe.graph (torch), moved from the P300 project (tests @ d833264,
``tests/test_ssvep_methods_step3.py`` section 5), plus a 5-class shape check. The epoch-level
world is the one of test_eegpipe_phase (the P300 step-3 world)."""

import copy
import sys
from pathlib import Path

import numpy as np
import pytest

torch = pytest.importorskip("torch")
TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from eegpipe import evaluate as evl  # noqa: E402
from eegpipe import graph as gr  # noqa: E402
from eegpipe import networks as nw  # noqa: E402
from eegpipe import phase as ph  # noqa: E402
from test_eegpipe_networks import ncfg  # noqa: E402
from test_eegpipe_phase import N_CH, N_NODE, base_cfg, folds_of, transformer, world  # noqa: E402

NORM = {"kind": "per_feature", "std_floor": 1e-8}
BIN = ["nontarget", "target"]


def gnn_spec(variant="nodes+phase", hidden=32, dropout=0.3):
  fe = 2 if variant == "nodes+phase" else 0
  return {"class": "ConnectivityGNN", "variant": variant, "edge_bands": ["delta"] if fe else [],
          "edge_components": ["cos", "sin"] if fe else [], "subtract_template": bool(fe),
          "params": {"n_node_feats": N_NODE, "n_edge_feats": fe, "hidden": hidden, "n_layers": 2,
                     "dropout": dropout, "embed_std": 0.1}}


def test_gnn_parameter_counts_shapes_builder_and_packing():
  """Known answers (exact, P300 D-014): nodes 6274, nodes+phase 6466 parameters for 2 classes; 5
  classes add 3 x 65 head parameters; builder refusals; PackedGNN unpacks exactly."""
  for variant, n in (("nodes", 6274), ("nodes+phase", 6466)):
    spec = gnn_spec(variant)
    width = N_NODE + N_CH * spec["params"]["n_edge_feats"]
    m = gr.model_builder(spec)(2, N_CH, width)
    assert nw.count_parameters(m) == n and not hasattr(m, "apply_max_norm")
    assert nw.count_parameters(gr.model_builder(spec)(5, N_CH, width)) == n + 3 * 65
  bad = gnn_spec()
  del bad["params"]["embed_std"]
  with pytest.raises(ValueError):
    gr.model_builder(bad)
  bad = gnn_spec("nodes")
  bad["params"]["n_edge_feats"] = 2
  with pytest.raises(ValueError):
    gr.model_builder(bad)
  rng = np.random.default_rng(0)
  node, edge = rng.normal(size=(3, N_CH, N_NODE)), rng.normal(size=(3, N_CH, N_CH, 2))
  P = gr.pack(node, edge)
  m = gr.model_builder(gnn_spec())(2, N_CH, P.shape[2])
  seen = {}
  orig = m.gnn.forward
  m.gnn.forward = lambda x, e=None: (seen.update(x=x, e=e), orig(x, e))[1]
  assert m(torch.from_numpy(P).float()).shape == (3, 2)
  assert np.allclose(seen["x"].numpy(), node, atol=1e-6) and np.allclose(seen["e"].numpy(), edge, atol=1e-6)


def test_per_feature_normalisation_equals_the_source_standardiser_on_packed_rows():
  Xr, Xn, sess, _ = world(8)
  E = transformer().fit(Xr).edge_tensor(Xr)
  P = gr.pack(Xn, E)
  mean, std = nw.fit_stats_per_feature(P, 1e-8)
  es = np.where(E.std(0) < 1e-8, 1.0, E.std(0))
  assert np.array_equal(mean[0, :, :N_NODE], Xn.mean(0)) and np.array_equal(std[0, :, :N_NODE], Xn.std(0))
  assert np.allclose(mean[0, :, N_NODE:].reshape(N_CH, N_CH, 2), E.mean(0), atol=1e-15)
  assert np.allclose(std[0, :, N_NODE:].reshape(N_CH, N_CH, 2), es, atol=1e-15)
  assert std[0, 3, N_NODE + 3 * 2] == 1.0 and std[0, 3, N_NODE + 3 * 2 + 1] == 1.0


def _gnn_cv(Xn, Xr, sess, variant, max_epochs=15, seed=20261107, dropout=0.3):
  return gr.cv_gnn(Xn, Xr, sess["y"], sess["unit_uid"], folds_of(sess), gnn_spec(variant, dropout=dropout), seed,
                   ncfg(max_epochs=max_epochs), NORM, base_cfg(), "cpu", BIN)


@pytest.mark.parametrize("variant", ["nodes", "nodes+phase"])
def test_gnn_learns_a_planted_erp(variant):
  Xr, Xn, sess, _ = world(9, erp_amp=0.8)
  pred, pt, rows, _ = _gnn_cv(Xn, Xr, sess, variant)
  assert evl.class_metrics(sess["y"], pred, BIN)["ba"] >= 0.85
  assert len(rows) == 4 and pt.shape == (len(sess["y"]), 2)


def test_gnn_learns_a_planted_phase_only_difference_through_its_edges():
  """Known answer (P300): zero node features; induced 2.5 Hz lags on channels 0-3 in target epochs
  only: nodes+phase (dropout 0) BA >= 0.90; nodes-only sees identical inputs, BA exactly 0.5."""
  Xr, Xn, sess, _ = world(10, couple=([0, 1, 2, 3], [0.0, np.pi / 2, np.pi, 3 * np.pi / 2], 1.5))
  Z = np.zeros_like(Xn)
  pred, _, _, _ = _gnn_cv(Z, Xr, sess, "nodes+phase", max_epochs=30, dropout=0.0)
  assert evl.class_metrics(sess["y"], pred, BIN)["ba"] >= 0.90
  pred_n, _, _, _ = _gnn_cv(Z, Xr, sess, "nodes", max_epochs=2, dropout=0.0)
  assert evl.class_metrics(sess["y"], pred_n, BIN)["ba"] == 0.5


def test_gnn_template_and_standardisation_come_from_training_units_only(monkeypatch):
  Xr, Xn, sess, _ = world(12)
  splits = folds_of(sess)
  cfg = base_cfg()
  for _, tr, te in splits:
    X2 = Xr.copy()
    X2[te] *= 1000.0
    a_tr, a_te = gr.fold_inputs_fn(Xn, Xr, gnn_spec(), cfg)(tr, te)
    b_tr, _ = gr.fold_inputs_fn(Xn, X2, gnn_spec(), cfg)(tr, te)
    assert np.array_equal(a_tr, b_tr)
    tpl = ph.phase_transformer({"bands": ["delta"], "subtract_template": True, "components": ["cos", "sin"]},
                               cfg).fit(Xr[tr]).edge_tensor(Xr[te])
    assert np.array_equal(a_te[..., N_NODE:].reshape(len(te), N_CH, N_CH, 2), tpl)
  seen = []
  real = nw.fit_network

  def spy(X, y, groups, *a, **k):
    f = real(X, y, groups, *a, **k)
    seen.append((np.array(X), np.array(groups), f["mean"], f["std"], f["fit_idx"], k.get("norm")))
    return f
  monkeypatch.setattr(nw, "fit_network", spy)
  gr.cv_gnn(Xn, Xr, sess["y"], sess["unit_uid"], splits, gnn_spec(), 1, ncfg(max_epochs=1), NORM, cfg, "cpu", BIN)
  for (Xa, ga, ma, sa, fi, norm), (_, tr, te) in zip(seen, splits):
    m_ref, s_ref = nw.fit_stats_per_feature(Xa[fi], 1e-8)
    assert norm == NORM and np.array_equal(ma, m_ref) and np.array_equal(sa, s_ref)
    assert not set(ga.tolist()) & set(sess["unit_uid"][te].tolist())


def test_cv_network_default_path_is_unchanged_by_the_fold_input_arguments():
  _, Xn, sess, _ = world(13)
  spec = {"class": "ShallowConvNet", "params": {"F1": 4, "temporal_kernel_length": 5, "pool_kernel_length": 10,
                                                "pool_stride": 5, "dropout_rate": 0.5}}
  splits = folds_of(sess)
  a = nw.cv_network(Xn, sess["y"], sess["unit_uid"], splits, spec, 3, ncfg(max_epochs=1), "cpu", BIN)
  b = nw.cv_network(None, sess["y"], sess["unit_uid"], splits, spec, 3, ncfg(max_epochs=1), "cpu", BIN,
                    fold_inputs=lambda tr, te: (Xn[tr], Xn[te]))
  assert np.array_equal(a[0], b[0]) and np.array_equal(a[1], b[1])
