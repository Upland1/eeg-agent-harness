"""Golden outputs of the FROZEN P300 pipeline on a fixed synthetic P300 study (spec v0.4 §4, decision D3).

Run once, with the P300 code exported read-only (``git archive <commit>``), never from the P300 checkout:

  <p300 venv>/bin/python kit_tests/golden/make_p300_goldens.py --p300 <export of d833264> --commit d833264 \
      --out kit_tests/golden/p300_d833264.npz

The study (numpy only, seed 20261109): 3 Training files, 8 channels at 256 Hz, 6 blocks per file (a 10x code, 18 flashes
of codes 1-9 at 64-sample steps, then 200), a planted ERP on target flashes (code == x), three flashes with a 400 uV
step (rejected by ptp). File 1 has 250-sample rests, so the 4-14 Hz span gate fails and the file is filtered block by
block (the fallback); files 0 and 2 have 1300-sample rests (continuous filtering). Everything is computed by the P300
code with the P300 Stage-2 settings (``configs/ssvep_methods_stage2.json``): per-file epochs, counts and gates
(``session.prepare_recording``), the session and its block folds, out-of-fold predictions of the baseline and all 20
F1 methods, the permutation draws, null and per-file tests (7 permutations), the 1-40 Hz network input (file 1 is
refused: its block-wise segments are shorter than padlen 2535), the phase epochs and every F3 phase-feature classifier,
condition-level connectivity (5 permutations), EEGNet and ShallowConvNet (files 0 and 2, 4 folds) and the F4 GNN
(seed 20261107, 3 epochs, CPU, deterministic), BH-FDR and NBS on fixed statistics, and the Stage-2 paired statistics
on a fixed score table. One BLAS/OpenMP thread and one torch thread (set below): two runs give identical files. ``kit_tests/test_eegpipe_p300_golden.py``
asks eegpipe for the same outputs from the same inputs; the event table eegpipe reads is derived here from the P300
flash table (``events.flash_table``, ``events.labels``), so the adapter's job is done by the P300 code itself.
"""

import argparse
import hashlib
import json
import os
import platform
import sys
from pathlib import Path

# One BLAS / OpenMP thread (set before numpy is imported) and one torch thread: the summation order of the
# connectivity matrix products and of torch's CPU reductions then does not depend on the machine's core count.
for _v in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
  os.environ[_v] = "1"

import numpy as np  # noqa: E402

SEED = 20261109
FS = 256.0
N_CH = 8
N_PERM = 7
RESTS = (1300, 250, 1300)


def synth_study():
  rng = np.random.default_rng(SEED)
  files = []
  k = np.arange(-48, 49)
  bump = 4.0 * np.exp(-0.5 * (k / 12.0) ** 2)
  for rest in RESTS:
    ev, t, lead = [], 600, 600
    targets = rng.permutation(np.arange(1, 10))[:6]
    for x in targets:
      ev.append((t, 100 + int(x)))
      codes = np.concatenate([rng.permutation(np.arange(1, 10)) for _ in range(2)])
      for i, c in enumerate(codes):
        ev.append((t + 32 + 64 * i, int(c)))
      end = t + 32 + 64 * len(codes)
      ev.append((end, 200))
      t = end + rest
    ns = t + lead
    data = 5.0 * rng.standard_normal((N_CH, ns))
    cur = None
    for s, c in ev:
      if c > 100:
        cur = c - 100
      elif 1 <= c <= 9 and c == cur:
        data[:, s + 77 + k] += bump
    flashes = [s for s, c in ev if 1 <= c <= 9]
    for s in rng.choice(flashes, 3, replace=False):
      data[int(rng.integers(N_CH)), s + 20:s + 40] += 400.0
    files.append((data, np.asarray(ev, dtype=np.int64)))
  return files


