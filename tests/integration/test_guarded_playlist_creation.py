import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import anyio
import httpx
import pytest

from yt_intel.approval.grants import InMemoryGrantStore
from yt_intel.approval.service import ApprovalService
from yt_intel.contracts.approval import HumanDecision
from yt_intel.contracts.proposals import PlaylistProposal
from yt_intel.domain.proposals import proposal_digest
from yt_intel.infrastructure.database import Database
from yt_intel.infrastructure.http import AccountedHttpExecutor
from yt_intel.infrastructure.quota import QuotaProfile, SqliteQuotaLedger
from yt_intel.infrastructure.repositories import (
    SqliteOperationRepository,
    SqliteProposalRepository,
)
from yt_intel.providers.fixture_writes import FixturePlaylistWrites
from yt_intel.providers.youtube import LiveYouTubeReadProvider
from yt_intel.providers.youtube_writes import YouTubeWriteAdapter
from yt_intel.services.creation import PlaylistCreationService

ROOT = Path(__file__).resolve().parents[2]


class Cancellation:
    def __init__(self):
        self.event = anyio.Event()

    def is_cancelled(self):
        return self.event.is_set()

    async def wait(self):
        await self.event.wait()


class FixtureDecision:
    async def request_decision(self, ctx, proposal, operation_id, challenge_ref):
        return HumanDecision(
            challenge_ref=challenge_ref,
            response_ref="fixture-response",
            operation_id=operation_id,
            proposal=proposal.ref,
            proposal_digest=proposal.digest,
            binding=ctx.binding,
            decision="approve",
            observed_at=datetime.now(UTC),
        )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("fail_at", "fault", "expected_state", "last_outcome"),
    [
        (None, "reject", "completed", "saved"),
        (1, "reject", "partial", "refused"),
        (1, "timeout_after_insert", "unknown", "unknown"),
    ],
)
async def test_write_journal_survives_item_failure(
    tmp_path, fail_at, fault, expected_state, last_outcome
):
    fixture = PlaylistProposal.model_validate_json(
        (ROOT / "tests/fixtures/contracts/playlist_proposal.json").read_bytes()
    )
    now = datetime.now(UTC)
    proposal = fixture.model_copy(
        update={"created_at": now, "expires_at": now + timedelta(minutes=5)}
    )
    proposal = proposal.model_copy(update={"digest": proposal_digest(proposal)})
    database = Database(tmp_path / "creation.sqlite3")
    proposals = SqliteProposalRepository(database)
    operations = SqliteOperationRepository(database)
    await proposals.save_proposal(proposal)
    profile = QuotaProfile.load(ROOT / "config/quota-profiles/youtube-2026-11-16.json")
    ledger = SqliteQuotaLedger(database, profile)
    simulator = FixturePlaylistWrites(
        proposal.binding.channel_id, fail_at=fail_at, fault=fault
    )
    transport = simulator.transport()

    def dispatch(request):
        endpoint = request.url.path.rsplit("/", 1)[-1]
        if request.method == "POST":
            with database.transaction(immediate=False) as connection:
                row = connection.execute("SELECT payload FROM operations").fetchone()
                journal = json.loads(row["payload"])
                assert journal["write_steps"][-1]["outcome"] == "pending"
                assert journal["write_steps"][-1]["planned_cost"] == {"general": 50}
                assert all(step["remote_id"] for step in journal["write_steps"][:-1])
                spent = connection.execute(
                    "SELECT SUM(spent) FROM quota_reservation_buckets"
                ).fetchone()[0]
                assert spent == 2 + 50 * len(journal["write_steps"])
            return transport.handle_request(request)
        if endpoint == "channels":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": proposal.binding.channel_id,
                            "snippet": {"title": proposal.destination_channel_title},
                        }
                    ]
                },
            )
        if endpoint == "videos":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": item.video_id,
                            "snippet": {
                                "title": item.title,
                                "channelTitle": item.channel_title,
                                "defaultAudioLanguage": item.audio_language,
                                "liveBroadcastContent": "none",
                            },
                            "contentDetails": {
                                "duration": f"PT{item.duration_seconds}S"
                            },
                            "status": {
                                "privacyStatus": "public",
                                "uploadStatus": "processed",
                            },
                        }
                        for item in proposal.items
                    ]
                },
            )
        return transport.handle_request(request)

    async with AccountedHttpExecutor(
        quota_ledger=ledger, transport=httpx.MockTransport(dispatch)
    ) as executor:
        service = PlaylistCreationService(
            proposals,
            operations,
            ApprovalService(FixtureDecision(), InMemoryGrantStore(), proposals),
            ledger,
            profile,
            LiveYouTubeReadProvider(executor, expected_mode="fixture"),
            YouTubeWriteAdapter(executor),
        )
        intent = await service.prepare(proposal.binding, proposal.ref)
        args = {"project_id": "fixture-project", "cancellation": Cancellation()}
        result = await service.create(
            proposal.binding, proposal.ref, intent.operation_id, **args
        )
        assert result.state == expected_state
        assert result.playlist_id
        posted = [request for request in simulator.requests if request.method == "POST"]
        assert posted[0].url.params["part"] == "snippet,status"
        assert json.loads(posted[0].content) == {
            "snippet": {
                "title": proposal.body.title,
                "description": proposal.body.description,
            },
            "status": {"privacyStatus": proposal.body.privacy},
        }
        for index, request in enumerate(posted[1:]):
            assert request.url.params["part"] == "snippet"
            assert json.loads(request.content) == {
                "snippet": {
                    "playlistId": result.playlist_id,
                    "resourceId": {
                        "kind": "youtube#video",
                        "videoId": proposal.items[index].video_id,
                    },
                    "position": index,
                }
            }
        assert [step.outcome for step in result.write_steps] == [
            "saved",
            "saved",
            last_outcome,
        ]
        assert (
            len([request for request in simulator.requests if request.method == "POST"])
            == 3
        )
        assert (
            await service.create(
                proposal.binding, proposal.ref, intent.operation_id, **args
            )
        ) == result
        assert (
            len([request for request in simulator.requests if request.method == "POST"])
            == 3
        )
    reopened = SqliteOperationRepository(Database(database.path))
    assert await reopened.get_operation(proposal.binding, intent.operation_id) == result
