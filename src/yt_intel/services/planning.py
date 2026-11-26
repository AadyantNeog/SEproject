from collections.abc import Callable
from datetime import UTC, datetime
from sqlite3 import Error as SqliteError
from uuid import uuid4

from yt_intel.contracts.common import OpaqueId
from yt_intel.contracts.models import CandidateSet
from yt_intel.contracts.proposals import PROPOSAL_LIFETIME, PlaylistProposal
from yt_intel.contracts.repositories import ProposalRepository
from yt_intel.domain.constraints import PlaylistRequest, planning_error
from yt_intel.domain.language import normalize_language_tag
from yt_intel.domain.proposals import PlaylistPlanner
from yt_intel.infrastructure.repositories import RepositoryConflict


class FixturePlanningService:
    """Build a local preview from a bundled candidate set and persist its exact content."""

    def __init__(
        self, catalog: CandidateSet, proposals: Callable[[], ProposalRepository]
    ) -> None:
        if catalog.binding.mode != "fixture" or catalog.source != "synthetic":
            raise ValueError(
                "playlist planning requires a synthetic fixture candidate set"
            )
        self._catalog = catalog
        self._proposals = proposals
        self._planner = PlaylistPlanner(normalize_language_tag)

    async def propose(
        self, request: PlaylistRequest, candidate_set_id: OpaqueId | None
    ) -> PlaylistProposal:
        if (
            candidate_set_id is not None
            and candidate_set_id != self._catalog.candidate_set_id
        ):
            raise planning_error(
                "CONTENT_UNAVAILABLE",
                "The requested candidate set is unavailable in this fixture.",
                "Omit candidate_set_id to use the bundled synthetic candidates.",
            )
        now = datetime.now(UTC)
        # Replay the static synthetic catalog. The resulting proposal expires
        # against the current clock used by the SQLite repository.
        candidates = self._catalog.model_copy(
            update={"created_at": now, "expires_at": now + PROPOSAL_LIFETIME}
        )
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
        return proposal
