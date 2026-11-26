import json
import sys
from pathlib import Path

import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp_types import TextContent

from yt_intel.contracts.errors import ResultEnvelope
from yt_intel.services.recommendations import RecommendationResult


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_fixture_recommendations_over_stdio() -> None:
    root = Path(__file__).resolve().parents[2]
    server = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "yt_intel",
            "serve",
            "--provider",
            "fixture",
            "--project-root",
            str(root),
        ],
    )
    async with stdio_client(server) as (reader, writer):
        async with ClientSession(reader, writer, read_timeout_seconds=10) as client:
            await client.initialize()
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}
            tool = tools["recommend_videos"]
            assert tool.annotations is not None and tool.annotations.read_only_hint
            assert tool.annotations.open_world_hint is False
            assert tool.output_schema is not None

            ranked = await client.call_tool(
                "recommend_videos",
                {
                    "snapshot_id": "fixture-snapshot",
                    "language": "en",
                    "topic": "database indexing",
                    "total_seconds": 720,
                    "max_video_seconds": 600,
                },
            )
            assert not ranked.is_error
            envelope = ResultEnvelope[RecommendationResult].model_validate_json(
                json.dumps(ranked.structured_content)
            )
            assert envelope.mode == "fixture" and envelope.status == "ok"
            assert envelope.data is not None
            assert [item.video.video_id for item in envelope.data.results] == [
                "fixture0301"
            ]
            assert envelope.data.results[0].preference_sources == ("likes",)
            assert envelope.data.sources["likes"].state == "retrieved"
            assert envelope.data.sources["subscriptions"].state == "not_requested"
            assert envelope.coverage is not None and envelope.coverage.retrieved == 2
            assert (envelope.data.total_seconds, envelope.data.unused_seconds) == (
                600,
                120,
            )
            assert isinstance(ranked.content[0], TextContent)
            assert "Mode: fixture (synthetic data)" in ranked.content[0].text
            assert "Unused time: 120 s" in ranked.content[0].text

            empty = await client.call_tool("recommend_videos", {"language": "ja"})
            assert not empty.is_error
            envelope = ResultEnvelope[RecommendationResult].model_validate_json(
                json.dumps(empty.structured_content)
            )
            assert envelope.status == "empty"
            assert envelope.data is not None and not envelope.data.results

            for arguments, code in (
                ({"snapshot_id": "foreign-snapshot"}, "CONTENT_UNAVAILABLE"),
                ({"limit": "1"}, "INVALID_INPUT"),
                ({"account_id": "foreign-account"}, "INVALID_INPUT"),
                ({"workflow_id": "unresolved-session"}, "INVALID_INPUT"),
            ):
                refused = await client.call_tool("recommend_videos", arguments)
                assert refused.is_error
                envelope = ResultEnvelope[RecommendationResult].model_validate_json(
                    json.dumps(refused.structured_content)
                )
                assert envelope.data is None
                assert envelope.error is not None and envelope.error.code == code
