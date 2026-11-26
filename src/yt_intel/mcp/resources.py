from pathlib import Path

from mcp.server import MCPServer
from pydantic import TypeAdapter, ValidationError

from yt_intel.client_skills import canonical_skills, project_file
from yt_intel.contracts.approval import ApprovableProposal
from yt_intel.presentation.previews import render_proposal

HELP_URI = "yt-intel://help"
CREATION_PREVIEW_URI = "yt-intel://fixture/previews/create"
RECOVERY_PREVIEW_URI = "yt-intel://fixture/previews/resume"
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
