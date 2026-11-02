"""PreToolUse guard (harness): blocks what CLAUDE.md forbids, for every session and subagent.

Reading data/raw/ is allowed; changing, copying, uploading or committing it is not.
In evaluation projects (.claude/harness.json has "eval_dir"), anything that names the
evaluation folder, and any web request or command matching the evaluation blocklist
(read by this hook from <eval_dir>/blocklist.json, which agents cannot read), is blocked.
Exit 2 blocks the tool call; the message on stderr is shown to Claude.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

PRIVATE = re.compile(r"(^|[\s/'\"])(CLAUDE(\.local)?\.md|\.claude/|\.harness/|agent_runs/)|(^|[\s'\"])(\./)?data/")
RAW = re.compile(r"data/raw")
RAW_CHANGE = re.compile(
  r"\b(rm|mv|cp|rsync|scp|sftp|curl|wget|tee|truncate|dd|shred|chmod|chown|ln|zip|tar|gzip|rclone|gsutil|gdown)\b"
  r"|\bsed\s+-i|>\s*\S*data/raw|\bopen\([^)]*['\"][wa+]")
AUDITOR_MEMORY = ".claude/agent-memory/methods-auditor/"
WRITE_TOOLS = ("Write", "Edit", "NotebookEdit")


def block(reason: str) -> None:
  print(f"Blocked by .claude/hooks/guard.py: {reason}", file=sys.stderr)
  sys.exit(2)


def project_root(event) -> Path:
  return Path(os.environ.get("CLAUDE_PROJECT_DIR", event.get("cwd", ".")))


def load_cfg(root: Path) -> dict:
  try:
    return json.loads((root / ".claude" / "harness.json").read_text())
  except (OSError, ValueError):
    return {}


def eval_terms(cfg: dict):
  """Strings that must never appear in a tool call of an evaluation project."""
  terms = []
  eval_dir = cfg.get("eval_dir")
  if eval_dir:
    p = Path(eval_dir)
    terms += [str(p), f"{p.parent.name}/{p.name}", "answer_key", "PREREGISTRATION"]
    try:
      terms += json.loads((p / "blocklist.json").read_text()).get("terms", [])
    except (OSError, ValueError):
      pass
  return [t for t in terms if t]


def current_branch(cwd: str) -> str:
  out = subprocess.run(["git", "-C", cwd, "branch", "--show-current"], capture_output=True, text=True)
  return out.stdout.strip()


def check_bash(cmd: str, cwd: str) -> None:
  if RAW.search(cmd) and RAW_CHANGE.search(cmd):
    block("recordings in data/raw/ may be read by project code only; never modify, copy, move or upload them.")
  if re.search(r"(^|[\s;&|])(rm|mv|cp|tee|sed\s+-i|touch)\b[^;&|]*\.harness/", cmd) or re.search(r">\s*\S*\.harness/", cmd):
    block(".harness/ is the frozen harness; never change it.")
  if re.search(r"\bgit\b[^;&|]*\bpush\b", cmd):
    block("agents never push; Sebastian pushes.")
  if re.search(r"\bgit\b[^;&|]*(\brebase\b|\bfilter-branch\b|--amend\b|\breset\s+--hard\b)", cmd):
    block("rewriting git history is not allowed.")
  for add in re.findall(r"\bgit\s+add\b[^;&|]*", cmd):
    if re.search(r"\s(-f|--force)\b", add):
      block("git add --force would bypass .gitignore and .git/info/exclude.")
    if re.search(r"\s(-A|--all|\.)(\s|$)", add):
      block("add files by explicit path, never git add -A or git add .")
    if PRIVATE.search(add):
      block("CLAUDE.md, .claude/, .harness/, agent_runs/, data and recordings stay out of git.")
  if re.search(r"\bgit\b[^;&|]*\b(commit|merge)\b", cmd):
    if current_branch(cwd) == "main" or re.search(r"\b(checkout|switch)\s+main\b", cmd):
      block("never commit or merge on main from Claude; Sebastian merges into main.")
  if re.search(r"\bgit\b[^;&|]*\bcommit\b", cmd) and re.search(r"claude|anthropic|co-authored-by", cmd, re.I):
    block("commit messages must not mention Claude, Anthropic or a co-author.")


def main() -> None:
  event = json.load(sys.stdin)
  tool = event.get("tool_name", "")
  args = event.get("tool_input", {}) or {}
  cwd = event.get("cwd", ".")

  root = project_root(event)
  cfg = load_cfg(root)
  text = json.dumps(args, ensure_ascii=False)
  own = str(root.resolve()).casefold()
  for term in eval_terms(cfg):
    if term.casefold() in own:  # e.g. the run's own folder name in a list of sibling runs
      continue
    if term.casefold() in text.casefold():
      block("this is an evaluation project: evaluation material and blocked sources are out of reach.")

  if cfg.get("mode") == "control":
    # Control arm of an evaluation: only leak, recording and push protection, no workflow rules.
    if tool == "Bash":
      cmd = args.get("command", "")
      if RAW.search(cmd) and RAW_CHANGE.search(cmd):
        block("recordings in data/raw/ are read-only; never modify, copy, move or upload them.")
      if re.search(r"\bgit\b[^;&|]*\bpush\b", cmd):
        block("pushing is not allowed in this project.")
    elif tool in WRITE_TOOLS and RAW.search(str(args.get("file_path", args.get("notebook_path", "")))):
      block("recordings in data/raw/ are read-only.")
    return

  if tool == "Bash":
    check_bash(args.get("command", ""), cwd)
    return

  if tool in WRITE_TOOLS:
    target = str(args.get("file_path", args.get("notebook_path", "")))
    if RAW.search(target):
      block("recordings in data/raw/ are read-only.")
    if "/.harness/" in target or target.startswith(".harness/"):
      block(".harness/ is the frozen harness; never change it.")
    if event.get("agent_type") == "methods-auditor":
      if AUDITOR_MEMORY not in target and not re.search(r"agent_runs/[^/]+/05_audit\.md$", target):
        block("the methods-auditor is read-only; it may only write 05_audit.md and its memory folder.")


if __name__ == "__main__":
  main()
