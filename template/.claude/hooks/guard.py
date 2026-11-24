"""PreToolUse guard (harness): blocks what CLAUDE.md forbids, for every session and subagent.

Reading data/raw/ is allowed; changing, copying, uploading or committing it is not.
In evaluation projects (.claude/harness.json has "eval_dir"), anything that names the
evaluation folder, and any web request or command matching the evaluation blocklist
(read by this hook from <eval_dir>/blocklist.json, which agents cannot read), is blocked.
The methods-auditor has a read-only shell: an allowlist of commands (see AUDITOR_*).
Exit 2 blocks the tool call; the message on stderr is shown to Claude.

Shell commands are tokenized (quotes, heredocs, `;` `&&` `||` `|` and newlines), so a rule
looks at what a command does (its command word, operands and redirect targets, the commit
message) rather than at any word anywhere in the text. A command that cannot be tokenized
falls back to the conservative whole-text checks of v0.1.

Every path a tool call names is resolved to an absolute, normalized path before it is checked
(lesson L26): relative to the shell's working directory as `cd`/`pushd` change it, with `..`,
symlinks, `~`, `$VAR`s assigned in the same command, `--option=path`, globs, and string
literals in heredocs and `-c` code. Resolved paths are checked against the evaluation folder,
the blocklist terms and the protected folders (data/raw, .harness, eegharness, eegpipe). A recursive
tool (grep -r, find, rg, tree, du, ls -R, tar, zip, rsync, cp -r) aimed at a folder that
contains the evaluation folder is blocked as well.

Blocked folders (v0.3.1): ``blocklist.json`` may also list ``"dirs"``, absolute folders that
are treated like the evaluation folder: any path inside one is blocked, and so is any
search or listing (the recursive tools above, plain ls, the Grep and Glob tools) whose
resolved starting folder contains one, e.g. ``grep -r x data/raw/..`` when the recordings'
parent folder holds other projects. A search or listing with no folder operand starts in
the current folder, which is checked the same way.
"""

import glob
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

PRIVATE = re.compile(r"(^|[\s/'\"])(CLAUDE(\.local)?\.md|\.claude/|\.harness/|agent_runs/)|(^|[\s'\"])(\./)?data/")
RAW = re.compile(r"data/raw")
RAW_CHANGE = re.compile(
  r"\b(rm|mv|cp|rsync|scp|sftp|curl|wget|tee|truncate|dd|shred|chmod|chown|ln|zip|tar|gzip|rclone|gsutil|gdown)\b"
  r"|\bsed\s+-i|>\s*\S*data/raw|\bopen\([^)]*['\"][wa+]")
# Python/NumPy/pandas calls that change a path, matched on the same line as data/raw (heredocs, python -c).
PY_WRITE = re.compile(
  r"(open\([^)\n]*data/raw[^)\n]*,\s*['\"][^'\"]*[wax+]"
  r"|(shutil\.\w+|os\.(remove|unlink|rename|replace|rmdir|makedirs|mkdir)|\.unlink|\.write_text|\.write_bytes"
  r"|\.rename|\.mkdir|\.touch|np\.save\w*|\.to_csv|\.to_parquet|\.savefig)\([^\n]*data/raw)")
MUTATING = {"rm", "rmdir", "mv", "cp", "rsync", "scp", "sftp", "tee", "truncate", "dd", "shred", "chmod",
            "chown", "ln", "zip", "unzip", "tar", "gzip", "gunzip", "rclone", "gsutil", "gdown", "curl",
            "wget", "touch", "mkdir", "install", "patch", "perl", "split"}
COPY_LIKE = {"cp", "rsync", "scp", "install"}  # for .harness/: only the destination (last operand) is written
WRAPPERS = {"sudo", "time", "command", "nohup", "nice", "env", "exec", "builtin"}
SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
SEPARATORS = {";", "&&", "||", "|", "&", "\n", "|&", "(", ")"}
REDIRECTS = {">", ">>", ">|", "&>", "&>>"}
AUDITOR_MEMORY = ".claude/agent-memory/methods-auditor/"
AUDITOR_FILES = re.compile(r"agent_runs/[^/]+/(05_audit|02b_plan_audit)\.md$")
AUDITOR_READ = {"ls", "cat", "head", "tail", "wc", "grep", "egrep", "fgrep", "rg", "find", "sha256sum",
                "md5sum", "diff", "cmp", "stat", "file", "tree", "du", "sort", "uniq", "cut", "nl", "jq",
                "echo", "printf", "pwd", "cd", "true", "basename", "dirname", "realpath", "comm", "tr"}
