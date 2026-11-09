"""Resumable folds that refuse a changed configuration (G22). numpy only.

    from eegharness.folds import FoldStore
    store = FoldStore(out / "folds", config={"model": "net", "channels": chans, "seeds": 3})
    for key in keys:
        if store.done(key):
            continue
        ...
        store.save(key, meta={"best_epoch": 41}, y_true=y, y_pred=p)

Definitions:
  The folder holds ``config.json`` and one ``<key>.npz`` per finished fold. The first
  ``FoldStore`` on a folder writes the configuration; a later one with a different
  configuration (compared as canonical JSON) raises ``ConfigMismatch``: use a new folder.
  ``save`` refuses to overwrite a finished fold and writes atomically (temporary file, then
  rename), so an interrupted run never leaves a half-written fold. Arrays are stored with
  ``allow_pickle=False``; ``meta`` (JSON-serialisable) is stored inside the same file.
  Keys may be real file or method names, with spaces, hyphens, ``+``, ``=``, ``,``, ``(``, ``)``;
  never ``/``, ``\\``, ``:``, ``*``, ``?``, ``"``, ``<``, ``>``, ``|`` or a control character, and
  they start with neither ``.`` nor a space and do not end with a space.
"""

import json
import os
import re
from pathlib import Path

import numpy as np

# Keys may be real file and method names ("Training 5 - F.ebr", "Shrinkage-LDA lsqr", "fbcsp+fbcca"); they
# exclude path separators and characters no common file system allows, and cannot start with "." or a space.
KEY = re.compile(r"[^./\\\s:*?\"<>|\x00-\x1f][^/\\:*?\"<>|\x00-\x1f]*")


class ConfigMismatch(RuntimeError):
  """The folder belongs to a run with another configuration."""


def _canon(cfg) -> str:
  return json.dumps(cfg, sort_keys=True, default=str)


class FoldStore:
  def __init__(self, folder, config: dict):
    self.folder = Path(folder)
    self.folder.mkdir(parents=True, exist_ok=True)
    self.config = config
    cfg_path = self.folder / "config.json"
    if cfg_path.exists():
      saved = json.loads(cfg_path.read_text())
      if _canon(saved) != _canon(json.loads(_canon(config))):
        raise ConfigMismatch(f"{self.folder} was made with another configuration; use a new folder.\n"
                             f"saved: {_canon(saved)}\nnow:   {_canon(config)}")
    else:
      cfg_path.write_text(json.dumps(config, indent=1, sort_keys=True, default=str) + "\n")

  def _path(self, key: str) -> Path:
    if not isinstance(key, str) or not KEY.fullmatch(key) or key != key.rstrip():
      raise ValueError(f"invalid fold key {key!r}")
    return self.folder / f"{key}.npz"

  def done(self, key: str) -> bool:
    return self._path(key).exists()

  def keys(self) -> list:
    return sorted(p.stem for p in self.folder.glob("*.npz"))

  def save(self, key: str, meta: dict | None = None, **arrays) -> Path:
    path = self._path(key)
    if path.exists():
      raise FileExistsError(f"fold {key!r} is already saved in {self.folder}")
    if "__meta__" in arrays:
      raise ValueError("__meta__ is reserved")
    tmp = path.with_name(f".{key}.tmp.npz")
    payload = {k: np.asarray(v) for k, v in arrays.items()}
    payload["__meta__"] = np.array(json.dumps(meta or {}, sort_keys=True, default=str))
    with open(tmp, "wb") as f:
      np.savez(f, **payload)
    os.replace(tmp, path)
    return path

  def load(self, key: str) -> tuple:
    """(arrays dict, meta dict) of a saved fold."""
    with np.load(self._path(key), allow_pickle=False) as z:
      arrays = {k: z[k] for k in z.files if k != "__meta__"}
      meta = json.loads(str(z["__meta__"]))
    return arrays, meta
