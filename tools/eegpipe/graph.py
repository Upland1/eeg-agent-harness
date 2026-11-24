"""Family F4: the supervisor's edge-gated GNN on the complete electrode graph (torch).

Ported from P300 ``p300/graph.py`` @ cd5db15, itself from ``mas-ssvep-eeg-xai`` v1.0.4
(``src/models/graph/connectivity_gnn.py``: ``EdgeGatedLayer``, ``ConnectivityGNN``;
``src/features/connectivity/graph_inputs.py``: ``build_inputs``, the train-only standardiser;
``scripts/connectivity/graph_modeling/benchmark_gnn.py::make_model``: hidden 32, 2 layers,
dropout 0.3). Unchanged except that the number of nodes comes from the data and the number of
classes from the settings (k classes, D5).
Architecture: node encoder Linear + ELU plus a learned channel embedding N(0, embed_std);
``n_layers`` edge-gated layers h <- LayerNorm(h + Dropout(ELU(W_self h_i + agg_i))), agg_i =
mean over the other nodes j of sigmoid(Linear(e_ij)) * W_msg h_j (no self messages); readout
concat(mean, max over nodes) -> Dropout -> Linear. No max-norm (the trainer applies max-norm
only to models that define it). Inputs: node features = the channel's epoch (the classical
epoch); edge features (variant ``nodes+phase``) = the F3(b) phasors of the raw epoch after the
label-free template fitted on the TRAINING fold (eegpipe.phase.edge_tensor). Packing: one row
per node [node features of i, e_i0, ..., e_i(C-1)], so the F2 trainer is reused unchanged; its
``per_feature`` normalisation over the fitting epochs IS [M]'s standardiser (per (channel,
feature) for nodes, per (i, j, feature) for edges, std < floor -> 1).
"""

import inspect

import numpy as np
import torch
from torch import nn

from eegpipe import networks as nw
from eegpipe import phase as ph

VARIANTS = ("nodes", "nodes+phase")


class EdgeGatedLayer(nn.Module):
  """Ported from [M] connectivity_gnn.py::EdgeGatedLayer (l.17-46), unchanged."""

  def __init__(self, hidden, n_edge_feats, dropout):
    super().__init__()
    self.w_self = nn.Linear(hidden, hidden, bias=False)
    self.w_msg = nn.Linear(hidden, hidden, bias=False)
    self.gate = nn.Linear(n_edge_feats, hidden) if n_edge_feats > 0 else None
    self.act = nn.ELU()
    self.drop = nn.Dropout(dropout)
    self.norm = nn.LayerNorm(hidden)

  def forward(self, h, e=None):
    n = h.shape[1]
    msg = self.w_msg(h)
    off = 1.0 - torch.eye(n, dtype=h.dtype, device=h.device)  # no self messages [M]
    if self.gate is not None:
      if e is None:
        raise ValueError("this layer has an edge gate; pass edge features")
      g = torch.sigmoid(self.gate(e))
      agg = (g * msg.unsqueeze(1) * off[None, :, :, None]).sum(dim=2)
    else:
      agg = torch.einsum("ij,bjh->bih", off, msg)
    agg = agg / max(n - 1, 1)
    return self.norm(h + self.drop(self.act(self.w_self(h) + agg)))


class ConnectivityGNN(nn.Module):
  """Ported from [M] connectivity_gnn.py::ConnectivityGNN (l.49-69); embed std explicit, no graph
  features."""

  def __init__(self, n_nodes, n_node_feats, n_edge_feats, n_classes, hidden, n_layers, dropout, embed_std):
    super().__init__()
    self.n_nodes, self.n_edge_feats = n_nodes, n_edge_feats
    self.encoder = nn.Sequential(nn.Linear(n_node_feats, hidden), nn.ELU())
    self.embed = nn.Parameter(torch.randn(n_nodes, hidden) * embed_std)
    self.layers = nn.ModuleList([EdgeGatedLayer(hidden, n_edge_feats, dropout) for _ in range(n_layers)])
    self.drop = nn.Dropout(dropout)
    self.head = nn.Linear(2 * hidden, n_classes)

  def forward(self, x, e=None):
    h = self.encoder(x) + self.embed
    for layer in self.layers:
      h = layer(h, e)
    return self.head(self.drop(torch.cat([h.mean(dim=1), h.max(dim=1).values], dim=1)))


