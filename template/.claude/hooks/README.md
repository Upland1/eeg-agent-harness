# hooks — guardrails

Registered in `.claude/settings.json`. They run for every Claude session in
this project and for every subagent. Exit code 2 blocks the action and shows the
reason to Claude.

| File | Event | What it does |
|---|---|---|
| `guard.py` | PreToolUse (all tools) | Blocks: changing, copying, moving or uploading anything in `data/raw/` (reading is allowed); changes to `.harness/`; `git push`; history rewrites; `git add -f`, `-A`, `.`; `git add` of CLAUDE.md, `.claude/`, `.harness/`, `agent_runs/`, `data/`; commits or merges on `main`; commit messages mentioning Claude/Anthropic/co-author; methods-auditor writes outside `05_audit.md` and its memory folder. **Evaluation projects** (`.claude/harness.json` has `eval_dir`): any tool call naming the evaluation folder, answer keys, the preregistration, or a term of `<eval_dir>/blocklist.json` (web searches and fetches included) |
| `run_tests.py` | PostToolUse (Edit, Write) | After an edit to a `.py` file under `src/`, `scripts/`, `readers/` or `tests/`, runs `pytest tests/ -q -x`; shows failures to Claude. Silent when there are no tests yet |

Notes:
- The guard matches text, so it is a strong fence, not a wall: a determined
  command could still reach a file by a path it does not recognize. The
  evaluation also scans every session transcript afterwards
  (`eval/tools/check_leaks.py`) and flags the run if anything slipped through.
- You, in your own terminal, are never blocked.
- To switch the hooks off temporarily, rename `.claude/settings.json`.
