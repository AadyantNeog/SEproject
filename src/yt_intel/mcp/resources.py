from pathlib import Path

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ResourceError, ResourceNotFoundError
from mcp_types import ResourceLink
from pydantic import TypeAdapter, ValidationError

from yt_intel.client_skills import canonical_skills, project_file
from yt_intel.contracts.approval import ApprovableProposal
from yt_intel.contracts.errors import ContractError
from yt_intel.contracts.proposals import ProposalRef
from yt_intel.presentation.previews import render_proposal
from yt_intel.services.planning import FixturePlanningService

HELP_URI = "yt-intel://help"
CREATION_PREVIEW_URI = "yt-intel://fixture/previews/create"
RECOVERY_PREVIEW_URI = "yt-intel://fixture/previews/resume"
SAVED_PREVIEW_URI = "yt-intel://proposals/{proposal_id}/{version}"
_PREVIEW_ADAPTER = TypeAdapter(ApprovableProposal)


def register_fixture_resources(
    server: MCPServer[None], project_root: Path | None
) -> None:
    _register_text(
        server,
        HELP_URI,
        "Fixture server help",
        "YouTube Video Intelligence is running in fixture mode. Use fixture_status to check it. "
        "When started with --project-root, list resources for available synthetic previews "
        "and canonical skills.",
    )
    if project_root is None:
        return

    fixtures = Path("tests", "fixtures", "contracts")
    for uri, filename, purpose in (
        (CREATION_PREVIEW_URI, "playlist_proposal.json", "create"),
        (RECOVERY_PREVIEW_URI, "resume_proposal.json", "resume"),
    ):
        path = project_file(project_root, fixtures / filename)
        if path.is_file():
            try:
                proposal = _PREVIEW_ADAPTER.validate_json(path.read_bytes())
            except ValidationError:
                raise ValueError(f"invalid fixture preview for {purpose}") from None
            if proposal.binding.mode != "fixture" or proposal.purpose != purpose:
                raise ValueError(f"invalid fixture preview for {purpose}")
            _register_text(
                server,
                uri,
                f"Synthetic playlist preview ({purpose})",
                render_proposal(proposal),
            )

    for name, data in canonical_skills(project_root).items():
        _register_text(
            server,
            f"yt-intel://skills/{name}",
            name,
            data.decode("utf-8"),
            "text/markdown",
        )


def _register_text(
    server: MCPServer[None],
    uri: str,
    name: str,
    contents: str,
    mime_type: str = "text/plain",
) -> None:
    @server.resource(uri, name=name, mime_type=mime_type)
    def read_text() -> str:
        return contents


def register_saved_proposal_previews(
    server: MCPServer[None], service: FixturePlanningService, state_path: Path
) -> None:
    @server.resource(
        SAVED_PREVIEW_URI, name="Saved playlist preview", mime_type="text/plain"
    )
    async def read_saved_preview(proposal_id: str, version: str) -> str:
        unavailable = "The requested playlist preview is unavailable."
        try:
            ref = ProposalRef(proposal_id=proposal_id, version=int(version))
        except ValueError:
            raise ResourceNotFoundError(unavailable) from None
        if str(ref.version) != version or not state_path.is_file():
            raise ResourceNotFoundError(unavailable)
        try:
            proposal = await service.current_preview(ref)
        except ContractError as error:
            raise ResourceError(error.detail.message) from error
        if proposal is None:
            raise ResourceNotFoundError(unavailable)
        return render_proposal(proposal)


def saved_proposal_link(ref: ProposalRef) -> ResourceLink:
    return ResourceLink(
        type="resource_link",
        uri=SAVED_PREVIEW_URI.format(proposal_id=ref.proposal_id, version=ref.version),
        name="Saved playlist preview",
        mime_type="text/plain",
    )
