from pathlib import Path
from sqlite3 import Error as SqliteError
from typing import Annotated, Literal
from uuid import uuid4

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp_types import CallToolResult, TextContent, ToolAnnotations
from pydantic import ValidationError

from yt_intel.client_skills import project_file
from yt_intel.contracts.common import Contract, LanguageTag, OpaqueId, Positive
from yt_intel.contracts.errors import ContractError, ResultEnvelope
from yt_intel.contracts.models import CandidateSet
from yt_intel.contracts.proposals import PlaylistProposal, Privacy
from yt_intel.domain.constraints import parse_playlist_request, planning_error
from yt_intel.infrastructure.database import Database, default_database_path
from yt_intel.infrastructure.repositories import SqliteProposalRepository
from yt_intel.presentation.previews import render_proposal
from yt_intel.presentation.results import render_error
from yt_intel.services.fixture_candidates import FixtureCandidateSets
from yt_intel.services.planning import FixturePlanningService

from .discovery import FixtureCancellation
from .resources import register_saved_proposal_previews, saved_proposal_link
from .workflows import FixtureWorkflowRuntime


class _PreviewReferences(Contract):
    candidate_set_id: OpaqueId | None = None
    workflow_id: OpaqueId | None = None


def register_fixture_planning(
    server: MCPServer[None],
    project_root: Path,
    fixture_db: Path | None,
    candidate_sets: FixtureCandidateSets,
    workflows: FixtureWorkflowRuntime | None,
) -> None:
    candidate_path = project_file(
        project_root, Path("tests/fixtures/recommendations/candidates.json")
    )
    if not candidate_path.is_file():
        return
    catalog = CandidateSet.model_validate_json(candidate_path.read_bytes())
    state_path = (fixture_db or default_database_path("fixture")).expanduser().resolve()
    service = FixturePlanningService(
        catalog,
        lambda: SqliteProposalRepository(Database(state_path)),
        candidate_sets,
    )
    register_saved_proposal_previews(server, service, state_path)

    @server.tool(
        annotations=ToolAnnotations(
            read_only_hint=False, destructive_hint=False, open_world_hint=False
        )
    )
    async def propose_playlist(
        ctx: Context[None, object],
        title: str | None = None,
        topic: str | None = None,
        total_seconds: Positive | None = None,
        max_video_seconds: Positive | None = None,
        language: LanguageTag | None = None,
        description: str = "",
        privacy: Privacy = "private",
        duration_mode: Literal["max", "exact"] = "max",
        include_seed: bool = False,
        candidate_set_id: OpaqueId | None = None,
        workflow_id: OpaqueId | None = None,
    ) -> Annotated[CallToolResult, ResultEnvelope[PlaylistProposal]]:
        """Preview a playlist from synthetic discovery candidates or the bundled set."""
        request_id = uuid4().hex
        fields = dict((ctx.request_context.params or {}).get("arguments", {}))
        try:
            try:
                references = _PreviewReferences.model_validate(
                    {
                        "candidate_set_id": fields.pop("candidate_set_id", None),
                        "workflow_id": fields.pop("workflow_id", None),
                    }
                )
            except ValidationError as error:
                raise planning_error(
                    "INVALID_INPUT",
                    "Invalid workflow or candidate set reference.",
                    "Use the IDs returned by the fixture tools.",
                ) from error
            request = parse_playlist_request(fields)
            if references.workflow_id is None:
                proposal, coverage = await service.propose(
                    request, references.candidate_set_id
                )
            else:
                if workflows is None:
                    raise planning_error(
                        "INVALID_INPUT",
                        "Workflow session is unavailable.",
                        "Start a fixture workflow and follow its stage order.",
                    )
                async with workflows.service.stage(
                    references.workflow_id,
                    "propose_playlist",
                    binding=catalog.binding,
                    request_id=request_id,
                    cancellation=FixtureCancellation(),
                    candidate_set_id=references.candidate_set_id,
                ) as access:
                    proposal, coverage = await service.propose(
                        request, references.candidate_set_id
                    )
                    access.proposal_ref = proposal.ref
        except (OSError, SqliteError):
            return _preview_error(
                request_id,
                planning_error(
                    "PROVIDER_UNAVAILABLE",
                    "The local workflow could not be accessed.",
                    "Check access to the fixture database and try again.",
                ),
            )
        except ContractError as error:
            return _preview_error(request_id, error)
        result = ResultEnvelope[PlaylistProposal](
            mode="fixture",
            request_id=request_id,
            status="ok",
            data=proposal,
            warnings=proposal.warnings,
            coverage=coverage,
        )
        return CallToolResult(
            structured_content=result.model_dump(),
            content=[
                TextContent(type="text", text=render_proposal(proposal)),
                saved_proposal_link(proposal.ref),
            ],
        )


def _preview_error(request_id: OpaqueId, error: ContractError) -> CallToolResult:
    result = ResultEnvelope[PlaylistProposal](
        mode="fixture",
        request_id=request_id,
        status="error",
        data=None,
        error=error.detail,
    )
    return CallToolResult(
        is_error=True,
        structured_content=result.model_dump(),
        content=[
            TextContent(type="text", text=render_error(error.detail, mode="fixture"))
        ],
    )
