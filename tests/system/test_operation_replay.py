import json
import sys
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from yt_intel.contracts.proposals import PlaylistProposal
from yt_intel.domain.proposals import proposal_digest
from yt_intel.infrastructure.database import Database
from yt_intel.infrastructure.repositories import (
    OperationItem,
    SqliteOperationRepository,
    SqliteProposalRepository,
    WriteStep,
)
from yt_intel.providers.fixture_writes import FixturePlaylistWrites
from yt_intel.providers.youtube_writes import item_request, playlist_request

ROOT = Path(__file__).resolve().parents[2]
OPERATION = "interrupted-fixture-write"


async def _interrupted_operation(path, scenario):
    database = Database(path)
    proposal = PlaylistProposal.model_validate_json(
        (ROOT / "tests/fixtures/contracts/playlist_proposal.json").read_text(
            encoding="utf-8"
        )
    )
    now = datetime.now(UTC)
    items = tuple(
        entry.model_copy(
            update={
                "video_id": video_id,
                "title": "B-Tree Database Indexing Deep Dive",
                "channel_title": "Systems Study Lab",
                "duration_seconds": duration,
            }
        )
        for entry, video_id, duration in zip(
            proposal.items, ("vidIndex001", "vidMore0001"), (1200, 300), strict=True
        )
    )
    proposal = proposal.model_copy(
        update={
            "items": items,
            "total_seconds": 1500,
            "unused_seconds": 300,
            "created_at": now - timedelta(minutes=7),
            "expires_at": now - timedelta(minutes=1),
        }
    )
    proposal = proposal.model_copy(update={"digest": proposal_digest(proposal)})
    await SqliteProposalRepository(database).save_proposal(proposal)
    operations = SqliteOperationRepository(database)
    claimed = await operations.claim_operation(
        proposal.binding, OPERATION, proposal.digest
    )
    create = WriteStep(endpoint="playlists.insert", planned_cost={})
    playlist = None
    steps = [create]
    if scenario != "unknown_create":
        with httpx.Client(
            base_url="https://www.googleapis.com/youtube/v3/",
            transport=FixturePlaylistWrites(
                proposal.binding.channel_id, database=database
            ).transport(),
        ) as fixture:
            response = fixture.post("playlists", json=playlist_request(proposal.body))
            response.raise_for_status()
            playlist = response.json()["id"]
            steps[0] = create.model_copy(
                update={"outcome": "saved", "remote_id": playlist}
            )
            response = fixture.post(
                "playlistItems", json=item_request(playlist, items[0].video_id, 0)
            )
            response.raise_for_status()
            if scenario in {"applied", "drift"}:
                fixture.post(
                    "playlistItems",
                    json=item_request(
                        playlist,
                        items[1].video_id if scenario == "applied" else "vidIndex002",
                        1,
                    ),
                ).raise_for_status()
            steps.extend(
                (
                    WriteStep(
                        endpoint="playlistItems.insert",
                        position=0,
                        planned_cost={},
                        outcome="saved",
                        remote_id=response.json()["id"],
                    ),
                    WriteStep(
                        endpoint="playlistItems.insert", position=1, planned_cost={}
                    ),
                )
            )
    await operations.update_operation(
        claimed.model_copy(
            update={
                "state": "unknown" if playlist is None else "creating",
                "updated_at": now - timedelta(minutes=6),
                "proposal_ref": proposal.ref,
                "playlist_id": playlist,
                "planned_items": tuple(
                    OperationItem(
                        video_id=item.video_id, duration_seconds=item.duration_seconds
                    )
                    for item in items
                ),
                "write_steps": tuple(steps),
            }
        )
    )
    return playlist


