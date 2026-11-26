from datetime import timedelta
from uuid import uuid4

from yt_intel.contracts.common import AccountBinding, OpaqueId, VideoId
from yt_intel.contracts.workflow import (
    CallCeiling,
    Clock,
    Endpoint,
    QuotaLedger,
    WorkflowPlan,
    WorkflowSession,
)
from yt_intel.infrastructure.clock import SystemClock
from yt_intel.infrastructure.quota import QuotaProfile

_WORKFLOW_LIFETIME = timedelta(minutes=5)
_VIDEO_TO_PLAYLIST: dict[Endpoint, CallCeiling] = {
    # Seed twice (explicit fetch and discovery), four hydration batches, revalidation.
    "videos.list": CallCeiling(calls=7, attempts_per_call=3),
    "search.list": CallCeiling(calls=4, attempts_per_call=3),
    "channels.list": CallCeiling(calls=1, attempts_per_call=3),
    "playlistItems.list": CallCeiling(calls=1, attempts_per_call=3),
    "playlists.insert": CallCeiling(calls=1, attempts_per_call=1),
    "playlistItems.insert": CallCeiling(calls=50, attempts_per_call=1),
}


class WorkflowService:
    """Create account-bound workflow sessions from server-defined call bounds."""

    def __init__(
        self, ledger: QuotaLedger, profile: QuotaProfile, clock: Clock | None = None
    ) -> None:
        self._ledger = ledger
        self._profile = profile
        self._clock = clock or SystemClock()
        self._sessions: dict[OpaqueId, tuple[WorkflowSession, VideoId | None]] = {}

    async def begin_video_to_playlist(
        self, binding: AccountBinding, project_id: OpaqueId, seed: VideoId | None
    ) -> WorkflowSession:
        now = self._clock.now()
        self._sessions = {
            identifier: entry
            for identifier, entry in self._sessions.items()
            if entry[0].idle_expires_at > now
        }
        plan = WorkflowPlan(
            plan_id=uuid4().hex,
            binding=binding,
            project_id=project_id,
            quota_profile_id=self._profile.profile_id,
            endpoint_ceilings=_VIDEO_TO_PLAYLIST,
            buckets={},
            candidate_cap=200,
            page_cap=4,
            sample_cap=0,
            deadline=now + _WORKFLOW_LIFETIME,
            cancellation_policy="stop and release unused quota",
            reconciliation_allowance={"playlistItems.list": 2},
        )
        plan = plan.model_copy(update={"buckets": self._profile.required_buckets(plan)})
        reservation = await self._ledger.reserve(plan)
        session = WorkflowSession(
            workflow_id=uuid4().hex,
            kind="video_to_playlist",
            stage="reserved",
            plan=plan,
            reservation_id=reservation.reservation_id,
            next_stages=("get_video",),
            spent_attempts={},
            remaining_attempts={
                endpoint: (
                    ceiling.calls + plan.reconciliation_allowance.get(endpoint, 0)
                )
                * ceiling.attempts_per_call
                for endpoint, ceiling in plan.endpoint_ceilings.items()
            },
            idle_expires_at=min(reservation.reset_at, plan.deadline),
        )
        self._sessions[session.workflow_id] = (session, seed)
        return session
