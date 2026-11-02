"""The one structure every reader returns."""

from dataclasses import dataclass, field

import numpy as np


@dataclass
class Recording:
  """A continuous recording as a reader delivers it.

  data: (n_channels, n_samples) float array.
  fs: sampling rate in Hz, as stored in (or derived from) the file.
  ch_names: one name per row of data.
  events: (n_events, 2) int array of (sample index, integer code), sorted by sample.
  durations: optional (n_events,) int array, samples each marker lasted.
  event_labels: optional {code: text} when the format stores text labels.
  meta: anything else the reader wants to report (header fields, units).
  """

  data: np.ndarray
  fs: float
  ch_names: list
  events: np.ndarray
  durations: np.ndarray = None
  event_labels: dict = field(default_factory=dict)
  meta: dict = field(default_factory=dict)

  def validate(self) -> None:
    """Raise ValueError if the reader returned something inconsistent."""
    if self.data.ndim != 2:
      raise ValueError(f"data must be 2-D (channels, samples), got shape {self.data.shape}")
    if len(self.ch_names) != self.data.shape[0]:
      raise ValueError(f"{len(self.ch_names)} channel names for {self.data.shape[0]} channels")
    if not np.isfinite(self.fs) or self.fs <= 0:
      raise ValueError(f"invalid sampling rate {self.fs}")
    ev = np.asarray(self.events)
    if ev.size and (ev.ndim != 2 or ev.shape[1] != 2):
      raise ValueError(f"events must be (n, 2), got shape {ev.shape}")
    if ev.size:
      if ev[:, 0].min() < 0 or ev[:, 0].max() >= self.data.shape[1]:
        raise ValueError("event sample index outside the recording")
      if np.any(np.diff(ev[:, 0]) < 0):
        raise ValueError("events are not sorted by sample")
    if self.durations is not None and len(self.durations) != len(ev):
      raise ValueError("durations must have one entry per event")
