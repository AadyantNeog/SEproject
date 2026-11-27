"""A2-08 NFR-08 measurements for validation, ranking and proposal construction.

The in-process targets use a deterministic synthetic workload of 200 candidate
videos so the SRS bound "ranking up to 200 candidates" is exercised at its
limit. The stdio targets repeat the shipped fixture tools through a real MCP
subprocess, each with its own temporary fixture database and quota ledger, so
the reported times include JSON-RPC transport and SQLite accounting. Every
sample checks its own result before it counts. Reports contain identifiers,
counts and timings only.
"""

import argparse
import asyncio
import ctypes
import json
import os
import platform
import subprocess
import sys
from collections.abc import Awaitable, Callable, Mapping
from contextlib import AsyncExitStack
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from yt_intel.contracts.common import AccountBinding
from yt_intel.contracts.errors import ContractError
from yt_intel.contracts.models import (
    CandidateSet,
    Channel,
    ChannelSample,
    Coverage,
    LibrarySnapshot,
    PlaylistOccurrence,
    SourceCoverage,
    SubscriptionSignal,
    Video,
)
from yt_intel.domain.constraints import parse_playlist_request
from yt_intel.domain.identifiers import (
    parse_channel_ref,
    parse_video_id,
    validate_result_limit,
)
from yt_intel.domain.language import normalize_language_tag, parse_language_tag
from yt_intel.domain.profiles import build_profile, rank_recommendations
from yt_intel.domain.proposals import PlaylistPlanner
from yt_intel.domain.ranking import ChannelCorpus, rank_channels, rank_videos
from yt_intel.local_checks import MIN_RUNS, Measurement, measure

CANDIDATES = 200
CHANNELS = 20
TARGET_MS = {"validation": 100.0, "ranking": 2000.0, "proposal": 2000.0}
NOW = datetime(2026, 11, 28, 9, 0, tzinfo=UTC)
BINDING = AccountBinding(
    installation_id="benchmark-installation",
    credential_binding_id="benchmark-binding",
    channel_id="UCbench00000000000000000",
    mode="fixture",
)
# A fixed vocabulary keeps term overlap realistic: candidates share some
# terms with the seed and profile, and differ in others.
_TOPICS = (
    ("database", "indexing", "btree", "query", "planner"),
    ("sqlite", "storage", "pages", "journal", "wal"),
    ("postgres", "vacuum", "mvcc", "transactions", "isolation"),
    ("hash", "partition", "sharding", "replication", "consensus"),
    ("python", "asyncio", "testing", "profiling", "typing"),
    ("graph", "traversal", "shortest", "path", "heuristics"),
    ("compiler", "parsing", "lexer", "grammar", "bytecode"),
    ("networks", "tcp", "latency", "congestion", "routing"),
)
_LANGUAGES = ("en", "en-US", "en-GB", "fr", None)
_CATEGORIES = ("27", "28", None)


def _video(index: int, *, channel: int | None = None) -> Video:
    topic = _TOPICS[index % len(_TOPICS)]
    neighbour = _TOPICS[(index + 1) % len(_TOPICS)]
    language = _LANGUAGES[index % len(_LANGUAGES)]
    channel_number = index % CHANNELS if channel is None else channel
    video_id = f"bench{index:06d}"
    return Video(
        video_id=video_id,
        channel_id=f"UCbench{channel_number:017d}",
        title=f"{topic[0].title()} {topic[1]} lesson {index}",
        channel_title=f"Synthetic {topic[0]} channel {channel_number}",
        canonical_url=f"https://www.youtube.com/watch?v={video_id}",
        description=(
            f"A synthetic walkthrough of {' '.join(topic)} with notes on "
            f"{neighbour[index % len(neighbour)]} and worked examples. " * 4
        ),
        tags=(*topic[:3], neighbour[0]) if index % 7 else None,
        category_id=_CATEGORIES[index % len(_CATEGORIES)],
        published_at=NOW - timedelta(days=index + 1),
        duration_seconds=None if index % 23 == 0 else 120 + (index * 37) % 1380,
        default_audio_language=language,
        default_metadata_language=None,
        language_evidence="audio" if language else "unknown",
        availability="available",
        live_status="recorded",
        fetched_at=NOW - timedelta(minutes=5),
    )


