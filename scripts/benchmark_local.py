"""Run the reusable timing harness against the local fixture server."""

from pathlib import Path

from yt_intel.local_checks import main_benchmark

if __name__ == "__main__":
    raise SystemExit(main_benchmark(Path(__file__).resolve().parents[1]))
