"""check_install.py: known answers on this environment and on a missing or too-old package."""

import sys
from importlib import metadata
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT))
import check_install as ci  # noqa: E402


def test_requirements_are_read_from_requirements_txt():
  assert ci.requirements() == {"numpy": "1.26", "scipy": "1.18", "scikit-learn": "1.9", "mne": "1.6", "pytest": "8"}


def test_quick_check_passes_here_and_fails_on_a_missing_or_old_package(monkeypatch, capsys):
  assert ci.main(["--quick"]) == 0
  assert "ready" in capsys.readouterr().out
  real = metadata.version

  def missing(dist):
    if dist == "scipy":
      raise metadata.PackageNotFoundError(dist)
    return real(dist)

  monkeypatch.setattr(ci.metadata, "version", missing)
  assert ci.main(["--quick"]) == 1
  out = capsys.readouterr().out
  assert "MISSING  scipy" in out and "NOT READY: scipy" in out
  monkeypatch.setattr(ci.metadata, "version", lambda d: "1.2.0" if d == "mne" else real(d))
  assert ci.main(["--quick"]) == 1
  assert "TOO OLD  mne: 1.2.0 (>= 1.6)" in capsys.readouterr().out


def test_version_comparison_is_numeric():
  assert ci._ver("1.10.0") > ci._ver("1.9")
  assert ci._ver("2.13.0+cpu") >= ci._ver("2.13")
