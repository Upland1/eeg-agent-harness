"""Label-free, seeded choice of ONE data part per participant for confirmation (G19, G25).

  python -m eegpipe.runner.select --config configs/pipeline.json --out outputs/selection [--root .]

Generic version of the P300 project's ``tools/select_stage2_sessions.py`` @ cd5db15 (rule D-016).
Nothing here opens a recording: the data parts come from ``adapter.dataset_parts`` (names only).
Rule (settings section ``selection``):
  1. a part is ineligible if its participant is a development participant (G19: development
     data never enter the confirmatory test), if it contains an excluded file, or if the
     optional label-free ``adapter.eligible(part) -> (bool, reason)`` says so; every reason
     is recorded;
  2. per participant independently: eligible parts sorted as strings; k =
     default_rng([seed, number(P)]).integers(0, n_P), number(P) = the participant id's digits
     (natural order; ids without digits get their position in natural order); one generator per
     participant, so one participant's draw does not depend on the others;
  3. roles: "confirmatory", "reported_separately" (``reported_separately``: in the tables, never
     in a test), "development_excluded".
Output: a new folder (G9) with selection.json (``chosen_parts`` and ``stage2_parts`` with
participant, part, role, files), parts.csv, summary.txt.
"""

import argparse
import csv
import json
import re
from pathlib import Path

import numpy as np

from eegpipe.paired import natural_key
from eegpipe.runner.methods import load_adapter


def participant_number(p, all_ids):
  m = re.findall(r"\d+", str(p))
  if m:
    return int(m[-1])
  return sorted(all_ids, key=natural_key).index(p)


def evaluate(parts, sel, adapter=None):
  dev = set(sel.get("development_participants", []))
  excl = set(sel.get("excluded_files", []))
  rows = []
  for prt in sorted(parts, key=lambda r: natural_key(r["part"])):
    reasons = []
    if prt["participant"] in dev:
      reasons.append("development participant (G19)")
    bad = [f for f in prt["files"] if f"{prt['part']}/{f}" in excl or f in excl]
    if bad:
      reasons.append(f"excluded file(s) {bad}")
    if adapter is not None and hasattr(adapter, "eligible"):
      ok, why = adapter.eligible(prt)
      if not ok:
        reasons.append(f"adapter: {why}")
    rows.append({"participant": prt["participant"], "part": prt["part"], "files": list(prt["files"]),
                 "eligible": not reasons, "reasons": " ; ".join(reasons)})
  return rows


def draw(rows, seed):
  ids = sorted({r["participant"] for r in rows}, key=natural_key)
  out = []
  for p in ids:
    elig = sorted(r["part"] for r in rows if r["participant"] == p and r["eligible"])
    if not elig:
      out.append((p, [], None, None))
      continue
    k = int(np.random.default_rng([int(seed), participant_number(p, ids)]).integers(0, len(elig)))
    out.append((p, elig, k, elig[k]))
  return out


def role_of(p, sel):
  if p in set(sel.get("development_participants", [])):
    return "development_excluded"
  return "reported_separately" if p in set(sel.get("reported_separately", [])) else "confirmatory"


def select(cfg, adapter, root="."):
  from eegpipe.runner.methods import data_root
  sel = cfg["selection"]
  rows = evaluate(adapter.dataset_parts(data_root(cfg, root)), sel, adapter)
  draws = draw(rows, sel["seed"])
  if any(c is not None and role_of(p, sel) == "development_excluded" for p, _, _, c in draws):
    raise RuntimeError("a development participant was drawn")
  files_of = {r["part"]: r["files"] for r in rows}
  stage2 = [{"participant": p, "part": c, "role": role_of(p, sel), "files": files_of[c]} for p, _, _, c in draws if c]
  return {"rule": {"seed": sel["seed"], "draw": "sorted(eligible_P)[default_rng([seed, number(P)]).integers(0, n_P)]",
                   "development_participants": sel.get("development_participants", []),
                   "excluded_files": sel.get("excluded_files", []),
                   "reported_separately": sel.get("reported_separately", [])},
          "chosen_parts": [s["part"] for s in stage2], "stage2_parts": stage2,
          "draws": [{"participant": p, "eligible_sorted": e, "draw_index": k, "chosen": c} for p, e, k, c in draws],
          "excluded": {r["part"]: r["reasons"] for r in rows if not r["eligible"]}}


def main(argv=None):
  from eegharness.outputs import ComputeTimer, new_output_dir, record_compute_time
  ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
  ap.add_argument("--config", required=True)
  ap.add_argument("--out", required=True)
  ap.add_argument("--root", default=".")
  a = ap.parse_args(argv)
  timer = ComputeTimer(device="cpu")
  cfg = json.loads(Path(a.config).read_text())
  res = select(cfg, load_adapter(cfg, a.root), a.root)
  out = new_output_dir(a.out, inputs=[a.config], params={"config": a.config}, root=a.root)
  (out / "selection.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
  with open(out / "parts.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["participant", "part", "role", "n_files"])
    w.writeheader()
    for s in res["stage2_parts"]:
      w.writerow({"participant": s["participant"], "part": s["part"], "role": s["role"], "n_files": len(s["files"])})
  (out / "summary.txt").write_text(json.dumps({k: res[k] for k in ("rule", "chosen_parts", "excluded")}, indent=1) + "\n")
  record_compute_time(out, timer)
  print(f"written: {out}")
  return out


if __name__ == "__main__":
  main()
