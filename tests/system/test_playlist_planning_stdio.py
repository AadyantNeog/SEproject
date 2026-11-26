import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp_types import TextContent

from yt_intel.contracts.errors import ResultEnvelope
from yt_intel.contracts.proposals import PlaylistProposal
from yt_intel.domain.proposals import proposal_digest
from yt_intel.infrastructure.database import Database
from yt_intel.infrastructure.repositories import SqliteProposalRepository


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_fixture_playlist_preview_is_stored(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    database_path = tmp_path / "state.sqlite3"
    server = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "yt_intel",
            "serve",
            "--provider",
            "fixture",
            "--project-root",
            str(root),
            "--fixture-db",
            str(database_path),
        ],
    )
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
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}
            tool = tools["propose_playlist"]
            assert tool.output_schema is not None
            assert (
                tool.annotations is not None
                and tool.annotations.read_only_hint is False
            )
            assert tool.annotations.open_world_hint is False
            assert "create_playlist" not in tools

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

    database = Database(database_path)
    store = SqliteProposalRepository(database)
    assert (
        await store.get_proposal(proposal.binding, proposal.ref, now=datetime.now(UTC))
        == proposal
    )
    with database.transaction(immediate=False) as connection:
        assert connection.execute("SELECT COUNT(*) FROM proposals").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM operations").fetchone()[0] == 0
