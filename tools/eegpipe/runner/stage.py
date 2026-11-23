"""Stage runner: every selected data part x every family part, resumable, from a frozen commit (G22, G25).

  python -m eegpipe.runner.stage --config configs/pipeline.json --out outputs/stage2 [--parts all|cpu|gpu]
         [--data-parts P1,P2] [--dry-run] [--rerun-after-provenance PART|FAMILY] [--root .]

Generic version of the P300 project's ``scripts/run_stage2.py`` @ cd5db15 (design D-016, audits
C4/C4b), unchanged in behaviour:
  * data parts: ``stage2_parts`` of the selection output named in ``stage.selection_output``
    (eegpipe.runner.select); a list holding a development participant or an excluded file is
    refused;
  * scope: ``stage.scope`` names an entry of ``stage.scopes``, a set of dotted-key overrides of
    existing keys only (no silent new keys, G5);
  * family parts, one process each (a crash loses at most one part; every GPU job stays short):
    ``classical`` (CPU), ``f3`` (CPU), ``f2__<model>`` (GPU), ``f4__<model>`` (GPU), each run as
    ``python -m eegpipe.runner.methods`` with its own part config;
  * root ``<out>/<scope>_<key12>_<commit>/`` (key = sha256 of the settings and the selection);
    a rerun at the same commit reuses it and SKIPS every terminal part (done with the same
    part-config hash, or failed/timed out ``retry.max_attempts`` times); a new commit or
    settings gives a new root (G9);
  * the tracked code (``stage.tracked``) must be clean; HEAD and the tree are checked before and
    after every job; every finished part's results.json must report the root commit, a clean
    tree, a config hash equal to its part config, and epochs/folds hashes identical across the
    parts of a data part; any mismatch stops the run ("provenance_mismatch",
    "tree_changed_during_job"); a provenance failure is never retried automatically: the
    orchestrator reruns it at the same commit with ``--rerun-after-provenance`` (logged) or
    abandons the run; provenance attempts do not count towards the retry limit;
  * frozen retry rule: a failed or timed-out part is retried at once, at most
    ``retry.max_attempts`` attempts in total (across invocations), then it is terminal;
  * a timed-out part (``stage.job_timeout_hours``) is killed with its whole process group;
  * every attempt is recorded before its job starts (status ``running``, attempt number, stage pid);
    a part found ``running`` with no live stage process (the stage was killed from outside, e.g. for
    low memory) is recorded as ``interrupted`` before anything else runs; interrupted attempts count
    in ``n_attempts`` and toward ``retry.max_attempts``, and the index lists them (0.6.0, L49);
  * single machine only: roots are never merged.
"""

import argparse
import copy
import csv
import datetime as dt
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

STATUS_DONE, STATUS_FAILED, STATUS_TIMEOUT = "done", "failed", "timeout"
STATUS_MISMATCH, STATUS_TREE = "provenance_mismatch", "tree_changed_during_job"
PROVENANCE_STATUSES = (STATUS_MISMATCH, STATUS_TREE)
STATUS_RUNNING, STATUS_INTERRUPTED = "running", "interrupted"
RETRY_STATUSES = (STATUS_FAILED, STATUS_TIMEOUT, STATUS_INTERRUPTED)


def canonical(obj):
  return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256(text):
  return hashlib.sha256(text.encode() if isinstance(text, str) else text).hexdigest()


def git_state(root, tracked):
  def run(*args):
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True).stdout.strip()
  commit = run("rev-parse", "--short", "HEAD")
  dirty = run("status", "--porcelain", "--", *tracked)
  return commit or "nocommit", bool(dirty)


def _get(d, dotted):
  for k in dotted.split("."):
    d = d[k]
  return d


def _set(d, dotted, value):
  keys = dotted.split(".")
  for k in keys[:-1]:
    d = d[k]
  if keys[-1] not in d:
    raise KeyError(dotted)
  d[keys[-1]] = value


def scoped_config(template):
  st = template["stage"]
  if st["scope"] not in st["scopes"]:
    raise ValueError(f"stage.scope {st['scope']!r} not among {sorted(st['scopes'])}")
  cfg = copy.deepcopy(template)
  for key, val in st["scopes"][st["scope"]].items():
    try:
      _get(cfg, key)
    except KeyError:
      raise KeyError(f"scope override {key!r} is not a key of the settings") from None
    _set(cfg, key, copy.deepcopy(val))
  return cfg


