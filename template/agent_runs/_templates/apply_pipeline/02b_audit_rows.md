## Pipeline audit rows — add to 02b_plan_audit.md (and the results check in 05_audit.md)

| Check | PASS / FAIL / N/A | Evidence (file:line, output path) |
|---|---|---|
| G24: `eegpipe/` untouched (`git diff <base> -- eegpipe` empty); any gap is a new project module with tests |  |  |
| Adapter: label rule reproduces PARADIGM exactly (test name); units never cross; unit ids unique across files |  |  |
| Adapter: fs and channel names from the header; channels selected by name (G21) |  |  |
| Settings: `validate` passes; every required key has a source; no unconfirmed profile default left (G17 i) |  |  |
| Unit (G13): the label unit of the permutation scheme argued from event timing |  |  |
| Folds: grouped by unit, balanced by stratum (and by label for per-unit labels); `check_no_leak` on every split |  |  |
| Gates: span and window gates reported for every file; any failure stopped the run |  |  |
| L56: every quantity a gate, runtime bound or decision rule uses names its code path and output field; `check_plan_fields.py` PASS (`--final` after the code) |  |  |
| Development vs confirmation (G19, G25): disjoint; selection label-free and seeded; freeze commit approved |  |  |
| Stage: every part terminal or listed as pending; no provenance stop left unresolved; outputs from one commit |  |  |
| Statistics: Holm family = the planned primaries; INTERIM stamp present if the root was incomplete |  |  |
| Seeds (G18): >= 3 per stochastic method; seed spread reported |  |  |
| Results (G23): every number traced to `eegpipe.runner.collect` / part outputs |  |  |
