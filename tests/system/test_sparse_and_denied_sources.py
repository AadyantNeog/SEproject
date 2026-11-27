"""J2-08 read-path integration over MCP stdio.

Each test drives the real fixture server. Requests go MCP → library and
analysis services → AccountedHttpExecutor → API-shaped fixture dispatch,
and state lives in a real SQLite database with the persistent quota ledger.
Expected FR-4 values are hand-calculated from
tests/fixtures/libraries/library_catalog.json:

- likes: libVid00001 (PT10M = 600 s) and libVid00003 (PT20M = 1,200 s)
- the first 3 of 4 owned playlists hold pli-101 libVid00001 (2026-11-01T10Z),
  pli-102 deleted libGone0009 (11-02T10Z), pli-201 libVid00003 (11-03T10Z)
  and pli-301 libVid00002, PT15M = 900 s (11-04T10Z)
- one subscription, UCbbb…, created 2026-09-20T10:00:00Z; its upload sample
  is libVid00004
"""

import json
import os
import sys
from collections import Counter
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import anyio
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from yt_intel.infrastructure.database import Database

ROOT = Path(__file__).resolve().parents[2]
CATALOG = json.loads(
    (ROOT / "tests/fixtures/libraries/library_catalog.json").read_text(encoding="utf-8")
)
FULL_PERIODS = {
    "period_a": {"start": "2026-09-01T00:00:00Z", "end": "2026-10-01T00:00:00Z"},
    "period_b": {"start": "2026-11-01T00:00:00Z", "end": "2026-12-01T00:00:00Z"},
}
# Patch the fixture provider in the server process only, so faults are
# scripted per endpoint without touching the shipped server code.
LAUNCHER = """
import json, os, sys
from yt_intel.cli import main
from yt_intel.providers import fixture
spec = json.loads(os.environ.get("YT_TEST_FAULTS", "[]"))
original = fixture.FixtureYouTubeProvider.__init__
def with_faults(self, dataset, **kwargs):
    kwargs["faults"] = tuple(kwargs.get("faults", ())) + tuple(
        fixture.FixtureFault(**item) for item in spec
    )
    original(self, dataset, **kwargs)
fixture.FixtureYouTubeProvider.__init__ = with_faults
raise SystemExit(main(sys.argv[1:]))
"""


@asynccontextmanager
async def _client(
    database: Path, faults: Sequence[dict[str, object]] = ()
) -> AsyncIterator[ClientSession]:
    params = StdioServerParameters(
        command=sys.executable,
        args=[
            "-c",
            LAUNCHER,
            "serve",
            "--provider",
            "fixture",
            "--project-root",
            str(ROOT),
            "--fixture-db",
            str(database),
        ],
        env={**os.environ, "YT_TEST_FAULTS": json.dumps(list(faults))},
    )
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer, read_timeout_seconds=30) as client:
            await client.initialize()
            yield client


async def _ok(client: ClientSession, tool: str, args: dict[str, object]) -> Any:
    result = await client.call_tool(tool, args)
    assert not result.is_error, result.content
    assert result.structured_content is not None
    assert result.structured_content["mode"] == "fixture"
    return result.structured_content


async def _error(client: ClientSession, tool: str, args: dict[str, object]) -> str:
    result = await client.call_tool(tool, args)
    assert result.is_error and result.structured_content is not None
    assert result.structured_content["data"] is None
    return str(result.structured_content["error"]["code"])


def _attempts(database: Path) -> Counter[str]:
    with Database(database).transaction(immediate=False) as connection:
        rows = connection.execute("SELECT endpoint FROM quota_attempts").fetchall()
    return Counter(row["endpoint"] for row in rows)


def _seconds(video_id: str) -> int:
    duration = CATALOG["videos"][video_id]["contentDetails"]["duration"]
    assert duration.startswith("PT") and duration.endswith("M")
    return int(duration[2:-1]) * 60


