"""Seed an interrupted fixture write so the native resume dialog can be checked."""

import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src"))
    from yt_intel.fixture_recovery_demo import main as seed

    return seed(root)


if __name__ == "__main__":
    raise SystemExit(main())
