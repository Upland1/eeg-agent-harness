"""One data part (e.g. one session) x one family part: every enabled method under the same folds.

  python -m eegpipe.runner.methods --config <part_config.json> --out <folder>

Generic version of the P300 project's ``scripts/run_ssvep_methods.py`` @ cd5db15. Steps:
  0. settings checked before any data is read (eegpipe.settings.validate);
  1. files of ``stage.dataset_part`` from the adapter; each read through ``adapter.read`` (fs and
     channel names from the header must match the settings; channels selected by NAME, G21),
     events from ``adapter.events``, prepared by ``epochs.prepare_file`` (rejection, span gate,
     continuous or unit-wise band-pass, cut, decimate). A failing window gate stops the run;
  2. assembly (unit uids unique across files) and folds (``folds``: n, seed; balanced by stratum =
     file, and by unit label when ``label_scheme`` is ``unit_label``);
  3. the enabled family (``part``): ``classical`` (baseline, F1 suite, SSVEP methods), ``f3``
     (phase features, condition-level connectivity), ``f2__<model>`` (one network, every seed),
     ``f4__<model>`` (one GNN, every seed). A method that raises is recorded as
     "failed: <error>" and the run continues; a method that is also permuted stops the run;
  4. per-stratum permutation tests for ``permutation.methods`` of this part (eegpipe.evaluate);
  5. outputs in a new folder (eegharness.outputs, G9): results.json (commit, dirty flag, settings
     hash, epochs and folds hashes, method statuses), config_used.json, pooled.csv,
     per_file.csv, per_condition.csv, per_fold.csv, curves.csv, per_file_tests.csv, gates.csv,
     summary.txt. Stochastic methods have one row per seed and a "mean" row (G18).
"""

import argparse
import copy
import csv
import hashlib
import importlib
import json
import sys
from pathlib import Path

import numpy as np

from eegpipe import classical as cl
from eegpipe import dataset as ds
from eegpipe import epochs as ep
from eegpipe import evaluate as evl
from eegpipe import folds as fo

PARTS_CPU = ("classical", "f3")


def canonical(obj):
  return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256(text):
  return hashlib.sha256(text.encode() if isinstance(text, str) else text).hexdigest()


def load_adapter(cfg, root):
  if str(root) not in sys.path:
    sys.path.insert(0, str(root))
  return importlib.import_module(cfg["adapter"])


def data_root(cfg, root="."):
  """``data_root`` of the settings, relative to the project root unless absolute."""
  d = Path(cfg["data_root"])
  return d if d.is_absolute() else Path(root) / d


def part_files(adapter, cfg, root="."):
  parts = {p["part"]: p for p in adapter.dataset_parts(data_root(cfg, root))}
  dp = cfg["stage"]["dataset_part"]
  if dp not in parts:
    raise ValueError(f"data part {dp!r} not found by the adapter")
  excluded = set(cfg["selection"].get("excluded_files", []))
  return parts[dp]["participant"], [f for f in sorted(parts[dp]["files"]) if f"{dp}/{f}" not in excluded and f not in excluded]


def read_file(adapter, cfg, rel, root="."):
  path = data_root(cfg, root) / rel
  data, fs, names = adapter.read(path)
  if float(fs) != float(cfg["fs_hz"]):
    raise ValueError(f"{rel}: fs {fs} from the header != settings fs_hz {cfg['fs_hz']} (G21)")
  missing = [c for c in cfg["channels"] if c not in names]
  if missing:
    raise ValueError(f"{rel}: channels {missing} not in the file")
  idx = [list(names).index(c) for c in cfg["channels"]]
  data = np.asarray(data, dtype=np.float64)[idx]
  events = adapter.events(path, data, fs, list(cfg["channels"]), cfg)
  return path, data, float(fs), events


