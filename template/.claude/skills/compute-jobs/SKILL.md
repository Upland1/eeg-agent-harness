---
name: compute-jobs
description: How long and GPU jobs are planned, smoke-tested, run (by the orchestrator within docs/COMPUTE.md limits, or by Sebastian), resumed and reported (CLAUDE.md G22). Read it when a plan has any job longer than a few minutes, any GPU job, or any job on remote hardware.
---

# Compute jobs (CLAUDE.md G22)

## Limits

`docs/COMPUTE.md` holds the per-job limits Sebastian set for this project:

| Key | Meaning |
|---|---|
| `cpu_max_minutes` | longest CPU job the orchestrator may run itself |
| `gpu_max_minutes` | longest local GPU job the orchestrator may run itself (0 = none) |
| `gpu_device` | which local GPU, if any |

Agents never edit `docs/COMPUTE.md`. Missing file or key = 0 (nothing runs locally
beyond smoke tests).

## In the plan ("Runs" section of 02_plan.md)

One row per job: exact command, device (cpu / local GPU / remote), expected runtime and
how it was estimated (smoke-test time × scale), seeds, output folder (G9), who runs it.
The orchestrator runs it only if the expected runtime is within the limit for its device;
otherwise Sebastian does.

## Before any long job

1. A **smoke test** committed in `tests/` or as a script flag (`--smoke-test`) runs the
   same entry point end to end on synthetic data or one fold, on CPU, in under 5 minutes.
   It passes on the commit that will run the job.
2. The job is **resumable**: each fold/seed is saved as it finishes with its
   configuration (`eegharness.folds.FoldStore`). A rerun skips finished folds; a different
   configuration on the same folder is refused ("use a new output folder").
3. The audit (05_audit) is PASS.

## Running (orchestrator)

- Run in the foreground and wait for it; never leave background jobs.
- If the job exceeds its stated runtime by more than 50 %, stop it, record it in
  `log.md`, and hand it to Sebastian with the resumable command.
- Record device, runtime and exit status in `log.md`; provenance (G9) records the device.

## Handing a job to Sebastian

One message (logged in `human_contacts.md` as an approval/request): the exact commands,
where to run them (local GPU, Colab, cluster), expected runtime, the environment needed
(do not reinstall packages that replace the GPU build), where outputs must be written so
they persist, and which folders to drop into the run folder.
