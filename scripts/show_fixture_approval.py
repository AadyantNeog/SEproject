"""Open the native helper with the bundled synthetic creation preview."""

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from yt_intel.approval.grants import InMemoryGrantStore
from yt_intel.approval.native import NativeApprovalAdapter
from yt_intel.approval.service import (
    ApprovalRejected,
    ApprovalService,
    ApprovalUnavailable,
)
from yt_intel.contracts.proposals import PROPOSAL_LIFETIME, PlaylistProposal
from yt_intel.contracts.workflow import RequestContext
from yt_intel.domain.proposals import proposal_digest
from yt_intel.infrastructure.database import Database
from yt_intel.infrastructure.repositories import SqliteProposalRepository

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "tests/fixtures/contracts/playlist_proposal.json"
)


class FixtureCancellation:
    def is_cancelled(self) -> bool:
        return False

    async def wait(self) -> None:
        await asyncio.Future()


async def main() -> int:
    fixture = PlaylistProposal.model_validate_json(FIXTURE.read_bytes())
    if fixture.binding.mode != "fixture":
        raise ValueError("the desktop proof requires a synthetic fixture")
    now = datetime.now(UTC)
    proposal = fixture.model_copy(
        update={"created_at": now, "expires_at": now + PROPOSAL_LIFETIME}
    )
    proposal = proposal.model_copy(update={"digest": proposal_digest(proposal)})
    ctx = RequestContext(
        request_id="fixture-desktop-proof",
        binding=proposal.binding,
        reservation_id="fixture-desktop-proof",
        deadline=proposal.expires_at,
        cancellation=FixtureCancellation(),
    )
    with TemporaryDirectory() as directory:
        repository = SqliteProposalRepository(
            Database(Path(directory) / "proof.sqlite3")
        )
        await repository.save_proposal(proposal)
        service = ApprovalService(
            NativeApprovalAdapter(), InMemoryGrantStore(), repository
        )
        try:
            await service.request_grant(ctx, proposal, "fixture-desktop-proof")
        except ApprovalRejected:
            print("Dialog rejected or closed. No grant issued.")
        except ApprovalUnavailable as error:
            print(f"Approval unavailable. {error}")
            return 1
        else:
            print(
                "Synthetic approval accepted. The process discards the grant on exit."
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