def make_estimator(method_id, cfg):
  """Module-level factory (picklable for permutation workers) for every scikit-learn method."""
  if method_id == "baseline" or method_id.startswith("f1/"):
    return cl.make_method(method_id, cfg)
  if method_id.startswith("f3/"):
    from eegpipe import phase as ph
    return ph.make_f3(method_id, cfg)
  if method_id == "ssvep/fbcca":
    from eegpipe.ssvep import fbcca
    return fbcca.make_fbcca(cfg)
  raise ValueError(f"no estimator for method {method_id!r}")


FB_SPACES = ("fbcsp", "fbcca", "fbcsp+fbcca")


def input_kind(method_id):
  """Which epoch array a method reads: 'clf' (classical epochs), 'fb' (FBCCA bank), 'fb_csp' (FBCSP bank),
  'fb_both' (FBCCA bank then FBCSP bank, for the union), 'phase'."""
  if method_id == "ssvep/fbcca":
    return "fb"
  if method_id.startswith("f1/") and method_id.split("/")[1] in FB_SPACES:
    return {"fbcca": "fb", "fbcsp": "fb_csp", "fbcsp+fbcca": "fb_both"}[method_id.split("/")[1]]
  if method_id.startswith("f3/"):
    return "phase"
  return "clf"


def filterbank_inputs(raws, cfg):
  """Filter-bank epochs of every file: {"fb", "fb_csp", "fb_both", "gates"}. ``ssvep.filterbank.fbcsp_bank``
  (optional) is the FBCSP bank; without it FBCSP reads the FBCCA bank (v0.4 gap 1)."""
  from eegpipe.ssvep import filterbank as fbank
  fb = cfg["ssvep"]["filterbank"]
  margin = cfg["epochs"]["fallback"]["margin_s"]

  def run(bank):
    outs = [fbank.subband_epochs(d, fs, e, r, fb["window_s"], fb["window_rounding"], bank, fb["padlen"],
                                 fb.get("tol", 1e-3), margin) for _, d, fs, e, r in raws]
    return np.concatenate([o["X"] for o in outs]), [o["filtering"] for o in outs]
  x_cca, filt = run(fb["bank"])
  out = {"fb": x_cca, "filtering": filt}
  if fb.get("fbcsp_bank"):
    x_csp, filt2 = run(fb["fbcsp_bank"])
    out.update(fb_csp=x_csp, fb_both=np.concatenate([x_cca, x_csp], axis=1), filtering_csp=filt2)
  else:
    out.update(fb_csp=x_cca, fb_both=x_cca)
  return out


def classical_ids(cfg):
  ids = cl.method_ids(cfg) if cfg["f1"].get("enabled", True) else (["baseline"] if cfg.get("baseline") else [])
  if cfg.get("ssvep", {}).get("enabled") and cfg["ssvep"].get("fbcca", {}).get("enabled", True):
    ids.append("ssvep/fbcca")
  return ids


def metric_row(y, pred, names, **extra):
  return {**extra, **evl.class_metrics(y, pred, names)}


def write_csv(path, rows, empty=("none",)):
  fields = []
  for r in rows:
    fields += [k for k in r if k not in fields]
  with open(path, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields or list(empty))
    w.writeheader()
    w.writerows(rows)


def group_rows(method, seed, y, pred, sess, names, conditions):
  per_file, per_cond = [], []
  for f in np.unique(sess["file_idx"]):
    m = sess["file_idx"] == f
    per_file.append(metric_row(y[m], pred[m], names, method=method, seed=seed, file=sess["file_names"][f]))
  cond = np.array([conditions[f] for f in sess["file_idx"]])
  for c in sorted(set(cond.tolist())):
    m = cond == c
    per_cond.append(metric_row(y[m], pred[m], names, method=method, seed=seed, condition=c))
  return per_file, per_cond


def seed_mean(rows, keys):
  """'mean' rows over seeds of the metric columns, per group (G18)."""
  out = {}
  for r in rows:
    if r["seed"] in ("", "mean"):
      continue
    k = tuple(r.get(x) for x in keys)
    out.setdefault(k, []).append(r)
  res = []
  for k, rs in out.items():
    m = {x: v for x, v in zip(keys, k)}
    m["seed"] = "mean"
    m["n_seeds"] = len(rs)
    for col in rs[0]:
      if col.startswith(("ba", "ca_")):
        m[col] = float(np.mean([float(r[col]) for r in rs]))
      elif col.startswith("n_") and col not in m:
        m[col] = rs[0][col]
    m["status"] = rs[0].get("status", "ok")
    res.append(m)
  return res


