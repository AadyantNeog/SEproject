from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp_types import CallToolResult, TextContent, ToolAnnotations

from yt_intel.client_skills import project_file
from yt_intel.contracts.common import LanguageTag, OpaqueId, Positive
from yt_intel.contracts.errors import ContractError, ResultEnvelope
from yt_intel.contracts.models import CandidateSet
from yt_intel.contracts.proposals import PlaylistProposal, Privacy
from yt_intel.domain.constraints import parse_playlist_request
from yt_intel.infrastructure.database import Database
from yt_intel.infrastructure.repositories import SqliteProposalRepository
from yt_intel.presentation.previews import render_proposal
from yt_intel.presentation.results import render_error
from yt_intel.services.planning import FixturePlanningService


def register_fixture_planning(
    server: MCPServer[None], project_root: Path, fixture_db: Path | None
) -> None:
    candidate_path = project_file(
        project_root, Path("tests/fixtures/recommendations/candidates.json")
    )
    if not candidate_path.is_file():
        return
    catalog = CandidateSet.model_validate_json(candidate_path.read_bytes())
    service = FixturePlanningService(
        catalog, lambda: SqliteProposalRepository(Database(fixture_db))
    )

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
    ) -> Annotated[CallToolResult, ResultEnvelope[PlaylistProposal]]:
        """Store and preview a synthetic proposal locally without creating a playlist."""
        request_id = uuid4().hex
        fields = dict((ctx.request_context.params or {}).get("arguments", {}))
        candidate_reference = fields.pop("candidate_set_id", None)
        try:
            proposal = await service.propose(
                parse_playlist_request(fields), candidate_reference
            )
        except ContractError as error:
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
                    TextContent(
                        type="text", text=render_error(error.detail, mode="fixture")
                    )
                ],
            )
        result = ResultEnvelope[PlaylistProposal](
            mode="fixture",
            request_id=request_id,
            status="ok",
            data=proposal,
            warnings=proposal.warnings,
            coverage=catalog.coverage,
        )
        return CallToolResult(
            structured_content=result.model_dump(),
            content=[TextContent(type="text", text=render_proposal(proposal))],
        )
