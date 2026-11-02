"""Profile a dataset folder.

  python .harness/tools/run_profile.py --data <folder> --out docs/DATA_PROFILE [--plugin readers/x.py] [--max-files N]

Writes <out>.json and <out>.md. Reads the recordings; never writes next to them.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from eegprofile.profile import profile_dataset  # noqa: E402
from eegprofile.report import to_markdown  # noqa: E402


def main(argv=None) -> int:
  ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  ap.add_argument("--data", required=True)
  ap.add_argument("--out", required=True, help="output path without extension")
  ap.add_argument("--plugin", action="append", default=[], help="reader plugin .py (repeatable)")
  ap.add_argument("--max-files", type=int, default=None, help="profile only the first N files (smoke run)")
  ap.add_argument("--no-mne", action="store_true", help="do not register the MNE readers")
  a = ap.parse_args(argv)
  data, out = Path(a.data).resolve(), Path(a.out).resolve()
  if out == data or data in out.parents:
    ap.error("--out must not be inside --data")
  prof = profile_dataset(data, plugins=a.plugin, max_files=a.max_files, use_mne=not a.no_mne)
  out.parent.mkdir(parents=True, exist_ok=True)
  out.with_suffix(".json").write_text(json.dumps(prof, indent=1, ensure_ascii=False))
  out.with_suffix(".md").write_text(to_markdown(prof))
  s = prof["summary"]
  print(f"files {s['n_files']}, profiled {s['n_profiled']}, no reader {s['n_no_reader']}, "
        f"errors {s['n_unreadable']} -> {out.with_suffix('.json')}, {out.with_suffix('.md')}")
  return 0


if __name__ == "__main__":
  sys.exit(main())