def part_names(cfg):
  out = []
  if cfg.get("f1", {}).get("enabled", True) or cfg.get("baseline") or cfg.get("ssvep", {}).get("enabled"):
    out.append("classical")
  f3 = cfg.get("f3", {})
  if f3.get("enabled") and (f3["classification"]["order"] or f3["condition_level"].get("enabled")):
    out.append("f3")
  if cfg.get("networks", {}).get("enabled"):
    out += [f"f2__{m}" for m in cfg["networks"]["order"]]
  if cfg.get("f4", {}).get("enabled"):
    out += [f"f4__{m}" for m in cfg["f4"]["order"]]
  return out


def is_gpu(part):
  return part.startswith(("f2__", "f4__"))


def part_config(cfg, part, data_part, role, template_sha):
  c = copy.deepcopy(cfg)
  c["stage"] = {**c["stage"], "part": part, "dataset_part": data_part, "role": role, "template_sha256": template_sha}
  if "networks" in c:
    c["networks"]["enabled"] = part.startswith("f2__")
    if part.startswith("f2__"):
      c["networks"]["order"] = [part[4:]]
  if "f4" in c:
    c["f4"]["enabled"] = part.startswith("f4__")
    if part.startswith("f4__"):
      c["f4"]["order"] = [part[4:]]
  if "f3" in c:
    c["f3"]["enabled"] = part == "f3"
  return c


def slug(s):
  return str(s).replace("/", "__")


def load_selection(cfg, root):
  so = cfg["stage"].get("selection_output")
  if not so:
    raise ValueError("stage.selection_output is not set: run eegpipe.runner.select and set it (freeze)")
  p = Path(so) if Path(so).is_absolute() else Path(root) / so
  raw = (p / "selection.json").read_bytes()
  sel = json.loads(raw)
  dev = set(cfg["selection"].get("development_participants", []))
  excl = set(cfg["selection"].get("excluded_files", []))
  for r in sel["stage2_parts"]:
    if r["participant"] in dev:
      raise ValueError(f"selection contains the development participant {r['participant']}")
    for name in r["files"]:
      if f"{r['part']}/{name}" in excl or name in excl:
        raise ValueError(f"selection contains the excluded file {r['part']}/{name}")
  if [r["part"] for r in sel["stage2_parts"]] != sel["chosen_parts"]:
    raise ValueError("selection.json chosen_parts and stage2_parts disagree")
  return sel, raw


def read_json(p):
  try:
    return json.loads(Path(p).read_text())
  except (OSError, ValueError, TypeError):
    return None


def is_terminal(st, commit, part_sha, max_attempts):
  if not st or st.get("commit") != commit or st.get("part_config_sha256") != part_sha:
    return False, False
  done = bool(st.get("status") == STATUS_DONE and st.get("outdir") and (Path(st["outdir"]) / "summary.txt").is_file())
  counted = int(st.get("n_counted_attempts", st.get("n_attempts", 0)))
  exhausted = st.get("status") in RETRY_STATUSES and counted >= max_attempts
  return done or exhausted, done


def stage_alive(pid):
  """True if ``pid`` is a live stage runner process (a reused pid of another program is not)."""
  try:
    os.kill(int(pid), 0)
  except (OSError, TypeError, ValueError):
    return False
  try:
    cmd = Path(f"/proc/{int(pid)}/cmdline").read_bytes().replace(b"\0", b" ")
  except OSError:
    return True  # no /proc: trust the live pid
  return b"eegpipe.runner.stage" in cmd


def mark_interrupted(root, pdir):
  """A part left ``running`` by a stage process that no longer exists becomes ``interrupted`` (L49)."""
  st = read_json(pdir / "part_status.json")
  if not st or st.get("status") != STATUS_RUNNING:
    return st
  if stage_alive(st.get("stage_pid")):
    raise RuntimeError(f"{pdir}: attempt {st.get('n_attempts')} is running in stage process {st.get('stage_pid')}; "
                       "one stage per root")
  st = {**st, "status": STATUS_INTERRUPTED, "n_interrupted": int(st.get("n_interrupted", 0)) + 1,
        "interrupted_found_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")}
  (pdir / "part_status.json").write_text(json.dumps(st, indent=1))
  with open(root / "attempts.jsonl", "a") as f:
    f.write(json.dumps({"event": "interrupted", **st}) + "\n")
  return st