def test_fr4_exact_totals_boundaries_and_cached_analysis(tmp_path: Path) -> None:
    database = tmp_path / "state.sqlite3"

    async def run() -> None:
        async with _client(database) as client:
            library = await _ok(client, "get_library", {})
            summary = library["data"]
            assert (
                summary["likes_count"],
                summary["subscriptions_count"],
                summary["owned_playlists_count"],
                summary["playlist_occurrences_count"],
                summary["unique_videos_count"],
            ) == (2, 1, 3, 4, 4)
            assert {k: v["state"] for k, v in summary["sources"].items()} == {
                "likes": "retrieved",
                "subscriptions": "retrieved",
                "playlists": "retrieved",
            }
            playlists = summary["sources"]["playlists"]["coverage"]
            assert (playlists["truncated"], playlists["inaccessible"]) == (True, 1)
            assert playlists["warnings"] == [
                "Selected first 3 of 4 unsampled owned playlists in returned order."
            ]
            # Every provider call went through the accounted executor.
            fetched = _attempts(database)
            assert fetched == Counter(
                {
                    "videos.list": 4,
                    "playlistItems.list": 4,
                    "subscriptions.list": 1,
                    "playlists.list": 1,
                    "channels.list": 1,
                }
            )
            snapshot = summary["snapshot_id"]

            report = (
                await _ok(
                    client,
                    "analyse_library",
                    {"snapshot_id": snapshot, **FULL_PERIODS},
                )
            )["data"]
            liked = [_seconds("libVid00001"), _seconds("libVid00003")]
            assert liked == [600, 1200]
            assert report["likes"]["count"] == report["likes"]["denominator"] == 2
            assert report["likes"]["runtime"]["mean_seconds"] == sum(liked) / 2
            assert report["likes"]["runtime"]["median_seconds"] == 900.0
            assert report["likes"]["timestamp_basis"] == (
                "like_event_timestamps_unavailable"
            )
            listed = report["playlists"]
            assert (
                listed["selected_playlists_count"],
                listed["occurrence_count"],
                listed["unique_video_count"],
                listed["inaccessible_occurrence_count"],
            ) == (3, 4, 3, 1)
            bands = {b["band"]: b["count"] for b in listed["runtime"]["bands"]}
            assert bands == {
                "[0,300)": 0,
                "[300,900)": 1,
                "[900,1800)": 2,
                "[1800,3600)": 0,
                "[3600,infinity)": 0,
            }
            combined = report["combined_videos"]
            assert (
                combined["count"],
                combined["overlap_count"],
                combined["likes_only_count"],
                combined["playlists_only_count"],
                combined["excluded_subscription_sample_videos"],
            ) == (3, 2, 0, 1, 1)
            channels = {b["bucket_id"]: b["count"] for b in combined["top_channels"]}
            assert channels == {
                "UCaaaaaaaaaaaaaaaaaaaaaa": 1,
                "UCbbbbbbbbbbbbbbbbbbbbbb": 1,
                "UCcccccccccccccccccccccc": 1,
            }
            categories = Counter(
                CATALOG["videos"][v]["snippet"]["categoryId"]
                for v in ("libVid00001", "libVid00002", "libVid00003")
            )
            assert {
                b["bucket_id"]: b["count"] for b in combined["top_categories"]
            } == dict(categories)
            assert report["subscriptions"]["channel_ids"] == [
                "UCbbbbbbbbbbbbbbbbbbbbbb"
            ]
            comparison = report["period_comparison"]
            assert comparison["interval_convention"] == (
                "utc_start_inclusive_end_exclusive"
            )
            additions = comparison["playlist_additions"]
            assert (additions["count_a"], additions["count_b"]) == (0, 4)
            assert additions["percent_change"] is None
            assert additions["percent_change_reason"] == "undefined_zero_baseline"
            created = comparison["subscription_creations"]
            assert (created["count_a"], created["count_b"]) == (1, 0)
            assert created["percent_change"] == -100.0
            assert comparison["likes_trend"]["available"] is False

            # Boundaries: the start instant is included and the end is excluded.
            edge = (
                await _ok(
                    client,
                    "analyse_library",
                    {
                        "snapshot_id": snapshot,
                        "period_a": {
                            "start": "2026-09-01T00:00:00Z",
                            "end": "2026-09-20T10:00:00Z",
                        },
                        "period_b": {
                            "start": "2026-11-01T10:00:00Z",
                            "end": "2026-11-04T10:00:00Z",
                        },
                    },
                )
            )["data"]["period_comparison"]
            assert edge["subscription_creations"]["count_a"] == 0
            assert edge["playlist_additions"]["count_b"] == 3
            inclusive = (
                await _ok(
                    client,
                    "analyse_library",
                    {
                        "snapshot_id": snapshot,
                        "period_a": {
                            "start": "2026-09-20T10:00:00Z",
                            "end": "2026-09-20T10:00:01Z",
                        },
                        "period_b": {
                            "start": "2026-11-04T10:00:00Z",
                            "end": "2026-11-04T10:00:01Z",
                        },
                    },
                )
            )["data"]["period_comparison"]
            assert inclusive["subscription_creations"]["count_a"] == 1
            assert inclusive["playlist_additions"]["count_b"] == 1
            empty = (
                await _ok(
                    client,
                    "analyse_library",
                    {
                        "snapshot_id": snapshot,
                        "period_a": {
                            "start": "2025-01-01T00:00:00Z",
                            "end": "2025-02-01T00:00:00Z",
                        },
                        "period_b": {
                            "start": "2025-03-01T00:00:00Z",
                            "end": "2025-04-01T00:00:00Z",
                        },
                    },
                )
            )["data"]["period_comparison"]
            assert empty["playlist_additions"]["count_a"] == 0
            assert empty["playlist_additions"]["count_b"] == 0
            assert empty["playlist_additions"]["note"] is not None
            # Analysing a stored snapshot is a cached read with no provider call.
            assert _attempts(database) == fetched

    anyio.run(run)


