# Changelog

## 0.1.0 — 2026-11-02

First version, derived from the P300 project setup of 2026-11-01 with all
paradigm content removed.

- General rules G1–G8; "When you don't know" (UNKNOWN, questions only a human
  can answer, contamination flags).
- Six agents: paradigm-analyst (new), literature-scout, pipeline-engineer,
  synthetic-tester, methods-auditor, results-analyst; all read
  `docs/DATA_PROFILE.md` and `docs/PARADIGM.md` instead of fixed data facts.
- Skills: `onboard` (new), `assignment` (requires an approved PARADIGM.md),
  `cite-sources`.
- Deterministic profiler with a reader registry (MNE formats + per-project plugins).
- Guard hook: recordings read-only, `.harness/` frozen, git safety, auditor
  read-only, evaluation material and blocklist out of reach; control mode.
- `new_project.py`: harness and control arms, frozen-version check for evaluations.
- `kit_tests/`: 14 known-answer tests (profiler, guard, project creation, run isolation, paradigm neutrality).
