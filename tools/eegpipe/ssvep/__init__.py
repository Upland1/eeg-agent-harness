"""SSVEP option of eegpipe (Sebastian's decision, 2026-11-07): FBCCA, FBCSP (+ LDA), CCNN and
DualBranchFusionCNN, ported from ``mas-ssvep-eeg-xai`` v1.0.4 (f725369). Everything that was a
module constant there (stimulus frequencies, harmonics, sub-band edges, fs, channels, window)
is a setting filled from PARADIGM.md (``ssvep`` profile). Filter banks run on the continuous
recording, never on short windows (G21; [M] PF-14).

Importing this package registers the feature steps ``fbcsp``, ``fbcca`` and ``fbcsp+fbcca`` in
``eegpipe.classical`` (they take filter-bank epochs (n, B, C, T) from ``filterbank.subband_epochs``).
"""

from eegpipe import classical as _cl
from eegpipe.ssvep import fbcca as _fbcca
from eegpipe.ssvep import fbcsp as _fbcsp


def _fbcsp_step(f1cfg):
  c = f1cfg["fbcsp"]
  return ("fbcsp", _fbcsp.FBCSPTransformer(n_components=c["n_components"], reg=c["reg"], var_floor=c["var_floor"]))


def _fbcca_step(f1cfg):
  c = f1cfg["fbcca"]
  return ("fbcca", _fbcca.FBCCAFeatures(fs=c["fs_hz"], stimulus_freqs_hz=c["stimulus_freqs_hz"],
                                        n_harmonics=c["n_harmonics"], response_multiple=c["response_multiple"],
                                        weight_a=c["weight_a"], weight_b=c["weight_b"]))


def _union_step(f1cfg):
  """FBCSP features then FBCCA scores. With ``f1.fbcca.n_bands`` = n the input holds the n FBCCA-bank bands
  first and the FBCSP-bank bands after them (runner input "fb_both"); without it both read the same bands."""
  from sklearn.pipeline import FeatureUnion, Pipeline

  from eegpipe.ssvep.filterbank import BandSlice
  n = f1cfg["fbcca"].get("n_bands")
  if n is None:
    return ("fbcsp+fbcca", FeatureUnion([_fbcsp_step(f1cfg), _fbcca_step(f1cfg)]))
  n = int(n)
  return ("fbcsp+fbcca", FeatureUnion([("fbcsp", Pipeline([("bands", BandSlice(n, None)), _fbcsp_step(f1cfg)])),
                                        ("fbcca", Pipeline([("bands", BandSlice(0, n)), _fbcca_step(f1cfg)]))]))


_cl.FEATURE_STEPS.update({"fbcsp": _fbcsp_step, "fbcca": _fbcca_step, "fbcsp+fbcca": _union_step})