def _launcher(directory, state, decision):
    audit = directory / "approval-audit.txt"
    launcher = directory / "recovery_fixture.py"
    launcher.write_text(
        f"""
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from yt_intel.contracts.approval import HumanDecision
from yt_intel.mcp.server import build_fixture_server
from yt_intel.providers.fixture import FixtureDataset

load_catalog = FixtureDataset.from_json_file
def with_extra_video(cls, path):
    dataset = load_catalog(path)
    if path.name != "catalog.json" or "vidIndex001" not in dataset.videos:
        return dataset
    template = dataset.videos["vidIndex001"]
    return replace(dataset, videos={{**dataset.videos, "vidMore0001": {{
        **template, "id": "vidMore0001", "contentDetails": {{"duration": "PT5M"}}
    }}}})
FixtureDataset.from_json_file = classmethod(with_extra_video)

class FixtureApproval:
    async def request_decision(self, ctx, proposal, operation_id, challenge_ref):
        assert proposal.purpose == "resume"
        with Path({str(audit)!r}).open("a", encoding="utf-8") as target:
            target.write(proposal.ref.proposal_id + "\\n")
        return HumanDecision(
            challenge_ref=challenge_ref, response_ref="fixture-response",
            operation_id=operation_id, proposal=proposal.ref,
            proposal_digest=proposal.digest, binding=ctx.binding,
            observed_at=datetime.now(UTC), decision={decision!r},
        )

build_fixture_server(
    Path({str(ROOT)!r}), fixture_db=Path({str(state)!r}), creation_approval=FixtureApproval(),
).run(transport="stdio")
""",
        encoding="utf-8",
    )
    return launcher, audit