class PackedGNN(nn.Module):
  """ConnectivityGNN on packed rows (B, N, F_node + N * F_edge) (module docstring)."""

  def __init__(self, n_classes, n_channels, n_samples, n_node_feats, n_edge_feats, hidden, n_layers,
               dropout, embed_std):
    super().__init__()
    if n_samples != n_node_feats + n_channels * n_edge_feats:
      raise ValueError(f"packed width {n_samples} != {n_node_feats} + {n_channels} * {n_edge_feats}")
    self.n_channels, self.n_node_feats, self.n_edge_feats = n_channels, n_node_feats, n_edge_feats
    self.gnn = ConnectivityGNN(n_channels, n_node_feats, n_edge_feats, n_classes, hidden, n_layers,
                               dropout, embed_std)

  def forward(self, x):
    if x.dim() != 3 or x.shape[1] != self.n_channels:
      raise ValueError(f"expected (B, {self.n_channels}, F), got {tuple(x.shape)}")
    nodes = x[..., :self.n_node_feats]
    e = None
    if self.n_edge_feats > 0:
      e = x[..., self.n_node_feats:].reshape(x.shape[0], self.n_channels, self.n_channels, self.n_edge_feats)
    return self.gnn(nodes, e)


SHAPE_ARGS = ("n_classes", "n_channels", "n_samples")


def required_params():
  return sorted(k for k in inspect.signature(PackedGNN.__init__).parameters if k not in ("self",) + SHAPE_ARGS)


def model_builder(spec):
  """``{"class": "ConnectivityGNN", "variant", "params"}`` -> build(n_classes, n_channels, n_samples);
  refuses a table that does not name exactly the constructor's parameters (G5), as
  networks.model_builder."""
  if spec["class"] != "ConnectivityGNN":
    raise ValueError(f"unknown graph network class {spec['class']!r}")
  if spec["variant"] not in VARIANTS:
    raise ValueError(f"variant {spec['variant']!r}; choose from {VARIANTS}")
  need, got = set(required_params()), set(spec["params"])
  if need != got:
    raise ValueError(f"ConnectivityGNN: missing {sorted(need - got)}, unknown {sorted(got - need)}")
  params = dict(spec["params"])
  if (spec["variant"] == "nodes") != (int(params["n_edge_feats"]) == 0):
    raise ValueError("variant 'nodes' needs n_edge_feats 0 and 'nodes+phase' needs n_edge_feats > 0")
  return lambda nc, ch, T: PackedGNN(nc, ch, T, **params)


def pack(node, edge):
  """(n, C, Fn), (n, C, C, Fe) or None -> (n, C, Fn + C * Fe) float64 (module docstring)."""
  node = np.asarray(node, dtype=np.float64)
  if edge is None:
    return node
  edge = np.asarray(edge, dtype=np.float64)
  n, C = node.shape[:2]
  return np.concatenate([node, edge.reshape(n, C, -1)], axis=-1)


def fold_inputs_fn(X_node, X_raw, spec, cfg):
  """(train idx, test idx) -> (packed train rows, packed test rows); the edge template is fitted
  on the training-fold raw epochs only (G1)."""
  def f(train, test):
    if spec["variant"] == "nodes":
      return pack(X_node[train], None), pack(X_node[test], None)
    pf = ph.phase_transformer({"bands": spec["edge_bands"], "subtract_template": spec["subtract_template"],
                               "components": spec["edge_components"]}, cfg).fit(X_raw[train])
    return (pack(X_node[train], pf.edge_tensor(X_raw[train])), pack(X_node[test], pf.edge_tensor(X_raw[test])))
  return f


def cv_gnn(X_node, X_raw, y, unit_uid, splits, spec, seed, ncfg, norm, cfg, device, class_names):
  """Out-of-fold predictions of one GNN variant and seed (``networks.cv_network`` with fold-wise
  inputs and the ``per_feature`` normalisation ``norm``)."""
  return nw.cv_network(None, y, unit_uid, splits, spec, seed, ncfg, device, class_names,
                       fold_inputs=fold_inputs_fn(X_node, X_raw, spec, cfg), norm=norm,
                       build=model_builder(spec))
