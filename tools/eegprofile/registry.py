"""Reader registry: MNE for standard formats, plugins for lab formats.

A plugin is a .py file that defines
  EXTENSIONS = (".xyz",)        # lower-case, with the dot
  def read(path) -> Recording   # see recording.py
and ships with a round-trip test in the project's tests/.
"""

import importlib.util
from pathlib import Path

from .readers import mne_formats


def load_plugin(path):
  path = Path(path)
  spec = importlib.util.spec_from_file_location(f"eegprofile_plugin_{path.stem}", path)
  mod = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(mod)
  if not hasattr(mod, "EXTENSIONS") or not hasattr(mod, "read"):
    raise ValueError(f"plugin {path} must define EXTENSIONS and read(path)")
  mod.PLUGIN_NAME = path.name
  return mod


class Registry:
  def __init__(self, plugins=(), use_mne=True):
    self.readers = {}
    if use_mne:
      for ext in mne_formats.EXTENSIONS:
        self.readers[ext] = mne_formats
    for p in plugins:  # plugins override MNE for the same extension
      mod = load_plugin(p)
      for ext in mod.EXTENSIONS:
        self.readers[ext.lower()] = mod

  def reader_for(self, path):
    return self.readers.get(Path(path).suffix.lower())

  @staticmethod
  def name(reader) -> str:
    return getattr(reader, "PLUGIN_NAME", getattr(reader, "__name__", "?"))
