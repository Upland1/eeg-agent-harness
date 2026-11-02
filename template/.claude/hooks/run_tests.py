"""PostToolUse: run the synthetic tests after an edit to pipeline code.

Exit 2 shows the failing output to Claude (the edit itself has already happened).
"""

import json
import os
import subprocess
import sys
from pathlib import Path

event = json.load(sys.stdin)
path = str((event.get("tool_input") or {}).get("file_path", ""))
root = Path(os.environ.get("CLAUDE_PROJECT_DIR", event.get("cwd", ".")))
if not path.endswith(".py") or not any(f"/{d}/" in path or path.startswith(f"{d}/") for d in ("src", "scripts", "readers", "tests")):
  sys.exit(0)
if not any((root / "tests").glob("test_*.py")):
  sys.exit(0)

python = root / ".venv" / "bin" / "python"
if not python.exists():
  python = Path(sys.executable)
try:
  run = subprocess.run([str(python), "-m", "pytest", "tests/", "-q", "-x"], cwd=root,
                       capture_output=True, text=True, timeout=150)
except subprocess.TimeoutExpired:
  print("pytest tests/ took over 150 s; tests must stay under about a minute (CLAUDE.md G2).", file=sys.stderr)
  sys.exit(2)
if run.returncode not in (0, 5):  # 5 = no tests collected
  print("pytest tests/ failed after this edit:\n" + run.stdout[-3000:], file=sys.stderr)
  sys.exit(2)
