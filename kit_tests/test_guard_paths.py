"""Known-answer tests for lesson L26: the guard resolves every path (relative, `..`, symlinks,
quotes, globs, variables, cd) to an absolute path before checking it against the evaluation
folder and the protected project folders. In round 1, `cat ../../<eval-folder>/...` from inside
a project was not blocked."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT))
import new_project  # noqa: E402


@pytest.fixture(scope="module")
def lab(tmp_path_factory):
  """lab/eval (evaluation folder) next to lab/projects/{h,c}; ../../eval from a project is the eval folder."""
  lab = tmp_path_factory.mktemp("lab")
  ev = lab / "eval"
  (ev / "cases" / "c1" / "inputs").mkdir(parents=True)
  (ev / "secret.md").write_text("answer")
  (ev / "sec ret.md").write_text("answer")
  (ev / "blocklist.json").write_text(json.dumps({"terms": ["hidden-repo"]}))
  arms = {}
  for arm, extra in (("h", []), ("c", ["--control"])):
    p = lab / "projects" / arm
    new_project.main([str(p), "--name", arm, "--eval-dir", str(ev), "--allow-dirty", *extra])
    (p / "docs").mkdir(exist_ok=True)
    (p / "docs" / "notes.md").write_text("n")
    (p / "src").mkdir(exist_ok=True)
    (p / "data" / "raw" / "S1").mkdir(parents=True)
    (p / "data" / "raw" / "S1" / "a.edf").write_bytes(b"x")
    os.symlink(ev, p / "docs" / "ref")                     # directory symlink into the eval folder
    os.symlink("../../eval/secret.md", p / "notes_link")   # relative file symlink into the eval folder
    arms[arm] = p
  os.symlink(arms["h"] / "data" / "raw", lab / "rawlink")  # outside the project, pointing at the recordings
  os.symlink(arms["c"] / "data" / "raw", lab / "rawlink_c")
  os.symlink(".harness", arms["h"] / "hl")                 # inside the project, pointing at .harness
  return lab, ev, arms


def guard(project: Path, tool: str, inp: dict, agent=None, cwd=None):
  ev = {"tool_name": tool, "tool_input": inp, "cwd": str(cwd or project)}
  if agent:
    ev["agent_type"] = agent
  r = subprocess.run([sys.executable, str(project / ".claude" / "hooks" / "guard.py")],
                     input=json.dumps(ev), capture_output=True, text=True,
                     env={"CLAUDE_PROJECT_DIR": str(project), "PATH": "/usr/bin:/bin", "HOME": "/nonexistent"})
  return r.returncode, r.stderr


EVAL_BASH = [
  "cat ../../eval/secret.md",                               # relative (the round-1 case)
  "cat ./../../eval/./secret.md",                           # . and ..
  "cd .. && cd .. && cat eval/secret.md",                   # cd, then a relative path
  "cd ../.. ; head -5 eval/secret.md",
  'cat "../../eval/secret.md"',                             # double quotes
  "cat '../../eval/sec ret.md'",                            # single quotes, space in the name
  "cat docs/ref/secret.md",                                 # directory symlink
  "cat notes_link",                                         # file symlink
  "ls ../../ev*",                                           # glob
  "D=../../eval; cat $D/secret.md",                         # variable set in the command
  "D=../../eval cat ${D}/secret.md",
  "diff --from-file=../../eval/secret.md docs/notes.md",    # --option=path
  "python3 -c \"print(open('../../eval/secret.md').read())\"",
  "python3 - <<'EOF'\nprint(open('../../eval/secret.md').read())\nEOF",
  "bash -c 'cat ../../eval/secret.md'",
  "grep -r answer ../..",                                   # recursive read of a folder containing eval
  "find ../.. -name '*.md'",
  "echo x > ../../eval/new.txt",                            # redirect target
  "cp ../../eval/secret.md /tmp/x.md",
  "ls 'unterminated ../../eval/secret.md",                  # unparseable: fallback still resolves
]

ALLOW_BASH = [
  "cat docs/notes.md",
  "ls ..",
  "cd .. && ls",
  "grep -rn x src/",
  "git status",
  "python3 scripts/run.py --out outputs/x --config=configs/a.yaml",
  "cat README.md && ls -la docs",
  "find . -name '*.py'",
  "sed -n 1,5p docs/notes.md | wc -l",
  "cat ../h/docs/notes.md 2>/dev/null; cat ../c/docs/notes.md 2>/dev/null",
]


@pytest.mark.parametrize("arm", ["h", "c"])
@pytest.mark.parametrize("cmd", EVAL_BASH)
def test_paths_to_eval_folder_blocked_in_both_arms(lab, arm, cmd):
  """Known answer: every spelling of a path into the evaluation folder is blocked (exit 2), in both arms."""
  _, _, arms = lab
  code, err = guard(arms[arm], "Bash", {"command": cmd})
  assert code == 2 and "evaluation" in err, (cmd, err)


@pytest.mark.parametrize("arm", ["h", "c"])
@pytest.mark.parametrize("cmd", ALLOW_BASH)
def test_normal_commands_still_pass(lab, arm, cmd):
  """Known answer: ordinary commands inside the project and its parent folder pass (exit 0)."""
  _, _, arms = lab
  code, err = guard(arms[arm], "Bash", {"command": cmd})
  assert code == 0, (cmd, err)


@pytest.mark.parametrize("arm", ["h", "c"])
def test_file_tools_resolve_paths(lab, arm):
  """Known answer: Read/Write/Grep/Glob with an unnormalized path, a symlink, or an ancestor of the eval
  folder (recursive tools) are blocked; the same tools inside the project pass."""
  _, _, arms = lab
  p = arms[arm]
  blocked = [
    ("Read", {"file_path": f"{p}/../../eval/secret.md"}),
    ("Read", {"file_path": f"{p}/docs/ref/secret.md"}),
    ("Read", {"file_path": f"{p}/notes_link"}),
    ("Write", {"file_path": f"{p}/../../eval/new.md", "content": "x"}),
    ("Grep", {"pattern": "answer", "path": f"{p}/../.."}),
    ("Glob", {"pattern": "../../eval/*", "path": str(p)}),
    ("Glob", {"pattern": "**/*.md", "path": f"{p}/../.."}),
  ]
  for tool, inp in blocked:
    assert guard(p, tool, inp)[0] == 2, (tool, inp)
  allowed = [
    ("Read", {"file_path": f"{p}/docs/notes.md"}),
    ("Grep", {"pattern": "x", "path": str(p)}),
    ("Glob", {"pattern": "**/*.py", "path": str(p)}),
    ("Read", {"file_path": f"{p}/../{arm}/docs/notes.md"}),
  ]
  for tool, inp in allowed:
    assert guard(p, tool, inp)[0] == 0, (tool, inp)


def test_protected_project_folders_resolved(lab):
  """Known answer: writes reaching data/raw or .harness through .., a symlink outside the project, or a
  symlink inside it are blocked; reading the recordings through the symlink passes."""
  _, _, arms = lab
  h = arms["h"]
  for cmd in ("rm ../h/data/raw/S1/a.edf", "rm ../../rawlink/S1/a.edf", "echo x > ../../rawlink/S1/n.txt",
              "cp ../../rawlink/S1/a.edf /tmp/copy.edf", "echo 1 > ../h/.harness/VERSION", "echo 1 > hl/VERSION",
              "cd ../../rawlink && rm S1/a.edf"):
    assert guard(h, "Bash", {"command": cmd})[0] == 2, cmd
  assert guard(h, "Bash", {"command": "head -c 1 ../../rawlink/S1/a.edf"})[0] == 0
  assert guard(h, "Write", {"file_path": str(h.parent.parent / "rawlink" / "S1" / "x.txt")})[0] == 2
  assert guard(h, "Edit", {"file_path": str(h / "hl" / "VERSION")})[0] == 2
  c = arms["c"]
  assert guard(c, "Bash", {"command": "rm ../../rawlink_c/S1/a.edf"})[0] == 2  # recordings protected in control too


def test_auditor_write_paths_resolved(lab):
  """Known answer: the auditor's allowed files are checked after resolution: a .. escape or a path outside
  the project with the same name is blocked; its real audit file passes."""
  _, _, arms = lab
  h = arms["h"]
  assert guard(h, "Write", {"file_path": f"{h}/agent_runs/r/05_audit.md"}, agent="methods-auditor")[0] == 0
  assert guard(h, "Write", {"file_path": f"{h}/agent_runs/r/../../src/05_audit.md"}, agent="methods-auditor")[0] == 2
  assert guard(h, "Write", {"file_path": "/tmp/elsewhere/agent_runs/r/05_audit.md"}, agent="methods-auditor")[0] == 2
  assert guard(h, "Bash", {"command": "python -m eegharness.compare_runs --a a --b b --out agent_runs/r/../../outputs"},
               agent="methods-auditor")[0] == 2