AUDITOR_GIT = {"diff", "show", "log", "status", "blame", "ls-files", "rev-parse", "branch", "describe",
               "grep", "shortlog", "cat-file", "merge-base", "rev-list", "ls-tree", "name-rev"}
WRITE_TOOLS = ("Write", "Edit", "NotebookEdit")
# Same list as .harness/tools/eegprofile/formats.py DOCUMENT_EXTS (a kit test keeps them equal).
DOCUMENT_EXTS = {".txt", ".md", ".rst", ".pdf", ".doc", ".docx", ".odt", ".rtf", ".html", ".htm",
                 ".csv", ".tsv", ".json", ".xls", ".xlsx", ".ods", ".log", ".ini", ".yaml", ".yml"}
RECURSIVE = {"find", "rg", "tree", "du", "tar", "zip", "rsync", "ag", "fd", "locate"}
STRING_PATH = re.compile(r"""['"]([^'"\n]*/[^'"\n]*)['"]""")
VAR = re.compile(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?")
CTX = {"root": Path("."), "eval_dir": None, "terms": [], "own": "", "dirs": []}
LISTING = {"ls", "dir", "vdir", "tree", "du"}


# ---------------------------------------------------------------- paths (L26)

def real(p) -> Path:
  return Path(os.path.realpath(p))


def is_under(p: Path, folder) -> bool:
  return folder is not None and (p == folder or folder in p.parents)


def resolve_token(tok: str, base: Path, env: dict) -> list:
  """Absolute, normalized paths (symlinks followed) that a command token may name."""
  s = tok
  if s.startswith("-"):
    if "=" not in s:
      return []
    s = s.split("=", 1)[1]
  s = s.lstrip("@")
  if not s or s == "-" or "://" in s:
    return []
  s = VAR.sub(lambda m: env.get(m.group(1), os.environ.get(m.group(1), m.group(0))), s)
  s = os.path.expanduser(s)
  path = s if os.path.isabs(s) else str(base / s)
  out = [real(path)]
  if any(c in s for c in "*?["):
    static = re.split(r"[*?\[]", path, maxsplit=1)[0]
    out = [real(os.path.dirname(static) or "/")] + [real(m) for m in glob.glob(path)[:500]]
  return out


def check_eval_path(p: Path, recursive: bool = False) -> None:
  ev = CTX["eval_dir"]
  if ev is not None and (is_under(p, ev) or (recursive and is_under(ev, p))):
    block("this is an evaluation project: evaluation material and blocked sources are out of reach "
          f"(path resolves to {p}).")
  for d in CTX["dirs"]:
    if is_under(p, d) or (recursive and is_under(d, p)):
      block("this is an evaluation project: blocked sources are out of reach "
            f"(path resolves to {p}, which is or contains a blocked folder).")
  low = str(p).casefold()
  for term in CTX["terms"]:
    if term.casefold() in low and term.casefold() not in CTX["own"]:
      block("this is an evaluation project: evaluation material and blocked sources are out of reach.")


def protected(p: Path) -> str:
  """Which protected project folder a resolved path lies in ('' if none)."""
  root = CTX["root"]
  for rel, name in (("data/raw", "raw"), (".harness", "harness"), ("eegharness", "eegharness"), ("eegpipe", "eegpipe")):
    if is_under(p, real(root / rel)):
      return name
  return ""


def check_written(paths, raw_only: bool) -> None:
  for p in paths:
    kind = protected(p)
    if kind == "raw":
      block("recordings in data/raw/ may be read by project code only; never modify, copy, move or upload them.")
    if raw_only:
      continue
    if kind == "harness":
      block(".harness/ is the frozen harness; never change it.")
    if kind == "eegharness":
      block("eegharness/ is vendored harness code; never change it by hand (a new harness version replaces it).")
    if kind == "eegpipe":
      block("eegpipe/ is the vendored pipeline; configure it in configs/pipeline.json, never edit it (G24; a deviation is a new project module with tests).")


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


def blocked_dirs(cfg: dict) -> list:
  """Absolute folders from <eval_dir>/blocklist.json "dirs" (symlinks resolved)."""
  eval_dir = cfg.get("eval_dir")
  if not eval_dir:
    return []
  try:
    dirs = json.loads((Path(eval_dir) / "blocklist.json").read_text()).get("dirs", [])
  except (OSError, ValueError):
    return []
  return [real(d) for d in dirs if isinstance(d, str) and os.path.isabs(d)]


def current_branch(cwd: str) -> str:
  out = subprocess.run(["git", "-C", cwd, "branch", "--show-current"], capture_output=True, text=True)
  return out.stdout.strip()


# ---------------------------------------------------------------- shell parsing

HEREDOC = re.compile(r"<<-?[ \t]*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")


def split_heredocs(cmd: str):
  """Remove heredoc bodies from the command. Returns (command without bodies, {delimiter: [bodies]}).

  Each body is replaced by nothing; the `<<DELIM` marker stays, so the segment that reads
  the heredoc can find its body by delimiter.
  """
  lines = cmd.split("\n")
  out, bodies, i = [], {}, 0
  while i < len(lines):
    line = lines[i]
    out.append(line)
    pending = [m.group(2) for m in HEREDOC.finditer(line)]
    i += 1
    for delim in pending:
      body = []
      while i < len(lines) and lines[i].strip() != delim:
        body.append(lines[i])
        i += 1
      i += 1  # the delimiter line
      bodies.setdefault(delim, []).append("\n".join(body))
  return "\n".join(out), bodies


def segments(cmd: str):
  """Tokenize into simple commands. Returns a list of token lists, or None if it cannot be parsed."""
  lex = shlex.shlex(cmd, posix=True, punctuation_chars=";&|<>()\n")
  lex.whitespace = " \t\r"
  lex.whitespace_split = True
  lex.commenters = ""
  try:
    toks = list(lex)
  except ValueError:
    return None
  segs, cur = [], []
  for t in toks:
    if t in SEPARATORS or (set(t) <= set(";&|\n()") and t):
      if cur:
        segs.append(cur)
      cur = []
    else:
      cur.append(t)
  if cur:
    segs.append(cur)
  return segs


def parse_segment(seg):
  """Split a simple command into (command word, args, redirect targets, heredoc delimiters)."""
  words, targets, heredocs, i = [], [], [], 0
  while i < len(seg):
    t = seg[i]
    if t in REDIRECTS or re.fullmatch(r"\d?>>?|&>>?", t):
      if i + 1 < len(seg) and seg[i + 1] == "&":  # 2>&1
        i += 3
        continue
      if i + 1 < len(seg):
        targets.append(seg[i + 1])
      i += 2
      continue
    if t in ("<<", "<<-"):
      if i + 1 < len(seg):
        heredocs.append(seg[i + 1].strip("'\""))
      i += 2
      continue
    if t in ("<", "<<<", "<&", ">&"):
      i += 2
      continue
    words.append(t)
    i += 1
  while words and (re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", words[0]) or words[0] in WRAPPERS):
    words = words[1:]
  if not words:
    return "", [], targets, heredocs
  return os.path.basename(words[0]), words[1:], targets, heredocs


def assignments(seg) -> dict:
  out = {}
  for w in seg:
    m = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)=(.*)", w, re.S)
    if not m:
      break
    out[m.group(1)] = m.group(2)
  return out


def operands(cmd: str, args):
  """Non-option arguments; for sed the script argument is not an operand."""
  ops = [a for a in args if not a.startswith("-") or a == "-"]
  if cmd == "sed":
    if any(a in ("-e", "--expression", "-f") or a.startswith("--expression=") for a in args):
      skip = {i + 1 for i, a in enumerate(args) if a in ("-e", "--expression", "-f")}
      ops = [a for i, a in enumerate(args) if i not in skip and not a.startswith("-")]
    else:
      ops = ops[1:]
  return ops


def in_dir(path: str, name: str, root: Path) -> bool:
  """True if `path` points into the project's own folder `name` (e.g. .harness)."""
  p = path[2:] if path.startswith("./") else path
  if p == name or p.startswith(name + "/"):
    return True
  return str(root / name) in path


def git_sub(args):
  """(subcommand, its args) of `git [-C dir] [-c k=v] <sub> ...`."""
  i = 0
  while i < len(args):
    a = args[i]
    if a in ("-C", "-c", "--git-dir", "--work-tree"):
      i += 2
    elif a.startswith("-"):
      i += 1
    else:
      return a, args[i + 1:]
  return "", []


def commit_message(sub_args, heredocs, bodies, cwd) -> str:
  parts, i = [], 0
  while i < len(sub_args):
    a = sub_args[i]
    if a in ("-m", "--message") and i + 1 < len(sub_args):
      parts.append(sub_args[i + 1])
      i += 2
      continue
    if a.startswith("--message="):
      parts.append(a.split("=", 1)[1])
    elif re.fullmatch(r"-[a-zA-Z]*m.+", a) and not a.startswith("--"):
      parts.append(a[a.index("m") + 1:])
    elif a in ("-F", "--file") and i + 1 < len(sub_args):
      src = sub_args[i + 1]
      if src == "-":
        parts += [b for d in heredocs for b in bodies.get(d, [])]
      else:
        try:
          parts.append((Path(cwd) / src).read_text(errors="ignore"))
        except OSError:
          pass
      i += 2
      continue
    i += 1
  return "\n".join(parts)


# ---------------------------------------------------------------- checks

def check_bash_fallback(cmd: str, cwd: str) -> None:
  """v0.1 whole-text checks, used only when a command cannot be tokenized."""
  check_eval_text(cmd, Path(cwd))
  if RAW.search(cmd) and RAW_CHANGE.search(cmd):
    block("recordings in data/raw/ may be read by project code only; never modify, copy, move or upload them.")
  if re.search(r"(^|[\s;&|])(rm|mv|cp|tee|sed\s+-i|touch)\b[^;&|]*\.harness/", cmd) or re.search(r">\s*\S*\.harness/", cmd):
    block(".harness/ is the frozen harness; never change it.")
  if re.search(r"\bgit\b[^;&|]*\bpush\b", cmd):
    block("agents never push; the supervisor pushes.")
  if re.search(r"\bgit\b[^;&|]*(\brebase\b|\bfilter-branch\b|--amend\b|\breset\s+--hard\b)", cmd):
    block("rewriting git history is not allowed.")
  if re.search(r"\bgit\b[^;&|]*\badd\b", cmd) and (re.search(r"\s(-f|--force|-A|--all|\.)(\s|$)", cmd) or PRIVATE.search(cmd)):
    block("add files by explicit path; CLAUDE.md, .claude/, .harness/, agent_runs/ and data stay out of git.")
  if re.search(r"\bgit\b[^;&|]*\b(commit|merge)\b", cmd):
    if current_branch(cwd) == "main" or re.search(r"\b(checkout|switch)\s+main\b", cmd):
      block("never commit or merge on main from Claude; the supervisor merges into main.")
    if re.search(r"claude|anthropic|co-authored-by", cmd, re.I):
      block("commit messages must not mention Claude, Anthropic or a co-author (this command could not be parsed; "
            "write the message with -m and keep other text out of the command).")


def check_eval_text(text: str, base: Path) -> None:
  """Paths inside free text (code, unparseable commands): string literals and path-like words."""
  cands = STRING_PATH.findall(text) + re.findall(r"[^\s'\"();|&<>=]*/[^\s'\"();|&<>]*", text)
  for c in cands:
    for p in resolve_token(c.strip(), base, {}):
      check_eval_path(p)


def check_raw_text(text: str) -> None:
  for line in text.split("\n"):
    if "data/raw" in line and PY_WRITE.search(line):
      block("recordings in data/raw/ may be read by project code only; never modify, copy, move or upload them.")


def check_bash(cmd: str, cwd: str, root: Path, raw_only: bool = False) -> None:
  stripped, bodies = split_heredocs(cmd)
  segs = segments(stripped)
  if segs is None:
    if raw_only:
      check_eval_text(cmd, Path(cwd))
      if RAW.search(cmd) and RAW_CHANGE.search(cmd):
        block("recordings in data/raw/ are read-only; never modify, copy, move or upload them.")
      if re.search(r"\bgit\b[^;&|]*\bpush\b", cmd):
        block("pushing is not allowed in this project.")
      return
    check_bash_fallback(cmd, cwd)
    return
  for body_list in bodies.values():
    for body in body_list:
      check_raw_text(body)
      check_eval_text(body, Path(cwd))
  branch = None
  here = real(cwd)  # the shell's working directory, followed through cd/pushd (L26)
  env = {}
  for seg in segs:
    env.update(assignments(seg))
    for v in assignments(seg).values():
      for part in v.split(":"):
        for p in resolve_token(part, here, env):
          check_eval_path(p)
    name, args, targets, heredocs = parse_segment(seg)
    if name in ("cd", "pushd"):
      dest = next((a for a in args if not a.startswith("-")), "~")
      found = resolve_token(dest, here, env)
      if found:
        here = found[0]
        check_eval_path(here)
      continue
    recursive = name in RECURSIVE or (name in ("grep", "egrep", "fgrep", "ls", "cp", "chmod", "chown", "rm")
                                      and any(re.fullmatch(r"-[A-Za-z]*[rR][A-Za-z]*|--recursive", a) for a in args))
    listing = recursive or name in LISTING
    resolved_args = [p for a in args for p in resolve_token(a, here, env)]
    resolved_targets = [p for a in targets for p in resolve_token(a, here, env)]
    for p in resolved_args + resolved_targets:
      check_eval_path(p, recursive=listing)
    if listing and not any(p.is_dir() for p in resolved_args):
      check_eval_path(here, recursive=True)  # no folder operand: it starts in the current folder
    if name and "/" in seg[0]:
      for p in resolve_token(seg[0], here, env):
        check_eval_path(p)
    for t in targets:
      if "data/raw" in t:
        block("recordings in data/raw/ are read-only; never write into them.")
    check_written([p for p in resolved_targets if not str(p).startswith("/dev/")], raw_only)
    is_mut = name in MUTATING or name == "xargs" or (name == "sed" and any(a.startswith(("-i", "--in-place")) for a in args))
    if is_mut and protected(here) == "raw":
      block("recordings in data/raw/ may be read by project code only; never modify, copy, move or upload them "
            "(this command runs inside data/raw/).")
    if is_mut and protected(here) in ("harness", "eegharness", "eegpipe") and not raw_only:
      block(".harness/, eegharness/ and eegpipe/ are frozen harness code; never change them (this command runs inside one).")
    if name in ("python", "python3") and "-c" in args:
      check_raw_text(" ".join(args))
      check_eval_text(" ".join(args), here)
    if name in SHELLS or name == "eval":
      # a shell runs its heredoc or -c string: check that text with the same rules
      inner = [b for d in heredocs for b in bodies.get(d, [])]
      if "-c" in args and args.index("-c") + 1 < len(args):
        inner.append(args[args.index("-c") + 1])
      if name == "eval":
        inner.append(" ".join(args))
      for text in inner:
        check_bash(text, str(here), root, raw_only)
    ops = operands(name, args)
    if name in MUTATING or (name == "sed" and any(a == "-i" or a.startswith(("-i", "--in-place")) for a in args)):
      checked = ops if name not in ("curl", "wget") else args
      if any("data/raw" in o for o in checked) or any(
          protected(p) == "raw" for o in checked for p in resolve_token(o, here, env)):
        block("recordings in data/raw/ may be read by project code only; never modify, copy, move or upload them.")
    if name == "xargs" and any(a in MUTATING for a in args) and "data/raw" in " ".join(args):
      block("recordings in data/raw/ may be read by project code only; never modify, copy, move or upload them.")
    if name == "git":
      sub, sargs = git_sub(args)
      if sub == "push":
        block("agents never push; the supervisor pushes." if not raw_only else "pushing is not allowed in this project.")
    if raw_only:
      continue
    # .harness/ and the vendored eegharness/ are frozen
    written = []
    if name in COPY_LIKE or name == "mv":
      written = ops[-1:] if name in COPY_LIKE else ops
    elif name in MUTATING or name == "sed" and any(a.startswith(("-i", "--in-place")) for a in args):
      written = ops
    for w in written + targets:
      if in_dir(w, ".harness", root):
        block(".harness/ is the frozen harness; never change it.")
      if in_dir(w, "eegharness", root):
        block("eegharness/ is vendored harness code; never change it by hand (a new harness version replaces it).")
      if in_dir(w, "eegpipe", root):
        block("eegpipe/ is the vendored pipeline; configure it in configs/pipeline.json, never edit it (G24; a deviation is a new project module with tests).")
    check_written([p for w in written for p in resolve_token(w, here, env)], raw_only)
    if name != "git":
      continue
    sub, sargs = git_sub(args)
    if sub in ("rebase", "filter-branch") or (sub == "commit" and "--amend" in sargs) or (sub == "reset" and "--hard" in sargs):
      block("rewriting git history is not allowed.")
    if sub == "add":
      if any(a in ("-f", "--force") for a in sargs):
        block("git add --force would bypass .gitignore and .git/info/exclude.")
      if any(a in ("-A", "--all", ".", "-u", "--update") for a in sargs):
        block("add files by explicit path, never git add -A or git add .")
      if any(PRIVATE.search(" " + a) for a in sargs if not a.startswith("-")):
        block("CLAUDE.md, .claude/, .harness/, agent_runs/, data and recordings stay out of git.")
    if sub in ("switch", "checkout"):
      names = [a for a in sargs if not a.startswith("-")]
      if "--" not in sargs and names:
        branch = names[0]
    if sub in ("commit", "merge"):
      effective = branch if branch is not None else current_branch(cwd)
      if effective == "main":
        block("never commit or merge on main from Claude; the supervisor merges into main.")
    if sub == "commit":
      msg = commit_message(sargs, heredocs, bodies, cwd)
      if re.search(r"claude|anthropic|co-authored-by", msg, re.I):
        block("commit messages must not mention Claude, Anthropic or a co-author.")


def check_auditor_bash(cmd: str, root: Path, cwd: str = ".") -> None:
  """The methods-auditor's shell: read-only commands only (CLAUDE.md, methods-auditor)."""
  deny = "the methods-auditor's shell is read-only: "
  if "<<" in cmd or "$(" in cmd or "`" in cmd:
    block(deny + "no heredocs, $( ) or backticks; run one plain read-only command at a time.")
  segs = segments(cmd)
  if segs is None:
    block(deny + "this command could not be parsed.")
  for seg in segs:
    name, args, targets, _ = parse_segment(seg)
    if any(t not in ("/dev/null",) for t in targets):
      block(deny + "no output redirection (only to /dev/null).")
    if not name:
      continue
    if name in AUDITOR_READ:
      if name == "find" and any(a in ("-exec", "-execdir", "-delete", "-ok", "-okdir", "-fprint", "-fprint0",
                                      "-fprintf", "-fls") for a in args):
        block(deny + "find without -exec, -delete or -fprint.")
      if name == "sort" and any(a == "-o" or a.startswith(("-o", "--output")) for a in args):
        block(deny + "sort without -o.")
      continue
    if name == "sed":
      scripts = [a for a in args if not a.startswith("-")][:1]
      if (args[:1] == ["-n"] and scripts and all(o in ("-n",) or not o.startswith("-") for o in args)
          and re.fullmatch(r"((\d+|\$)(,(\d+|\$))?p;?)+", scripts[0])):
        continue  # print lines only, e.g. sed -n 245,300p file
      block(deny + "sed only as `sed -n <first>,<last>p <file>` (print lines).")
    if name == "git":
      sub, sargs = git_sub(args)
      if sub not in AUDITOR_GIT:
        block(deny + f"git {sub or '(none)'} is not a read-only git command "
              f"(allowed: {', '.join(sorted(AUDITOR_GIT))}).")
      if any(a.startswith("--output") for a in sargs):
        block(deny + "git without --output.")
      if sub == "branch" and any(not a.startswith("-") or a in ("-d", "-D", "-m", "-M", "-c", "-C", "-f", "--delete",
                                                                  "--move", "--copy", "--force", "-u",
                                                                  "--set-upstream-to", "--unset-upstream",
                                                                  "--edit-description") for a in sargs):
        block(deny + "git branch may only list branches.")
      continue
    if name == "pytest" or (re.fullmatch(r"python(3(\.\d+)?)?", name) and args[:2] == ["-m", "pytest"]):
      if not ("-p" in args and "no:cacheprovider" in args) and "-pno:cacheprovider" not in args:
        block(deny + "run pytest as `python -m pytest -p no:cacheprovider ...` (no cache written).")
      if any(a.startswith(("--junit", "--resultlog", "--result-log", "--cov", "--basetemp", "--lf", "--sw")) for a in args):
        block(deny + "pytest without report, coverage or state options.")
      continue
    if re.fullmatch(r"python(3(\.\d+)?)?", name) and args[:2] == ["-m", "eegharness.compare_runs"]:
      outs = [args[i + 1] for i, a in enumerate(args) if a == "--out" and i + 1 < len(args)]
      outs += [a.split("=", 1)[1] for a in args if a.startswith("--out=")]
      runs = real(root / "agent_runs")
      if not outs or not all(real(o if os.path.isabs(o) else Path(cwd) / o).parent != runs
                             and is_under(real(o if os.path.isabs(o) else Path(cwd) / o), runs) for o in outs):
        block(deny + "compare_runs only with --out inside the run folder (agent_runs/<run>/...).")
      continue
    if re.fullmatch(r"python(3(\.\d+)?)?", name) and args[:2] == ["-m", "eegharness.numbers"]:
      if args[2:3] != ["check"]:
        block(deny + "eegharness.numbers only as `check` (it reads; `derive` writes and is the analyst's).")
      continue
    if re.fullmatch(r"python(3(\.\d+)?)?", name) and args[:1] and args[0] in (
        ".harness/tools/check_plan_fields.py", "./.harness/tools/check_plan_fields.py"):
      continue  # reads the plan and the code (0.6.0, L56); redirects are refused above
    if re.fullmatch(r"python(3(\.\d+)?)?", name) and args[:2] in (["-m", "eegharness.outputs"], ["-m", "eegharness.sources"]):
      # the checks G22 and G15 tell the auditor to run (0.6.0, L50); both only read
      if args[2:3] != ["check"]:
        block(deny + f"{args[1]} only as `check` (it reads).")
      if any(a == "--record" or a.startswith("--record=") for a in args):
        block(deny + "eegharness.outputs check without --record (recording writes an output; the orchestrator's).")
      continue
    block(deny + f"`{name}` is not on the auditor's list (read-only file tools, read-only git, "
          "python -m pytest -p no:cacheprovider, python -m eegharness.compare_runs, "
          "python -m eegharness.numbers check, python -m eegharness.outputs check, "
          "python -m eegharness.sources check, python .harness/tools/check_plan_fields.py).")


def check_analyst_bash(cmd: str, root: Path, cwd: str) -> None:
  """The paradigm-analyst's shell runs one thing: the document reader on a document (G16, L25)."""
  deny = ("the paradigm-analyst's shell only runs `python .harness/tools/read_document.py <document>`: ")
  if "<<" in cmd or "$(" in cmd or "`" in cmd:
    block(deny + "no heredocs, $( ) or backticks.")
  segs = segments(cmd)
  if not segs or len(segs) != 1:
    block(deny + "one command, no pipes or chains.")
  name, args, targets, _ = parse_segment(segs[0])
  if any(t != "/dev/null" for t in targets):
    block(deny + "no output redirection.")
  reader = real(root / ".harness" / "tools" / "read_document.py")
  if not re.fullmatch(r"python(3(\.\d+)?)?", name) or not args or real(Path(cwd) / args[0]) != reader:
    block(deny + "nothing else.")
  docs = [a for a in args[1:] if not a.startswith("-") and not re.fullmatch(r"\d+", a)]
  for d in docs:
    if Path(d).suffix.lower() not in DOCUMENT_EXTS:
      block(deny + f"{d} is not a document; recordings are read only by project code.")


def check_analyst_write(tool: str, resolved, root: Path) -> None:
  """L36: the paradigm-analyst edits docs/PARADIGM.md only, and once that file is committed it appends with
  Edit; a Write would rewrite frozen text."""
  try:
    rel = resolved[0].relative_to(real(root)).as_posix() if resolved else ""
  except ValueError:
    rel = ""
  if tool in ("Edit", "NotebookEdit") and rel != "docs/PARADIGM.md":
    block("the paradigm-analyst has Edit for docs/PARADIGM.md only (L36).")
  if tool == "Write" and rel == "docs/PARADIGM.md":
    r = subprocess.run(["git", "-C", str(root), "ls-files", "--error-unmatch", "--", rel], capture_output=True, text=True)
    if r.returncode == 0:
      block("docs/PARADIGM.md is committed: append your revision with Edit; frozen text stays unchanged (L36).")


def main() -> None:
  event = json.load(sys.stdin)
  tool = event.get("tool_name", "")
  args = event.get("tool_input", {}) or {}
  cwd = event.get("cwd", ".")

  root = project_root(event)
  cfg = load_cfg(root)
  text = json.dumps(args, ensure_ascii=False)
  own = str(root.resolve()).casefold()
  terms = eval_terms(cfg)
  CTX.update(root=root, own=own, terms=terms, dirs=blocked_dirs(cfg),
             eval_dir=real(cfg["eval_dir"]) if cfg.get("eval_dir") else None)
  for term in terms:
    if term.casefold() in own:  # e.g. the run's own folder name in a list of sibling runs
      continue
    if term.casefold() in text.casefold():
      block("this is an evaluation project: evaluation material and blocked sources are out of reach.")
  # file tools: resolve every path argument (L26)
  if tool != "Bash":
    base = real(cwd)
    for key in ("file_path", "notebook_path", "path"):
      if isinstance(args.get(key), str) and args[key]:
        for p in resolve_token(args[key], base, {}):
          check_eval_path(p, recursive=tool in ("Grep", "Glob"))
    if tool in ("Grep", "Glob") and not (isinstance(args.get("path"), str) and args["path"]):
      check_eval_path(base, recursive=True)  # no path: it searches the current folder
    if tool == "Glob" and isinstance(args.get("pattern"), str):
      gbase = real(args["path"]) if isinstance(args.get("path"), str) and args["path"] else base
      for p in resolve_token(args["pattern"], gbase, {}):
        check_eval_path(p, recursive=True)

  if cfg.get("mode") == "control":
    # Control arm of an evaluation: only leak, recording and push protection, no workflow rules.
    if tool == "Bash":
      check_bash(args.get("command", ""), cwd, root, raw_only=True)
    elif tool in WRITE_TOOLS:
      target = str(args.get("file_path", args.get("notebook_path", "")))
      if RAW.search(target):
        block("recordings in data/raw/ are read-only.")
      check_written(resolve_token(target, real(cwd), {}), raw_only=True)
    return

  if event.get("agent_type") == "paradigm-analyst" and tool in ("Read", "Grep", "NotebookRead"):
    target = args.get("file_path") or args.get("path") or args.get("notebook_path") or ""
    if target and any(is_under(p, real(root / "data")) for p in resolve_token(target, real(cwd), {})):
      block("the paradigm-analyst reads documents in the data folder only through "
            "`python .harness/tools/read_document.py <path>`, which refuses recordings (G16).")

  if tool == "Bash":
    if event.get("agent_type") == "paradigm-analyst":
      check_analyst_bash(args.get("command", ""), root, cwd)
    if event.get("agent_type") == "methods-auditor":
      check_auditor_bash(args.get("command", ""), root, cwd)
    check_bash(args.get("command", ""), cwd, root)
    return

  if tool in WRITE_TOOLS:
    target = str(args.get("file_path", args.get("notebook_path", "")))
    if RAW.search(target):
      block("recordings in data/raw/ are read-only.")
    if "/.harness/" in target or target.startswith(".harness/"):
      block(".harness/ is the frozen harness; never change it.")
    if in_dir(target, "eegharness", root):
      block("eegharness/ is vendored harness code; never change it by hand (a new harness version replaces it).")
    if in_dir(target, "eegpipe", root):
      block("eegpipe/ is the vendored pipeline; configure it in configs/pipeline.json, never edit it (G24; a deviation is a new project module with tests).")
    resolved = resolve_token(target, real(cwd), {})
    check_written(resolved, raw_only=False)
    if event.get("agent_type") == "paradigm-analyst":
      check_analyst_write(tool, resolved, root)
    if event.get("agent_type") == "methods-auditor":
      try:
        rel = resolved[0].relative_to(real(root)).as_posix() if resolved else ""
      except ValueError:
        rel = ""
      if not (rel.startswith(AUDITOR_MEMORY) or re.fullmatch(r"agent_runs/[^/]+/(05_audit|02b_plan_audit)\.md", rel)):
        block("the methods-auditor is read-only; it may only write 02b_plan_audit.md, 05_audit.md and its memory folder.")


if __name__ == "__main__":
  main()
