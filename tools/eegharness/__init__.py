"""Shared tools for EEG analysis projects: versioned output folders with provenance (G9),
a regression check between two output folders, grouped splits with a leakage check,
unit-level permutation tests and chance levels (core, numpy only), and seeds and resumable
folds for long or deep-learning jobs (torch optional, never required).

Vendored: each project holds a committed copy of this package at its root
(``eegharness/``), so project code never imports uncommitted files. Do not edit the copy;
a new harness version replaces it.
"""

__version__ = "0.4.1"
