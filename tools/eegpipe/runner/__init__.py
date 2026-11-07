"""The dev -> freeze -> confirm machinery (G19, G22, G25).

  python -m eegpipe.runner.methods --config <part_config.json> --out <folder>      one data part x one family
  python -m eegpipe.runner.select  --config configs/pipeline.json --out outputs/selection
  python -m eegpipe.runner.stage   --config configs/pipeline.json --out outputs/stage2 [--parts cpu|gpu]
  python -m eegpipe.runner.collect --stage <root> --out outputs/stage2_stats [--interim]

Generic versions of the P300 project's ``scripts/run_ssvep_methods.py``, ``scripts/run_stage2.py``,
``tools/select_stage2_sessions.py`` and ``tools/stage2_stats.py`` @ cd5db15. What those scripts
did with the P300 study's files is the project ADAPTER's job (``adapter.py`` at the project root,
named by the settings key ``adapter``):

  dataset_parts(data_root) -> [{"participant": str, "part": str, "files": [relative paths]}]
      the data parts (e.g. sessions) of the study; one part is one evaluation (its own folds);
  read(path) -> (data (C, N) float, fs float, ch_names list)            fs and names from the header (G21)
  events(path, data, fs, ch_names, settings) -> the event table of eegpipe.epochs
      (onset, unit, label, unit_start, unit_end, optional code and unit_target);
  condition_of(path) -> str   (optional; default: the file name)
"""