def verify_child(outdir, commit, part_sha):
  res = read_json(Path(outdir) / "results.json") if outdir else None
  cu = read_json(Path(outdir) / "config_used.json") if outdir else None
  if res is None or cu is None:
    return ["results.json or config_used.json missing"], None, None
  probs = []
  if res.get("commit") != commit:
    probs.append(f"child commit {res.get('commit')} != root commit {commit}")
  if res.get("tracked_files_dirty") is not False:
    probs.append(f"child tracked_files_dirty = {res.get('tracked_files_dirty')}")
  if sha256(canonical(cu)) != part_sha:
    probs.append("config_used.json differs from the part config")
  if not res.get("epochs_sha256") or not res.get("folds_sha256"):
    probs.append("epochs_sha256/folds_sha256 missing")
  return probs, res.get("epochs_sha256"), res.get("folds_sha256")


def run_job(cmd, log_path, timeout_s, cwd):
  t0 = time.time()
  with open(log_path, "w") as log:
    proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, cwd=str(cwd),
                            env={**os.environ, "PYTHONUNBUFFERED": "1"}, start_new_session=True)
    try:
      rc = proc.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
      _kill_group(proc)
      return STATUS_TIMEOUT, None, time.time() - t0
    except BaseException:
      _kill_group(proc)
      raise
  return (STATUS_DONE if rc == 0 else STATUS_FAILED), rc, time.time() - t0


def _kill_group(proc):
  for sig, wait in ((signal.SIGTERM, 30), (signal.SIGKILL, 30)):
    try:
      os.killpg(proc.pid, sig)
    except ProcessLookupError:
      return
    try:
      proc.wait(timeout=wait)
      return
    except subprocess.TimeoutExpired:
      continue


def write_index(root, plan):
  rows = []
  for s, part in plan:
    st = read_json(root / "parts" / slug(s["part"]) / part / "part_status.json") or {}
    rows.append({"participant": s["participant"], "data_part": s["part"], "role": s["role"], "part": part,
                 "gpu": is_gpu(part), "status": st.get("status", "pending"), "outdir": st.get("outdir", ""),
                 "commit": st.get("commit", ""), "n_attempts": st.get("n_attempts", 0),
                 "n_interrupted": st.get("n_interrupted", 0), "seconds": st.get("seconds", ""),
                 "log": st.get("log", "")})
  if rows:
    with open(root / "index.csv", "w", newline="") as f:
      w = csv.DictWriter(f, fieldnames=list(rows[0]))
      w.writeheader()
      w.writerows(rows)
  (root / "index.json").write_text(json.dumps({"root": str(root), "parts": rows}, indent=1, ensure_ascii=False))


def child_command(cpath, pdir, root):
  return [sys.executable, "-m", "eegpipe.runner.methods", "--config", str(cpath), "--out", str(pdir), "--root", str(root)]


