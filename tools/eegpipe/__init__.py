"""Sebastian's EEG pipeline as a configurable library (harness v0.4, G24).

Classical ML suite, EEGNet and ShallowConvNet with their trainer, phase features and
condition-level connectivity (debiased wPLI, BH-FDR, NBS), the edge-gated GNN, grouped
cross-validation with leakage gates, the dev -> freeze -> confirm runner and paired
statistics, plus an SSVEP option (FBCCA, FBCSP, CCNN, DualBranchFusionCNN).

Ported from the P300 project's ``p300/ssvep-methods`` branch (code @ cd5db15, tests @ d833264)
and from ``mas-ssvep-eeg-xai`` v1.0.4 (f725369); each module names its source.

Vendored: each project holds a committed copy at its root (``eegpipe/``). A project
configures it (``configs/pipeline.json``, ``eegpipe.settings``) and never edits it (G24); a
deviation is a new project module with its own tests. Core needs numpy, scipy and
scikit-learn; torch is needed only by ``networks``, ``graph`` and ``ssvep.ccnn`` /
``ssvep.fusion``.
"""

__version__ = "0.4.0"
