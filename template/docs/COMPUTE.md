# Compute limits

Set by Sebastian; agents never edit this file (CLAUDE.md G22). The orchestrator runs a
job itself only if its expected runtime fits the limit for its device and its smoke test
has passed; every other job goes to Sebastian as exact commands.

cpu_max_minutes: 120
gpu_max_minutes: 120
gpu_device: cuda:0
cpu_working_threads:

Work expected to take longer than the limit is split into resumable parts (one fold, one
seed or one session per part, each saved with `eegharness.folds`), and each part must fit
the limit on its own. A part that cannot be made to fit, and anything on remote hardware,
goes to Sebastian as an exact command.

<!-- gpu_device: the local GPU the orchestrator may use (e.g. cuda:0), or none.
     With gpu_device: none, no GPU job runs locally whatever gpu_max_minutes says.
     cpu_working_threads: the threads every job of a long run uses (n_jobs, OMP/MKL/OpenBLAS and torch
     threads), set by Sebastian for this machine's cooling (e.g. 4-6 on a laptop), at most its cores; no
     default. eegpipe.settings.validate refuses settings above it, or while it is unset (L39). -->
