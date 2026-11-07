# Compute limits

Set by Sebastian; agents never edit this file (CLAUDE.md G22). The orchestrator runs a
job itself only if its expected runtime fits the limit for its device and its smoke test
has passed; every other job goes to Sebastian as exact commands.

cpu_max_minutes: 10
gpu_max_minutes: 30
gpu_device: cuda:0

<!-- gpu_device: the local GPU the orchestrator may use (e.g. cuda:0), or none.
     With gpu_device: none, no GPU job runs locally whatever gpu_max_minutes says. -->
