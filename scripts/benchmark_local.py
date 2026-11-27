"""Run the reusable timing harness against the local fixture server."""

import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src"))
    from yt_intel.local_checks import main_benchmark

    return main_benchmark(root)


if __name__ == "__main__":
    raise SystemExit(main())
