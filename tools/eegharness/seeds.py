"""Seeds, seed spread and device provenance (G18). torch is optional: used only if installed.

    from eegharness.seeds import fold_seed, seed_everything, torch_generator, seed_summary
    for r in range(3):                       # at least 3 seeds (G18)
        for f, (train, test) in enumerate(splits):
            s = fold_seed(42, r, f)
            seed_everything(s)               # before building the model
            loader = DataLoader(..., generator=torch_generator(s))

Definitions:
  ``fold_seed(base, repeat, fold) = base + 1000 * repeat + fold`` (fold < 1000): distinct
  for every (repeat, fold), the same for every arm of an A/B comparison.
  ``seed_everything`` seeds Python's ``random``, numpy's global generator and, if torch can
  be imported, torch (CPU and CUDA); with ``deterministic=True`` it also asks torch for
  deterministic algorithms (warn only) and disables cuDNN autotuning. It returns what it set.
  ``torch_state()`` describes torch's device and determinism settings if the running process
  has imported torch, else None; ``outputs.new_output_dir`` stores it in provenance.json.
  ``seed_summary(values)``: n, mean, SD (ddof 1), min, max, and whether n meets the G18
  minimum of 3.
"""

import math
import random
import sys

import numpy as np

MIN_SEEDS = 3


def fold_seed(base: int, repeat: int, fold: int) -> int:
  if not 0 <= fold < 1000 or repeat < 0:
    raise ValueError("need 0 <= fold < 1000 and repeat >= 0")
  return int(base) + 1000 * int(repeat) + int(fold)


def _torch():
  try:
    import torch  # noqa: PLC0415 (optional dependency)
  except ImportError:
    return None
  return torch


def seed_everything(seed: int, *, deterministic: bool = True) -> dict:
  random.seed(seed)
  np.random.seed(seed % (2**32))
  done = {"seed": int(seed), "python": True, "numpy": True, "torch": False}
  torch = _torch()
  if torch is not None:
    torch.manual_seed(seed)
    if hasattr(torch, "cuda") and torch.cuda.is_available():
      torch.cuda.manual_seed_all(seed)
    if deterministic:
      torch.use_deterministic_algorithms(True, warn_only=True)
      torch.backends.cudnn.deterministic = True
      torch.backends.cudnn.benchmark = False
    done["torch"] = True
    done["deterministic"] = bool(deterministic)
  return done


def torch_generator(seed: int):
  """A seeded torch.Generator for DataLoader(generator=...)."""
  torch = _torch()
  if torch is None:
    raise ImportError("torch is not installed; torch_generator needs it")
  g = torch.Generator()
  g.manual_seed(seed)
  return g


def torch_state():
  """Device and determinism settings of an already imported torch, else None."""
  torch = sys.modules.get("torch")
  if torch is None:
    return None
  st = {"torch": getattr(torch, "__version__", "unknown")}
  try:
    cuda = torch.cuda.is_available()
    st["cuda_available"] = bool(cuda)
    st["cuda_version"] = getattr(torch.version, "cuda", None)
    st["devices"] = [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())] if cuda else []
    st["cudnn_deterministic"] = bool(torch.backends.cudnn.deterministic)
    st["cudnn_benchmark"] = bool(torch.backends.cudnn.benchmark)
    st["deterministic_algorithms"] = bool(torch.are_deterministic_algorithms_enabled())
  except Exception as e:  # never let provenance fail a run
    st["error"] = f"{type(e).__name__}: {e}"
  return st


def seed_summary(values) -> dict:
  v = [float(x) for x in values]
  if not v:
    raise ValueError("no values")
  n = len(v)
  mean = sum(v) / n
  sd = math.sqrt(sum((x - mean) ** 2 for x in v) / (n - 1)) if n > 1 else float("nan")
  return {"n": n, "mean": mean, "sd": sd, "min": min(v), "max": max(v), "meets_minimum": n >= MIN_SEEDS}
