import json
import sys
from pathlib import Path

import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.shared.exceptions import MCPError
from mcp_types import TextContent, TextResourceContents

from yt_intel.bootstrap import HELP_URI, FixtureStatus
from yt_intel.contracts.errors import ResultEnvelope
from yt_intel.mcp.resources import CREATION_PREVIEW_URI, RECOVERY_PREVIEW_URI


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_fixture_stdio_negotiates_and_serves_tool_and_resource():
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "yt_intel", "serve", "--provider", "fixture"],
    )
    async with stdio_client(server) as (reader, writer):
        async with ClientSession(reader, writer, read_timeout_seconds=10) as client:
            initialized = await client.initialize()
            assert initialized.protocol_version == "2025-11-25"
            assert initialized.capabilities.tools is not None
            assert initialized.capabilities.resources is not None

            tools = (await client.list_tools()).tools
            assert [tool.name for tool in tools] == ["fixture_status"]
            assert tools[0].annotations is not None
            assert tools[0].annotations.read_only_hint is True
            assert tools[0].input_schema["type"] == "object"
            assert tools[0].output_schema is not None
            assert tools[0].output_schema["type"] == "object"

            result = await client.call_tool("fixture_status", {})
            assert not result.is_error
            envelope = ResultEnvelope[FixtureStatus].model_validate_json(
                json.dumps(result.structured_content)
            )
            assert (envelope.schema_version, envelope.mode, envelope.status) == (
                "1",
                "fixture",
                "ok",
            )
            assert envelope.data == FixtureStatus()
            assert result.content == [
                TextContent(type="text", text="The fixture server is available.")
            ]

            invalid = await client.call_tool("fixture_status", {"mode": "live"})
            assert invalid.is_error
            envelope = ResultEnvelope[FixtureStatus].model_validate_json(
                json.dumps(invalid.structured_content)
            )
            assert envelope.error is not None
            assert envelope.error.code == "INVALID_INPUT"
            assert isinstance(invalid.content[0], TextContent)
            assert "Next action:" in invalid.content[0].text

            resources = (await client.list_resources()).resources
            assert [str(resource.uri) for resource in resources] == [HELP_URI]
            contents = (await client.read_resource(HELP_URI)).contents
            assert len(contents) == 1
            assert isinstance(contents[0], TextResourceContents)
            assert contents[0].mime_type == "text/plain"
            assert "fixture mode" in contents[0].text


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_checkout_resources_are_read_only_and_allowlisted():
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
            resources = {item.uri for item in (await client.list_resources()).resources}
            skill_uri = "yt-intel://skills/brain-ingest"
            assert {
                HELP_URI,
                CREATION_PREVIEW_URI,
                RECOVERY_PREVIEW_URI,
                skill_uri,
            } <= resources
            create = (await client.read_resource(CREATION_PREVIEW_URI)).contents[0]
            recovery = (await client.read_resource(RECOVERY_PREVIEW_URI)).contents[0]
            skill = (await client.read_resource(skill_uri)).contents[0]
            assert isinstance(create, TextResourceContents)
            assert isinstance(recovery, TextResourceContents)
            assert isinstance(skill, TextResourceContents)
            assert "Mode: fixture (synthetic data)" in create.text
            assert "Videos in order (2)" in create.text
            assert "Missing videos to insert (1)" in recovery.text
            assert skill.mime_type == "text/markdown"
            assert (
                skill.text
                == (root / ".agents/skills/brain-ingest/SKILL.md").read_bytes().decode()
            )
            with pytest.raises(MCPError):
                await client.read_resource("yt-intel://skills/../../AGENTS.md")
            missing_tool = await client.call_tool("create_playlist", {})
            assert missing_tool.is_error
