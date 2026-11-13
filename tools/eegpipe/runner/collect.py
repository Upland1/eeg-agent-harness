"""Confirmatory statistics of a stage root (G19, G23, G25).

  python -m eegpipe.runner.collect --stage <root> --out outputs/stage2_stats [--interim] [--root .]

Generic version of the P300 project's ``tools/stage2_stats.py`` @ cd5db15 (``collect``, ``main``):
  * completeness: a part is terminal when done, or failed/timed out on ``retry.max_attempts``
    attempts; a part never attempted or awaiting its retry is "pending", never a method failure.
    With any pending part the tool refuses unless ``--interim``; then every output carries
    ``statistics.interim_stamp`` and the folder name ends in _INTERIM;
  * provenance: root.json clean and matching the root name, settings and selection; every done
    part's results.json commit = root commit, clean tree, config hash = the recomputed part
    config; epochs/folds hashes identical across the parts of a data part; a provenance status
    or a merged root is refused. Any mismatch: no output;
  * participant score: pooled balanced accuracy of the data part (stochastic methods: the seed
    "mean" row); a failed part, a failed method row, a missing row or an undefined BA makes the
    participant missing for that method (failures.csv, with the cause);
  * tests: eegpipe.paired.analyse over ``statistics.holm_family`` against ``comparator``.
Output (G9): tests.csv, participants.csv, differences.csv, per_file.csv, per_condition.csv,
failures.csv, pending.csv, results.json, summary.txt. Every number is computed here (G11, G23).
"""

import argparse
import csv
import json
import math
import sys
from pathlib import Path

from eegpipe import paired as pr
from eegpipe.runner import stage as stg


class Refusal(Exception):
  pass


def read_csv(p):
  with open(p, newline="") as f:
    return list(csv.DictReader(f))


def _mean_row(r):
  return r.get("seed", "") in ("", "mean", None)


def _f(x):
  try:
    v = float(x)
  except (TypeError, ValueError):
    return None
  return v if math.isfinite(v) else None


def part_methods(cfg, part):
  from eegpipe.runner.methods import classical_ids
  if part == "classical":
    return classical_ids(cfg)
  if part == "f3":
    from eegpipe import phase as ph
    return ph.f3_method_ids(cfg)
  if part.startswith(("f2__", "f4__")):
    return [f"{part[:2]}/{part[4:]}"]
  raise ValueError(part)


def collect(root):
  root = Path(root)
  template = json.loads((root / "stage_config.json").read_text())
  cfg = stg.scoped_config(template)
  sel_raw = (root / "selection.json").read_bytes()
  sel = json.loads(sel_raw)
  meta = json.loads((root / "root.json").read_text())
  commit = meta["commit"]
  template_sha = stg.sha256(stg.canonical(template))
  if (meta.get("tracked_files_dirty") is not False or root.name.endswith("_dirty") or not root.name.endswith(f"_{commit}")
          or meta.get("template_sha256") != template_sha or meta.get("selection_sha256") != stg.sha256(sel_raw)):
    raise Refusal(f"root.json does not match the root (dirty, commit, settings or selection): {meta}")
  merged = sorted(p.name for p in root.glob("attempts_merged_*.jsonl"))
  if merged:
    raise Refusal(f"root contains merged attempt logs {merged}: roots are never merged")
  max_att = int(cfg["stage"]["retry"]["max_attempts"])
  sc = cfg["statistics"]
  wanted = [cfg["comparator"], *sc["holm_family"]]
  fams = stg.part_names(cfg)
  participants, scores, pooled, per_file, per_cond, failures, pending = {}, {}, [], [], [], [], []
  for srow in sel["stage2_parts"]:
    p, dpart = srow["participant"], srow["part"]
    participants[p] = {"participant": p, "data_part": dpart, "role": srow["role"]}
    scores.setdefault(p, {})
    ctx = {"participant": p, "data_part": dpart, "role": srow["role"]}
    hashes = {}
    for part in fams:
      pdir = root / "parts" / stg.slug(dpart) / part
      psha = stg.sha256(stg.canonical(stg.part_config(cfg, part, dpart, srow["role"], template_sha)))
      st = stg.read_json(pdir / "part_status.json")
      if st and st.get("status") in stg.PROVENANCE_STATUSES:
        raise Refusal(f"{dpart} {part}: {st['status']} recorded by the runner: {st.get('provenance_problems')}")
      if st and (st.get("commit") != commit or st.get("part_config_sha256") != psha):
        raise Refusal(f"{dpart} {part}: part_status.json commit/config hash differ from the root")
      terminal, done = stg.is_terminal(st, commit, psha, max_att)
      mids = part_methods(cfg, part)
      if not terminal:
        why = "never attempted" if not st else f"{st.get('status')} after {st.get('n_attempts')} of {max_att} attempts"
        for mid in mids:
          scores[p][mid] = None
          pending.append({**ctx, "method": mid, "part": part, "state": why})
        continue
      if not done:
        for mid in mids:
          scores[p][mid] = None
          failures.append({**ctx, "method": mid, "part": part,
                           "cause": f"part failed after {st['n_attempts']} attempts (log {st.get('log', '')})"})
        continue
      od = Path(st["outdir"])
      probs, ep, fo = stg.verify_child(od, commit, psha)
      if probs or (ep, fo) != (st.get("epochs_sha256"), st.get("folds_sha256")):
        raise Refusal(f"{dpart} {part}: provenance check failed: {probs or 'hashes differ from part_status.json'}")
      hashes[part] = (ep, fo)
      prow = {r["method"]: r for r in read_csv(od / "pooled.csv") if _mean_row(r)}
      for mid in mids:
        r = prow.get(mid)
        ba = _f(r["ba"]) if r else None
        if r is None:
          cause = "no pooled row"
        elif str(r.get("status", "")).startswith("failed"):
          cause, ba = r["status"], None
        elif ba is None:
          cause = "undefined balanced accuracy"
        else:
          cause = None
        scores[p][mid] = ba
        if cause:
          failures.append({**ctx, "method": mid, "part": part, "cause": cause})
        pooled.append({**ctx, "method": mid, "primary": mid in wanted, "valid": ba is not None,
                       "status": r.get("status", "") if r else "missing", "ba": ba, "source": str(od)})
      for fn, dest in (("per_file.csv", per_file), ("per_condition.csv", per_cond)):
        for r in read_csv(od / fn):
          if r["method"] in mids and _mean_row(r):
            dest.append({**ctx, **r, "source": str(od)})
    if len(set(hashes.values())) > 1:
      raise Refusal(f"{dpart}: retained epochs or folds differ between parts: {hashes}")
  return {"config": cfg, "participants": participants, "scores": scores, "pooled": pooled, "commit": commit,
          "per_file": per_file, "per_condition": per_cond, "failures": failures, "pending": pending}


