"""Known-answer tests for blocked folders (v0.3.1): blocklist.json "dirs" are treated like the
evaluation folder. In v0.3.0 only the evaluation folder was protected against recursive
searches, so `grep -r x data/raw/..` read every sibling of the recordings' folder (the
supervisor's other pipelines and results) when data/raw linked into a shared data folder.

Layout (mirrors the SSVEP demo):
  lab/02_data/Datos/{pipeline/, script.py, DataFolder/S1/a.edf}   data/raw -> DataFolder
  lab/02_data/results/
  lab/04_experiments/{demo, demo-eval, other-eval}
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT))
import new_project  # noqa: E402


def _build(lab: Path, name: str, dirs) -> Path:
  ev = lab / "04_experiments" / f"{name}-eval"
  ev.mkdir(parents=True)
  bl = {"terms": []}  # no terms: the folders alone must do the blocking
  if dirs is not None:
    bl["dirs"] = [str(d) for d in dirs]
  (ev / "blocklist.json").write_text(json.dumps(bl))
  p = lab / "04_experiments" / name
  new_project.main([str(p), "--name", name, "--eval-dir", str(ev), "--allow-dirty"])
  (p / "data").mkdir(exist_ok=True)
  os.symlink(lab / "02_data" / "Datos" / "DataFolder", p / "data" / "raw")
  (p / "src").mkdir(exist_ok=True)
  (p / "src" / "a.py").write_text("x = 1\n")
  return p


@pytest.fixture(scope="module")
def lab(tmp_path_factory):
  lab = tmp_path_factory.mktemp("lab")
  datos = lab / "02_data" / "Datos"
  (datos / "pipeline").mkdir(parents=True)
  (datos / "pipeline" / "run.py").write_text("PLV = 'secret'\n")
  (datos / "script.py").write_text("PLV = 'secret'\n")
  (datos / "DataFolder" / "S1").mkdir(parents=True)
  (datos / "DataFolder" / "S1" / "a.edf").write_bytes(b"x")
  (lab / "02_data" / "results").mkdir()
  (lab / "04_experiments" / "other-eval").mkdir(parents=True)
  dirs = [datos / "pipeline", datos / "script.py", lab / "02_data" / "results", lab / "04_experiments" / "other-eval"]
  return {"lab": lab, "datos": datos, "demo": _build(lab, "demo", dirs), "old": _build(lab, "old", None)}


def guard(project: Path, tool: str, inp: dict, cwd=None):
  ev = {"tool_name": tool, "tool_input": inp, "cwd": str(cwd or project)}
  r = subprocess.run([sys.executable, str(project / ".claude" / "hooks" / "guard.py")],
                     input=json.dumps(ev), capture_output=True, text=True,
                     env={"CLAUDE_PROJECT_DIR": str(project), "PATH": "/usr/bin:/bin", "HOME": "/nonexistent"})
  return r.returncode, r.stderr


BLOCKED_BASH = [
  "grep -r PLV data/raw/..",                      # the reported gap
  "grep -rl PLV data/raw/../",
  "grep -r PLV ../../02_data",                    # 02_data, relative
  "grep -R PLV ../../02_data/Datos",              # Datos, relative
  "rg PLV data/raw/..",
  "find data/raw/.. -name '*.py'",
  "find ../../02_data",
  "ls data/raw/..",                               # plain listing of the parent shows blocked names
  "ls -la ../../02_data/Datos",
  "ls -R ../../02_data",
  "tree data/raw/..",
  "du -a data/raw/..",
  "ls ..",                                        # 04_experiments holds other-eval
  "cd data/raw/.. && grep -r PLV",                # no folder operand: starts in Datos
  "cd data/raw/.. && ls",
  "cd data/raw/.. && find . -name '*.py'",
  "cd ../../02_data && grep -rn PLV .",
  "D=data/raw/..; grep -r PLV $D",
  "bash -c 'grep -r PLV data/raw/..'",
  "cat data/raw/../pipeline/run.py",              # inside a blocked folder, no terms needed
  "cat data/raw/../script.py",                    # a blocked file
  "ls ../../02_data/results",
  "cat ../other-eval/x.md",
]

ALLOWED_BASH = [
  "ls data/raw",
  "ls data/raw/S1",
  "ls -la data/raw/",
  "grep -r PLV data/raw",
  "find data/raw -name '*.edf'",
  "head -c 1 data/raw/S1/a.edf",
  "cd data/raw && ls",
  "cd data/raw && find . -name '*.edf'",
  "grep -rn x src/",
  "find . -name '*.py'",
  "ls",
  "ls -la docs",
  "git status",
]


@pytest.mark.parametrize("cmd", BLOCKED_BASH)
def test_blocked_folders_out_of_reach(lab, cmd):
  """Known answer: searches and listings that start in or above a blocked folder, and paths inside
  one, are blocked (exit 2)."""
  code, err = guard(lab["demo"], "Bash", {"command": cmd})
  assert code == 2 and "blocked" in err, (cmd, err)


@pytest.mark.parametrize("cmd", ALLOWED_BASH)
def test_recordings_and_project_still_reachable(lab, cmd):
  """Known answer: the recordings' own folder and the project stay searchable (exit 0)."""
  code, err = guard(lab["demo"], "Bash", {"command": cmd})
  assert code == 0, (cmd, err)


def test_file_tools(lab):
  """Known answer: Grep/Glob/Read reaching a blocked folder, or searching a folder that contains one
  (also with no path, from that folder as cwd), are blocked; the same tools on data/raw pass."""
  p, datos = lab["demo"], lab["datos"]
  blocked = [
    ("Grep", {"pattern": "PLV", "path": f"{p}/data/raw/.."}, None),
    ("Grep", {"pattern": "PLV", "path": str(datos.parent)}, None),
    ("Grep", {"pattern": "PLV"}, datos),
    ("Glob", {"pattern": "**/*.py", "path": str(datos)}, None),
    ("Glob", {"pattern": "../*/*.py", "path": f"{p}/data/raw"}, None),
    ("Read", {"file_path": f"{p}/data/raw/../pipeline/run.py"}, None),
    ("Read", {"file_path": str(datos / "script.py")}, None),
  ]
  for tool, inp, cwd in blocked:
    assert guard(p, tool, inp, cwd=cwd)[0] == 2, (tool, inp, cwd)
  allowed = [
    ("Grep", {"pattern": "x", "path": f"{p}/data/raw"}, None),
    ("Glob", {"pattern": "**/*.edf", "path": f"{p}/data/raw"}, None),
    ("Grep", {"pattern": "x"}, None),
    ("Read", {"file_path": f"{p}/src/a.py"}, None),
  ]
  for tool, inp, cwd in allowed:
    assert guard(p, tool, inp, cwd=cwd)[0] == 0, (tool, inp, cwd)


def test_without_dirs_the_gap_is_open(lab):
  """The buggy variant (G2): with no "dirs" in the blocklist (v0.3.0 behaviour), the reported
  command passes, so the blocking above comes from the blocked folders."""
  assert guard(lab["old"], "Bash", {"command": "grep -r PLV data/raw/.."})[0] == 0
  assert guard(lab["old"], "Bash", {"command": "cat data/raw/../pipeline/run.py"})[0] == 0
