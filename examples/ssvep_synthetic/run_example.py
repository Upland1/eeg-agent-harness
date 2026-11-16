"""Worked example: a synthetic 5-class SSVEP study, from recordings to a cited write-up, on CPU.

It builds a throwaway project the way the agents build a real one (vendored ``eegpipe`` and
``eegharness``, an adapter, committed settings, a frozen selection), then runs the pipeline's
deterministic steps:

  1. data      : 1 development + N confirmatory participants, one session each, two runs ("A", "B"),
                 8 trials of 4 s per class and run at 256 Hz on 8 channels; a sinusoid at the class
                 frequency (with its 2nd harmonic) in white noise, amplitude drawn per participant
                 (``eegpipe.testing.synth``);
  2. settings  : ``configs/pipeline.json`` from the ``ssvep`` profile, every required value with a
                 source; primary FBCSP+FBCCA -> shrinkage LDA, comparator training-free FBCCA;
                 networks off (CPU only); committed;
  3. select    : ``eegpipe.runner.select`` (the development participant is never drawn), written
                 into ``configs/selection/`` and committed: the freeze;
  4. stage     : ``eegpipe.runner.stage`` runs every selected part at the frozen commit, in child
                 processes, with provenance and compute time;
  5. collect   : ``eegpipe.runner.collect``: paired Wilcoxon / sign test / Hodges-Lehmann with a
                 bootstrap interval, Holm over the primary;
  6. numbers   : a committed ``eegharness.numbers`` spec, ``derive``, a short ``results.md`` whose
                 every number is a ``[num:key]`` citation, and ``check``.

    python examples/ssvep_synthetic/run_example.py <new project dir> [--participants 8] [--seed 20261116]

Takes about 2-4 min on a laptop CPU with the defaults. Prints the results and the check; exits 1 if
the check fails. Needs numpy, scipy, scikit-learn (no torch, no MNE) and git.
"""

import argparse
import copy
import csv
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

KIT = Path(__file__).resolve().parents[2]
TOOLS = KIT / "tools"
sys.path.insert(0, str(TOOLS))
from eegpipe import settings as st  # noqa: E402
from eegpipe.testing import synth  # noqa: E402

FS = 256.0
FREQS = [8.0, 10.0, 12.0, 15.0, 20.0]
CLASSES = [f"{f:g}Hz" for f in FREQS]
CHANNELS = [f"C{i}" for i in range(8)]
RUNS = ("A", "B")
TRIALS_PER_CLASS = 8          # per run
PRIMARY = "f1/fbcsp+fbcca/Shrinkage-LDA lsqr"
COMPARATOR = "ssvep/fbcca"
SOURCE = "example: synthetic study (examples/ssvep_synthetic/run_example.py)"

ADAPTER = '''"""Adapter of the synthetic example: recordings are .npz files with the eegpipe event table."""
from pathlib import Path

import numpy as np


def dataset_parts(root):
  root = Path(root)
  out = []
  for p in sorted(d.name for d in root.iterdir() if d.is_dir()):
    files = sorted(f"{p}/{f.name}" for f in (root / p).glob("*.npz"))
    out.append({"participant": p, "part": p, "files": files})
  return out


def read(path):
  z = np.load(path)
  return z["data"], float(z["fs"]), [str(c) for c in z["ch"]]


def events(path, data, fs, ch, settings):
  z = np.load(path)
  return {k: z[k] for k in ("onset", "unit", "label", "unit_start", "unit_end", "code")}


def condition_of(path):
  return Path(path).stem
'''


def git(proj, *args):
  return subprocess.run(["git", "-C", str(proj), "-c", "user.name=example", "-c", "user.email=example@localhost", *args],
                        capture_output=True, text=True, check=True).stdout.strip()


def write_data(proj, n_participants, seed):
  """P00 = development; P01..PN confirmatory. Amplitude (x noise SD) drawn per participant."""
  rng = np.random.default_rng(seed)
  amps = {}
  for i in range(n_participants + 1):
    p = f"P{i:02d}"
    amp = float(rng.uniform(0.03, 0.12))
    amps[p] = amp
    for r, run in enumerate(RUNS):
      data, ev, info = synth.recording(seed + 100 * i + r, fs=FS, n_channels=len(CHANNELS),
                                       n_units=5 * TRIALS_PER_CLASS, n_epochs=1, tail=int(4 * FS), rest=int(FS),
                                       lead=int(4 * FS), scheme="per_unit", n_classes=5, effect="ssvep", amp=amp,
                                       noise=1.0, freqs=FREQS, harmonics=2)
      path = proj / "data" / "raw" / p / f"{run}.npz"
      path.parent.mkdir(parents=True, exist_ok=True)
      np.savez(path, data=data, fs=FS, ch=np.array(info["ch_names"]), **ev)
  return amps