def main(argv=None, git=None, command=child_command):
  ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
  ap.add_argument("--config", required=True)
  ap.add_argument("--out", required=True)
  ap.add_argument("--root", default=".")
  ap.add_argument("--parts", choices=("all", "cpu", "gpu"), default="all")
  ap.add_argument("--data-parts", default="")
  ap.add_argument("--dry-run", action="store_true")
  ap.add_argument("--rerun-after-provenance", action="append", default=[], metavar="PART|FAMILY")
  a = ap.parse_args(argv)
  proj = Path(a.root).resolve()
  template_text = Path(a.config).read_text()
  template = json.loads(template_text)
  cfg = scoped_config(template)
  tracked = cfg["stage"].get("tracked", ["eegpipe", "eegharness", "configs", "readers", "adapter.py"])
  git = git or (lambda: git_state(proj, tracked))
  sel, sel_raw = load_selection(template, proj)
  commit, dirty = git()
  if dirty:
    sys.exit("tracked code or settings are modified: the stage runs only from a clean, frozen commit (G25)")
  template_sha = sha256(canonical(template))
  key = sha256(canonical(template) + "\n" + sha256(sel_raw))
  root = Path(a.out).resolve() / f"{cfg['stage']['scope']}_{key[:12]}_{commit}"
  max_att = int(cfg["stage"]["retry"]["max_attempts"])
  parts_sel = sel["stage2_parts"]
  if a.data_parts:
    want = a.data_parts.split(",")
    unknown = [w for w in want if w not in sel["chosen_parts"]]
    if unknown:
      sys.exit(f"data parts not in the selection: {unknown}")
    parts_sel = [s for s in parts_sel if s["part"] in want]
  fams = part_names(cfg)
  plan_all = [(s, p) for s in sel["stage2_parts"] for p in fams]
  plan = [(s, p) for s in parts_sel for p in fams if a.parts == "all" or (a.parts == "gpu") == is_gpu(p)]
  timeout_s = float(cfg["stage"]["job_timeout_hours"]) * 3600.0
  if a.dry_run:
    for s, p in plan:
      print(f"{s['part']} ({s['role']}) {p}{' [GPU]' if is_gpu(p) else ''}")
    print(f"root: {root}  ({len(plan)} parts)")
    return root
  root.mkdir(parents=True, exist_ok=True)
  meta = {"commit": commit, "tracked_files_dirty": False, "template_sha256": template_sha,
          "selection_sha256": sha256(sel_raw), "key": key, "scope": cfg["stage"]["scope"], "max_attempts": max_att}
  if not (root / "root.json").exists():
    (root / "stage_config.json").write_text(template_text)
    (root / "selection.json").write_bytes(sel_raw)
    (root / "root.json").write_text(json.dumps(meta, indent=1))
  elif read_json(root / "root.json") != meta:
    raise RuntimeError(f"{root} holds a different commit, settings or selection")
  for s, part in plan_all:  # attempts left running by a killed stage (L49), before anything else runs
    pdir0 = root / "parts" / slug(s["part"]) / part
    if (pdir0 / "part_status.json").is_file():
      mark_interrupted(root, pdir0)
  sanctioned = set(a.rerun_after_provenance)
  blocked = []
  for s, part in plan_all:
    st0 = read_json(root / "parts" / slug(s["part"]) / part / "part_status.json")
    if st0 and st0.get("status") in PROVENANCE_STATUSES and f"{s['part']}|{part}" not in sanctioned:
      blocked.append(f"{s['part']}|{part} ({st0['status']})")
  unknown = sorted(sanctioned - {f"{s['part']}|{p}" for s, p in plan_all})
  if unknown:
    sys.exit(f"--rerun-after-provenance names parts not in the plan: {unknown}")
  if blocked:
    sys.exit(f"provenance failure(s) need the orchestrator's decision (rerun with --rerun-after-provenance "
             f"PART|FAMILY at this commit, logged, or abandon the run): {blocked}")
  for k in sorted(sanctioned):
    with open(root / "attempts.jsonl", "a") as f:
      f.write(json.dumps({"event": "rerun_after_provenance", "part_key": k, "commit": commit,
                          "utc": dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")}) + "\n")
  n_failed = 0
  for s, part in plan:
    pdir = root / "parts" / slug(s["part"]) / part
    pdir.mkdir(parents=True, exist_ok=True)
    pcfg = part_config(cfg, part, s["part"], s["role"], template_sha)
    psha = sha256(canonical(pcfg))
    terminal, done = is_terminal(read_json(pdir / "part_status.json"), commit, psha, max_att)
    if terminal:
      print(f"skip ({'done' if done else f'failed after {max_att} attempts'}): {s['part']} {part}", flush=True)
      n_failed += not done
      continue
    cpath = pdir / "part_config.json"
    if cpath.exists() and sha256(canonical(json.loads(cpath.read_text()))) != psha:
      raise RuntimeError(f"{cpath} differs from the part config of this run")
    cpath.write_text(json.dumps(pcfg, indent=1, ensure_ascii=False))
    while True:
      if git() != (commit, False):
        raise RuntimeError(f"HEAD or the tracked tree changed during the run (root commit {commit}); stopped")
      prev = read_json(pdir / "part_status.json") or {}
      before = {d.name for d in pdir.iterdir() if d.is_dir()}
      stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
      n_att = int(prev.get("n_attempts", 0)) + 1
      counted_prev = int(prev.get("n_counted_attempts", prev.get("n_attempts", 0))
                         if prev.get("status") not in PROVENANCE_STATUSES else prev.get("n_counted_attempts", 0))
      log = pdir / f"attempt_{stamp}_{n_att}.log"
      running = {"status": STATUS_RUNNING, "commit": commit, "tracked_files_dirty": False, "part_config_sha256": psha,
                 "log": str(log), "utc_start": stamp, "n_attempts": n_att, "n_counted_attempts": counted_prev + 1,
                 "n_interrupted": int(prev.get("n_interrupted", 0)), "max_attempts": max_att,
                 "stage_pid": os.getpid(), "data_part": s["part"], "participant": s["participant"],
                 "role": s["role"], "part": part}
      (pdir / "part_status.json").write_text(json.dumps(running, indent=1))  # before the job (L49)
      with open(root / "attempts.jsonl", "a") as f:
        f.write(json.dumps({"event": "started", **running}) + "\n")
      print(f"run: {s['part']} {part} -> {log.name}", flush=True)
      status, rc, secs = run_job(command(cpath, pdir, proj), log, timeout_s, proj)
      tree_after = git()
      new = sorted(d for d in pdir.iterdir() if d.is_dir() and d.name not in before)
      outdir = new[-1] if new else None
      if status == STATUS_DONE and (len(new) != 1 or not (outdir / "summary.txt").is_file()):
        status = STATUS_FAILED
      probs, ep_sha, fo_sha = verify_child(outdir, commit, psha) if status == STATUS_DONE else ([], None, None)
      if tree_after != (commit, False):
        final = STATUS_TREE
        probs = [f"HEAD/tree after the job {tree_after} != ({commit!r}, False)"] + probs
      else:
        final = STATUS_MISMATCH if probs else status
      counted = counted_prev + (final not in PROVENANCE_STATUSES)
      st = {"status": final, "returncode": rc, "seconds": secs, "commit": commit, "tracked_files_dirty": False,
            "part_config_sha256": psha, "outdir": str(outdir) if outdir else "", "log": str(log),
            "new_folders": [str(d) for d in new], "utc_start": stamp, "n_attempts": n_att,
            "n_counted_attempts": counted, "n_interrupted": int(prev.get("n_interrupted", 0)), "max_attempts": max_att, "timeout_seconds": timeout_s,
            "provenance_problems": probs, "epochs_sha256": ep_sha, "folds_sha256": fo_sha,
            "data_part": s["part"], "participant": s["participant"], "role": s["role"], "part": part}
      (pdir / "part_status.json").write_text(json.dumps(st, indent=1))
      with open(root / "attempts.jsonl", "a") as f:
        f.write(json.dumps(st) + "\n")
      write_index(root, plan_all)
      if final == STATUS_TREE:
        raise RuntimeError(f"{s['part']} {part}: tree changed during the job: {probs}; stopped")
      if probs:
        raise RuntimeError(f"{s['part']} {part}: provenance check failed: {probs}")
      if status == STATUS_DONE:
        for q in fams:
          o = read_json(root / "parts" / slug(s["part"]) / q / "part_status.json")
          if o and o.get("status") == STATUS_DONE and (o["epochs_sha256"], o["folds_sha256"]) != (ep_sha, fo_sha):
            raise RuntimeError(f"{s['part']}: epochs/folds differ between parts {o['part']} and {part}")
      print(f"{status}: {s['part']} {part} ({secs:.1f} s, attempt {st['n_attempts']} of {max_att})", flush=True)
      if status == STATUS_DONE or counted >= max_att:
        break
    n_failed += status != STATUS_DONE
  write_index(root, plan_all)
  print(f"written: {root}  ({n_failed} part(s) not done)")
  if n_failed:
    sys.exit(1)
  return root


if __name__ == "__main__":
  main()
