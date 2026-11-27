"""Build the locked project and check one read-only fixture call over MCP."""

import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src"))
    from yt_intel.local_checks import main_check

    return main_check(root)


if __name__ == "__main__":
    raise SystemExit(main())
