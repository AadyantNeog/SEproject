from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp_types import CallToolResult, TextContent, ToolAnnotations

from yt_intel.contracts.approval import ApprovalAdapter
from yt_intel.contracts.common import Contract
from yt_intel.contracts.errors import ErrorDetail, ResultEnvelope
from yt_intel.infrastructure.database import Database, default_database_path
from yt_intel.infrastructure.repositories import SqliteCacheRepository
from yt_intel.presentation.results import render_error
from yt_intel.services.fixture_candidates import FixtureCandidateSets

from .discovery import register_fixture_discovery
from .execution import register_fixture_execution
from .library import register_fixture_library
from .planning import register_fixture_planning
from .recommendations import register_fixture_recommendations
from .resources import register_fixture_resources
from .workflows import fixture_workflow_runtime, register_fixture_workflows


class FixtureStatus(Contract):
    provider: Literal["fixture"] = "fixture"
    available: Literal[True] = True


def build_fixture_server(
    project_root: Path | None,
    *,
    fixture_db: Path | None = None,
    creation_approval: ApprovalAdapter | None = None,
) -> MCPServer[None]:
    server: MCPServer[None] = MCPServer("YouTube Video Intelligence")
    register_fixture_resources(server, project_root)
    server.tool(
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False)
    )(fixture_status)
    if project_root is not None:
        state_path = (
            (fixture_db or default_database_path("fixture")).expanduser().resolve()
        )
        workflows = fixture_workflow_runtime(project_root, database_path=state_path)
        candidate_sets = FixtureCandidateSets(
            lambda: SqliteCacheRepository(Database(state_path))
        )
        register_fixture_discovery(
            server, project_root, state_path, candidate_sets, workflows
        )
        library_runtime = register_fixture_library(
            server, project_root, state_path, workflows
        )
        register_fixture_planning(
            server, project_root, state_path, candidate_sets, workflows
        )
        register_fixture_recommendations(server, project_root, library_runtime)
        if workflows is not None:
            register_fixture_workflows(server, workflows)
            register_fixture_execution(
                server,
                project_root,
                state_path,
                workflows,
                approval_adapter=creation_approval,
            )
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
