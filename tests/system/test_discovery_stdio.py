import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp_types import TextContent

from yt_intel.contracts.errors import ResultEnvelope
from yt_intel.contracts.models import RankedChannel
from yt_intel.contracts.proposals import PlaylistProposal
from yt_intel.infrastructure.database import Database
from yt_intel.infrastructure.repositories import SqliteCacheRepository
from yt_intel.mcp.discovery import VideoDiscoveryEnvelope
from yt_intel.services.fixture_candidates import FixtureCandidateSets


def fixture_server(database_path: Path) -> StdioServerParameters:
    root = Path(__file__).resolve().parents[2]
    return StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "yt_intel",
            "serve",
            "--provider",
            "fixture",
            "--project-root",
            str(root),
            "--fixture-db",
            str(database_path),
        ],
    )


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_fixture_discovery_over_stdio(tmp_path: Path) -> None:
    server = fixture_server(tmp_path / "state.sqlite3")
    async with stdio_client(server) as (reader, writer):
        async with ClientSession(reader, writer, read_timeout_seconds=10) as client:
            await client.initialize()
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}
            for name in ("find_similar_videos", "find_similar_channels"):
                tool = tools[name]
                assert tool.annotations is not None
                assert tool.annotations.open_world_hint is False
                assert tool.output_schema is not None
            assert tools["find_similar_videos"].annotations.read_only_hint is False
            assert tools["find_similar_channels"].annotations.read_only_hint is True

            videos = await client.call_tool(
                "find_similar_videos",
                {"video": "https://youtu.be/vidIndex001", "limit": 1},
            )
            assert not videos.is_error
            ranking = VideoDiscoveryEnvelope.model_validate_json(
                json.dumps(videos.structured_content)
            )
            assert ranking.mode == "fixture" and ranking.status == "ok"
            assert ranking.data is not None
            assert [row.video.video_id for row in ranking.data] == ["vidIndex002"]
            assert ranking.data[0].video.duration_seconds == 1201
            assert ranking.coverage is not None and ranking.coverage.paginated
            assert ranking.coverage.unknown == 2
            assert ranking.candidate_set_id is not None
            assert isinstance(videos.content[0], TextContent)
            assert "Mode: fixture (synthetic data)" in videos.content[0].text
            assert "Audio language: unknown" in videos.content[0].text

            channels = await client.call_tool(
                "find_similar_channels",
                {"channel": "https://www.youtube.com/@SystemsStudyLab"},
            )
            assert not channels.is_error
            comparison = ResultEnvelope[tuple[RankedChannel, ...]].model_validate_json(
                json.dumps(channels.structured_content)
            )
            assert comparison.mode == "fixture" and comparison.status == "ok"
            assert comparison.data is not None
            assert [row.sample.channel.channel_id for row in comparison.data] == [
                "UCbbbbbbbbbbbbbbbbbbbbbb"
            ]
            sample = comparison.data[0].sample
            assert sample.video_ids == ("vidIndex002",)
            assert sample.selection_rule_version == "first-accessible-uploads-v1"
            assert comparison.coverage is not None and comparison.coverage.sampled
            assert isinstance(channels.content[0], TextContent)
            assert "Channel sample: 1 usable" in channels.content[0].text

            for args, code in (
                (
                    {"video": "https://example.com/watch?v=vidIndex001"},
                    "UNSUPPORTED_IDENTIFIER",
                ),
                ({"video": "vidIndex001", "limit": "1"}, "INVALID_INPUT"),
                ({"video": "vidIndex001", "binding": "live"}, "INVALID_INPUT"),
                (
                    {"video": "vidIndex001", "workflow_id": "unresolved-session"},
                    "INVALID_INPUT",
                ),
                ({"video": "vidOmit0009"}, "CONTENT_UNAVAILABLE"),
            ):
                refused = await client.call_tool("find_similar_videos", args)
                assert refused.is_error
                error = VideoDiscoveryEnvelope.model_validate_json(
                    json.dumps(refused.structured_content)
                )
                assert error.data is None
                assert error.candidate_set_id is None
                assert error.error is not None and error.error.code == code


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_discovered_candidates_reach_planner_after_restart(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "state.sqlite3"
    server = fixture_server(database_path)
    async with stdio_client(server) as (reader, writer):
        async with ClientSession(reader, writer, read_timeout_seconds=10) as client:
            await client.initialize()
            search = await client.call_tool(
                "find_similar_videos", {"video": "vidIndex002", "limit": 1}
            )
            assert not search.is_error
            ranking = VideoDiscoveryEnvelope.model_validate_json(
                json.dumps(search.structured_content)
            )
            candidate_set_id = ranking.candidate_set_id
            assert candidate_set_id is not None

    async with stdio_client(server) as (reader, writer):
        async with ClientSession(reader, writer, read_timeout_seconds=10) as client:
            await client.initialize()
            fields = {
                "title": "Indexing from discovery",
                "topic": "database indexing",
                "total_seconds": 1800,
                "max_video_seconds": 1200,
                "language": "en",
            }
            missing = await client.call_tool(
                "propose_playlist",
                {**fields, "candidate_set_id": "discovery-" + "0" * 32},
            )
            assert missing.is_error
            error = ResultEnvelope[PlaylistProposal].model_validate_json(
                json.dumps(missing.structured_content)
            )
            assert error.error is not None and error.error.code == "CONTENT_UNAVAILABLE"

            preview = await client.call_tool(
                "propose_playlist", {**fields, "candidate_set_id": candidate_set_id}
            )
            assert not preview.is_error
            result = ResultEnvelope[PlaylistProposal].model_validate_json(
                json.dumps(preview.structured_content)
            )
            assert result.data is not None and result.coverage is not None
            proposal = result.data
            assert proposal.candidate_set_id == candidate_set_id
            assert [item.video_id for item in proposal.items] == ["vidIndex001"]
            assert (proposal.total_seconds, proposal.unused_seconds) == (1200, 600)
            assert proposal.exclusions["seed_not_requested"] == 1
            assert result.coverage.paginated and result.coverage.unknown == 2

    candidates = FixtureCandidateSets(
        lambda: SqliteCacheRepository(Database(database_path))
    )
    now = datetime.now(UTC)
    collection = await candidates.load(candidate_set_id, proposal.binding, now=now)
    assert collection is not None and collection.seed_video_id == "vidIndex002"
    other_account = proposal.binding.model_copy(
        update={"credential_binding_id": "other-account"}
    )
    assert await candidates.load(candidate_set_id, other_account, now=now) is None
    assert (
        await candidates.load(
            candidate_set_id, proposal.binding, now=collection.expires_at
        )
        is None
    )
