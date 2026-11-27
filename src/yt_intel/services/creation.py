from datetime import timedelta
from typing import Literal
from uuid import uuid4

from anyio import CancelScope

from yt_intel.approval.service import ApprovalRejected, ApprovalService
from yt_intel.contracts.approval import ApprovedWriteContext
from yt_intel.contracts.common import AccountBinding, OpaqueId
from yt_intel.contracts.errors import ContractError, ErrorCode, ErrorDetail
from yt_intel.contracts.proposals import PlaylistProposal, ProposalRef
from yt_intel.contracts.provider import YouTubeReadProvider, YouTubeWriteProvider
from yt_intel.contracts.workflow import (
    CallCeiling,
    CancellationToken,
    Clock,
    QuotaLedger,
    RequestContext,
    WorkflowPlan,
)
from yt_intel.domain.language import normalize_language_tag
from yt_intel.domain.proposals import proposal_digest
from yt_intel.infrastructure.clock import SystemClock
from yt_intel.infrastructure.http import compute_write_request_digest
from yt_intel.infrastructure.quota import QuotaProfile
from yt_intel.infrastructure.repositories import (
    OperationIntent,
    OperationItem,
    SqliteOperationRepository,
    SqliteProposalRepository,
    WriteStep,
)
from yt_intel.providers.youtube_writes import (
    CREATE_PARAMS,
    INSERT_PARAMS,
    item_request,
    playlist_request,
)

type WriteEndpoint = Literal["playlists.insert", "playlistItems.insert"]


def _blocked(code: ErrorCode, message: str) -> ContractError:
    return ContractError(
        ErrorDetail(
            code=code,
            message=message,
            retryable=False,
            safe_next_action="Check the current preview and recorded operation before continuing.",
        )
    )


