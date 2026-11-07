# Backlog

Changes planned for the next kit version. Evaluation round 2 was withdrawn; items are taken into the next version as approved.

## v0.3

### L27 — results-analyst derived write-up numbers with scratch scripts outside the repository

Added 2026-11-06. **Done in v0.3.0** (G23, results-analyst instructions, the auditor's
results check; the guard option was not taken: Sebastian chose the auditor).

**What happened.** The results-analyst computed numbers for the write-up with scratch scripts
in `/tmp`, although G11 (derived numbers come from committed scripts,
`template/CLAUDE.md:105`) and lesson L4 forbid it. The numbers in the handoff could not be
reproduced from the repository.

**Planned changes.**

1. `template/.claude/agents/results-analyst.md`: any derivation (difference, ratio, mean,
   p-value, count, interval) goes into a committed tool with a test before its numbers
   enter a handoff. No scratch scripts, no inline calculation.
2. Handoff contract (`template/agent_runs/README.md` and the templates): a handoff that
   cites a path outside the repository cannot be marked READY.
3. To consider, with known-answer tests whichever is chosen:
   - guard: block writes of scripts outside the project root (e.g. `/tmp`, `$TMPDIR`) and
     running them, for all agents or for the results-analyst only;
   - methods-auditor check: flag any path outside the repository cited in a handoff or a
     results file, and any number in `06_results.md` that no committed script outputs.
