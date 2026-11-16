# Worked example: a synthetic SSVEP study

```bash
python examples/ssvep_synthetic/run_example.py <new folder> [--participants 8] [--seed 20261116]
```

About 30 s on a laptop CPU; numpy, scipy, scikit-learn and git only. The script builds a project
in `<new folder>` and runs, in order, what `/apply-pipeline` runs after the agents have written the
adapter and the settings:

| Step | Command (inside the project) | Output |
|---|---|---|
| Data | `eegpipe.testing.synth.recording`: 5 classes (8, 10, 12, 15, 20 Hz, with a 2nd harmonic), 8 trials of 4 s per class and run, runs `A` and `B`, 8 channels at 256 Hz, white noise of SD 1, a sinusoid amplitude drawn per participant from [0.03, 0.12]; `P00` is the development participant | `data/raw/P*/A.npz`, `B.npz` |
| Adapter | `adapter.py` (the four functions of the runner contract) | committed |
| Settings | `eegpipe.settings.from_profile("ssvep")`, with the study's values; primary `f1/fbcsp+fbcca/Shrinkage-LDA lsqr`, comparator `ssvep/fbcca`; Holm family = the primary; networks off | `configs/pipeline.json`, committed |
| Select and freeze | `python -m eegpipe.runner.select`; the settings point at the selection; commit | `configs/selection/<run>/selection.json` |
| Stage | `python -m eegpipe.runner.stage` at the frozen commit, one child process per part | `outputs/stage/main_<hash>_<commit>/` |
| Collect | `python -m eegpipe.runner.collect` | `outputs/stats/confirmatory/<run>/tests.csv`, `participants.csv`, ... |
| Numbers | a committed spec `configs/numbers.json`, `python -m eegharness.numbers derive`, `results.md` with `[num:key]` citations, `python -m eegharness.numbers check` | `outputs/numbers/<run>/numbers.json`, `results.md` |

With the defaults the check reports `10 citation(s), 0 problem(s)`, and the result is: the trained
primary is worse than training-free FBCCA on these data (Hodges-Lehmann -7.2 pp, 95 % bootstrap
interval -12.5 to -1.9 pp, 1 positive, 6 negative, 1 zero difference, Holm p = 0.0418; mean balanced
accuracy 46.2 % against 53.4 %). With 16 training trials per class a trained classifier has little
to learn from; the example shows the machinery, not a method ranking. `kit_tests/test_worked_example.py`
pins these outputs (`kit_tests/golden/worked_example_ssvep.json`).

What the example leaves out, because the agents do it in a real study: reading the recordings
(profiler, reader plugin), `docs/PARADIGM.md`, the plan and its audit, the development run, the
human approvals, permutation tests (`permutation.n_permutations` is 0 here), the network methods,
and the results audit.
