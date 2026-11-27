"""Run the fixed-budget live read-only check on a provisioned protected runner."""

import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src"))
    from yt_intel.live_read_check import main as run_check

    return run_check()


if __name__ == "__main__":
    raise SystemExit(main())
