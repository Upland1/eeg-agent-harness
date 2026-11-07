"""Complex-spectrum CNN (CCNN) for frequency-tagged responses (torch).

Ported from ``mas-ssvep-eeg-xai`` v1.0.4 ``src/models/cnn/ccnn.py:20-53``, unchanged except that
``fs`` has no default (it comes from the header, G21; [M] defaulted to 256) and ``n_filters`` is
explicit in the parameter table (G5; [M] default 2C). The epoch (B, C, T) is zero-padded to
nfft = max(T, round(fs / resolution_hz)), rfft, the bins with f_min <= f <= f_max kept,
[real | imag] / T concatenated along frequency into one map (B, 1, C, 2 n_bins); spatial
Conv2d (1 -> F, (C, 1)) -> BN -> ReLU -> Dropout; spectral Conv2d (F -> F, (1, K)) -> BN -> ReLU ->
Dropout; Linear. Both convolutions keep their bias ([M]'s parameter count R-8: 27,977 for C 7,
32,309 for C 8 at 256 samples, 256 Hz, 3-50 Hz, 0.25 Hz, 5 classes, F = 2C). Trained by
``eegpipe.networks.fit_network`` (grouped inner validation, train-only normalisation, seeds,
early stopping), registered in ``networks.CLASSES`` as "CCNN".
"""

import numpy as np
import torch
from torch import nn

from eegpipe import networks as nw


class CCNN(nn.Module):
  def __init__(self, n_classes, n_channels, n_samples, fs, f_min, f_max, resolution_hz, n_filters, spectral_kernel,
               dropout):
    super().__init__()
    self.n_channels, self.n_samples, self.fs = int(n_channels), int(n_samples), float(fs)
    self.nfft = max(self.n_samples, int(round(self.fs / resolution_hz)))
    freqs = np.fft.rfftfreq(self.nfft, 1.0 / self.fs)
    idx = np.flatnonzero((freqs >= f_min) & (freqs <= f_max))
    if len(idx) < spectral_kernel:
      raise ValueError(f"only {len(idx)} bins in [{f_min}, {f_max}] Hz, need >= spectral_kernel={spectral_kernel}")
    self.register_buffer("bin_idx", torch.as_tensor(idx, dtype=torch.long), persistent=False)
    self.bins_hz = freqs[idx]
    self.n_bins = len(idx)
    F = int(n_filters)
    self.spatial = nn.Sequential(nn.Conv2d(1, F, (self.n_channels, 1)), nn.BatchNorm2d(F), nn.ReLU(), nn.Dropout(dropout))
    self.spectral = nn.Sequential(nn.Conv2d(F, F, (1, spectral_kernel)), nn.BatchNorm2d(F), nn.ReLU(), nn.Dropout(dropout))
    self.head = nn.Linear(F * (2 * self.n_bins - spectral_kernel + 1), n_classes)

  def spectrum(self, x):
    z = torch.fft.rfft(x, n=self.nfft, dim=-1)[..., self.bin_idx] / self.n_samples
    return torch.cat([z.real, z.imag], dim=-1).unsqueeze(1)

  def forward(self, x):
    if x.dim() == 4 and x.shape[1] == 1:
      x = x[:, 0]
    if x.dim() != 3 or x.shape[1] != self.n_channels or x.shape[2] != self.n_samples:
      raise ValueError(f"expected (B, {self.n_channels}, {self.n_samples}), got {tuple(x.shape)}")
    return self.head(self.spectral(self.spatial(self.spectrum(x))).flatten(1))


nw.CLASSES["CCNN"] = CCNN
