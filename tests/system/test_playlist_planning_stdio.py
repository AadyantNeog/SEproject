import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.shared.exceptions import MCPError
from mcp_types import INVALID_PARAMS, ResourceLink, TextContent, TextResourceContents

from yt_intel.contracts.errors import ResultEnvelope
from yt_intel.contracts.proposals import PlaylistProposal, ProposalRef
from yt_intel.domain.proposals import proposal_digest
from yt_intel.infrastructure.database import Database
from yt_intel.infrastructure.repositories import SqliteProposalRepository
from yt_intel.mcp.resources import SAVED_PREVIEW_URI

ROOT = Path(__file__).resolve().parents[2]


def fixture_server(database_path: Path) -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "yt_intel",
            "serve",
            "--provider",
            "fixture",
            "--project-root",
            str(ROOT),
            "--fixture-db",
            str(database_path),
        ],
    )


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_fixture_playlist_preview_is_stored(tmp_path: Path) -> None:
    database_path = tmp_path / "state.sqlite3"
    server = fixture_server(database_path)
    request = {
        "title": "Indexing for beginners",
        "topic": "database indexing",
        "total_seconds": 720,
        "max_video_seconds": 600,
        "language": "en",
    }
    async with stdio_client(server) as (reader, writer):
        async with ClientSession(reader, writer, read_timeout_seconds=10) as client:
            await client.initialize()
            templates = await client.list_resource_templates()
            assert SAVED_PREVIEW_URI in {
                item.uri_template for item in templates.resource_templates
            }
            with pytest.raises(MCPError) as missing:
                await client.read_resource("yt-intel://proposals/missing-preview/1")
            assert missing.value.code == INVALID_PARAMS
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}
            tool = tools["propose_playlist"]
            assert tool.output_schema is not None
            assert (
                tool.annotations is not None
                and tool.annotations.read_only_hint is False
            )
            assert tool.annotations.open_world_hint is False
            creation_tool = tools["create_playlist"]
            assert creation_tool.annotations is not None
            assert creation_tool.annotations.read_only_hint is False
            assert "confirmed" not in creation_tool.input_schema["properties"]

            for args, code in (
                ({"title": "Need clarification"}, "CLARIFICATION_REQUIRED"),
                ({**request, "duration_mode": "exact"}, "CLARIFICATION_REQUIRED"),
                ({**request, "language": "ja"}, "NO_FEASIBLE_PLAYLIST"),
                ({**request, "max_video_seconds": 599}, "NO_FEASIBLE_PLAYLIST"),
                (
                    {**request, "candidate_set_id": "foreign-candidate-set"},
                    "CONTENT_UNAVAILABLE",
                ),
                ({**request, "confirmed": True}, "INVALID_INPUT"),
                ({**request, "total_seconds": "720"}, "INVALID_INPUT"),
            ):
                refused = await client.call_tool("propose_playlist", args)
                assert refused.is_error
                error = ResultEnvelope[PlaylistProposal].model_validate_json(
                    json.dumps(refused.structured_content)
                )
                assert error.data is None
                assert error.error is not None and error.error.code == code
            assert not database_path.exists()

            preview = await client.call_tool(
                "propose_playlist",
                {**request, "candidate_set_id": "fixture-recommendations"},
            )
            assert not preview.is_error
            result = ResultEnvelope[PlaylistProposal].model_validate_json(
                json.dumps(preview.structured_content)
            )
            assert result.status == "ok" and result.mode == "fixture"
            assert result.data is not None
            proposal = result.data
            unprepared = await client.call_tool(
                "create_playlist",
                {
                    **proposal.ref.model_dump(),
                    "workflow_id": "missing-workflow",
                    "operation_id": "missing-operation",
                },
            )
            assert unprepared.is_error
            assert unprepared.structured_content is not None
            assert unprepared.structured_content["error"]["code"] == "INVALID_INPUT"
            assert proposal.state == "proposed" and proposal.ref.version == 1
            assert proposal.body.privacy == "private"
            assert [item.video_id for item in proposal.items] == ["fixture0301"]
            assert proposal.items[0].audio_language == "en-US"
            assert (proposal.total_seconds, proposal.unused_seconds) == (600, 120)
            assert proposal.exclusions["audio_language_mismatch"] == 1
            assert proposal.expires_at - proposal.created_at == timedelta(minutes=10)
            assert proposal.digest == proposal_digest(proposal)
            assert isinstance(preview.content[0], TextContent)
            assert "Mode: fixture (synthetic data)" in preview.content[0].text
            assert "Unused time: 120 s" in preview.content[0].text
            assert proposal.items[0].canonical_url in preview.content[0].text
            link = preview.content[1]
            assert isinstance(link, ResourceLink)
            assert str(link.uri) == f"yt-intel://proposals/{proposal.ref.proposal_id}/1"
            read_again = await client.read_resource(link.uri)
            assert len(read_again.contents) == 1
            resource = read_again.contents[0]
            assert isinstance(resource, TextResourceContents)
            assert resource.mime_type == "text/plain"
            assert resource.text == preview.content[0].text

    database = Database(database_path)
    store = SqliteProposalRepository(database)
    assert (
        await store.get_proposal(proposal.binding, proposal.ref, now=datetime.now(UTC))
        == proposal
    )
    with database.transaction(immediate=False) as connection:
        assert connection.execute("SELECT COUNT(*) FROM proposals").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM operations").fetchone()[0] == 0


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_saved_preview_denies_stale_and_foreign_versions(tmp_path: Path) -> None:
    database_path = tmp_path / "state.sqlite3"
    store = SqliteProposalRepository(Database(database_path))
    base = PlaylistProposal.model_validate_json(
        (ROOT / "tests/fixtures/contracts/playlist_proposal.json").read_bytes()
    )
    now = datetime.now(UTC)
    base = base.model_copy(
        update={"created_at": now, "expires_at": now + timedelta(minutes=10)}
    )

    def fixture_proposal(
        proposal_id: str, version: int = 1, **updates: object
    ) -> PlaylistProposal:
        proposal = base.model_copy(
            update={
                "ref": ProposalRef(proposal_id=proposal_id, version=version),
                **updates,
            }
        )
        return proposal.model_copy(update={"digest": proposal_digest(proposal)})

    stale = fixture_proposal("two-versions")
    current = fixture_proposal("two-versions", version=2)
    foreign = fixture_proposal(
        "foreign-preview",
        binding=base.binding.model_copy(
            update={"credential_binding_id": "other-fixture-account"}
        ),
    )
    expired = fixture_proposal(
        "expired-preview",
        created_at=now - timedelta(minutes=20),
        expires_at=now - timedelta(minutes=10),
    )
    changed = fixture_proposal("changed-preview").model_copy(
        update={"digest": "f" * 64}
    )
    rejected = fixture_proposal("rejected-preview", state="rejected")
    for proposal in (stale, current, foreign, expired, changed, rejected):
        await store.save_proposal(proposal)

    async with stdio_client(fixture_server(database_path)) as (reader, writer):
        async with ClientSession(reader, writer, read_timeout_seconds=10) as client:
            await client.initialize()
            latest = await client.read_resource("yt-intel://proposals/two-versions/2")
            assert isinstance(latest.contents[0], TextResourceContents)
            assert current.digest in latest.contents[0].text
            for suffix in (
                "two-versions/1",
                "two-versions/02",
                "foreign-preview/1",
                "expired-preview/1",
                "changed-preview/1",
                "rejected-preview/1",
            ):
                with pytest.raises(MCPError) as denied:
                    await client.read_resource(f"yt-intel://proposals/{suffix}")
                assert denied.value.code == INVALID_PARAMS
                assert (
                    denied.value.message
                    == "The requested playlist preview is unavailable."
                )
