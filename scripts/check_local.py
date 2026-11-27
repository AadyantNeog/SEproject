"""Build the locked project and check one read-only fixture call over MCP."""

from pathlib import Path

from yt_intel.local_checks import main_check

if __name__ == "__main__":
    raise SystemExit(main_check(Path(__file__).resolve().parents[1]))
