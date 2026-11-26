import sys
from pathlib import Path

import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


@pytest.mark.anyio
async def test_begin_workflow_reserves_composed_budget_over_stdio():
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
            args = {"kind": "video_to_playlist", "video": "dQw4w9WgXcQ"}
            seen = set()
            for _ in range(3):
                result = await client.call_tool("begin_workflow", args)
                assert not result.is_error
                assert result.structured_content is not None
                data = result.structured_content["data"]
                assert data["reserved"] == {"general": 2583, "search": 12}
                seen.add(data["workflow_id"])
            assert len(seen) == 3
            denied = await client.call_tool("begin_workflow", args)
            assert denied.is_error
            assert denied.structured_content is not None
            assert denied.structured_content["error"]["code"] == "QUOTA_INSUFFICIENT"