def settings(selection_output=None):
  cfg = st.from_profile("ssvep", {
    "settings_version": 1, "description": "synthetic 5-class SSVEP worked example", "classes": CLASSES,
    "fs_hz": FS, "channels": CHANNELS, "units": "arbitrary (synthetic, noise SD 1)", "adapter": "adapter",
    "data_root": "data/raw", "comparator": COMPARATOR,
    "folds": {"n_folds": 4, "seed": 20261107, "balance_by_label": True},
    "selection": {"seed": 20261111, "development_participants": ["P00"], "excluded_files": [],
                  "reported_separately": []},
    "stage": {"name": "confirmation", "scope": "main", "scopes": {"main": {}}, "selection_output": selection_output,
              "tracked": ["eegpipe", "eegharness", "configs", "adapter.py"], "retry": {"max_attempts": 2},
              "job_timeout_hours": 0.5, "dataset_part": None, "part": None},
  })
  ep = synth.erp_settings(FS)
  ep.pop("classes")
  ep["rejection"].update(enabled=False, window_s=[0.0, 4.0], window_rounding="floor")
  ep["bandpass"].update(band_hz=[1.0, 90.0], numtaps=257, padlen=771)
  ep["epoch"] = {"window_s": [0.0, 4.0], "window_rounding": "floor", "decim": 1}
  ep["span_gates"], ep["window_gates"] = [], [{"name": "stimulation_window", "window_s": [0.0, 4.0],
                                                "window_rounding": "floor"}]
  cfg["epochs"] = ep
  cfg["ssvep"]["stimulus_freqs_hz"] = FREQS
  cfg["ssvep"]["filterbank"]["window_s"] = [0.0, 4.0]
  f1 = cfg["f1"]
  f1["enabled"] = True
  f1["feature_spaces"], f1["model_order"] = ["fbcsp+fbcca"], ["Shrinkage-LDA lsqr"]
  f1["models"] = {"Shrinkage-LDA lsqr": f1["models"]["Shrinkage-LDA lsqr"]}
  f1["models"]["Shrinkage-LDA lsqr"]["params"]["priors"] = [0.2] * 5
  f1["fbcca"].update(fs_hz=FS, stimulus_freqs_hz=FREQS)
  cfg["networks"]["enabled"] = False
  cfg.pop("network_input", None)
  cfg["permutation"].update(methods=[], n_permutations=0, n_jobs=1)
  s = cfg["statistics"]
  s["holm_family"], s["min_n"] = [PRIMARY], 5
  s["bootstrap"]["n_resamples"] = 2000
  s["holm_missing_p_source"] = "family of 1"
  cfg["sources"] = {k: SOURCE for k in st.required_sources(cfg)}
  return cfg


NUMBERS_SPEC = lambda stats: {"numbers": [  # noqa: E731
  {"key": "n", "op": "value", "decimals": 0, "a": {"csv": f"{stats}/tests.csv", "where": {"method": PRIMARY}, "column": "n"}},
  {"key": "p_holm", "op": "value", "decimals": 4,
   "a": {"csv": f"{stats}/tests.csv", "where": {"method": PRIMARY}, "column": "p_holm"}},
  *[{"key": k, "op": "pp", "decimals": 1, "unit": "pp",
     "a": {"csv": f"{stats}/tests.csv", "where": {"method": PRIMARY}, "column": c}}
    for k, c in (("hl_pp", "hodges_lehmann"), ("hl_low_pp", "hl_ci_low"), ("hl_high_pp", "hl_ci_high"))],
  *[{"key": k, "op": "value", "decimals": 0, "a": {"csv": f"{stats}/tests.csv", "where": {"method": PRIMARY}, "column": k}}
    for k in ("n_positive", "n_negative", "n_zero_differences")],
  {"key": "ba_primary_mean_frac", "op": "mean", "decimals": 4,
   "rows": {"csv": f"{stats}/participants.csv", "where": {"method": PRIMARY, "role": "confirmatory"}, "column": "ba"}},
  {"key": "ba_primary_mean", "op": "pp", "decimals": 1, "unit": "%", "a": {"key": "ba_primary_mean_frac"}},
  {"key": "ba_comparator_mean_frac", "op": "mean", "decimals": 4,
   "rows": {"csv": f"{stats}/participants.csv", "where": {"method": COMPARATOR, "role": "confirmatory"}, "column": "ba"}},
  {"key": "ba_comparator_mean", "op": "pp", "decimals": 1, "unit": "%", "a": {"key": "ba_comparator_mean_frac"}},
]}