def test_denied_and_unrequested_sources_are_not_reported_as_zero(
    tmp_path: Path,
) -> None:
    denied = [
        {
            "endpoint": "subscriptions.list",
            "kind": "http",
            "status_code": 403,
            "body": {"error": {"errors": [{"reason": "insufficientPermissions"}]}},
        }
    ]

    async def run() -> None:
        async with _client(tmp_path / "denied.sqlite3", denied) as client:
            library = await _ok(client, "get_library", {})
            data = library["data"]
            assert data["sources"]["subscriptions"] == {
                "state": "denied",
                "coverage": None,
            }
            assert data["warnings"] == [
                "Library source 'subscriptions' was denied (SCOPE_REQUIRED)."
            ]
            assert (data["likes_count"], data["subscriptions_count"]) == (2, 0)
            analysis = await _ok(
                client,
                "analyse_library",
                {"snapshot_id": data["snapshot_id"], **FULL_PERIODS},
            )
            assert analysis["warnings"] == [
                "Source 'subscriptions' was denied in this snapshot."
            ]
            comparison = analysis["data"]["period_comparison"]
            assert comparison["sources"] == ["likes", "playlists"]
            assert comparison["subscription_creations"] is None
            assert comparison["playlist_additions"]["count_b"] == 4

        async with _client(tmp_path / "sparse.sqlite3") as client:
            library = await _ok(client, "get_library", {"sources": ["likes"]})
            data = library["data"]
            assert {k: v["state"] for k, v in data["sources"].items()} == {
                "likes": "retrieved",
                "subscriptions": "not_requested",
                "playlists": "not_requested",
            }
            analysis = await _ok(
                client,
                "analyse_library",
                {"snapshot_id": data["snapshot_id"], **FULL_PERIODS},
            )
            comparison = analysis["data"]["period_comparison"]
            assert comparison["sources"] == ["likes"]
            assert comparison["playlist_additions"] is None
            assert comparison["subscription_creations"] is None
            assert len(analysis["warnings"]) == 2
            assert all("not requested" in w for w in analysis["warnings"])
            combined = analysis["data"]["combined_videos"]
            assert (combined["count"], combined["likes_only_count"]) == (2, 2)

    anyio.run(run)


def test_read_failures_are_typed_bounded_and_accounted(tmp_path: Path) -> None:
    def fault(**changes: object) -> dict[str, object]:
        return {"endpoint": "videos.list", "kind": "http", **changes}

    cases = [
        ("unavailable", [fault(status_code=503)] * 3, "PROVIDER_UNAVAILABLE", 3),
        (
            "timeout",
            [{"endpoint": "videos.list", "kind": "timeout"}] * 3,
            "WORKFLOW_TIMEOUT",
            3,
        ),
        (
            "quota",
            [
                fault(
                    status_code=403,
                    body={"error": {"errors": [{"reason": "quotaExceeded"}]}},
                )
            ],
            "QUOTA_EXHAUSTED",
            1,
        ),
        ("recovered", [fault(status_code=503)], None, 2),
    ]

    async def run() -> None:
        for label, faults, code, attempts in cases:
            database = tmp_path / f"{label}.sqlite3"
            async with _client(database, faults) as client:
                if code is None:
                    video = await _ok(client, "get_video", {"video": "libVid00001"})
                    assert video["data"]["video_id"] == "libVid00001"
                else:
                    assert (
                        await _error(client, "get_video", {"video": "libVid00001"})
                        == code
                    )
                assert _attempts(database) == Counter({"videos.list": attempts})
                if label == "quota":
                    # Upstream exhaustion is remembered; no further attempt is sent.
                    assert (
                        await _error(client, "get_video", {"video": "libVid00001"})
                        == "QUOTA_EXHAUSTED"
                    )
                    assert _attempts(database) == Counter({"videos.list": 1})

    anyio.run(run)


def test_disconnect_and_retention_remove_account_data(tmp_path: Path) -> None:
    database = tmp_path / "state.sqlite3"

    async def run() -> None:
        async with _client(database) as client:
            snapshot = (await _ok(client, "get_library", {}))["data"]["snapshot_id"]
            spent = _attempts(database)
            with Database(database).transaction() as connection:
                connection.execute(
                    "UPDATE snapshots SET retained_until = ? WHERE snapshot_id = ?",
                    ("2000-01-01T00:00:00+00:00", snapshot),
                )
            assert (
                await _error(client, "analyse_library", {"snapshot_id": snapshot})
                == "CONTENT_UNAVAILABLE"
            )
            fresh = (await _ok(client, "get_library", {}))["data"]["snapshot_id"]
            spent = _attempts(database)
            outcome = (await _ok(client, "disconnect_account", {}))["data"]
            assert outcome == {
                "local_data_removed": True,
                "tokens_removed": True,
                "revoked": False,
                "warnings": [],
            }
            status = await _ok(client, "get_account_status", {})
            assert status["data"] is None
            for tool, args in (
                ("get_library", {}),
                ("analyse_library", {"snapshot_id": fresh}),
                ("disconnect_account", {}),
            ):
                assert await _error(client, tool, args) == "AUTH_REQUIRED"
        with Database(database).transaction(immediate=False) as connection:
            assert (
                connection.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 0
            )
            assert (
                connection.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 0
            )
        # Project quota accounting survives disconnect and is never refunded.
        assert _attempts(database) == spent

    anyio.run(run)