def _coverage(count: int, basis: str, *, sampled: bool = False) -> Coverage:
    return Coverage(
        complete=not sampled,
        paginated=False,
        sampled=sampled,
        truncated=False,
        retrieved=count,
        usable=count,
        inaccessible=0,
        unknown=0,
        limits={"candidates": CANDIDATES},
        completeness_basis=basis,
    )


def seed_video() -> Video:
    return _video(0).model_copy(
        update={"video_id": "benchSeed01", "title": "Database indexing with btree"}
    )


def candidate_videos() -> tuple[Video, ...]:
    return tuple(_video(index) for index in range(1, CANDIDATES + 1))


def candidate_set(videos: tuple[Video, ...]) -> CandidateSet:
    return CandidateSet(
        candidate_set_id="benchmark-candidates",
        binding=BINDING,
        videos=videos,
        source="synthetic",
        seed_video_id=None,
        topic="database indexing",
        coverage=_coverage(len(videos), "Synthetic benchmark candidates"),
        ranking_version="benchmark",
        config_version="benchmark-v1",
        created_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(hours=1),
    )


def _sample(channel: int, videos: tuple[Video, ...]) -> ChannelSample:
    channel_id = f"UCbench{channel:017d}"
    topic = _TOPICS[channel % len(_TOPICS)]
    return ChannelSample(
        channel=Channel(
            channel_id=channel_id,
            title=f"Synthetic {topic[0]} channel {channel}",
            canonical_url=f"https://www.youtube.com/channel/{channel_id}",
            handle=None,
            description=f"Lessons about {' '.join(topic)}.",
            uploads_playlist_id=None,
            fetched_at=NOW - timedelta(minutes=5),
        ),
        video_ids=tuple(video.video_id for video in videos),
        attempted=len(videos),
        usable=len(videos),
        skipped=0,
        selection_rule_version="benchmark-uploads-v1",
        coverage=_coverage(len(videos), "Synthetic channel sample", sampled=True),
    )


def channel_corpora(
    videos: tuple[Video, ...],
) -> tuple[ChannelCorpus, tuple[ChannelCorpus, ...]]:
    """Split the 200 candidates into 20 channels and build a separate seed."""
    grouped: dict[int, list[Video]] = {}
    for index, video in enumerate(videos):
        grouped.setdefault(index % CHANNELS, []).append(video)
    corpora = tuple(
        ChannelCorpus(_sample(channel, tuple(items)), tuple(items))
        for channel, items in sorted(grouped.items())
    )
    seed_items = tuple(_video(9000 + index, channel=999) for index in range(10))
    return ChannelCorpus(_sample(999, seed_items), seed_items), corpora


