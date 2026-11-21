import json
import sys

import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp_types import TextContent, TextResourceContents

from yt_intel.bootstrap import HELP_URI, FixtureStatus
from yt_intel.contracts.errors import ResultEnvelope


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
            assert (envelope.schema_version, envelope.mode, envelope.status) == ("1", "fixture", "ok")
            assert envelope.data == FixtureStatus()
            assert result.content == [TextContent(type="text", text="The fixture server is available.")]

            invalid = await client.call_tool("fixture_status", {"mode": "live"})
            assert invalid.is_error
            envelope = ResultEnvelope[FixtureStatus].model_validate_json(
                json.dumps(invalid.structured_content)
            )
            assert envelope.error is not None
            assert envelope.error.code == "INVALID_INPUT"

            resources = (await client.list_resources()).resources
            assert [str(resource.uri) for resource in resources] == [HELP_URI]
            contents = (await client.read_resource(HELP_URI)).contents
            assert len(contents) == 1
            assert isinstance(contents[0], TextResourceContents)
            assert contents[0].mime_type == "text/plain"
            assert "fixture mode" in contents[0].text
