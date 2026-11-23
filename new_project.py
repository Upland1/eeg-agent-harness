"""Create (or update) a project from the harness kit.

  python new_project.py DEST --name NAME                      # harness project
  python new_project.py DEST --name NAME --update             # refresh harness files, keep work
  python new_project.py DEST --name NAME --eval-dir EVAL --case EVAL/cases/<case>          # evaluation, harness arm
  python new_project.py DEST --name NAME --eval-dir EVAL --case EVAL/cases/<case> --control  # evaluation, control arm

Recordings are never copied by this script: put them in DEST/data/raw/ yourself.
"""

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

KIT = Path(__file__).resolve().parent
EXCLUDE_HARNESS = ["CLAUDE.md", "CLAUDE.local.md", ".claude/", ".harness/", "agent_runs/"]
EXCLUDE_CONTROL = ["CLAUDE.local.md", ".claude/"]


def kit_version(allow_dirty: bool, strict: bool) -> dict:
  version = (KIT / "VERSION").read_text().strip()
  info = {"version": version, "git": None, "dirty": None}
  if (KIT / ".git").exists():
    git = lambda *a: subprocess.run(["git", "-C", str(KIT), *a], capture_output=True, text=True).stdout.strip()
    info["git"] = git("describe", "--tags", "--always", "--dirty")
    info["dirty"] = bool(git("status", "--porcelain"))
    tag_ok = git("tag", "--points-at", "HEAD") != ""
  else:
    tag_ok = False
  if strict and (info["dirty"] is not False or not tag_ok) and not allow_dirty:
    sys.exit(f"harness kit is not a clean, tagged commit ({info}); evaluation projects need a frozen "
             f"version. Commit and tag the kit (git tag v{version}), or pass --allow-dirty for a dry run.")
  return info


def ensure_git(dest: Path, exclude_lines):
  if not (dest / ".git").exists():
    subprocess.run(["git", "init", "-q", "-b", "main", str(dest)], check=True)
  ex = dest / ".git" / "info" / "exclude"
  ex.parent.mkdir(parents=True, exist_ok=True)
  have = ex.read_text().splitlines() if ex.exists() else []
  add = [l for l in exclude_lines if l not in have]
  if add:
    ex.write_text("\n".join(have + ["# local only, never committed"] + add) + "\n")


def settings(eval_dir) -> dict:
  s = json.loads((KIT / "template" / ".claude" / "settings.json").read_text())
  if eval_dir:
    p = "/" + str(Path(eval_dir).resolve())  # "//abs/path" = absolute path rule
    s["permissions"] = {"deny": [f"{t}({p}/**)" for t in ("Read", "Edit", "Write")]}
  return s


def make_data_and_inputs(dest: Path):
  """data/ (recordings go in data/raw/, a folder or a symlink) and inputs/ exist in every project (L41)."""
  for d in ("data", "inputs"):
    (dest / d).mkdir(exist_ok=True)


def copy_inputs(case, dest: Path):
  make_data_and_inputs(dest)
  if not case:
    return
  src = Path(case) / "inputs"
  if not src.is_dir():
    sys.exit(f"{src} not found")
  for f in src.iterdir():
    if f.is_file():
      shutil.copy2(f, dest / "inputs" / f.name)