def preference_snapshot() -> LibrarySnapshot:
    """Build a snapshot that uses all three preference sources."""
    liked = tuple(_video(1000 + index) for index in range(40))
    listed = tuple(_video(2000 + index) for index in range(30))
    subscribed = tuple(
        _video(3000 + index, channel=500 + index // 5) for index in range(50)
    )
    subscriptions = tuple(
        SubscriptionSignal(
            subscription_id=f"benchmark-subscription-{channel}",
            channel_id=f"UCbench{500 + channel:017d}",
            subscribed_at=None,
            topic_sample=_sample(
                500 + channel, subscribed[channel * 5 : channel * 5 + 5]
            ),
            coverage=_coverage(5, "Synthetic subscription sample", sampled=True),
        )
        for channel in range(10)
    )
    occurrences = tuple(
        PlaylistOccurrence(
            playlist_id="PLbenchmark0000000000000000000001",
            playlist_item_id=f"benchmark-item-{position}",
            video_id=video.video_id,
            position=position,
            added_at=None,
            accessibility="available",
        )
        for position, video in enumerate(listed)
    )
    videos = {video.video_id: video for video in (*liked, *listed, *subscribed)}
    return LibrarySnapshot(
        snapshot_id="benchmark-snapshot",
        binding=BINDING,
        started_at=NOW - timedelta(minutes=6),
        fetched_at=NOW - timedelta(minutes=5),
        likes={video.video_id: None for video in liked},
        subscriptions=subscriptions,
        owned_playlist_ids=("PLbenchmark0000000000000000000001",),
        playlist_occurrences=occurrences,
        videos=videos,
        sources={
            "likes": SourceCoverage(
                state="retrieved", coverage=_coverage(len(liked), "Synthetic likes")
            ),
            "playlists": SourceCoverage(
                state="retrieved",
                coverage=_coverage(len(listed), "Synthetic playlist items"),
            ),
            "subscriptions": SourceCoverage(
                state="retrieved",
                coverage=_coverage(len(subscriptions), "Synthetic subscriptions"),
            ),
        },
        retained_until=NOW + timedelta(hours=24),
    )


PLAYLIST_REQUEST: Mapping[str, object] = {
    "title": "Benchmark indexing study",
    "topic": "database indexing",
    "total_seconds": 7200,
    "max_video_seconds": 1200,
    "language": "en",
}


def _validate_inputs() -> None:
    """One validation pass over every user-supplied field FR-1..FR-5 accept."""
    assert parse_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert parse_video_id("https://youtu.be/dQw4w9WgXcQ?t=42")
    assert parse_channel_ref("https://www.youtube.com/@SystemsStudyLab")
    assert parse_channel_ref("UCbbbbbbbbbbbbbbbbbbbbbb")
    assert validate_result_limit(25) == 25
    assert parse_language_tag("en-US")
    assert parse_playlist_request(PLAYLIST_REQUEST).total_seconds == 7200
    for refused in (
        lambda: parse_video_id("https://example.com/watch?v=dQw4w9WgXcQ"),
        lambda: validate_result_limit(51),
        lambda: parse_playlist_request({**PLAYLIST_REQUEST, "total_seconds": "7200"}),
    ):
        try:
            refused()
        except ContractError:
            continue
        raise AssertionError("Invalid input was accepted.")


def _sync(operation: Callable[[], None]) -> Callable[[], Awaitable[None]]:
    async def sample() -> None:
        operation()

    return sample


def in_process_targets() -> dict[str, tuple[str, Callable[[], Awaitable[None]]]]:
    """Return named targets, each mapped to its NFR-08 class and a checked sample."""
    seed = seed_video()
    videos = candidate_videos()
    channel_seed, channels = channel_corpora(videos)
    profile = build_profile(preference_snapshot())
    pool = candidate_set(videos)
    request = parse_playlist_request(PLAYLIST_REQUEST)
    planner = PlaylistPlanner(normalize_language_tag)

    def similar_videos() -> None:
        assert rank_videos(seed, videos, limit=50)

    def similar_channels() -> None:
        assert rank_channels(channel_seed, channels, limit=10)

    def recommendations() -> None:
        assert rank_recommendations(profile, videos, limit=50)

    def proposal() -> None:
        result = planner.plan(
            request,
            pool,
            binding=BINDING,
            destination_channel_title="Benchmark channel",
            proposal_id="benchmark-proposal",
            now=NOW,
        )
        assert 1 <= len(result.items) <= 50

    return {
        "validate_inputs": ("validation", _sync(_validate_inputs)),
        "rank_similar_videos_200": ("ranking", _sync(similar_videos)),
        "rank_similar_channels_200": ("ranking", _sync(similar_channels)),
        "rank_recommendations_200": ("ranking", _sync(recommendations)),
        "construct_proposal_200": ("proposal", _sync(proposal)),
    }


def workload() -> dict[str, object]:
    seed = seed_video()
    videos = candidate_videos()
    channel_seed, channels = channel_corpora(videos)
    snapshot = preference_snapshot()
    result = PlaylistPlanner(normalize_language_tag).plan(
        parse_playlist_request(PLAYLIST_REQUEST),
        candidate_set(videos),
        binding=BINDING,
        destination_channel_title="Benchmark channel",
        proposal_id="benchmark-proposal",
        now=NOW,
    )
    return {
        "candidates": len(videos),
        "similar_videos_ranked": len(rank_videos(seed, videos, limit=50)),
        "channels": len(channels),
        "channel_seed_videos": len(channel_seed.videos),
        "similar_channels_ranked": len(rank_channels(channel_seed, channels, limit=10)),
        "profile_sources": sorted(
            source
            for source, state in snapshot.sources.items()
            if state.state == "retrieved"
        ),
        "profile_videos": len(snapshot.videos),
        "recommendations_ranked": len(
            rank_recommendations(build_profile(snapshot), videos, limit=50)
        ),
        "proposal_items": len(result.items),
        "proposal_total_seconds": result.total_seconds,
        "proposal_request": dict(PLAYLIST_REQUEST),
    }


# --- MCP stdio targets -------------------------------------------------------

_DISCOVERY_VIDEO = {"video": "https://youtu.be/vidIndex001", "limit": 1}
_DISCOVERY_CHANNEL = {"channel": "https://www.youtube.com/@SystemsStudyLab"}
_PREVIEW = {
    "title": "Indexing for beginners",
    "topic": "database indexing",
    "total_seconds": 720,
    "max_video_seconds": 600,
    "language": "en",
    "candidate_set_id": "fixture-recommendations",
}
_INVALID_VIDEO = {"video": "https://example.com/watch?v=vidIndex001"}


def _server(root: Path, database: Path, command: list[str]) -> StdioServerParameters:
    return StdioServerParameters(
        command=command[0],
        args=[
            *command[1:],
            "serve",
            "--provider",
            "fixture",
            "--project-root",
            str(root),
            "--fixture-db",
            str(database),
        ],
    )


def _data(result: Any) -> dict[str, Any]:
    if result.is_error or not isinstance(result.structured_content, dict):
        raise AssertionError("A fixture tool returned an error during measurement.")
    content = result.structured_content
    assert content["mode"] == "fixture" and content["status"] == "ok"
    return content


async def _call(client: ClientSession, name: str, arguments: dict[str, object]) -> Any:
    return await client.call_tool(name, arguments)


async def _stdio_target(
    root: Path,
    workspace: Path,
    command: list[str],
    name: str,
    runs: int,
) -> tuple[Measurement, dict[str, object]]:
    async with AsyncExitStack() as stack:
        reader, writer = await stack.enter_async_context(
            stdio_client(_server(root, workspace / f"{name}.sqlite3", command))
        )
        client = await stack.enter_async_context(
            ClientSession(reader, writer, read_timeout_seconds=30)
        )
        await client.initialize()
        observed: dict[str, object] = {}
        if name == "find_similar_videos":

            async def sample() -> None:
                content = _data(await _call(client, name, dict(_DISCOVERY_VIDEO)))
                assert [row["video"]["video_id"] for row in content["data"]] == [
                    "vidIndex002"
                ]
                observed["ranked"] = [
                    row["video"]["video_id"] for row in content["data"]
                ]

            observed["input"] = dict(_DISCOVERY_VIDEO)
        elif name == "find_similar_channels":

            async def sample() -> None:
                content = _data(await _call(client, name, dict(_DISCOVERY_CHANNEL)))
                ranked = [
                    row["sample"]["channel"]["channel_id"] for row in content["data"]
                ]
                assert ranked == ["UCbbbbbbbbbbbbbbbbbbbbbb"]
                observed["ranked"] = ranked

            observed["input"] = dict(_DISCOVERY_CHANNEL)
        elif name == "recommend_videos":
            library = _data(await _call(client, "get_library", {"sources": ["likes"]}))
            arguments = {
                "snapshot_id": library["data"]["snapshot_id"],
                "language": "en",
                "total_seconds": 1300,
            }

            async def sample() -> None:
                content = _data(await _call(client, name, arguments))
                ranked = [
                    item["video"]["video_id"] for item in content["data"]["results"]
                ]
                assert ranked == ["vidIndex001"]
                observed["ranked"] = ranked

            observed["input"] = {**arguments, "snapshot_id": "<saved fixture snapshot>"}
        elif name == "propose_playlist":

            async def sample() -> None:
                content = _data(await _call(client, name, dict(_PREVIEW)))
                proposal = content["data"]
                assert proposal["total_seconds"] <= _PREVIEW["total_seconds"]
                observed["items"] = [item["video_id"] for item in proposal["items"]]
                observed["total_seconds"] = proposal["total_seconds"]

            observed["input"] = dict(_PREVIEW)
        elif name == "find_similar_videos_invalid_input":

            async def sample() -> None:
                result = await _call(
                    client, "find_similar_videos", dict(_INVALID_VIDEO)
                )
                assert result.is_error
                code = result.structured_content["error"]["code"]
                assert code == "UNSUPPORTED_IDENTIFIER"
                observed["error_code"] = code

            observed["input"] = dict(_INVALID_VIDEO)
        else:
            raise ValueError(f"Unknown stdio target {name}.")
        timing = await measure(sample, runs)
    return timing, observed


# Fixture-sized end-to-end calls. They include provider fixture reads, the
# quota ledger and JSON-RPC transport, so holding them to the in-process
# bound is stricter than NFR-08 requires. The 200-candidate bound is
# covered by the in-process targets above.
STDIO_TARGETS = {
    "find_similar_videos": "ranking",
    "find_similar_channels": "ranking",
    "recommend_videos": "ranking",
    "propose_playlist": "proposal",
    "find_similar_videos_invalid_input": "validation",
}


def _memory_bytes() -> int | None:
    if sys.platform == "win32":

        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong),
                ("load", ctypes.c_ulong),
                ("total_physical", ctypes.c_ulonglong),
                ("available_physical", ctypes.c_ulonglong),
                ("total_page", ctypes.c_ulonglong),
                ("available_page", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong),
                ("available_virtual", ctypes.c_ulonglong),
                ("available_extended", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.length = ctypes.sizeof(MemoryStatus)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.total_physical)
        return None
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (AttributeError, OSError, ValueError):
        return None


