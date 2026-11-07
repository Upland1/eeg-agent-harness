"""Assembly of per-file epochs into one data set, and the epochs/folds hashes (G9, G25).

Generic version of P300 ``p300/session.py::assemble_session`` and
``scripts/run_ssvep_methods.py::rows_sha256, epochs_and_folds_sha256`` @ cd5db15.

Unit uids are unique across the assembled files (and therefore across participants
when files of several participants are assembled): uid = (number of units of the earlier
files) + unit index within the file. Arrays per epoch: X, y, unit_local, unit_uid,
file_idx, onset (+ any extra columns the files carry, e.g. code). Per unit uid:
unit_file (file index) and unit_local_of_uid. The stratum used for fold balance and
null shuffles defaults to the file (``unit_file``).
"""

import hashlib
import json

import numpy as np

BASE_KEYS = ("y", "unit", "onset")


def assemble(file_results):
  """List of ``epochs.prepare_file`` outputs (in file order) -> concatenated arrays."""
  if not file_results:
    raise ValueError("no files")
  extra = sorted(set(file_results[0]) - set(BASE_KEYS) - {"X", "keep", "counts", "gates", "segments",
                                                          "unit_start", "unit_end"})
  Xs = []
  cols = {k: [] for k in ("y", "unit_local", "unit_uid", "file_idx", "onset", *extra)}
  unit_file, unit_local_of_uid = [], []
  offset = 0
  shape = None
  for fi, r in enumerate(file_results):
    nu = int(len(r["unit_start"]))
    if shape is None:
      shape = r["X"].shape[1:]
    elif r["X"].shape[1:] != shape:
      raise ValueError(f"file {fi}: epoch shape {r['X'].shape[1:]} != {shape} (channels or length differ)")
    Xs.append(r["X"])
    cols["y"].append(r["y"])
    cols["unit_local"].append(r["unit"])
    cols["unit_uid"].append(r["unit"] + offset)
    cols["file_idx"].append(np.full(len(r["y"]), fi, dtype=np.int64))
    cols["onset"].append(r["onset"])
    for k in extra:
      cols[k].append(np.asarray(r[k]))
    unit_file += [fi] * nu
    unit_local_of_uid += list(range(nu))
    offset += nu
  out = {k: np.concatenate(v) for k, v in cols.items()}
  for k in ("y", "unit_local", "unit_uid", "file_idx", "onset"):
    out[k] = out[k].astype(np.int64)
  out["X"] = np.concatenate(Xs, axis=0)
  out["unit_file"] = np.asarray(unit_file, dtype=np.int64)
  out["unit_local_of_uid"] = np.asarray(unit_local_of_uid, dtype=np.int64)
  return out


def _canon(obj):
  def conv(o):
    if isinstance(o, np.generic):
      return o.item()
    if isinstance(o, np.ndarray):
      return o.tolist()
    raise TypeError(type(o))
  return json.dumps(obj, sort_keys=True, default=conv, separators=(",", ":"))


def rows_sha256(obj):
  """sha256 of the canonical JSON of ``obj`` (numpy scalars and arrays as Python values)."""
  return hashlib.sha256(_canon(obj).encode()).hexdigest()


def epochs_and_folds_sha256(epoch_rows, count_rows, file_names, fold_rows):
  """(epochs hash, folds hash). Epochs: retained epochs (file, unit, unit uid, onset, label,
  extra columns) with the per-file counts and file names; folds: fold of every unit uid.
  Identical hashes across the parts of one data set prove they used the same epochs and
  folds (P300 Stage-2 audit C4 #4)."""
  return rows_sha256({"files": list(file_names), "epochs": epoch_rows, "counts": count_rows}), \
      rows_sha256({"folds": fold_rows})


def epoch_rows(sess, file_names, extra=("code",)):
  """One dict per epoch (the rows hashed above)."""
  cols = [c for c in extra if c in sess]
  return [{"file": file_names[int(sess["file_idx"][i])], "unit": int(sess["unit_local"][i]),
           "unit_uid": int(sess["unit_uid"][i]), "onset": int(sess["onset"][i]), "label": int(sess["y"][i]),
           **{c: sess[c][i].item() if hasattr(sess[c][i], "item") else sess[c][i] for c in cols}}
          for i in range(len(sess["y"]))]
