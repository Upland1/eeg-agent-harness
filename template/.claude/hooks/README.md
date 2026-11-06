# hooks — guardrails

Registered in `.claude/settings.json`. They run for every Claude session in
this project and for every subagent. Exit code 2 blocks the action and shows the
reason to Claude.

| File | Event | What it does |
|---|---|---|
| `guard.py` | PreToolUse (all tools) | Blocks: changing, copying, moving or uploading anything in `data/raw/` (reading is allowed); changes to `.harness/` and to the vendored `eegharness/`; `git push`; history rewrites; `git add -f`, `-A`, `.`; `git add` of CLAUDE.md, `.claude/`, `.harness/`, `agent_runs/`, `data/`; commits or merges on `main`; commit messages mentioning Claude/Anthropic/co-author; methods-auditor writes outside `02b_plan_audit.md`, `05_audit.md` and its memory folder, and any auditor shell command outside its read-only list (read-only git, `python -m pytest -p no:cacheprovider`, file reading, `compare_runs` into the run folder). Shell commands are tokenized: rules look at the command word, operands, redirect targets and the commit message, and at heredocs or `-c` strings run by a shell; an unparseable command gets the conservative whole-text checks. **Evaluation projects** (`.claude/harness.json` has `eval_dir`): any tool call naming the evaluation folder, answer keys, the preregistration, or a term of `<eval_dir>/blocklist.json` (web searches and fetches included) |
| `run_tests.py` | PostToolUse (Edit, Write) | After an edit to a `.py` file under `src/`, `scripts/`, `readers/` or `tests/`, runs `pytest tests/ -q -x`; shows failures to Claude. Silent when there are no tests yet |
| `log_cost.py` | SubagentStop, Stop | Appends tokens (input, output, cache write, cache read; once per API response) and wall time of each agent call, and the orchestrator session's running totals, to `agent_runs/<run>/cost.jsonl` (control arm: `.claude/cost.jsonl`). Never blocks. `python .claude/hooks/log_cost.py --summary agent_runs/<run>` prints the table for `log.md` |

Notes:
- The guard resolves every path it can see to an absolute path before checking it
  (relative paths, `..`, `cd`, symlinks, quotes, globs, `~`, variables set in the
  command, string literals in code). It is still a fence, not a wall: a path built at
  run time (inside a script, by `$( )`, or from variables set in an earlier command)
  is not visible to it. The
  evaluation also scans every session transcript afterwards
  (`eval/tools/check_leaks.py`) and flags the run if anything slipped through.
- You, in your own terminal, are never blocked.
- To switch the hooks off temporarily, rename `.claude/settings.json`.
