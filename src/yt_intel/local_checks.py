"""Offline stdio probes shared by the local check and benchmark commands."""

import argparse
import asyncio
import json
import os
import platform
import subprocess
import sys
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from math import ceil
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter
from typing import Literal, TypedDict

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

FIXTURE_VIDEO = "libVid00001"
MIN_RUNS = 30
type Status = Literal["passed", "failed", "skipped"]


class Stage(TypedDict):
    status: Status
    detail: str


class Measurement(TypedDict):
    warmups: int
    runs: int
    median_ms: float
    p95_ms: float
    samples_ms: list[float]


class _ProbeError(RuntimeError):
    """Messages created by this probe and safe to put in local evidence."""


def _error_detail(error: BaseException) -> str:
    if isinstance(error, _ProbeError):
        return str(error)
    if isinstance(error, BaseExceptionGroup) and len(error.exceptions) == 1:
        return _error_detail(error.exceptions[0])
    return type(error).__name__


def _stage(status: Status, detail: str) -> Stage:
    return {"status": status, "detail": detail}


def _arguments(root: Path, state: Path) -> list[str]:
    return [
        "-m",
        "yt_intel",
        "serve",
        "--provider",
        "fixture",
        "--project-root",
        str(root),
        "--fixture-db",
        str(state),
    ]


@asynccontextmanager
async def fixture_session(
    root: Path, state: Path, *, wheel: Path | None = None
) -> AsyncIterator[ClientSession]:
    env = {"PYTHONPATH": str(wheel)} if wheel is not None else None
    parameters = StdioServerParameters(
        command=sys.executable,
        args=_arguments(root, state),
        env=env,
        cwd=str(state.parent),
    )
    # Drop server diagnostics from the report. Only synthetic structured results
    # are accepted as evidence and no stderr is written to the benchmark JSON.
    with open(os.devnull, "w", encoding="utf-8") as devnull:
        async with stdio_client(parameters, errlog=devnull) as (reader, writer):
            async with ClientSession(reader, writer, read_timeout_seconds=15) as client:
                await client.initialize()
                yield client


async def fetch_fixture_video(client: ClientSession) -> None:
    result = await client.call_tool("get_video", {"video": FIXTURE_VIDEO})
    envelope = result.structured_content
    if result.is_error or not isinstance(envelope, dict):
        raise _ProbeError("The fixture metadata tool returned an error.")
    data = envelope.get("data")
    if (
        envelope.get("mode") != "fixture"
        or envelope.get("status") != "ok"
        or not isinstance(data, dict)
        or data.get("video_id") != FIXTURE_VIDEO
    ):
        raise _ProbeError("The response did not match the expected synthetic fixture.")


def _build(root: Path, output: Path) -> Path:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            "--wheel",
            "--no-isolation",
            "--outdir",
            str(output),
        ],
        cwd=root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=120,
        check=False,
    )
    wheels = list(output.glob("*.whl"))
    if result.returncode or len(wheels) != 1:
        raise _ProbeError(f"Locked wheel build failed (exit {result.returncode}).")
    return wheels[0]


async def check_local(root: Path) -> dict[str, Stage]:
    stages = {
        stage: _stage("skipped", "A prerequisite stage did not complete.")
        for stage in ("build", "start", "fetch", "cleanup")
    }
    active = "build"
    try:
        with TemporaryDirectory(prefix="yt-intel-local-check-") as directory:
            workspace = Path(directory)
            try:
                wheel = _build(root, workspace)
                stages["build"] = _stage(
                    "passed", "Built one wheel without dependency installation."
                )
                active = "start"
                async with fixture_session(
                    root, workspace / "state.sqlite3", wheel=wheel
                ) as client:
                    stages["start"] = _stage(
                        "passed", "Initialized the fixture MCP server from the wheel."
                    )
                    active = "fetch"
                    await fetch_fixture_video(client)
                    stages["fetch"] = _stage(
                        "passed", "get_video returned the expected synthetic video."
                    )
                    active = "cleanup"
            except Exception as error:
                stages[active] = _stage("failed", _error_detail(error))
        if stages["cleanup"]["status"] != "failed":
            stages["cleanup"] = _stage(
                "passed", "Closed the subprocess and removed temporary files."
            )
    except OSError as error:
        stages["cleanup"] = _stage("failed", type(error).__name__)
    return stages


async def measure(
    sample: Callable[[], Awaitable[None]], runs: int = MIN_RUNS
) -> Measurement:
    """Measure async operations after exactly one successful unmeasured warm-up."""
    if runs < MIN_RUNS:
        raise ValueError(f"At least {MIN_RUNS} measured runs are required.")
    await sample()
    elapsed = []
    for _ in range(runs):
        start = perf_counter()
        await sample()
        elapsed.append((perf_counter() - start) * 1000)
    return {
        "warmups": 1,
        "runs": runs,
        "median_ms": median(elapsed),
        "p95_ms": sorted(elapsed)[ceil(0.95 * runs) - 1],
        "samples_ms": elapsed,
    }


async def benchmark_fixture(root: Path, runs: int) -> dict[str, object]:
    with TemporaryDirectory(prefix="yt-intel-benchmark-") as directory:
        start = perf_counter()
        async with fixture_session(root, Path(directory) / "state.sqlite3") as client:
            start_ms = (perf_counter() - start) * 1000
            timing = await measure(lambda: fetch_fixture_video(client), runs)
    return {
        "mode": "fixture",
        "target": "mcp.get_video",
        "provider_calls": "synthetic",
        "live_quota": 0,
        "mcp_startup_ms": start_ms,
        "environment": {
            "os": platform.system(),
            "os_release": platform.release(),
            "python": platform.python_version(),
            "logical_cpus": os.cpu_count(),
        },
        "measurement": timing,
    }


def main_check(root: Path) -> int:
    argparse.ArgumentParser(
        description="Build the locked project and check the local fixture MCP server."
    ).parse_args()
    stages = asyncio.run(check_local(root))
    print(json.dumps({"mode": "fixture", "live_quota": 0, "stages": stages}, indent=2))
    return int(any(stage["status"] != "passed" for stage in stages.values()))


def main_benchmark(root: Path) -> int:
    parser = argparse.ArgumentParser(
        description="Measure offline fixture MCP fetch latency."
    )
    parser.add_argument(
        "--runs", type=int, default=MIN_RUNS, help="Measured runs (minimum 30)."
    )
    args = parser.parse_args()
    if args.runs < MIN_RUNS:
        parser.error("at least 30 measured runs are required")
    try:
        result = asyncio.run(benchmark_fixture(root, args.runs))
    except Exception as error:
        print(
            json.dumps(
                {"mode": "fixture", "status": "failed", "error": type(error).__name__}
            )
        )
        return 1
    print(json.dumps(result, indent=2))
    return 0
