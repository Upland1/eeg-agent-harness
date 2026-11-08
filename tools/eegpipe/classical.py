"""Family F1: the 10-model scikit-learn suite of Sebastian's pipeline, and the baseline.

Ported from P300 ``p300/classical.py`` and ``p300/evaluate.py::make_estimator`` @ cd5db15,
itself a port of ``get_sklearn_model_suite`` of ``mas-ssvep-eeg-xai`` v1.0.4 (f725369,
``src/models/classical/sklearn_models.py`` l.17-39): the same 10 models (``MODEL_NAMES``),
in the same order and names, each wrapped as Pipeline(feature step, StandardScaler, model)
so that the scaler is fitted on the training fold only. Every hyperparameter comes from the
settings' parameter table (G5): ``build_model`` refuses a table that does not name every
parameter of the estimator (scikit-learn ``get_params``, except parameters whose default is
the string "deprecated"). Class priors of LDA/QDA are set explicitly in the table: uniform
1/k (k = number of classes) unless the plan says otherwise (``uniform_priors`` helps write
them).

Feature steps (``FEATURE_STEPS``; a project may only choose among them, G24):
  ``raw``: the epoch (n_channels x n_times) flattened channel-major;
  ``cca``: the target-template CCA spatial filter (eegpipe.cca, ERP option);
  ``fbcsp`` / ``fbcca``: registered by ``eegpipe.ssvep`` (SSVEP option).
Method ids: ``baseline`` (CCA + shrinkage LDA, ``make_baseline``) and
``f1/<feature step>/<model name>``.
"""

import numpy as np
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis, QuadraticDiscriminantAnalysis
from sklearn.linear_model import LogisticRegression, RidgeClassifier, SGDClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler

from eegpipe.cca import CCASpatialFilter

MODEL_NAMES = ("Ridge", "LogReg L2", "LogReg L1", "LogReg ElasticNet", "SGD log-loss", "SGD PA",
               "LDA svd", "Shrinkage-LDA lsqr", "Shrinkage-LDA eigen", "QDA")
CLASSES = {c.__name__: c for c in (RidgeClassifier, LogisticRegression, SGDClassifier,
                                   LinearDiscriminantAnalysis, QuadraticDiscriminantAnalysis)}
ARRAY_PARAMS = ("priors",)
FEATURE_STEPS = {}


def flatten_epochs(X):
  """(n_epochs, n_channels, n_times) -> (n_epochs, n_channels * n_times), channel-major."""
  X = np.asarray(X, dtype=np.float64)
  return X.reshape(X.shape[0], -1)


def uniform_priors(k):
  return [1.0 / k] * k


def required_params(cls):
  """Parameter names the table must set for ``cls`` (all but deprecated ones)."""
  return sorted(k for k, v in cls().get_params().items() if not (isinstance(v, str) and v == "deprecated"))


def build_model(spec):
  """spec = {"class": <scikit-learn class name>, "params": {...}} -> unfitted estimator."""
  cls = CLASSES.get(spec["class"])
  if cls is None:
    raise ValueError(f"unknown model class {spec['class']!r}; known: {sorted(CLASSES)}")
  params = dict(spec["params"])
  need = set(required_params(cls))
  missing, extra = need - set(params), set(params) - need
  if missing or extra:
    raise ValueError(f"{spec['class']}: parameters missing {sorted(missing)}, unknown {sorted(extra)}")
  for k in ARRAY_PARAMS:
    if k in params and params[k] is not None:
      params[k] = np.asarray(params[k], dtype=np.float64)
  return cls(**params)


def build_scaler(scfg):
  return StandardScaler(copy=True, with_mean=bool(scfg["with_mean"]), with_std=bool(scfg["with_std"]))


def _raw(f1cfg):
  return ("flatten", FunctionTransformer(flatten_epochs, validate=False, accept_sparse=False, check_inverse=False))


def _cca(f1cfg):
  c = f1cfg["cca"]
  return ("cca", CCASpatialFilter(n_filters=c["n_filters"], reg=c["reg"], target_label=c.get("target_label", 1)))


FEATURE_STEPS.update(raw=_raw, cca=_cca)


def feature_step(space, f1cfg):
  if space not in FEATURE_STEPS and space in ("fbcsp", "fbcca", "fbcsp+fbcca"):
    import eegpipe.ssvep  # noqa: F401  (registers the SSVEP feature steps)
  if space not in FEATURE_STEPS:
    raise ValueError(f"unknown feature space {space!r}; known: {sorted(FEATURE_STEPS)}")
  return FEATURE_STEPS[space](f1cfg)


def make_f1(space, model_name, f1cfg):
  """Pipeline(feature step, StandardScaler, model) for one F1 configuration."""
  if model_name not in f1cfg["models"]:
    raise ValueError(f"model {model_name!r} not in the settings' f1.models")
  return Pipeline([feature_step(space, f1cfg), ("scaler", build_scaler(f1cfg["scaler"])),
                   ("model", build_model(f1cfg["models"][model_name]))])


def make_baseline(model_cfg):
  """model_cfg = {"cca": {"n_filters", "reg"}, "lda": {"solver", "shrinkage", "priors"}}."""
  c, l = model_cfg["cca"], model_cfg["lda"]
  return Pipeline([
    ("cca", CCASpatialFilter(n_filters=c["n_filters"], reg=c["reg"], target_label=c.get("target_label", 1))),
    ("lda", LinearDiscriminantAnalysis(solver=l["solver"], shrinkage=l["shrinkage"],
                                       priors=None if l["priors"] is None else np.asarray(l["priors"], float))),
  ])


def method_ids(cfg):
  """All F1 method ids of a run: the baseline first (if configured), then F1 in settings order."""
  f1 = cfg["f1"]
  base = ["baseline"] if cfg.get("baseline") else []
  return base + [f"f1/{s}/{m}" for s in f1["feature_spaces"] for m in f1["model_order"]]


def primary_f1_id(cfg):
  p = cfg["f1"]["primary"]
  return f"f1/{p['features']}/{p['model']}"


def make_method(method_id, cfg):
  """Unfitted estimator for an F1 method id."""
  if method_id == "baseline":
    return make_baseline(cfg["baseline"]["model"])
  parts = method_id.split("/", 2)
  if len(parts) != 3 or parts[0] != "f1":
    raise ValueError(f"unknown method id {method_id!r}")
  return make_f1(parts[1], parts[2], cfg["f1"])
