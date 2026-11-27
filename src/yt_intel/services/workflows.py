from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import timedelta
from typing import Literal
from uuid import uuid4

from yt_intel.contracts.common import AccountBinding, OpaqueId, VideoId
from yt_intel.contracts.errors import ContractError, ErrorCode, ErrorDetail
from yt_intel.contracts.workflow import (
    CallCeiling,
    CancellationToken,
    Clock,
    Endpoint,
    QuotaLedger,
    RequestContext,
    WorkflowPlan,
    WorkflowSession,
)
from yt_intel.infrastructure.clock import SystemClock
from yt_intel.infrastructure.quota import QuotaProfile

_WORKFLOW_LIFETIME = timedelta(minutes=5)
type PreviewStage = Literal["get_video", "find_similar_videos", "propose_playlist"]

_NEXT_STAGE: dict[PreviewStage, tuple[PreviewStage, ...]] = {
    "get_video": ("find_similar_videos",),
    "find_similar_videos": ("propose_playlist",),
    "propose_playlist": (),
}
_VIDEO_TO_PLAYLIST: dict[Endpoint, CallCeiling] = {
    # Seed twice (explicit fetch and discovery), four hydration batches, revalidation.
    "videos.list": CallCeiling(calls=7, attempts_per_call=3),
    "search.list": CallCeiling(calls=4, attempts_per_call=3),
    "channels.list": CallCeiling(calls=1, attempts_per_call=3),
    "playlistItems.list": CallCeiling(calls=1, attempts_per_call=3),
    "playlists.insert": CallCeiling(calls=1, attempts_per_call=1),
    "playlistItems.insert": CallCeiling(calls=50, attempts_per_call=1),
}


@dataclass(slots=True)
class _ActiveWorkflow:
    session: WorkflowSession
    seed: VideoId | None
    candidate_set_id: OpaqueId | None = None
    running: bool = False


@dataclass(slots=True)
class StageAccess:
    context: RequestContext
    candidate_set_id: OpaqueId | None = None


def _workflow_error(code: ErrorCode, message: str) -> ContractError:
    return ContractError(
        ErrorDetail(
            code=code,
            message=message,
            retryable=False,
            safe_next_action="Use the current workflow and follow its stage order.",
        )
    )


class WorkflowService:
    """Create account-bound workflow sessions from server-defined call bounds."""

    def __init__(
        self, ledger: QuotaLedger, profile: QuotaProfile, clock: Clock | None = None
    ) -> None:
        self._ledger = ledger
        self._profile = profile
        self._clock = clock or SystemClock()
        self._sessions: dict[OpaqueId, _ActiveWorkflow] = {}

    async def begin_video_to_playlist(
        self, binding: AccountBinding, project_id: OpaqueId, seed: VideoId | None
    ) -> WorkflowSession:
        now = self._clock.now()
        self._sessions = {
            identifier: entry
            for identifier, entry in self._sessions.items()
            if entry.session.idle_expires_at > now
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
        self._sessions[session.workflow_id] = _ActiveWorkflow(session, seed)
        return session

    @asynccontextmanager
    async def stage(
        self,
        workflow_id: OpaqueId,
        stage: PreviewStage,
        *,
        binding: AccountBinding,
        request_id: OpaqueId,
        cancellation: CancellationToken,
        video: VideoId | None = None,
        candidate_set_id: OpaqueId | None = None,
    ) -> AsyncIterator[StageAccess]:
        """Give the next handler the original reservation for one stage."""
        entry = self._sessions.get(workflow_id)
        if entry is None:
            raise _workflow_error("INVALID_INPUT", "Workflow session is unavailable.")
        session = entry.session
        if session.plan.binding != binding:
            raise _workflow_error(
                "ACCOUNT_MISMATCH", "Workflow belongs to another account."
            )
        if self._clock.now() >= session.idle_expires_at or cancellation.is_cancelled():
            raise _workflow_error(
                "WORKFLOW_TIMEOUT", "Workflow expired or was cancelled."
            )
        if entry.running or stage not in session.next_stages:
            raise _workflow_error(
                "INVALID_INPUT", "Workflow stage is out of order or busy."
            )
        if stage == "propose_playlist":
            if candidate_set_id is None or candidate_set_id != entry.candidate_set_id:
                raise _workflow_error(
                    "INVALID_INPUT", "Candidate set does not belong to this workflow."
                )
        elif video is None or (entry.seed is not None and entry.seed != video):
            raise _workflow_error(
                "INVALID_INPUT", "Video does not match the workflow seed."
            )

        access = StageAccess(
            context=RequestContext(
                request_id=request_id,
                binding=binding,
                reservation_id=session.reservation_id,
                deadline=session.idle_expires_at,
                cancellation=cancellation,
                workflow_id=workflow_id,
            )
        )
        entry.running = True
        try:
            yield access
            if (
                cancellation.is_cancelled()
                or self._clock.now() >= session.idle_expires_at
            ):
                raise _workflow_error(
                    "WORKFLOW_TIMEOUT", "Workflow expired or was cancelled."
                )
            if stage == "find_similar_videos":
                if access.candidate_set_id is None:
                    raise _workflow_error(
                        "INSUFFICIENT_DATA",
                        "Discovery did not produce a candidate set.",
                    )
                entry.candidate_set_id = access.candidate_set_id
            elif stage == "get_video":
                entry.seed = video
            entry.session = session.model_copy(
                update={"stage": stage, "next_stages": _NEXT_STAGE[stage]}
            )
        except BaseException:
            self._sessions.pop(workflow_id, None)
            await self._ledger.release(session.reservation_id)
            raise
        finally:
            entry.running = False