class PlaylistCreationService:
    """Guarded creation using a synthetic provider configuration."""

    def __init__(
        self,
        proposals: SqliteProposalRepository,
        operations: SqliteOperationRepository,
        approval: ApprovalService,
        ledger: QuotaLedger,
        profile: QuotaProfile,
        reads: YouTubeReadProvider,
        writes: YouTubeWriteProvider,
        clock: Clock | None = None,
    ) -> None:
        if proposals.database.path != operations.database.path:
            raise ValueError(
                "creation requires one database for proposals and operations"
            )
        self._proposals = proposals
        self._operations = operations
        self._approval = approval
        self._ledger = ledger
        self._profile = profile
        self._reads = reads
        self._writes = writes
        self._clock = clock or SystemClock()

    async def prepare(
        self,
        binding: AccountBinding,
        ref: ProposalRef,
        *,
        workflow_id: OpaqueId | None = None,
    ) -> OperationIntent:
        proposal = await self._current(binding, ref)
        intent = await self._operations.claim_operation(
            binding, uuid4().hex, proposal.digest
        )
        return await self._save(
            intent,
            proposal_ref=ref,
            workflow_id=workflow_id,
            planned_items=tuple(
                OperationItem(
                    video_id=item.video_id, duration_seconds=item.duration_seconds
                )
                for item in proposal.items
            ),
        )

    async def create(
        self,
        binding: AccountBinding,
        ref: ProposalRef,
        operation_id: OpaqueId,
        *,
        project_id: OpaqueId,
        cancellation: CancellationToken,
    ) -> OperationIntent:
        intent = await self._operations.get_operation(binding, operation_id)
        if intent is None:
            raise _blocked(
                "OPERATION_CONFLICT", "Operation is unavailable under this account."
            )
        if intent.proposal_ref != ref or intent.workflow_id is not None:
            raise _blocked(
                "OPERATION_CONFLICT", "Operation does not match this proposal."
            )
        if intent.state != "not_started":
            return intent
        proposal = await self._current(binding, ref)
        if proposal.digest != intent.digest:
            raise _blocked(
                "OPERATION_CONFLICT", "The prepared proposal content changed."
            )
        plan = WorkflowPlan(
            plan_id=uuid4().hex,
            binding=binding,
            project_id=project_id,
            quota_profile_id=self._profile.profile_id,
            endpoint_ceilings={
                "channels.list": CallCeiling(calls=1, attempts_per_call=3),
                "videos.list": CallCeiling(calls=1, attempts_per_call=3),
                "playlists.insert": CallCeiling(calls=1, attempts_per_call=1),
                "playlistItems.insert": CallCeiling(
                    calls=len(proposal.items), attempts_per_call=1
                ),
                "playlistItems.list": CallCeiling(calls=1, attempts_per_call=3),
            },
            buckets={},
            candidate_cap=len(proposal.items),
            page_cap=1,
            sample_cap=0,
            deadline=min(proposal.expires_at, self._clock.now() + timedelta(minutes=5)),
            cancellation_policy="stop and release unused quota",
            reconciliation_allowance={},
        )
        plan = plan.model_copy(update={"buckets": self._profile.required_buckets(plan)})
        reservation = await self._ledger.reserve(plan)
        ctx = RequestContext(
            binding=binding,
            request_id=uuid4().hex,
            reservation_id=reservation.reservation_id,
            deadline=min(plan.deadline, reservation.reset_at),
            cancellation=cancellation,
        )
        try:
            return await self._execute(ctx, proposal, intent)
        finally:
            with CancelScope(shield=True):
                await self._ledger.release(reservation.reservation_id)

    async def create_in_workflow(
        self, ctx: RequestContext, ref: ProposalRef, operation_id: OpaqueId
    ) -> OperationIntent:
        """Use the workflow stage's original quota reservation."""
        if ctx.workflow_id is None:
            raise _blocked("INVALID_INPUT", "A reserved workflow stage is required.")
        intent = await self._operations.get_operation(ctx.binding, operation_id)
        if (
            intent is None
            or intent.proposal_ref != ref
            or intent.workflow_id != ctx.workflow_id
        ):
            raise _blocked(
                "OPERATION_CONFLICT", "Operation does not match this proposal."
            )
        if intent.state != "not_started":
            return intent
        proposal = await self._current(ctx.binding, ref)
        if proposal.digest != intent.digest:
            raise _blocked("OPERATION_CONFLICT", "Prepared proposal content changed.")
        return await self._execute(ctx, proposal, intent)

    async def _execute(
        self, ctx: RequestContext, proposal: PlaylistProposal, intent: OperationIntent
    ) -> OperationIntent:
        try:
            grant = await self._approval.request_grant(
                ctx, proposal, intent.operation_id
            )
        except ApprovalRejected:
            return await self._save(intent, state="rejected")
        intent = self._approval.consume_for_claim(
            grant,
            proposal,
            intent.operation_id,
            lambda consume: self._operations.claim_approved_creation(
                intent, proposal, consume
            ),
        )
        try:
            await self._revalidate(ctx, proposal)
        except ContractError:
            return await self._save(intent, state="failed_preflight")
        except BaseException:
            with CancelScope(shield=True):
                await self._save(intent, state="failed_preflight")
            raise
        return await self._dispatch(ctx, proposal, intent)

    async def _current(
        self, binding: AccountBinding, ref: ProposalRef
    ) -> PlaylistProposal:
        if binding.mode != "fixture":
            raise _blocked("POLICY_BLOCKED", "Live playlist creation is disabled.")
        current = await self._proposals.get_current_proposal(
            binding, ref.proposal_id, now=self._clock.now()
        )
        if (
            not isinstance(current, PlaylistProposal)
            or current.ref != ref
            or current.state != "proposed"
            or current.digest != proposal_digest(current)
        ):
            raise _blocked(
                "PROPOSAL_CHANGED", "Use the current exact playlist preview."
            )
        return current

    async def _revalidate(
        self, ctx: RequestContext, proposal: PlaylistProposal
    ) -> None:
        channels = await self._reads.get_my_channels(ctx)
        if (
            len(channels) != 1
            or channels[0].channel_id != ctx.binding.channel_id
            or channels[0].title != proposal.destination_channel_title
        ):
            raise _blocked("ACCOUNT_MISMATCH", "The destination channel changed.")
        batch = await self._reads.get_videos(
            ctx, tuple(item.video_id for item in proposal.items)
        )
        for item in proposal.items:
            video = batch.videos.get(item.video_id)
            if (
                video is None
                or video.availability != "available"
                or video.live_status != "recorded"
                or video.duration_seconds != item.duration_seconds
                or video.language_evidence != "audio"
                or video.title != item.title
                or video.default_audio_language is None
                or normalize_language_tag(video.default_audio_language)
                != item.audio_language
            ):
                raise _blocked(
                    "PROPOSAL_CHANGED",
                    "A video's availability, duration, or audio changed.",
                )
        await self._current(ctx.binding, proposal.ref)

    async def _save(
        self, intent: OperationIntent, **changes: object
    ) -> OperationIntent:
        return await self._operations.update_operation(
            intent.model_copy(update={**changes, "updated_at": self._clock.now()})
        )

    def _authority(
        self,
        ctx: RequestContext,
        proposal: PlaylistProposal,
        intent: OperationIntent,
        endpoint: WriteEndpoint,
        params: dict[str, str],
        body: dict[str, object],
    ) -> ApprovedWriteContext:
        return ApprovedWriteContext(
            operation_id=intent.operation_id,
            reservation_id=ctx.reservation_id,
            binding=ctx.binding,
            proposal=proposal.ref,
            proposal_digest=proposal.digest,
            request_digest=compute_write_request_digest(
                endpoint, params=params, json_body=body
            ),
        )

    async def _dispatch(
        self,
        ctx: RequestContext,
        proposal: PlaylistProposal,
        intent: OperationIntent,
    ) -> OperationIntent:
        step = WriteStep(
            endpoint="playlists.insert",
            planned_cost=self._profile.costs["playlists.insert"],
        )
        intent = await self._save(intent, state="creating", write_steps=(step,))
        try:
            created = await self._writes.create_playlist(
                ctx,
                self._authority(
                    ctx,
                    proposal,
                    intent,
                    step.endpoint,
                    CREATE_PARAMS,
                    playlist_request(proposal.body),
                ),
                proposal.body,
            )
        except ContractError as error:
            return await self._failed_write(intent, step, error)
        except BaseException:
            await self._interrupt(intent, step)
            raise
        playlist_id = created.playlist_id
        intent = await self._save(
            intent,
            playlist_id=playlist_id,
            write_steps=(
                step.model_copy(update={"remote_id": playlist_id, "outcome": "saved"}),
            ),
        )
        item_ids = []
        for position, item in enumerate(proposal.items):
            step = WriteStep(
                endpoint="playlistItems.insert",
                position=position,
                planned_cost=self._profile.costs["playlistItems.insert"],
            )
            intent = await self._save(intent, write_steps=(*intent.write_steps, step))
            try:
                inserted = await self._writes.insert_playlist_item(
                    ctx,
                    self._authority(
                        ctx,
                        proposal,
                        intent,
                        step.endpoint,
                        INSERT_PARAMS,
                        item_request(playlist_id, item.video_id, position),
                    ),
                    playlist_id,
                    item.video_id,
                    position,
                )
            except ContractError as error:
                return await self._failed_write(intent, step, error)
            except BaseException:
                await self._interrupt(intent, step)
                raise
            item_ids.append(inserted.playlist_item_id)
            intent = await self._save(
                intent,
                write_steps=(
                    *intent.write_steps[:-1],
                    step.model_copy(
                        update={
                            "remote_id": inserted.playlist_item_id,
                            "outcome": "saved",
                        }
                    ),
                ),
            )
        try:
            page = await self._reads.list_playlist_items(ctx, playlist_id, 50)
        except ContractError:
            return await self._save(intent, state="verification_pending")
        except BaseException:
            with CancelScope(shield=True):
                await self._save(intent, state="verification_pending")
            raise
        expected = [
            (item_id, item.video_id, index)
            for index, (item_id, item) in enumerate(
                zip(item_ids, proposal.items, strict=True)
            )
        ]
        observed = [
            (item.playlist_item_id, item.video_id, item.position) for item in page.items
        ]
        verified = (
            page.next_page_token is None
            and page.omitted == 0
            and observed == expected
            and all(item.playlist_id == playlist_id for item in page.items)
        )
        return await self._save(
            intent, state="completed" if verified else "verification_pending"
        )

    async def _failed_write(
        self,
        intent: OperationIntent,
        step: WriteStep,
        error: ContractError,
    ) -> OperationIntent:
        unknown = error.detail.code == "OPERATION_UNKNOWN"
        return await self._save(
            intent,
            state="unknown"
            if unknown
            else "partial"
            if intent.playlist_id
            else "failed",
            write_steps=(
                *intent.write_steps[:-1],
                step.model_copy(
                    update={"outcome": "unknown" if unknown else "refused"}
                ),
            ),
        )

    async def _interrupt(self, intent: OperationIntent, step: WriteStep) -> None:
        with CancelScope(shield=True):
            await self._save(
                intent,
                state="unknown",
                write_steps=(
                    *intent.write_steps[:-1],
                    step.model_copy(update={"outcome": "unknown"}),
                ),
            )
