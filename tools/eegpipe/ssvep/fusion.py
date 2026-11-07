"""Dual-branch fusion CNN: spatial-harmonic power map + FBCCA scores (torch).

Ported from ``mas-ssvep-eeg-xai`` v1.0.4 ``src/models/cnn/spatial_spectral_cnn.py:40-55``
(``DualBranchFusionCNN``) and ``src/features/ssvep/harmonic_psd.py``, generalised:
  * the spatial input is (channels chosen BY NAME) x (power at the harmonic frequencies of the
    configured stimulus frequencies, on the actual fs grid): ``harmonic_map``; [M] used positional
    channels (1, 4, 5, 6) of a 7-channel layout (PF-06) and an fs-250 PSD grid (PF-04);
  * the first Linear of the spatial branch is sized by a dummy forward ([M] hard-wired 32 * 6 for
    a 4 x 8 map); with a 4 x 8 map and 5 FBCCA scores the parameter count is [M]'s 10,005;
  * both inputs are packed into one row (n, 1, C_sel * n_h + K) so that the shared trainer
    (``networks.fit_network``) trains it with grouped inner validation and early stopping, and its
    ``per_feature`` normalisation over the FITTING epochs is [M]'s per-branch StandardScaler
    (fitted on the training fold, l.80-88); [M] trained 140 fixed epochs without early stopping
    (a fixed-epoch run is ``patience`` > ``max_epochs`` in the trainer table).
Not ported: ``train_and_eval_fusion_cnn_cv`` (window-level StratifiedKFold, PF-01), the temporal
smoothing across trials (PF-02, G17 h) and ``train_final_model.py`` (fits on all windows).
"""

import numpy as np
import torch
from scipy import signal
from torch import nn

from eegpipe import networks as nw


def harmonic_targets(freqs, n_harmonics, response_multiple=1):
  """Frequencies f * m * h, for each stimulus frequency f (outer) and harmonic h (inner)."""
  return [float(f) * response_multiple * h for f in freqs for h in range(1, n_harmonics + 1)]


def harmonic_map(epochs, fs, targets, nfft=None):
  """(n, C, T) -> (n, C, n_targets): periodogram power (boxcar, density) at the bin nearest each
  target frequency; targets at or above Nyquist are refused."""
  X = np.asarray(epochs, dtype=np.float64)
  nfft = int(nfft or X.shape[-1])
  if max(targets) >= fs / 2:
    raise ValueError(f"a harmonic target ({max(targets)} Hz) is at or above Nyquist ({fs / 2} Hz)")
  f, p = signal.periodogram(X, fs=fs, window="boxcar", nfft=nfft, detrend="constant", scaling="density", axis=-1)
  idx = [int(np.argmin(np.abs(f - t))) for t in targets]
  return p[..., idx]


def pack(spatial, scores):
  """(n, C, H), (n, K) -> (n, 1, C * H + K) float64 (channel-major, then the K scores)."""
  spatial, scores = np.asarray(spatial, dtype=np.float64), np.asarray(scores, dtype=np.float64)
  return np.concatenate([spatial.reshape(len(spatial), -1), scores], axis=1)[:, None, :]


class DualBranchFusionCNN(nn.Module):
  def __init__(self, n_classes, n_spatial_channels, n_harmonic_bins, n_fbcca, dropout):
    super().__init__()
    self.shape = (int(n_spatial_channels), int(n_harmonic_bins))
    if self.shape[1] < 3:
      raise ValueError("need at least 3 harmonic bins (the (1, 3) convolution)")
    self.spatial = nn.Sequential(
      nn.Conv2d(1, 16, (self.shape[0], 1), bias=False), nn.BatchNorm2d(16), nn.ELU(), nn.Dropout2d(dropout),
      nn.Conv2d(16, 32, (1, 3), bias=False), nn.BatchNorm2d(32), nn.ELU(), nn.Dropout2d(dropout), nn.Flatten())
    with torch.no_grad():
      was = self.training
      self.eval()
      n_flat = self.spatial(torch.zeros(1, 1, *self.shape)).shape[1]
      self.train(was)
    self.spatial_head = nn.Sequential(nn.Linear(n_flat, 32), nn.ELU(), nn.Dropout(dropout))
    self.fbcca = nn.Sequential(nn.Linear(n_fbcca, 16), nn.BatchNorm1d(16), nn.ELU(), nn.Dropout(dropout),
                               nn.Linear(16, 16), nn.ELU())
    self.head = nn.Sequential(nn.Linear(48, 32), nn.ELU(), nn.Dropout(dropout), nn.Linear(32, n_classes))

  def forward(self, x_spatial, x_fbcca):
    return self.head(torch.cat([self.spatial_head(self.spatial(x_spatial)), self.fbcca(x_fbcca)], dim=1))


class PackedFusion(nn.Module):
  """DualBranchFusionCNN on packed rows (B, 1, C * H + K); built by networks.model_builder."""

  def __init__(self, n_classes, n_channels, n_samples, n_spatial_channels, n_harmonic_bins, n_fbcca, dropout):
    super().__init__()
    if n_channels != 1 or n_samples != n_spatial_channels * n_harmonic_bins + n_fbcca:
      raise ValueError(f"packed input (1, {n_samples}) != (1, {n_spatial_channels} * {n_harmonic_bins} + {n_fbcca})")
    self.c, self.h, self.k = n_spatial_channels, n_harmonic_bins, n_fbcca
    self.net = DualBranchFusionCNN(n_classes, n_spatial_channels, n_harmonic_bins, n_fbcca, dropout)

  def forward(self, x):
    if x.dim() == 4:
      x = x[:, 0]
    x = x[:, 0]
    sp = x[:, :self.c * self.h].reshape(-1, 1, self.c, self.h)
    return self.net(sp, x[:, self.c * self.h:])


nw.CLASSES["PackedFusion"] = PackedFusion
