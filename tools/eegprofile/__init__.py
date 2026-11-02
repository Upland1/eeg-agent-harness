"""Deterministic EEG dataset profiler: measures, never interprets."""

from pathlib import Path


def _version() -> str:
  for parent in Path(__file__).resolve().parents:
    f = parent / "VERSION"
    if f.is_file():
      return f.read_text().strip()
  return "unknown"


__version__ = _version()
