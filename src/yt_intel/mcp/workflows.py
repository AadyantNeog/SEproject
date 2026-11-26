from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated, Literal
from uuid import uuid4

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp_types import CallToolResult, TextContent, ToolAnnotations
from pydantic import ValidationError

from yt_intel.client_skills import project_file
from yt_intel.contracts.common import Contract, OpaqueId, UtcDateTime
from yt_intel.contracts.errors import ContractError, ErrorDetail, ResultEnvelope
from yt_intel.contracts.proposals import PlaylistProposal
from yt_intel.contracts.workflow import BucketVector
from yt_intel.domain.identifiers import parse_video_id
from yt_intel.infrastructure.database import Database
from yt_intel.infrastructure.quota import QuotaProfile, SqliteQuotaLedger
from yt_intel.presentation.results import render_error
from yt_intel.services.workflows import WorkflowService


class WorkflowInput(Contract):
    kind: Literal["video_to_playlist"]
    video: str | None = None


class WorkflowStarted(Contract):
    workflow_id: OpaqueId
    reserved: BucketVector
    expires_at: UtcDateTime


def register_fixture_workflows(server: MCPServer[None], project_root: Path) -> None:
    profile_path = project_file(
        project_root, Path("config/quota-profiles/youtube-2026-11-16.json")
    )
    proposal_path = project_file(
        project_root, Path("tests/fixtures/contracts/playlist_proposal.json")
    )
    if not profile_path.is_file() or not proposal_path.is_file():
        return
    binding = PlaylistProposal.model_validate_json(proposal_path.read_bytes()).binding
    if binding.mode != "fixture":
        raise ValueError("workflow fixtures require a synthetic account")
    profile = QuotaProfile.load(profile_path)
    storage: TemporaryDirectory[str] | None = None
    service: WorkflowService | None = None

    @server.tool(
        annotations=ToolAnnotations(read_only_hint=False, open_world_hint=False)
    )
    async def begin_workflow(
        ctx: Context[None, object],
        kind: Literal["video_to_playlist"],
        video: str | None = None,
    ) -> Annotated[CallToolResult, ResultEnvelope[WorkflowStarted]]:
        """Reserve the full synthetic video-to-playlist budget before fetching a seed."""
        nonlocal storage, service
        request_id = uuid4().hex
        try:
            inputs = WorkflowInput.model_validate(
                (ctx.request_context.params or {}).get("arguments", {})
            )
            seed = parse_video_id(inputs.video) if inputs.video is not None else None
            if service is None:
                storage = TemporaryDirectory(prefix="yt-intel-quota-")
                database = Database(Path(storage.name) / "state.sqlite3")
                service = WorkflowService(SqliteQuotaLedger(database, profile), profile)
            session = await service.begin_video_to_playlist(
                binding, "fixture-project", seed
            )
        except ValidationError:
            return _failed(
                request_id,
                ErrorDetail(
                    code="INVALID_INPUT",
                    message="Invalid workflow input.",
                    retryable=False,
                    safe_next_action="Use video_to_playlist and an optional YouTube video.",
                ),
            )
        except ContractError as error:
            return _failed(request_id, error.detail)
        result = ResultEnvelope[WorkflowStarted](
            mode="fixture",
            request_id=request_id,
            status="ok",
            data=WorkflowStarted(
                workflow_id=session.workflow_id,
                reserved=session.plan.buckets,
                expires_at=session.idle_expires_at,
            ),
        )
        return CallToolResult(
            structured_content=result.model_dump(),
            content=[
                TextContent(
                    type="text",
                    text=f"Reserved fixture workflow {session.workflow_id}.",
                )
            ],
        )


def _failed(request_id: OpaqueId, error: ErrorDetail) -> CallToolResult:
    result = ResultEnvelope[WorkflowStarted](
        mode="fixture", request_id=request_id, status="blocked", data=None, error=error
    )
    return CallToolResult(
        is_error=True,
        structured_content=result.model_dump(),
        content=[TextContent(type="text", text=render_error(error, mode="fixture"))],
    )
