import sys
from pathlib import Path

import anyio
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

ROOT = Path(__file__).resolve().parents[2]


def test_analyse_library_over_fixture_stdio_with_and_without_periods(
    tmp_path: Path,
) -> None:
    async def _run() -> None:
        db_file = tmp_path / "analysis-stdio.sqlite3"
        params = StdioServerParameters(
            command=sys.executable,
            args=[
                "-m",
                "yt_intel",
                "serve",
                "--provider",
                "fixture",
                "--project-root",
                str(ROOT),
                "--fixture-db",
                str(db_file),
            ],
        )
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer, read_timeout_seconds=15) as client:
                await client.initialize()
                tools = {tool.name for tool in (await client.list_tools()).tools}
                assert "analyse_library" in tools

                # 1. Collect a snapshot via get_library
                lib_res = await client.call_tool("get_library", {})
                assert not lib_res.is_error
                assert lib_res.structured_content is not None
                snapshot_id = lib_res.structured_content["data"]["snapshot_id"]

                # 2. Analyse that stored snapshot with two non-overlapping UTC periods
                ana_res = await client.call_tool(
                    "analyse_library",
                    {
                        "snapshot_id": snapshot_id,
                        "period_a": {
                            "start": "2026-09-01T00:00:00Z",
                            "end": "2026-10-01T00:00:00Z",
                        },
                        "period_b": {
                            "start": "2026-11-01T00:00:00Z",
                            "end": "2026-12-01T00:00:00Z",
                        },
                    },
                )
                assert not ana_res.is_error
                assert ana_res.structured_content is not None
                report = ana_res.structured_content["data"]
                assert report["snapshot_id"] == snapshot_id
                assert report["activity_label"] == "accessible_collection_activity"
                assert report["combined_videos"]["count"] >= 3
                assert (
                    report["combined_videos"]["excluded_subscription_sample_videos"]
                    >= 1
                )
                pc = report["period_comparison"]
                assert pc is not None
                assert pc["likes_trend"]["available"] is False
                # Playlist additions in Nov 2026 (Period B) vs 0 in Sep 2026 (Period A)
                assert pc["playlist_additions"]["count_a"] == 0
                assert pc["playlist_additions"]["count_b"] >= 1
                assert pc["playlist_additions"]["percent_change"] is None
                # Subscription created on 2026-09-20 (Period A) vs 0 in Period B
                assert pc["subscription_creations"]["count_a"] == 1
                assert pc["subscription_creations"]["count_b"] == 0

                # 3. Source-filtered period comparison respects selected sources
                pl_only_res = await client.call_tool(
                    "analyse_library",
                    {
                        "snapshot_id": snapshot_id,
                        "sources": ["playlists"],
                        "period_a": {
                            "start": "2026-09-01T00:00:00Z",
                            "end": "2026-10-01T00:00:00Z",
                        },
                        "period_b": {
                            "start": "2026-11-01T00:00:00Z",
                            "end": "2026-12-01T00:00:00Z",
                        },
                    },
                )
                assert not pl_only_res.is_error
                assert pl_only_res.structured_content is not None
                pl_pc = pl_only_res.structured_content["data"]["period_comparison"]
                assert pl_pc["sources"] == ["playlists"]
                assert pl_pc["playlist_additions"]["count_b"] >= 1
                assert pl_pc["subscription_creations"] is None
                assert pl_pc["likes_trend"] is None

                # 4. Overlapping periods fail cleanly with INVALID_INPUT
                overlap_res = await client.call_tool(
                    "analyse_library",
                    {
                        "snapshot_id": snapshot_id,
                        "period_a": {
                            "start": "2026-10-01T00:00:00Z",
                            "end": "2026-11-15T00:00:00Z",
                        },
                        "period_b": {
                            "start": "2026-11-01T00:00:00Z",
                            "end": "2026-12-01T00:00:00Z",
                        },
                    },
                )
                assert overlap_res.is_error
                assert overlap_res.structured_content is not None
                assert (
                    overlap_res.structured_content["error"]["code"] == "INVALID_INPUT"
                )

                # 5. Missing/foreign snapshot_id fails cleanly with CONTENT_UNAVAILABLE
                missing_res = await client.call_tool(
                    "analyse_library", {"snapshot_id": "snap-does-not-exist"}
                )
                assert missing_res.is_error
                assert missing_res.structured_content is not None
                assert (
                    missing_res.structured_content["error"]["code"]
                    == "CONTENT_UNAVAILABLE"
                )

    anyio.run(_run)


def test_analyse_library_validates_periods_before_fetching_or_opening_db(
    tmp_path: Path,
) -> None:
    async def _run() -> None:
        db_file = tmp_path / "no-fetch-on-invalid-period.sqlite3"
        params = StdioServerParameters(
            command=sys.executable,
            args=[
                "-m",
                "yt_intel",
                "serve",
                "--provider",
                "fixture",
                "--project-root",
                str(ROOT),
                "--fixture-db",
                str(db_file),
            ],
        )
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer, read_timeout_seconds=15) as client:
                await client.initialize()

                # Missing period_b with snapshot_id=None must fail BEFORE any fetch/DB init
                half_res = await client.call_tool(
                    "analyse_library",
                    {
                        "period_a": {
                            "start": "2026-09-01T00:00:00Z",
                            "end": "2026-10-01T00:00:00Z",
                        }
                    },
                )
                assert half_res.is_error
                assert half_res.structured_content is not None
                assert half_res.structured_content["error"]["code"] == "INVALID_INPUT"
                assert not db_file.exists()

                # Overlapping periods with snapshot_id=None must fail BEFORE any fetch/DB init
                overlap_res = await client.call_tool(
                    "analyse_library",
                    {
                        "period_a": {
                            "start": "2026-10-01T00:00:00Z",
                            "end": "2026-11-15T00:00:00Z",
                        },
                        "period_b": {
                            "start": "2026-11-01T00:00:00Z",
                            "end": "2026-12-01T00:00:00Z",
                        },
                    },
                )
                assert overlap_res.is_error
                assert overlap_res.structured_content is not None
                assert (
                    overlap_res.structured_content["error"]["code"] == "INVALID_INPUT"
                )
                assert not db_file.exists()

    anyio.run(_run)
