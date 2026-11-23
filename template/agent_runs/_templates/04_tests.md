# 04 · Tests

Status: DRAFT
Author: synthetic-tester
Reads: 02_plan.md, 03_changes.md, CLAUDE.md

## Tests added

| Test id | Simulates | Expected | Tolerance | Source of the expected answer | Result |
|---|---|---|---|---|---|
| `tests/test_....py::test_...` | | | | [n] / analytic / [own] | PASS / FAIL |

<!-- Source of the expected answer: the paper, textbook result or
documentation that says what the correct output is, or "analytic" with the
one-line derivation (G6). -->

## Command

```bash
pytest tests/ -q            # default run (slow tests left out), with its time
pytest tests/ -q -m ""      # full suite, with its time (G2)
```

## Output summary

<!-- Pass/fail counts and runtime. Paste failures in full. -->

## Coverage gaps

<!-- Planned tests that weren't written, and anything in 03_changes.md
that no test covers. Any tolerance loosened from the plan is listed here
with the reason. -->

## Sources

1.