def main(argv=None):
  ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  ap.add_argument("dest", help="a new (empty or missing) folder for the example project")
  ap.add_argument("--participants", type=int, default=8, help="confirmatory participants (plus 1 development)")
  ap.add_argument("--seed", type=int, default=20261116)
  a = ap.parse_args(argv)
  proj = Path(a.dest).resolve()
  if proj.exists() and any(proj.iterdir()):
    sys.exit(f"{proj} is not empty")
  t0 = time.time()
  py = sys.executable
  step = lambda m: print(f"[{time.time() - t0:6.1f} s] {m}", flush=True)  # noqa: E731

  step("1 data and project")
  proj.mkdir(parents=True, exist_ok=True)
  for pkg in ("eegpipe", "eegharness"):
    shutil.copytree(TOOLS / pkg, proj / pkg, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
  (proj / "adapter.py").write_text(ADAPTER)
  (proj / ".gitignore").write_text("data/\noutputs/\n__pycache__/\n")
  amps = write_data(proj, a.participants, a.seed)
  (proj / "configs").mkdir()
  cfg = settings()
  st.validate(cfg)
  (proj / "configs" / "pipeline.json").write_text(json.dumps(cfg, indent=1))
  git(proj, "init", "-q", "-b", "main")
  git(proj, "add", "-A")
  git(proj, "commit", "-qm", "example: project, adapter and settings")

  step("2 select and freeze")
  run = lambda mod, *args: subprocess.run([py, "-m", mod, *args], cwd=proj, check=True, capture_output=True, text=True)  # noqa: E731
  run("eegpipe.runner.select", "--config", "configs/pipeline.json", "--out", "configs/selection", "--root", ".")
  sel_dir = sorted((proj / "configs" / "selection").iterdir())[-1]
  cfg = settings(str(sel_dir.relative_to(proj)))
  (proj / "configs" / "pipeline.json").write_text(json.dumps(cfg, indent=1))
  git(proj, "add", "-A")
  git(proj, "commit", "-qm", "freeze: selection and settings")
  frozen = git(proj, "rev-parse", "--short", "HEAD")

  step(f"3 stage at the frozen commit {frozen} ({a.participants} parts)")
  run("eegpipe.runner.stage", "--config", "configs/pipeline.json", "--out", "outputs/stage", "--root", ".")
  stage_root = sorted(p for p in (proj / "outputs" / "stage").iterdir() if p.is_dir())[-1]

  step("4 collect")
  run("eegpipe.runner.collect", "--stage", str(stage_root.relative_to(proj)), "--out", "outputs/stats", "--root", ".")
  stats = sorted(p for p in (proj / "outputs" / "stats").rglob("tests.csv"))[-1].parent

  step("5 numbers")
  (proj / "configs" / "numbers.json").write_text(json.dumps(NUMBERS_SPEC(str(stats.relative_to(proj))), indent=1))
  git(proj, "add", "configs/numbers.json")
  git(proj, "commit", "-qm", "numbers spec")
  run("eegharness.numbers", "derive", "--spec", "configs/numbers.json", "--out", "outputs/numbers", "--root", ".")
  numbers = sorted((proj / "outputs" / "numbers").iterdir())[-1]
  vals = {r["key"]: r["text"] for r in csv.DictReader(open(numbers / "numbers.csv"))}
  report = (f"# Results (synthetic example)\n\n"
            f"Primary {PRIMARY} against {COMPARATOR}, n = {vals['n']} [num:n] participants: Hodges-Lehmann "
            f"difference {vals['hl_pp']} [num:hl_pp] (95 % bootstrap interval {vals['hl_low_pp']} [num:hl_low_pp] to "
            f"{vals['hl_high_pp']} [num:hl_high_pp]); {vals['n_positive']} [num:n_positive] positive, {vals['n_negative']} "
            f"[num:n_negative] negative, {vals['n_zero_differences']} [num:n_zero_differences] zero differences; Holm p = {vals['p_holm']} [num:p_holm]. Mean balanced accuracy "
            f"{vals['ba_primary_mean']} [num:ba_primary_mean] against {vals['ba_comparator_mean']} "
            f"[num:ba_comparator_mean].\n")
  (proj / "results.md").write_text(report)
  chk = subprocess.run([py, "-m", "eegharness.numbers", "check", "--numbers", str(numbers), "--report", "results.md"],
                       cwd=proj, capture_output=True, text=True)

  step("done")
  print(f"\nproject   {proj}\nfrozen    {frozen}\nstage     {stage_root.relative_to(proj)}\n"
        f"stats     {stats.relative_to(proj)}\nnumbers   {numbers.relative_to(proj)}\n"
        f"amplitudes {json.dumps({k: round(v, 3) for k, v in amps.items()})}\n\n{report}\ncheck: {chk.stdout.strip()}")
  return chk.returncode


if __name__ == "__main__":
  sys.exit(main())
