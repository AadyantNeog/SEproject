from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp_types import CallToolResult, TextContent, ToolAnnotations

from yt_intel.contracts.common import Contract
from yt_intel.contracts.errors import ErrorDetail, ResultEnvelope
from yt_intel.infrastructure.database import Database
from yt_intel.infrastructure.repositories import SqliteCacheRepository
from yt_intel.presentation.results import render_error
from yt_intel.services.fixture_candidates import FixtureCandidateSets

from .discovery import register_fixture_discovery
from .library import register_fixture_library
from .planning import register_fixture_planning
from .recommendations import register_fixture_recommendations
from .resources import register_fixture_resources
from .workflows import fixture_workflow_runtime, register_fixture_workflows


class FixtureStatus(Contract):
    provider: Literal["fixture"] = "fixture"
    available: Literal[True] = True


def build_fixture_server(
    project_root: Path | None, *, fixture_db: Path | None = None
) -> MCPServer[None]:
    server: MCPServer[None] = MCPServer("YouTube Video Intelligence")
    register_fixture_resources(server, project_root)
    server.tool(
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False)
    )(fixture_status)
    if project_root is not None:
        candidate_sets = FixtureCandidateSets(
            lambda: SqliteCacheRepository(Database(fixture_db))
        )
        register_fixture_discovery(server, project_root, candidate_sets)
        library_runtime = register_fixture_library(server, project_root, fixture_db)
        register_fixture_planning(server, project_root, fixture_db, candidate_sets)
        register_fixture_recommendations(server, project_root, library_runtime)
        workflows = fixture_workflow_runtime(project_root)
        if workflows is not None:
            register_fixture_workflows(server, workflows)
    return server


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
            content=[
                TextContent(type="text", text=render_error(problem, mode="fixture"))
            ],
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
