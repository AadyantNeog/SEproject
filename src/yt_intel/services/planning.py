from collections.abc import Callable
from datetime import UTC, datetime
from sqlite3 import Error as SqliteError
from uuid import uuid4

from pydantic import ValidationError

from yt_intel.contracts.common import OpaqueId
from yt_intel.contracts.models import CandidateSet, Coverage
from yt_intel.contracts.proposals import (
    PROPOSAL_LIFETIME,
    PlaylistProposal,
    ProposalRef,
)
from yt_intel.domain.constraints import PlaylistRequest, planning_error
from yt_intel.domain.language import normalize_language_tag
from yt_intel.domain.proposals import PlaylistPlanner, proposal_digest
from yt_intel.infrastructure.repositories import (
    RepositoryConflict,
    SqliteProposalRepository,
)
from yt_intel.services.fixture_candidates import FixtureCandidateSets


class FixturePlanningService:
    """Resolve synthetic candidates and persist the exact local preview."""

    def __init__(
        self,
        catalog: CandidateSet,
        proposals: Callable[[], SqliteProposalRepository],
        candidate_sets: FixtureCandidateSets,
    ) -> None:
        if catalog.binding.mode != "fixture" or catalog.source != "synthetic":
            raise ValueError(
                "playlist planning requires a synthetic fixture candidate set"
            )
        self._catalog = catalog
        self._proposals = proposals
        self._candidate_sets = candidate_sets
        self._planner = PlaylistPlanner(normalize_language_tag)

    async def propose(
        self, request: PlaylistRequest, candidate_set_id: OpaqueId | None
    ) -> tuple[PlaylistProposal, Coverage]:
        now = datetime.now(UTC)
        if (
            candidate_set_id is None
            or candidate_set_id == self._catalog.candidate_set_id
        ):
            # Replay only the bundled synthetic catalog. Discovery records retain their expiry.
            candidates = self._catalog.model_copy(
                update={"created_at": now, "expires_at": now + PROPOSAL_LIFETIME}
            )
        else:
            loaded = await self._candidate_sets.load(
                candidate_set_id, self._catalog.binding, now=now
            )
            if loaded is None:
                raise planning_error(
                    "CONTENT_UNAVAILABLE",
                    "The requested candidate set is missing or expired.",
                    "Run similar-video discovery again and use the returned candidate set ID.",
                )
            candidates = loaded
        proposal = self._planner.plan(
            request,
            candidates,
            binding=self._catalog.binding,
            destination_channel_title="Synthetic Database Lessons",
            proposal_id=uuid4().hex,
            now=now,
        )
        try:
            await self._proposals().save_proposal(proposal)
        except (OSError, SqliteError, RepositoryConflict) as error:
            raise planning_error(
                "PROVIDER_UNAVAILABLE",
                "The synthetic proposal could not be saved to local storage.",
                "Check access to the fixture database and try again.",
            ) from error
        return proposal, candidates.coverage

    async def current_preview(self, ref: ProposalRef) -> PlaylistProposal | None:
        binding = self._catalog.binding
        now = datetime.now(UTC)
        try:
            proposal = await self._proposals().get_current_proposal(
                binding, ref.proposal_id, now=now
            )
        except (OSError, SqliteError, ValidationError) as error:
            raise planning_error(
                "PROVIDER_UNAVAILABLE",
                "The local proposal store could not be read.",
                "Check access to the fixture database and try again.",
            ) from error
        if (
            not isinstance(proposal, PlaylistProposal)
            or proposal.ref != ref
            or proposal.binding != binding
            or not proposal.created_at <= now < proposal.expires_at
            or proposal.state not in {"proposed", "approved"}
            or proposal.digest != proposal_digest(proposal)
        ):
            return None
        return proposal