def _commit(root: Path) -> dict[str, object]:
    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, check=True
        ).stdout.strip()

    try:
        return {
            "commit": git("rev-parse", "HEAD"),
            "dirty": bool(git("status", "--porcelain")),
        }
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "dirty": None}


def environment() -> dict[str, object]:
    memory = _memory_bytes()
    cpus = os.cpu_count()
    return {
        "os": platform.system(),
        "os_release": platform.release(),
        "os_version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor() or None,
        "logical_cpus": cpus,
        "memory_gib": None if memory is None else round(memory / 2**30, 1),
        "python": platform.python_version(),
        "meets_reference_minimum": bool(
            cpus is not None
            and cpus >= 4
            and memory is not None
            and memory >= 8 * 2**30
        ),
    }


def _summary(kind: str, timing: Measurement) -> dict[str, object]:
    target = TARGET_MS.get(kind)
    return {
        "class": kind,
        "target_p95_ms": target,
        "passed": None if target is None else timing["p95_ms"] <= target,
        **timing,
    }


async def run(
    root: Path, runs: int, *, stdio: bool = True, command: list[str] | None = None
) -> dict[str, object]:
    if runs < MIN_RUNS:
        raise ValueError(f"At least {MIN_RUNS} measured runs are required.")
    targets: dict[str, object] = {}
    for name, (kind, sample) in in_process_targets().items():
        targets[name] = _summary(kind, await measure(sample, runs))
    stdio_results: dict[str, object] = {}
    if stdio:
        launcher = command or [sys.executable, "-m", "yt_intel"]
        with TemporaryDirectory(prefix="yt-intel-features-") as directory:
            for name, kind in STDIO_TARGETS.items():
                timing, observed = await _stdio_target(
                    root, Path(directory), launcher, name, runs
                )
                stdio_results[name] = {**_summary(kind, timing), "observed": observed}
    measured = [*targets.values(), *stdio_results.values()]
    return {
        "task": "A2-08",
        "mode": "fixture",
        "live_quota": 0,
        "measured_at": datetime.now(UTC).isoformat(timespec="seconds"),
        **_commit(root),
        "environment": environment(),
        "workload": workload(),
        "in_process": targets,
        "stdio": stdio_results,
        "all_targets_passed": all(
            item["passed"] is not False for item in measured if isinstance(item, dict)
        ),
    }


def main(root: Path) -> int:
    parser = argparse.ArgumentParser(
        description="Measure A2-08 NFR-08 validation, ranking and proposal targets."
    )
    parser.add_argument("--runs", type=int, default=MIN_RUNS)
    parser.add_argument(
        "--no-stdio", action="store_true", help="Skip MCP stdio targets."
    )
    parser.add_argument("--output", type=Path, help="Also write the JSON report here.")
    args = parser.parse_args()
    if args.runs < MIN_RUNS:
        parser.error(f"at least {MIN_RUNS} measured runs are required")
    report = asyncio.run(run(root, args.runs, stdio=not args.no_stdio))
    text = json.dumps(report, indent=2)
    if args.output is not None:
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["all_targets_passed"] else 1
