# Human contacts  (written by: orchestrator; categories confirmed by Sebastian)

One row per contact with Sebastian: every question, every approval request, every
request to run something or provide a file (CLAUDE.md G16). Write the row **before**
sending the contact; fill "Answer" and "Minutes" when it comes back.

Categories (the agent proposes, Sebastian confirms in the last column):
- `approval` — a gate the workflow requires (plan, PARADIGM, rule, merge, long run).
- `human-only fact` — no written source in reach answers it (all four searched, below).
- `should-have-found` — the answer was in a written source in reach: an input, a document
  in the data folder, documentation an input points to, or a measurement the agents could
  have made. Say which source in "Notes".

Sources to search before any question (G16): (1) inputs in full, appendices and tables;
(2) documents in the data folder and `inputs/`; (3) documentation the inputs point to;
(4) measurement with project code. In "Sources checked", give each one and what it said
(`searched, not found` counts).

| # | Date | Step | Contact (question or request, verbatim) | Sources checked → what each said | Proposed category | Answer | Minutes (Sebastian) | Confirmed category | Notes |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 2026-11-06 | 7 Approval | Approve docs/PARADIGM.md (Revision 1) and answer Q1–Q5 of section 10; decide on M6/M7 and the absolute path in DATA_PROFILE.* | PARADIGM §10 lists per question: (a) inputs/professor_notes.md full — not found; (b) data/raw/bitacora.docx full — partial (tones, ISI, reference, Oz note); (c) docs named by inputs — none named; (d) measurements M1–M5 @ bf7d88d | approval (+ Q1, Q2, Q4 human-only fact; Q3, Q5 human-only fact pending M7) | not given (headless validation run, stopped at the approval STOP) | — | approval; Q1 human-only fact; Q2 human-only fact; Q3 human-only fact (kept as an example); Q4 human-only fact; Q5 should-have-found | Single contact for onboarding. Categories confirmed by Sebastian on 2026-11-05. Q5 (sub-03 Oz detachment): a finer measurement (M7) with project code could have answered it before asking (G16 source 4). |
