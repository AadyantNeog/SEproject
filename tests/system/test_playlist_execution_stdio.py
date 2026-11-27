import sys
from pathlib import Path

import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from yt_intel.infrastructure.database import Database

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("decision", "expected_writes"), [("reject", 0), ("approve", 2)]
)
async def test_composed_execution_uses_one_reservation_and_rejection_has_no_writes(
    tmp_path, decision, expected_writes
):
    state = tmp_path / "state.sqlite3"
    wire_audit = tmp_path / "wire-audit.txt"
    launcher = tmp_path / "fixture_server.py"
    launcher.write_text(
        f"""
from datetime import UTC, datetime
from pathlib import Path
from yt_intel.contracts.approval import HumanDecision
from yt_intel.mcp.server import build_fixture_server
from yt_intel.providers.fixture_writes import FixturePlaylistWrites

class FixtureApproval:
    async def request_decision(self, ctx, proposal, operation_id, challenge_ref):
        return HumanDecision(
            challenge_ref=challenge_ref, response_ref="fixture-response",
            operation_id=operation_id, proposal=proposal.ref,
            proposal_digest=proposal.digest, binding=ctx.binding,
            observed_at=datetime.now(UTC), decision={decision!r},
        )

dispatch = FixturePlaylistWrites._dispatch
def audit(self, request):
    if request.method == "POST":
        with Path({str(wire_audit)!r}).open("a", encoding="utf-8") as target:
            target.write(request.url.path + "\\n")
    return dispatch(self, request)
FixturePlaylistWrites._dispatch = audit
build_fixture_server(
    Path({str(ROOT)!r}), fixture_db=Path({str(state)!r}), creation_approval=FixtureApproval(),
).run(transport="stdio")
""",
        encoding="utf-8",
    )
    parameters = StdioServerParameters(
        command=sys.executable,
        args=[str(launcher)],
        cwd=ROOT,
        env={"PYTHONPATH": str(ROOT / "src")},
    )
    async with stdio_client(parameters) as (reader, writer):
        async with ClientSession(reader, writer, read_timeout_seconds=15) as client:
            await client.initialize()
            workflow = await client.call_tool(
                "begin_workflow", {"kind": "video_to_playlist", "video": "vidIndex002"}
            )
            assert not workflow.is_error, workflow.content
            assert workflow.structured_content is not None
            workflow_id = workflow.structured_content["data"]["workflow_id"]
            seed_args = {"workflow_id": workflow_id, "video": "vidIndex002"}
            seed = await client.call_tool("get_video", seed_args)
            assert not seed.is_error, seed.content
            discovery = await client.call_tool(
                "find_similar_videos", {**seed_args, "limit": 1}
            )
            assert not discovery.is_error, discovery.content
            assert discovery.structured_content is not None
            preview = await client.call_tool(
                "propose_playlist",
                {
                    "workflow_id": workflow_id,
                    "candidate_set_id": discovery.structured_content[
                        "candidate_set_id"
                    ],
                    "title": "Indexing from discovery",
                    "topic": "database indexing",
                    "total_seconds": 1800,
                    "max_video_seconds": 1200,
                    "language": "en",
                },
            )
            assert not preview.is_error, preview.content
            assert preview.structured_content is not None
            proposal = preview.structured_content["data"]
            approval_args = {**proposal["ref"], "workflow_id": workflow_id}
            prepared = await client.call_tool("prepare_creation", approval_args)
            assert not prepared.is_error, prepared.content
            assert prepared.structured_content is not None
            operation_id = prepared.structured_content["data"]["operation_id"]
            creation_args = {**approval_args, "operation_id": operation_id}
            result = await client.call_tool("create_playlist", creation_args)
            assert result.structured_content is not None, result.content
            data = result.structured_content["data"]
            if decision == "reject":
                assert result.is_error
                assert result.structured_content["error"]["code"] == "APPROVAL_REJECTED"
                assert data["state"] == "rejected"
                assert data["playlist_id"] is None
                assert data["confirmed_items"] == 0
            else:
                assert not result.is_error, result.content
                assert data["state"] == "completed"
                assert data["confirmed_items"] == 1
            replay = await client.call_tool("create_playlist", creation_args)
            status = await client.call_tool(
                "get_operation", {"operation_id": operation_id}
            )
            assert (
                replay.structured_content is not None
                and status.structured_content is not None
            )
            assert (
                replay.structured_content["data"]
                == status.structured_content["data"]
                == data
            )

    requests = (
        wire_audit.read_text(encoding="utf-8").splitlines()
        if wire_audit.exists()
        else []
    )
    assert len(requests) == expected_writes
    with Database(state).transaction(immediate=False) as connection:
        reservations = connection.execute(
            "SELECT reservation_id, released FROM quota_reservations"
        ).fetchall()
        assert len(reservations) == 1 and reservations[0]["released"] == 1
        attempts = connection.execute(
            "SELECT reservation_id, endpoint FROM quota_attempts"
        ).fetchall()
        assert {row["reservation_id"] for row in attempts} == {
            reservations[0]["reservation_id"]
        }
        assert {row["endpoint"] for row in attempts} >= {"videos.list", "search.list"}
        assert (
            sum(row["endpoint"].endswith(".insert") for row in attempts)
            == expected_writes
        )
