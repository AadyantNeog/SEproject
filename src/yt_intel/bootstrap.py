from typing import Annotated, Literal
from uuid import uuid4

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp_types import CallToolResult, TextContent, ToolAnnotations

from .contracts.common import Contract
from .contracts.errors import ErrorDetail, ResultEnvelope

HELP_URI = "yt-intel://help"


class FixtureStatus(Contract):
    provider: Literal["fixture"] = "fixture"
    available: Literal[True] = True


def create_fixture_server() -> MCPServer:
    server = MCPServer("YouTube Video Intelligence")

    @server.tool(
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False)
    )
    def fixture_status(
        ctx: Context[None, object],
    ) -> Annotated[CallToolResult, ResultEnvelope[FixtureStatus]]:
        """Check the local fixture server's availability."""
        request_id = uuid4().hex
        if (ctx.request_context.params or {}).get("arguments"):
            problem = ErrorDetail(
                code="INVALID_INPUT",
                message="fixture_status does not accept arguments.",
                retryable=False,
                safe_next_action="Call fixture_status with an empty arguments object.",
            )
            result = ResultEnvelope[FixtureStatus](
                mode="fixture",
                request_id=request_id,
                status="error",
                data=None,
                error=problem,
            )
            return CallToolResult(
                is_error=True,
                structured_content=result.model_dump(),
                content=[TextContent(type="text", text=problem.message)],
            )
        result = ResultEnvelope[FixtureStatus](
            mode="fixture", request_id=request_id, status="ok", data=FixtureStatus()
        )
        return CallToolResult(
            structured_content=result.model_dump(),
            content=[
                TextContent(type="text", text=f"The {result.mode} server is available.")
            ],
        )

    @server.resource(HELP_URI, name="Fixture server help", mime_type="text/plain")
    def help_resource() -> str:
        return "YouTube Video Intelligence is running in fixture mode. Use fixture_status to check it."

    return server