def write_build(dest: Path, info: dict, mode: str, eval_dir, case):
  cfg = {"mode": mode, "harness": info, "created": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
  if eval_dir:
    cfg["eval_dir"] = str(Path(eval_dir).resolve())
  if case:
    cfg["case"] = Path(case).name
  (dest / ".claude").mkdir(exist_ok=True)
  hj = dest / ".claude" / "harness.json"
  if hj.exists():  # keep the project's own local settings (e.g. the eegharness.sources names list) on --update
    try:
      old = json.loads(hj.read_text())
    except ValueError:
      old = {}
    if isinstance(old, dict) and "sources" in old:
      cfg["sources"] = old["sources"]
  hj.write_text(json.dumps(cfg, indent=1) + "\n")


def make_control(dest: Path, a, info):
  (dest / ".claude" / "hooks").mkdir(parents=True, exist_ok=True)
  # only protection; tokens and time come from the transcripts after the run (cost_report.py),
  # so nothing in the control arm's setup or behaviour changes
  shutil.copy2(KIT / "template" / ".claude" / "hooks" / "guard.py", dest / ".claude" / "hooks" / "guard.py")
  s = settings(a.eval_dir)
  for event in ("PostToolUse", "SubagentStop", "Stop"):
    s["hooks"].pop(event, None)
  (dest / ".claude" / "settings.json").write_text(json.dumps(s, indent=2) + "\n")
  write_build(dest, info, "control", a.eval_dir, a.case)
  copy_inputs(a.case, dest)
  ensure_git(dest, EXCLUDE_CONTROL)


VENDORED = ("eegharness", "eegpipe")


def vendor(dest: Path) -> bool:
  """Copy tools/eegharness and tools/eegpipe into the project (committed code, L11; G24). True if
  either changed."""
  return any([_vendor_one(dest, name) for name in VENDORED])


def _vendor_one(dest: Path, name: str) -> bool:
  src, dst = KIT / "tools" / name, dest / name
  ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
  if dst.exists():
    files = [f for f in src.rglob("*") if f.is_file() and "__pycache__" not in f.parts and f.suffix != ".pyc"]
    have = [f for f in dst.rglob("*") if f.is_file() and "__pycache__" not in f.parts and f.suffix != ".pyc"]
    same = all((dst / f.relative_to(src)).is_file() and (dst / f.relative_to(src)).read_bytes() == f.read_bytes()
               for f in files) and len(have) == len(files)
    if same:
      return False
    shutil.rmtree(dst)
  shutil.copytree(src, dst, ignore=ignore)
  return True


def first_commit(dest: Path, info: dict):
  """Commit the project skeleton on main, so agents start from a clean tree."""
  paths = [p for p in (".gitignore", "README.md", "docs/DECISIONS.md", "docs/COMPUTE.md", "tests/conftest.py", "eegharness",
                       "eegpipe", "inputs")
           if (dest / p).exists()]
  git = ["git", "-C", str(dest)]
  subprocess.run(git + ["add", "--", *paths], check=True)
  r = subprocess.run(git + ["commit", "-q", "-m", f"chore: project skeleton (eegharness {info['version']})"],
                     capture_output=True, text=True)
  if r.returncode != 0:
    print(f"could not make the first commit ({r.stderr.strip() or r.stdout.strip()}); "
          f"commit {', '.join(paths)} yourself before /onboard.")


def make_harness(dest: Path, a, info):
  t = KIT / "template"
  claude = dest / ".claude"
  for sub in ("agents", "skills", "hooks"):
    if (claude / sub).exists():
      shutil.rmtree(claude / sub)
    shutil.copytree(t / ".claude" / sub, claude / sub)
  (claude / "settings.json").write_text(json.dumps(settings(a.eval_dir), indent=2) + "\n")
  write_build(dest, info, "harness", a.eval_dir, a.case)
  text = (t / "CLAUDE.md").read_text().replace("{{PROJECT}}", a.name).replace("{{HARNESS_VERSION}}", info["version"])
  (dest / "CLAUDE.md").write_text(text)
  runs = dest / "agent_runs"
  runs.mkdir(exist_ok=True)
  shutil.copy2(t / "agent_runs" / "README.md", runs / "README.md")
  if (runs / "_templates").exists():
    shutil.rmtree(runs / "_templates")
  shutil.copytree(t / "agent_runs" / "_templates", runs / "_templates")
  h = dest / ".harness"
  if h.exists():
    shutil.rmtree(h)
  shutil.copytree(KIT / "tools", h / "tools", ignore=shutil.ignore_patterns("tests", "__pycache__", ".pytest_cache"))
  shutil.copy2(KIT / "VERSION", h / "VERSION")
  (h / "build.json").write_text(json.dumps(info, indent=1) + "\n")
  for d in ("docs", "readers", "tests"):
    (dest / d).mkdir(exist_ok=True)
  vendored = vendor(dest)
  if not (dest / "tests" / "conftest.py").exists():
    shutil.copy2(t / "tests" / "conftest.py", dest / "tests" / "conftest.py")
  for doc in ("DECISIONS.md", "COMPUTE.md"):
    if not (dest / "docs" / doc).exists():
      shutil.copy2(t / "docs" / doc, dest / "docs" / doc)
  if not (dest / ".gitignore").exists():
    shutil.copy2(t / "gitignore", dest / ".gitignore")
  if not (dest / "README.md").exists():
    (dest / "README.md").write_text(f"# {a.name}\n")
  copy_inputs(a.case, dest)
  fresh = not (dest / ".git").exists()
  ensure_git(dest, EXCLUDE_HARNESS)
  if fresh:
    first_commit(dest, info)
  elif vendored:
    print(f"eegharness/ and eegpipe/ were updated to {info['version']}: review and commit them (git add eegharness eegpipe).")


def main(argv=None):
  ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  ap.add_argument("dest")
  ap.add_argument("--name", required=True)
  ap.add_argument("--control", action="store_true", help="control arm: no harness, only leak/recording protection")
  ap.add_argument("--eval-dir", help="evaluation folder (answer keys, policies); made unreachable for agents")
  ap.add_argument("--case", help="evaluation case folder; its inputs/ are copied to the project")
  ap.add_argument("--update", action="store_true", help="refresh harness files of an existing project")
  ap.add_argument("--allow-dirty", action="store_true")
  a = ap.parse_args(argv)
  dest = Path(a.dest).resolve()
  if dest.exists() and any(dest.iterdir()) and not a.update:
    sys.exit(f"{dest} is not empty; use --update to refresh the harness files of an existing project")
  if a.eval_dir and (dest == Path(a.eval_dir).resolve() or Path(a.eval_dir).resolve() in dest.parents):
    sys.exit("the project must not be inside the evaluation folder")
  dest.mkdir(parents=True, exist_ok=True)
  info = kit_version(a.allow_dirty, strict=bool(a.eval_dir))
  (make_control if a.control else make_harness)(dest, a, info)
  print(f"{'control' if a.control else 'harness'} project ready: {dest} (harness {info})")
  print(f"next: put the recordings in {dest / 'data' / 'raw'}/ (a folder, or a symlink to it)")
  print(f"next: create the project's own interpreter (L43; the test hook runs .venv/bin/python):\n"
        f"  python3 -m venv {dest / '.venv'} && {dest / '.venv' / 'bin' / 'pip'} install -r {KIT / 'requirements.txt'}")
  if not a.control:
    print(f"next: set cpu_working_threads in {dest / 'docs' / 'COMPUTE.md'} (no default; L39)")
  print(f"next: open Claude Code in {dest}" + ("" if a.control else " and run /onboard"))


if __name__ == "__main__":
  main()