def run(cfg, out, root="."):
  from eegpipe import settings as st
  st.validate(cfg, require_sources=False)
  part = cfg["stage"]["part"]
  names = list(cfg["classes"])
  adapter = load_adapter(cfg, root)
  participant, files = part_files(adapter, cfg, root)
  if not files:
    raise ValueError("no files in this data part")
  cond_of = getattr(adapter, "condition_of", lambda p: Path(p).name)
  results, raws, gate_rows = [], [], []
  for rel in files:
    path, data, fs, events = read_file(adapter, cfg, rel, root)
    r = ep.prepare_file(data, fs, events, cfg["epochs"])
    for k, v in r["gates"].items():
      if k.startswith("window__") and k.endswith("__passes") and v is False:
        raise RuntimeError(f"{rel}: window gate {k} fails; the analysis window crosses units (G1). Stopped.")
    gate_rows.append({"file": rel, **{k: v for k, v in r["gates"].items()}})
    results.append(r)
    raws.append((path, data, fs, events, r))
  sess = ds.assemble(results)
  sess["file_names"] = list(files)
  conditions = [cond_of(data_root(cfg, root) / f) for f in files]
  scheme = cfg["label_scheme"]
  ulabel = None
  if scheme == "unit_label":
    ulabel = np.array([sess["y"][sess["unit_uid"] == u][0] for u in range(len(sess["unit_file"]))])
  fcfg = cfg["folds"]
  ufold = fo.assign_unit_folds(sess["unit_file"], int(fcfg["n_folds"]), int(fcfg["seed"]),
                               unit_label=ulabel if fcfg.get("balance_by_label", scheme == "unit_label") else None)
  splits = fo.fold_splits(sess["unit_uid"], ufold, int(fcfg["n_folds"]))
  rows_e = ds.epoch_rows(sess, files)
  ep_sha, fo_sha = ds.epochs_and_folds_sha256(rows_e, [r["counts"] for r in results], files, ufold.tolist())

  inputs = {"clf": sess["X"]}
  if part == "classical" and cfg.get("ssvep", {}).get("enabled"):
    fbi = filterbank_inputs(raws, cfg)
    inputs.update(fb=fbi["fb"], fb_csp=fbi["fb_csp"], fb_both=fbi["fb_both"])
    for i, g in enumerate(gate_rows):
      g["filterbank_filtering"] = fbi["filtering"][i]
      if "filtering_csp" in fbi:
        g["filterbank_filtering_fbcsp"] = fbi["filtering_csp"][i]
  if part == "f3" or part.startswith("f4__"):
    from eegpipe import phase as ph
    inputs["phase"] = np.concatenate([ph.phase_epochs(d, fs, r["onset"], cfg["f3"]) for _, d, fs, e, r in raws])

  pooled, per_file, per_cond, per_fold, curves, statuses = [], [], [], [], [], {}
  perm_methods = [m for m in cfg["permutation"].get("methods", [])]
  y = sess["y"]

  def record(mid, seed, pred, rows_f, extra=None):
    pooled.append({**metric_row(y, pred, names, method=mid, seed=seed, status="ok"), **(extra or {})})
    pf, pc = group_rows(mid, seed, y, pred, sess, names, conditions)
    per_file.extend(pf)
    per_cond.extend(pc)
    per_fold.extend([{"method": mid, "seed": seed, **r} for r in rows_f])

  def fail(mid, exc):
    statuses[mid] = f"failed: {type(exc).__name__}: {exc}"
    pooled.append({"method": mid, "seed": "", "status": statuses[mid], "ba": ""})
    if mid in perm_methods:
      raise RuntimeError(f"permuted method {mid} failed: {exc}") from exc

  if part == "classical":
    for mid in classical_ids(cfg):
      try:
        X = inputs[input_kind(mid)]
        pred, _, rows_f = evl.cv_predict(X, y, splits, lambda m=mid: make_estimator(m, cfg), names)
        n_nc = sum(r["n_convergence_warnings"] > 0 for r in rows_f)
        statuses[mid] = evl.convergence_status(n_nc)
        record(mid, "", pred, rows_f, {"n_folds_not_converged": n_nc, "status": statuses[mid]})
      except Exception as exc:  # recorded, never silent
        fail(mid, exc)
  elif part == "f3":
    from eegpipe import connectivity as cn
    from eegpipe import phase as ph
    for mid in ph.f3_method_ids(cfg):
      try:
        pred, _, rows_f = evl.cv_predict(inputs["phase"], y, splits, lambda m=mid: make_estimator(m, cfg), names)
        statuses[mid] = "ok"
        record(mid, "", pred, rows_f)
      except Exception as exc:
        fail(mid, exc)
    ccfg = cfg["f3"]["condition_level"]
    if ccfg.get("enabled"):
      vals = evl.unit_values(sess, scheme, [r.get("unit_target") for r in results] if scheme == "unit_target" else None)
      sh = evl.draw_shuffles(vals, int(ccfg["n_permutations"]), int(ccfg["permutation_seed"]))
      res = cn.condition_level(inputs["phase"], y, sess["unit_uid"],
                               lambda p: evl.labels_for(sess, [s[p] for s in sh], scheme),
                               int(ccfg["n_permutations"]), float(cfg["fs_hz"]), cfg, sess["file_idx"])
      write_csv(Path(out) / "connectivity_edges.csv", res["edges"])
      write_csv(Path(out) / "connectivity_nbs.csv", res["nbs"])
      (Path(out) / "connectivity_summary.json").write_text(json.dumps(res["summary"], indent=1))
  elif part.startswith(("f2__", "f4__")):
    from eegpipe import networks as nw
    sec = "networks" if part.startswith("f2__") else "f4"
    name = part[4:]
    mid = f"{part[:2]}/{name}"
    ncfg = cfg["networks"]
    spec_cls = (cfg[sec]["models"][name]["class"] if sec == "f4" else ncfg["models"][name]["class"])
    if spec_cls == "CCNN":
      from eegpipe.ssvep import ccnn  # noqa: F401  (registers the class)
    if spec_cls == "PackedFusion":
      raise ValueError("PackedFusion needs packed (harmonic map, FBCCA score) inputs: run it with a project script "
                       "through eegpipe.ssvep.fusion (not a runner part in v0.4)")
    nw.set_determinism(ncfg["deterministic"])
    device = str(nw.resolve_device(ncfg["device"]))
    seed_rows = []
    try:
      if sec == "networks":
        from eegpipe import network_input as ni
        Xn = np.concatenate([ni.network_epochs(d, fs, e, r, cfg["network_input"], cfg["epochs"]["fallback"]["margin_s"])["X"]
                             for _, d, fs, e, r in raws])
      for seed in ncfg["seeds"]:
        if sec == "networks":
          pred, _, rows_f, cur = nw.cv_network(Xn, y, sess["unit_uid"], splits, ncfg["models"][name], int(seed), ncfg,
                                               device, names)
        else:
          from eegpipe import graph as gr
          pred, _, rows_f, cur = gr.cv_gnn(sess["X"], inputs["phase"], y, sess["unit_uid"], splits,
                                           cfg["f4"]["models"][name], int(seed), ncfg, cfg["f4"]["normalisation"],
                                           cfg, device, names)
        hit = sum(bool(r["hit_max_epochs"]) for r in rows_f)
        record(mid, int(seed), pred, rows_f, {"n_folds_hit_max_epochs": hit})
        seed_rows.append(pooled[-1])
        curves.extend([{"method": mid, "seed": int(seed), **c} for c in cur])
      statuses[mid] = "ok"
    except Exception as exc:
      fail(mid, exc)
    pooled.extend(seed_mean([r for r in pooled if r["method"] == mid], ["method"]))
    per_file.extend(seed_mean([r for r in per_file if r["method"] == mid], ["method", "file"]))
    per_cond.extend(seed_mean([r for r in per_cond if r["method"] == mid], ["method", "condition"]))
  else:
    raise ValueError(f"unknown part {part!r}")

  test_rows = []
  pm = [m for m in perm_methods if m in statuses and statuses[m].startswith("ok")]
  n_perm = int(cfg["permutation"].get("n_permutations", 0))
  if pm and n_perm > 0:
    if scheme == "unit_target":
      vals = evl.unit_values(sess, scheme, [r.get("unit_target") for r in results])
      codes = [evl.unit_code_sets(sess, f) for f in range(len(files))]
      shuffles = evl.draw_shuffles(vals, n_perm, int(cfg["permutation"]["seed"]), code_sets=codes)
      redraws = None
    else:
      vals = evl.unit_values(sess, scheme)
      shuffles, redraws = evl.draw_shuffles_constrained(vals, n_perm, int(cfg["permutation"]["seed"]),
                                                        evl.every_class_in_training(sess, splits, scheme, len(names)))
    nd = [evl.n_distinct_shuffles(v) for v in vals]
    for mid in pm:
      s2 = dict(sess)
      s2["X"] = inputs[input_kind(mid)]
      null = evl.permutation_null(s2, splits, [mid], make_estimator, cfg, scheme, names, shuffles,
                                  int(cfg["permutation"].get("n_jobs", 1)), int(cfg["permutation"].get("chunk_size", 8)))[0]
      obs = np.array([r["ba"] for r in per_file if r["method"] == mid and r["seed"] == ""])
      rows = evl.per_stratum_tests(obs, null[:, :-1], nd, float(cfg["permutation"]["alpha"]),
                                   float(cfg["permutation"]["critical_value_percentile"]),
                                   cfg["permutation"]["percentile_method"])
      for f, row in enumerate(rows):
        test_rows.append({"method": mid, "file": files[f], "observed_ba": float(obs[f]),
                          "n_redraws_total": None if redraws is None else int(redraws.sum()), **row})

  out = Path(out)
  config_text = canonical(cfg)
  res = {"participant": participant, "data_part": cfg["stage"]["dataset_part"], "part": part,
         "config_sha256": sha256(config_text), "epochs_sha256": ep_sha, "folds_sha256": fo_sha,
         "methods": statuses, "n_epochs": int(len(y)), "n_units": int(len(sess["unit_file"])), "files": files}
  prov = json.loads((out / "provenance.json").read_text())
  res["commit"], res["tracked_files_dirty"] = prov["commit_short"], prov["tracked_files_dirty"]
  (out / "config_used.json").write_text(json.dumps(cfg, indent=1, ensure_ascii=False))
  (out / "results.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
  write_csv(out / "pooled.csv", pooled)
  write_csv(out / "per_file.csv", per_file)
  write_csv(out / "per_condition.csv", per_cond)
  write_csv(out / "per_fold.csv", per_fold)
  write_csv(out / "curves.csv", curves)
  write_csv(out / "per_file_tests.csv", test_rows)
  write_csv(out / "gates.csv", gate_rows)
  (out / "summary.txt").write_text("\n".join([f"{k}: {v}" for k, v in res.items()]) + "\n")
  return res


def main(argv=None):
  from eegharness.outputs import new_output_dir
  ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
  ap.add_argument("--config", required=True)
  ap.add_argument("--out", required=True)
  ap.add_argument("--root", default=".", help="project root (git tree, adapter location)")
  a = ap.parse_args(argv)
  cfg = json.loads(Path(a.config).read_text())
  out = new_output_dir(a.out, inputs=[a.config], params={"config": a.config}, root=a.root)
  run(copy.deepcopy(cfg), out, a.root)
  print(f"written: {out}")
  return out


if __name__ == "__main__":
  main()
