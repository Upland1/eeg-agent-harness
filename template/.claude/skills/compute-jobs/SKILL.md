---
name: compute-jobs
description: How long and GPU jobs are planned, smoke-tested, run (by the orchestrator within docs/COMPUTE.md limits, or by the supervisor), resumed and reported (CLAUDE.md G22). Read it when a plan has any job longer than a few minutes, any GPU job, or any job on remote hardware.
---

# Compute jobs (CLAUDE.md G22)

## Limits

`docs/COMPUTE.md` holds the per-job limits the supervisor set for this project:

| Key | Meaning |
|---|---|
| `cpu_max_minutes` | longest CPU job the orchestrator may run itself |
| `gpu_max_minutes` | longest local GPU job the orchestrator may run itself (0 = none) |
| `gpu_device` | which local GPU, if any |
| `cpu_working_threads` | threads every job of a long run uses (n_jobs, OMP/MKL/OpenBLAS, torch); below the core limit, for the machine's cooling (L39) |
| `memory_max_gb` | memory the orchestrator's jobs may use together; no default, nothing runs in batches while unset (L54) |

Agents never edit `docs/COMPUTE.md`. Missing file or key = 0 (nothing runs locally
beyond smoke tests).

## In the plan ("Runs" section of 02_plan.md)

One row per job: exact command, device (cpu / local GPU / remote), expected runtime and
how it was estimated (smoke-test time × scale), seeds, output folder (G9), who runs it.
The orchestrator runs it only if the expected runtime is within the limit for its device;
otherwise the supervisor does.

## Before any long job

1. A **smoke test** committed in `tests/` or as a script flag (`--smoke-test`) runs the
   same entry point end to end on synthetic data or one fold, on CPU, in under 5 minutes.
   It passes on the commit that will run the job.
2. The job is **resumable**: each fold/seed is saved as it finishes with its
   configuration (`eegharness.folds.FoldStore`). A rerun skips finished folds; a different
   configuration on the same folder is refused ("use a new output folder").
3. The audit (05_audit) is PASS.

## Running (orchestrator)

- A job (or part) longer than a few minutes runs in the Bash tool's background mode,
  because a foreground call times out after 10 minutes; wait for its completion
  notification before doing anything that depends on it, start no second job meanwhile,
  and never end the session with a job still running.
- Work longer than the limit runs as resumable parts (per fold, seed or session), each
  within the limit; the next part starts only after the previous one finished cleanly.
- If the job exceeds its stated runtime by more than 50 %, stop it, record it in
  `log.md`, and hand it to the supervisor with the resumable command.
- Record device, runtime and exit status in `log.md`; provenance (G9) records the device.
- **Memory and data before each batch (L54, L44).** `docs/COMPUTE.md` sets `memory_max_gb`, the
  memory the orchestrator's jobs may use together (set by the supervisor). The plan states each part's
  peak memory, measured in the development run (maximum RSS, e.g. `/usr/bin/time -v`); a batch runs
  b parts at once only if b × peak fits `memory_max_gb`, and before each batch the driver checks
  that available memory is at least that sum, and waits or stops if not. The same check confirms
  `data/raw` resolves and that every profiled file is present, and stops otherwise:
  `python -m eegharness.compute precheck --parts <b> --peak-gb <peak>` (exit 1 = do not start).
- **Threads and temperature (L39).** A core limit is not a thermal limit. Every job of a long run
  uses `cpu_working_threads` threads: settings `n_jobs` at most that (`eegpipe.settings.validate`
  refuses more, and refuses while it is unset), and the driver exports `OMP_NUM_THREADS`,
  `MKL_NUM_THREADS`, `OPENBLAS_NUM_THREADS` and sets torch's threads to it. Every long-run driver
  logs CPU and GPU temperature once a minute next to its job table:
  `python -m eegharness.compute templog --out <run log folder>/temperature.tsv --interval 60 --pid <driver pid>`
  (in the background, collected with the job). Report the maximum per part; a reading within 5 °C
  of the critical limit goes to the supervisor.

## Handing a job to the supervisor

One message (logged in `human_contacts.md` as an approval/request): the exact commands,
where to run them (local GPU, Colab, cluster), expected runtime, the environment needed
(do not reinstall packages that replace the GPU build), where outputs must be written so
they persist, and which folders to drop into the run folder.