def write_csv(path, rows, empty=("none",)):
  fields = []
  for r in rows:
    fields += [k for k in r if k not in fields]
  with open(path, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields or list(empty))
    w.writeheader()
    w.writerows(rows)


def main(argv=None):
  from eegharness.outputs import ComputeTimer, new_output_dir, record_compute_time
  ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
  ap.add_argument("--stage", required=True)
  ap.add_argument("--out", required=True)
  ap.add_argument("--root", default=".")
  ap.add_argument("--interim", action="store_true")
  a = ap.parse_args(argv)
  timer = ComputeTimer(device="cpu")
  try:
    col = collect(a.stage)
  except Refusal as exc:
    sys.exit(f"refused: {exc}")
  cfg = col["config"]
  sc = cfg["statistics"]
  if col["pending"] and not a.interim:
    sys.exit(f"refused: {len(col['pending'])} method result(s) in parts that are not terminal; a confirmatory "
             f"analysis needs a complete root (use --interim for a stamped interim look)")
  interim = bool(col["pending"]) or a.interim
  run_status = sc["interim_stamp"] if interim else "confirmatory (every planned part terminal)"
  roles = {p: v["role"] for p, v in col["participants"].items()}
  tests, diffs = pr.analyse(col["scores"], roles, cfg["comparator"], sc, cfg.get("comparator_label", cfg["comparator"]))
  out = new_output_dir(Path(a.out) / ("INTERIM" if interim else "confirmatory"), inputs=[Path(a.stage) / "root.json"],
                       params={"stage": a.stage, "interim": interim}, root=a.root)
  res = {"run_status": run_status, "interim": interim, "stage_root": str(a.stage), "stage_root_commit": col["commit"],
         "scope": cfg["stage"]["scope"], "statistics": sc, "retry_rule": cfg["stage"]["retry"],
         "n_participants_confirmatory": sum(r == "confirmatory" for r in roles.values()),
         "participants_reported_separately": sorted(p for p, r in roles.items() if r in sc["separate_roles"]),
         "tests": tests, "failed_methods": col["failures"], "pending": col["pending"]}
  stamp = lambda rows: [{"run_status": run_status, **r} for r in rows]  # noqa: E731
  (out / "results.json").write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str))
  write_csv(out / "tests.csv", stamp(tests))
  write_csv(out / "participants.csv", stamp(col["pooled"]))
  write_csv(out / "differences.csv", stamp(diffs))
  write_csv(out / "per_file.csv", stamp(col["per_file"]))
  write_csv(out / "per_condition.csv", stamp(col["per_condition"]))
  write_csv(out / "failures.csv", stamp(col["failures"]), ("run_status", "participant", "method", "cause"))
  write_csv(out / "pending.csv", stamp(col["pending"]), ("run_status", "participant", "method", "state"))
  lines = [f"run_status: {run_status}"] + [f"  {json.dumps(t, default=str)}" for t in tests]
  (out / "summary.txt").write_text("\n".join(lines) + "\n")
  record_compute_time(out, timer)
  for t in tests:
    print(f"{t['method']}: n {t['n']}, p_holm {t['p_holm']}, HL {t.get('hodges_lehmann')} -> {t['verdict']}")
  print(f"written: {out}  [{run_status}]")
  return out


if __name__ == "__main__":
  main()
