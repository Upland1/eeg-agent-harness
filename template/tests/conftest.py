"""Make the project root importable for the tests (project packages, readers/, eegharness/).

Only committed project files are importable; never add `.harness/` to the path.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "tests"):
  if str(p) not in sys.path:
    sys.path.insert(0, str(p))


# Fast default, full suite on request (0.6.0, L55; CLAUDE.md G2). `pytest tests/` leaves out tests marked
# `@pytest.mark.slow`; `pytest tests/ -m ""` (or any -m expression) runs what the expression selects.
def pytest_configure(config):
  config.addinivalue_line("markers", "slow: longer than a few seconds; left out of the default run, "
                                     "run with -m \"\" before every freeze and commit (G2)")


def pytest_collection_modifyitems(config, items):
  args = [str(a) for a in config.invocation_params.args]
  if any(a == "-m" or a.startswith("-m") for a in args):
    return
  slow = [i for i in items if i.get_closest_marker("slow")]
  if slow:
    config.hook.pytest_deselected(items=slow)
    items[:] = [i for i in items if not i.get_closest_marker("slow")]