@asynccontextmanager
async def _client(launcher):
    parameters = StdioServerParameters(
        command=sys.executable,
        args=[str(launcher)],
        cwd=ROOT,
        env={"PYTHONPATH": str(ROOT / "src")},
    )
    async with stdio_client(parameters) as (reader, writer):
        async with ClientSession(reader, writer, read_timeout_seconds=15) as client:
            await client.initialize()
            yield client


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("scenario", "decision", "expected_writes"),
    [
        ("missing", "approve", 1),
        ("missing", "reject", 0),
        ("applied", "approve", 0),
        ("drift", "approve", 0),
        ("unknown_create", "approve", 0),
        ("expired_result", "approve", 0),
    ],
)
async def test_recovery_after_process_restart(
    tmp_path, scenario, decision, expected_writes
):
    path = tmp_path / "operations.sqlite3"
    playlist = await _interrupted_operation(path, scenario)
    if scenario == "expired_result":
        with Database(path).transaction() as connection:
            connection.execute(
                "UPDATE operations SET retained_until = ? WHERE operation_id = ?",
                ((datetime.now(UTC) - timedelta(seconds=1)).isoformat(), OPERATION),
            )
    launcher, audit = _launcher(tmp_path, path, decision)
    args = {"operation_id": OPERATION}
    async with _client(launcher) as client:
        reconciliation = await client.call_tool("reconcile_operation", args)
        assert reconciliation.structured_content is not None, reconciliation.content
        if scenario == "drift":
            assert reconciliation.is_error
            assert (
                reconciliation.structured_content["error"]["code"] == "PROPOSAL_CHANGED"
            )
        elif scenario == "expired_result":
            assert reconciliation.is_error
            assert (
                reconciliation.structured_content["error"]["code"]
                == "OPERATION_RESULT_EXPIRED"
            )
        else:
            assert not reconciliation.is_error, reconciliation.content
            data = reconciliation.structured_content["data"]
            assert data["playlist_id"] == playlist
            if scenario == "unknown_create":
                assert data["state"] == "manual_required"
                assert data["preview"] is None
            elif scenario == "applied":
                assert data["state"] == "complete"
                assert len(data["verified_items"]) == 2
                assert data["preview"] is None
            else:
                assert data["state"] == "resume_ready"
                assert len(data["verified_items"]) == 1
                preview = data["preview"]
                assert [item["video_id"] for item in preview["missing_suffix"]] == [
                    "vidMore0001"
                ]

    async with _client(launcher) as restarted:
        if scenario == "missing":
            resume_args = {**args, **preview["ref"]}
            result = await restarted.call_tool("resume_operation", resume_args)
            assert result.structured_content is not None, result.content
            replay = await restarted.call_tool("resume_operation", args)
            assert replay.structured_content is not None, replay.content
            if decision == "approve":
                assert not result.is_error, result.content
                completed = result.structured_content["data"]
                assert completed["state"] == "completed"
                assert completed["confirmed_duration_seconds"] == 1500
                assert completed["pending_items"] == []
                assert replay.structured_content["data"] == completed
            else:
                assert result.is_error
                assert result.structured_content["error"]["code"] == "APPROVAL_REJECTED"
                assert replay.structured_content["error"]["code"] == "PROPOSAL_CHANGED"
            assert audit.read_text(encoding="utf-8").splitlines() == [
                preview["ref"]["proposal_id"]
            ]
        else:
            assert not audit.exists()
        status = await restarted.call_tool("get_operation", args)
        assert status.structured_content is not None, status.content
        if scenario == "expired_result":
            assert status.is_error
            assert (
                status.structured_content["error"]["code"] == "OPERATION_RESULT_EXPIRED"
            )
        else:
            assert not status.is_error, status.content
        if scenario == "applied" or expected_writes:
            assert status.structured_content["data"]["confirmed_items"] == 2
            assert status.structured_content["data"]["state"] == "completed"

    with Database(path).transaction(immediate=False) as connection:
        calls = [
            row["endpoint"]
            for row in connection.execute("SELECT endpoint FROM quota_attempts")
        ]
        assert "playlists.insert" not in calls
        assert calls.count("playlistItems.insert") == expected_writes
        if scenario in {"unknown_create", "expired_result"}:
            assert calls == []
        assert connection.execute(
            "SELECT COUNT(*) FROM fixture_remote_items"
        ).fetchone()[0] == (
            0
            if playlist is None
            else 2
            if scenario in {"applied", "drift"}
            else 1 + expected_writes
        )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("status", "error_code"),
    [
        ({"privacyStatus": "public"}, "PROPOSAL_CHANGED"),
        ({}, "VERIFICATION_PENDING"),
        ({"privacyStatus": "privacystatusunspecified"}, "VERIFICATION_PENDING"),
    ],
    ids=["changed-to-public", "missing-privacy", "unknown-privacy"],
)
async def test_resume_rechecks_playlist_privacy_after_preview(
    tmp_path, status, error_code
):
    path = tmp_path / "operations.sqlite3"
    playlist = await _interrupted_operation(path, "missing")
    assert playlist is not None
    launcher, audit = _launcher(tmp_path, path, "approve")
    args = {"operation_id": OPERATION}

    async with _client(launcher) as client:
        result = await client.call_tool("reconcile_operation", args)
        assert not result.is_error and result.structured_content is not None
        assert result.structured_content["data"]["state"] == "resume_ready"
        preview = result.structured_content["data"]["preview"]
        assert preview["body"]["privacy"] == "private"

        # Simulate a remote settings change after the saved preview is issued.
        with Database(path).transaction() as connection:
            row = connection.execute(
                "SELECT body FROM fixture_remote_playlists WHERE playlist_id = ?",
                (playlist,),
            ).fetchone()
            body = json.loads(row["body"])
            body["status"] = status
            connection.execute(
                "UPDATE fixture_remote_playlists SET body = ? WHERE playlist_id = ?",
                (json.dumps(body), playlist),
            )

        resumed = await client.call_tool("resume_operation", {**args, **preview["ref"]})
        assert resumed.is_error and resumed.structured_content is not None
        assert resumed.structured_content["error"]["code"] == error_code

    assert audit.read_text(encoding="utf-8").splitlines() == [
        preview["ref"]["proposal_id"]
    ]
    with Database(path).transaction(immediate=False) as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM quota_attempts WHERE endpoint IN ('playlists.insert', 'playlistItems.insert')"
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM fixture_remote_items WHERE playlist_id = ?",
                (playlist,),
            ).fetchone()[0]
            == 1
        )
