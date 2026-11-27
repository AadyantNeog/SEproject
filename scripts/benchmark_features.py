"""Run the A2-08 NFR-08 feature measurements on offline fixtures."""

import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src"))
    from yt_intel.feature_benchmarks import main as run_benchmarks

    return run_benchmarks(root)


if __name__ == "__main__":
    raise SystemExit(main())
