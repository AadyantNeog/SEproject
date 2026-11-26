import json
import sys
from pathlib import Path

import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp_types import TextContent

from yt_intel.contracts.errors import ResultEnvelope
from yt_intel.contracts.models import RankedChannel, RankedVideo


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_fixture_discovery_over_stdio() -> None:
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
            for name in ("find_similar_videos", "find_similar_channels"):
                tool = tools[name]
                assert tool.annotations is not None and tool.annotations.read_only_hint
                assert tool.annotations.open_world_hint is False
                assert tool.output_schema is not None

            videos = await client.call_tool(
                "find_similar_videos",
                {"video": "https://youtu.be/vidIndex001", "limit": 1},
            )
            assert not videos.is_error
            ranking = ResultEnvelope[tuple[RankedVideo, ...]].model_validate_json(
                json.dumps(videos.structured_content)
            )
            assert ranking.mode == "fixture" and ranking.status == "ok"
            assert ranking.data is not None
            assert [row.video.video_id for row in ranking.data] == ["vidIndex002"]
            assert ranking.data[0].video.duration_seconds == 1201
            assert ranking.coverage is not None and ranking.coverage.paginated
            assert ranking.coverage.unknown == 2
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
                error = ResultEnvelope[tuple[RankedVideo, ...]].model_validate_json(
                    json.dumps(refused.structured_content)
                )
                assert error.data is None
                assert error.error is not None and error.error.code == code