def main(argv=None):
  ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
  ap.add_argument("--p300", required=True, help="read-only export of the P300 repository at --commit")
  ap.add_argument("--commit", required=True)
  ap.add_argument("--out", required=True)
  a = ap.parse_args(argv)
  root = Path(a.p300).resolve()
  sys.path[:0] = [str(root), str(root / "tools")]
  from p300 import classical as cl
  from p300 import evaluate as evl
  from p300 import events as ev
  from p300 import nn_input as ni
  from p300 import phase as ph
  from p300 import session as ss
  from p300 import session_eval as se
  import stage2_stats as s2

  cfg = json.loads((root / "configs" / "ssvep_methods_stage2.json").read_text())
  G = {}
  meta = {"p300_commit": a.commit, "seed": SEED, "fs": FS, "n_perm": N_PERM, "rests": RESTS,
          "python": platform.python_version(), "numpy": np.__version__}
  import scipy
  import sklearn
  meta.update(scipy=scipy.__version__, sklearn=sklearn.__version__)

  # ---- per file: inputs, generic event table (from the P300 flash table), P300 epochs
  files = synth_study()
  fres = []
  for f, (data, events) in enumerate(files):
    ft = ev.flash_table(events, cfg["events"]["post200_max_gap_samples"])
    G[f"in{f}__data"], G[f"in{f}__events"] = data, events
    G[f"in{f}__onset"], G[f"in{f}__unit"], G[f"in{f}__code"] = ft["onset"], ft["block"], ft["code"]
    G[f"in{f}__label"] = ev.labels(ft["code"], ft["block"], ft["block_x"], cfg["events"]["label_rule"])
    G[f"in{f}__unit_start"], G[f"in{f}__unit_end"], G[f"in{f}__unit_target"] = (
      ft["block_start"], ft["block_end"], ft["block_x"])
    r = ss.prepare_recording(data, FS, events, cfg)
    fres.append(r)
    for key in ("X", "y", "code", "block", "onset"):
      G[f"ep{f}__{key}"] = r[key]
    meta[f"ep{f}__counts"] = r["counts"]
    meta[f"ep{f}__gates"] = {k: (v if not isinstance(v, np.generic) else v.item()) for k, v in r["gates"].items()}
    try:
      nn = ni.network_epochs(data, FS, events, r["onset"], r["block"], cfg)
    except ValueError as exc:  # file 1: block-wise segments shorter than padlen 2535 -> loud refusal
      meta[f"nn{f}"] = {"error": f"{type(exc).__name__}: {exc}"}
      continue
    G[f"nn{f}__X"] = nn["X"]
    meta[f"nn{f}"] = {"filtering": nn["filtering"], "n_edge": int(nn["n_edge"]),
                      "gate": {k: (v.item() if isinstance(v, np.generic) else v) for k, v in nn["gate"].items()}}

  # ---- session, folds
  sess = ss.assemble_session(fres)
  fold = ss.assign_block_folds(sess["block_file"], int(cfg["folds"]["n_folds"]), int(cfg["folds"]["seed"]))
  splits = ss.fold_splits(sess["block_uid"], fold, int(cfg["folds"]["n_folds"]))
  G["sess__block_uid"], G["sess__file_idx"], G["sess__block_fold"] = sess["block_uid"], sess["file_idx"], fold

  # ---- classical: every method, observed labels
  ids = ["baseline"] + cl.method_ids(cfg)
  meta["methods"], meta["method_errors"] = ids, {}
  for mid in ids:
    try:
      pred, _, rows = evl.cv_predict(sess["X"], sess["y"], splits, lambda m=mid: cl.make_method(m, cfg))
      G[f"cl__{mid}__pred"] = pred
    except Exception as exc:  # recorded: the port must fail the same way
      meta["method_errors"][mid] = f"{type(exc).__name__}: {exc}"

  # ---- permutation: draws, null, observed per-file BA, per-file tests
  pm = list(cfg["permutation"]["methods"])
  shuffles = se.draw_session_shuffles([r["block_codes"] for r in fres], [r["block_x"] for r in fres], N_PERM,
                                      int(cfg["permutation"]["seed"]))
  for f, s in enumerate(shuffles):
    G[f"perm__shuffle{f}"] = s
  null = se.permutation_null(sess, splits, pm, cfg, shuffles, 1, 8)
  G["perm__null"] = null
  nd = [evl.n_distinct_shuffles("shuffle_block_targets", r["block_codes"], r["block_x"]) for r in fres]
  meta["perm__n_distinct"], meta["perm__methods"], meta["perm__tests"] = nd, pm, {}
  for mi, mid in enumerate(pm):
    obs, pooled = se.per_file_ba(sess, sess["y"], splits, mid, cfg)
    G[f"perm__obs__{mid}"] = obs
    meta["perm__tests"][mid] = se.per_file_tests(obs, null[mi, :, :len(files)], nd, cfg["alpha"],
                                                 float(cfg["permutation"]["critical_value_percentile"]),
                                                 cfg["permutation"]["percentile_method"])

  # ---- F3: phase epochs, phase-feature classifiers, condition-level connectivity (5 permutations)
  X_phase = np.concatenate([ph.phase_epochs(files[f][0], FS, fres[f]["onset"], cfg) for f in range(len(files))])
  G["f3__X_phase"] = X_phase
  meta["f3__methods"], meta["f3__errors"] = ph.f3_method_ids(cfg), {}
  for mid in ph.f3_method_ids(cfg):
    try:
      pred, _, _ = evl.cv_predict(X_phase, sess["y"], splits, lambda m=mid: ph.make_f3(m, cfg))
      G[f"f3__{mid}__pred"] = pred
    except Exception as exc:
      meta["f3__errors"][mid] = f"{type(exc).__name__}: {exc}"
  ccfg = cfg["f3"]["condition_level"]
  n_cl = 5
  cl_shuffles = se.draw_session_shuffles([r["block_codes"] for r in fres], [r["block_x"] for r in fres], n_cl,
                                         ccfg["permutation_seed"])
  for f, s in enumerate(cl_shuffles):
    G[f"f3a__shuffle{f}"] = s
  labels_of = lambda p: se.session_labels(sess, [s_[p] for s_ in cl_shuffles], cfg["events"]["label_rule"])  # noqa: E731
  res = ph.condition_level(X_phase, sess["y"], sess["block_uid"], labels_of, n_cl, FS, cfg, file_idx=sess["file_idx"])
  G["f3a__null_diff"], G["f3a__null_t"] = res["null_diff"], res["null_t"]
  for k, v in res["observed"].items():
    G[f"f3a__obs__{k}"] = v
  meta["f3a__n_perm"], meta["f3a__edges"], meta["f3a__nbs"], meta["f3a__summary"] = (
    n_cl, res["edges"], res["nbs"], res["summary"])

  # ---- F2 networks and F4 GNN (torch, CPU, deterministic, 3 epochs): files 0 and 2 for the networks (file 1 has
  # no network input), the whole session for the GNN
  import torch
  from p300 import graph as gr
  from p300 import networks as nw
  torch.set_num_threads(1)
  meta["torch"], meta["threads"] = torch.__version__, "BLAS/OpenMP 1, torch 1"
  ncfg = json.loads(json.dumps(cfg["networks"]))
  ncfg["trainer"]["max_epochs"] = 3
  nw.set_determinism(ncfg["deterministic"])
  s02 = ss.assemble_session([fres[0], fres[2]])
  fold02 = ss.assign_block_folds(s02["block_file"], 4, int(cfg["folds"]["seed"]))
  sp02 = ss.fold_splits(s02["block_uid"], fold02, 4)
  X_net = np.concatenate([G["nn0__X"], G["nn2__X"]])
  for name in ("eegnet", "shallowconvnet"):
    pred, p_t, rows_f, _ = nw.cv_network(X_net, s02["y"], s02["block_uid"], sp02, ncfg["models"][name], 20261107,
                                         ncfg, "cpu")
    G[f"f2__{name}__pred"], G[f"f2__{name}__p_target"] = pred, np.asarray(p_t)
    meta[f"f2__{name}__folds"] = [{k: r[k] for k in ("fold", "best_epoch", "epochs_run", "best_val_loss", "n_params")}
                                  for r in rows_f]
  f4 = cfg["f4"]
  gname = f4["primary"]
  pred, p_t, rows_f, _ = gr.cv_gnn(sess["X"], X_phase, sess["y"], sess["block_uid"], splits, f4["models"][gname],
                                   20261107, ncfg, f4["normalisation"], cfg, "cpu")
  G[f"f4__{gname}__pred"], G[f"f4__{gname}__p_target"] = pred, np.asarray(p_t)
  meta["f4__model"] = gname
  meta[f"f4__{gname}__folds"] = [{k: r[k] for k in ("fold", "best_epoch", "epochs_run", "best_val_loss", "n_params")}
                                 for r in rows_f]

  # ---- graphstats on fixed statistics
  rng = np.random.default_rng(SEED + 1)
  p_edges = rng.uniform(size=(4, 28)) ** 3
  G["gs__p"] = p_edges
  G["gs__bh"] = np.asarray(ph.benjamini_hochberg(p_edges.ravel(), 0.05))
  t_obs = rng.normal(size=28) * 2.0
  t_obs[:5] += 4.0
  t_obs[20:23] -= 4.0
  t_null = rng.normal(size=(50, 28)) * 2.0
  G["gs__t_obs"], G["gs__t_null"] = t_obs, t_null
  meta["gs__nbs"] = {d: _jsonable(ph.nbs(t_obs, t_null, 3.0, N_CH, d)) for d in ("target_gt_nontarget", "nontarget_gt_target")}

  # ---- paired statistics (Stage 2) on a fixed score table
  parts = [f"P{i:02d}" for i in range(1, 15)]
  rng = np.random.default_rng(SEED + 2)
  base = rng.uniform(0.55, 0.75, len(parts))
  scores = {p: {"baseline": float(b), "f1/raw/Shrinkage-LDA lsqr": float(b + rng.normal(0.03, 0.02)),
                "f2/eegnet": float(b + rng.normal(0.0, 0.02))} for p, b in zip(parts, base)}
  scores["P05"]["f2/eegnet"] = None
  roles = {p: ("reported_separately" if p == "P14" else "confirmatory") for p in parts}
  meta["paired__scores"], meta["paired__roles"] = scores, roles
  meta["paired__cfg_keys"] = sorted(cfg["stage2"])
  meta["paired__result"] = _jsonable(s2.analyse(scores, roles, cfg))

  out = Path(a.out)
  out.parent.mkdir(parents=True, exist_ok=True)
  np.savez_compressed(out, **G)
  meta["npz_sha256"] = hashlib.sha256(out.read_bytes()).hexdigest()
  out.with_suffix(".json").write_text(json.dumps(_jsonable(meta), indent=1, sort_keys=True) + "\n")
  print(f"written: {out} ({len(G)} arrays), {out.with_suffix('.json')}")


def _jsonable(o):
  if isinstance(o, dict):
    return {str(k): _jsonable(v) for k, v in o.items()}
  if isinstance(o, (list, tuple)):
    return [_jsonable(v) for v in o]
  if isinstance(o, np.ndarray):
    return o.tolist()
  if isinstance(o, np.generic):
    return o.item()
  return o


if __name__ == "__main__":
  main()
