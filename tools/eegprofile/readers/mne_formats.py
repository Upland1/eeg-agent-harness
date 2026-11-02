"""Standard formats through MNE-Python (mne.io.read_raw dispatches on the extension)."""

import numpy as np

from ..recording import Recording

EXTENSIONS = (".edf", ".bdf", ".gdf", ".vhdr", ".fif", ".set", ".cnt", ".mff", ".nxe")


def read(path) -> Recording:
  import mne

  raw = mne.io.read_raw(str(path), preload=True, verbose="error")
  fs = float(raw.info["sfreq"])
  picks_stim = mne.pick_types(raw.info, meg=False, stim=True)
  labels = {}
  if len(picks_stim):
    ev = mne.find_events(raw, shortest_event=1, consecutive=True, verbose="error")
    events = np.c_[ev[:, 0] - raw.first_samp, ev[:, 2]].astype(int)
    source = "stim channel " + ",".join(raw.ch_names[i] for i in picks_stim)
  elif len(raw.annotations):
    ev, mapping = mne.events_from_annotations(raw, verbose="error")
    events = np.c_[ev[:, 0] - raw.first_samp, ev[:, 2]].astype(int)
    labels = {int(v): str(k) for k, v in mapping.items()}
    source = "annotations"
  else:
    events = np.zeros((0, 2), dtype=int)
    source = "none found"
  return Recording(data=raw.get_data(), fs=fs, ch_names=list(raw.ch_names), events=events,
                   event_labels=labels,
                   meta={"reader": f"mne {mne.__version__}", "event_source": source,
                         "channel_types": dict(zip(raw.ch_names, raw.get_channel_types()))})
