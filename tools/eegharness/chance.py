"""Chance level for a finite number of test trials (G3, G19). Standard library only.

    from eegharness.chance import chance_level, p_above_chance
    chance_level(n_trials=80, n_classes=4, alpha=0.05)   # smallest accuracy significant at alpha
    p_above_chance(n_correct=31, n_trials=80, n_classes=4)

Definitions (binomial model):
  Under H0 each test trial is correct with probability p0 = 1 / n_classes (or ``p0`` if given,
  e.g. the largest class proportion for imbalanced classes), independently.
  ``p_above_chance`` = P(X >= n_correct), X ~ Binomial(n_trials, p0), computed exactly.
  ``chance_level`` = k_min / n_trials, with k_min the smallest k such that P(X >= k) <= alpha.
  Independence holds only if test trials are the exchangeable unit (G13); for windows cut
  from the same trial use the number of trials, or a permutation test instead.
"""

import math


def _log_pmf(k: int, n: int, p: float) -> float:
  if p in (0.0, 1.0):
    return 0.0 if (k == 0 and p == 0.0) or (k == n and p == 1.0) else -math.inf
  return (math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)
          + k * math.log(p) + (n - k) * math.log1p(-p))


def binom_sf(k: int, n: int, p: float) -> float:
  """P(X >= k) for X ~ Binomial(n, p), summed exactly in log space."""
  if not 0 <= p <= 1:
    raise ValueError("p must be in [0, 1]")
  if k <= 0:
    return 1.0
  if k > n:
    return 0.0
  logs = [_log_pmf(j, n, p) for j in range(k, n + 1)]
  m = max(logs)
  if m == -math.inf:
    return 0.0
  return min(1.0, math.exp(m) * sum(math.exp(v - m) for v in logs))


def _p0(n_classes, p0):
  if p0 is not None:
    return float(p0)
  if n_classes < 2:
    raise ValueError("n_classes must be >= 2")
  return 1.0 / n_classes


def p_above_chance(n_correct: int, n_trials: int, n_classes: int = 2, p0: float | None = None) -> float:
  return binom_sf(n_correct, n_trials, _p0(n_classes, p0))


def chance_level(n_trials: int, n_classes: int = 2, alpha: float = 0.05, p0: float | None = None) -> float:
  """Smallest accuracy (fraction) whose one-sided binomial p is <= alpha."""
  if n_trials < 1:
    raise ValueError("n_trials must be >= 1")
  if not 0 < alpha < 1:
    raise ValueError("alpha must be in (0, 1)")
  q = _p0(n_classes, p0)
  for k in range(0, n_trials + 1):
    if binom_sf(k, n_trials, q) <= alpha:
      return k / n_trials
  return math.inf  # not reachable with this many trials
