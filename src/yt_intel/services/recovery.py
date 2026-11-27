import json
from datetime import timedelta
from hashlib import sha256
from typing import Literal
from uuid import uuid4

from anyio import CancelScope

from yt_intel.approval.service import ApprovalRejected, ApprovalService
from yt_intel.contracts.approval import ApprovedWriteContext
from yt_intel.contracts.common import AccountBinding, Contract, OpaqueId, PlaylistId
from yt_intel.contracts.errors import ContractError, ErrorCode, ErrorDetail
from yt_intel.contracts.proposals import (
    PROPOSAL_LIFETIME,
    PlaylistProposal,
    ProposalRef,
    ResumeProposal,
    VerifiedPlaylistItem,
)
from yt_intel.contracts.provider import YouTubeReadProvider, YouTubeWriteProvider
from yt_intel.contracts.workflow import (
    CallCeiling,
    CancellationToken,
    Clock,
    Endpoint,
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
    OperationResultExpired,
    SqliteOperationRepository,
    SqliteProposalRepository,
    WriteStep,
)
from yt_intel.providers.youtube_writes import INSERT_PARAMS, item_request

_RECOVERY_DEADLINE = timedelta(seconds=30)
_WRITE_LEASE = timedelta(minutes=5)


class RecoveryResult(Contract):
    operation_id: OpaqueId
    state: Literal["manual_required", "complete", "resume_ready"]
    playlist_id: PlaylistId | None = None
    verified_items: tuple[VerifiedPlaylistItem, ...] = ()
    preview: ResumeProposal | None = None
    guidance: str


def _blocked(code: ErrorCode, message: str) -> ContractError:
    return ContractError(
        ErrorDetail(
            code=code,
            message=message,
            retryable=False,
            safe_next_action="Inspect the recorded operation and playlist before continuing.",
        )
    )


def resume_digest(proposal: ResumeProposal) -> str:
    fields = proposal.model_dump(mode="json", exclude={"digest", "state"})
    canonical = json.dumps(
        {"authority": "resume-v1", "proposal": fields},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return sha256(canonical.encode()).hexdigest()


class PlaylistRecoveryService:
    """Verify a saved playlist's exact ordered prefix without issuing writes."""

    def __init__(
        self,
        proposals: SqliteProposalRepository,
        operations: SqliteOperationRepository,
        ledger: QuotaLedger,
        profile: QuotaProfile,
        provider: YouTubeReadProvider,
        clock: Clock | None = None,
    ) -> None:
        self._proposals = proposals
        self._operations = operations
        self._ledger = ledger
        self._profile = profile
        self._provider = provider
        self._clock = clock or SystemClock()

    async def reconcile(
        self,
        binding: AccountBinding,
        operation_id: OpaqueId,
        *,
        project_id: OpaqueId,
        cancellation: CancellationToken,
        remote_playlist_id: PlaylistId | None = None,
    ) -> RecoveryResult:
        if binding.mode != "fixture":
            raise _blocked("POLICY_BLOCKED", "Live playlist recovery is disabled.")
        try:
            intent = await self._operations.get_recovery_operation(
                binding, operation_id
            )
        except OperationResultExpired as error:
            raise _blocked("OPERATION_RESULT_EXPIRED", str(error)) from error
        if intent is None:
            raise _blocked(
                "CONTENT_UNAVAILABLE",
                "Operation is unavailable or its detail has expired.",
            )
        if intent.state == "completed":
            return RecoveryResult(
                operation_id=operation_id,
                state="complete",
                playlist_id=intent.playlist_id,
                guidance="The recorded operation completed. No new requests are needed.",
            )
        if intent.state not in {
            "creating",
            "partial",
            "unknown",
            "verification_pending",
        }:
            raise _blocked(
                "OPERATION_CONFLICT",
                "This operation has no interrupted writes to recover.",
            )
        now = self._clock.now()
        if intent.state == "creating" and now < intent.updated_at + _WRITE_LEASE:
            raise _blocked("OPERATION_CONFLICT", "The write may still be running.")
        if remote_playlist_id is not None and intent.playlist_id not in {
            None,
            remote_playlist_id,
        }:
            raise _blocked(
                "OPERATION_CONFLICT",
                "The supplied ID differs from the recorded playlist.",
            )
        playlist_id = intent.playlist_id or remote_playlist_id
        if playlist_id is None:
            return RecoveryResult(
                operation_id=operation_id,
                state="manual_required",
                guidance="The create outcome is unknown. Identify the exact playlist manually before requesting verification.",
            )
        if intent.proposal_ref is None:
            raise _blocked(
                "OPERATION_RESULT_EXPIRED",
                "Original creation authority is unavailable.",
            )
        original = await self._proposals.get_retained_creation(
            binding, intent.proposal_ref, intent.digest, now=now
        )
        if original is None or proposal_digest(original) != intent.digest:
            raise _blocked(
                "OPERATION_RESULT_EXPIRED",
                "Original creation authority is unavailable.",
            )
        plan = WorkflowPlan(
            plan_id=uuid4().hex,
            project_id=project_id,
            binding=binding,
            quota_profile_id=self._profile.profile_id,
            endpoint_ceilings={
                endpoint: CallCeiling(calls=1, attempts_per_call=3)
                for endpoint in (
                    "channels.list",
                    "playlists.list",
                    "playlistItems.list",
                )
            },
            buckets={},
            candidate_cap=0,
            page_cap=1,
            sample_cap=50,
            deadline=now + _RECOVERY_DEADLINE,
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
            prefix = await self._verified_prefix(ctx, intent, original, playlist_id)
        finally:
            with CancelScope(shield=True):
                await self._ledger.release(reservation.reservation_id)
        if intent.playlist_id is None:
            return RecoveryResult(
                operation_id=operation_id,
                playlist_id=playlist_id,
                state="manual_required",
                verified_items=prefix,
                guidance="The supplied playlist is owned and its contents were checked. The original create could not be tied to it, so it cannot be resumed.",
            )
        if len(prefix) == len(original.items):
            await self._save(
                intent,
                state="completed",
                resume_ref=None,
                write_steps=self._reconciled_steps(intent, prefix),
            )
            return RecoveryResult(
                operation_id=operation_id,
                playlist_id=playlist_id,
                state="complete",
                verified_items=prefix,
                guidance="The exact playlist was verified. No more writes are needed.",
            )
        preview = self._preview(original, intent, playlist_id, prefix)
        await self._proposals.save_proposal(preview)
        await self._save(
            intent,
            state="partial",
            resume_ref=preview.ref,
            write_steps=self._reconciled_steps(intent, prefix),
        )
        return RecoveryResult(
            operation_id=operation_id,
            playlist_id=playlist_id,
            state="resume_ready",
            verified_items=prefix,
            preview=preview,
            guidance="Review the exact missing items. Resuming requires fresh native approval.",
        )

    async def _verified_prefix(
        self,
        ctx: RequestContext,
        intent: OperationIntent,
        original: PlaylistProposal,
        playlist_id: PlaylistId,
    ) -> tuple[VerifiedPlaylistItem, ...]:
        channels = await self._provider.get_my_channels(ctx)
        if len(channels) != 1 or channels[0].channel_id != ctx.binding.channel_id:
            raise _blocked(
                "ACCOUNT_MISMATCH", "Recovery account could not be verified."
            )
        owned = await self._provider.list_my_playlists(ctx, 50)
        destination = next(
            (
                item
                for item in owned.items
                if item.playlist_id == playlist_id
                and item.channel_id == ctx.binding.channel_id
                and item.title == original.body.title
            ),
            None,
        )
        if destination is None or destination.privacy is None:
            raise _blocked(
                "VERIFICATION_PENDING",
                "Exact playlist ownership, title and privacy could not be verified.",
            )
        if destination.privacy != original.body.privacy:
            raise _blocked(
                "PROPOSAL_CHANGED",
                "Playlist privacy differs from the approved preview.",
            )
        page = await self._provider.list_playlist_items(ctx, playlist_id, 50)
        if (
            page.next_page_token is not None
            or page.omitted
            or page.inaccessible
            or len(page.items) > len(original.items)
        ):
            raise _blocked(
                "VERIFICATION_PENDING",
                "Playlist contents are incomplete or differ from the preview.",
            )
        attempts = {
            step.position: step
            for step in intent.write_steps
            if step.endpoint == "playlistItems.insert"
        }
        verified = []
        for position, entry in enumerate(page.items):
            expected = original.items[position]
            recorded = attempts.get(position)
            if (
                entry.position != position
                or entry.video_id != expected.video_id
                or entry.playlist_id != playlist_id
                or entry.accessibility != "available"
                or recorded is None
                or recorded.outcome == "refused"
                or (
                    recorded.outcome == "saved"
                    and recorded.remote_id != entry.playlist_item_id
                )
            ):
                raise _blocked(
                    "PROPOSAL_CHANGED",
                    "Playlist contents differ from the recorded write prefix.",
                )
            verified.append(
                VerifiedPlaylistItem(
                    playlist_item_id=entry.playlist_item_id, item=expected
                )
            )
        if len({entry.playlist_item_id for entry in verified}) != len(verified) or any(
            position is not None
            and position >= len(verified)
            and step.outcome == "saved"
            for position, step in attempts.items()
        ):
            raise _blocked(
                "PROPOSAL_CHANGED",
                "A confirmed item is missing or repeated in the playlist.",
            )
        return tuple(verified)

    def _preview(
        self,
        original: PlaylistProposal,
        intent: OperationIntent,
        playlist_id: PlaylistId,
        prefix: tuple[VerifiedPlaylistItem, ...],
    ) -> ResumeProposal:
        now = self._clock.now()
        result = ResumeProposal(
            ref=ProposalRef(proposal_id=uuid4().hex, version=1),
            binding=original.binding,
            destination_channel_title=original.destination_channel_title,
            body=original.body,
            constraints=original.constraints,
            digest="0" * 64,
            created_at=now,
            expires_at=now + PROPOSAL_LIFETIME,
            original_operation_id=intent.operation_id,
            original_proposal=original.ref,
            original_digest=original.digest,
            remote_playlist_id=playlist_id,
            verified_at=now,
            verified_prefix=prefix,
            missing_suffix=original.items[len(prefix) :],
        )
        return result.model_copy(update={"digest": resume_digest(result)})

    async def _save(
        self, intent: OperationIntent, **changes: object
    ) -> OperationIntent:
        return await self._operations.update_operation(
            intent.model_copy(update={**changes, "updated_at": self._clock.now()})
        )

    @staticmethod
    def _reconciled_steps(
        intent: OperationIntent,
        prefix: tuple[VerifiedPlaylistItem, ...],
    ) -> tuple[WriteStep, ...]:
        steps = list(intent.write_steps)
        by_position = {
            step.position: index
            for index, step in enumerate(steps)
            if step.endpoint == "playlistItems.insert"
        }
        for position, verified in enumerate(prefix):
            index = by_position[position]
            steps[index] = steps[index].model_copy(
                update={
                    "outcome": "saved",
                    "remote_id": verified.playlist_item_id,
                }
            )
        return tuple(steps)

    async def resume(
        self,
        binding: AccountBinding,
        operation_id: OpaqueId,
        ref: ProposalRef | None,
        *,
        project_id: OpaqueId,
        cancellation: CancellationToken,
        approval: ApprovalService,
        writes: YouTubeWriteProvider,
    ) -> OperationIntent:
        if binding.mode != "fixture":
            raise _blocked("POLICY_BLOCKED", "Live playlist recovery is disabled.")
        try:
            intent = await self._operations.get_recovery_operation(
                binding, operation_id
            )
        except OperationResultExpired as error:
            raise _blocked("OPERATION_RESULT_EXPIRED", str(error)) from error
        if intent is None:
            raise _blocked(
                "CONTENT_UNAVAILABLE",
                "Operation is unavailable or its detail has expired.",
            )
        if ref is None:
            ref = intent.resume_ref or intent.last_resume_ref
        if (
            ref is not None
            and intent.last_resume_ref == ref
            and intent.state
            in {
                "completed",
                "partial",
                "unknown",
                "verification_pending",
            }
        ):
            return intent
        if (
            ref is None
            or intent.resume_ref != ref
            or intent.state != "partial"
            or intent.playlist_id is None
        ):
            raise _blocked(
                "PROPOSAL_CHANGED", "Reconcile and review the current resume preview."
            )
        now = self._clock.now()
        proposal = await self._proposals.get_current_proposal(
            binding, ref.proposal_id, now=now
        )
        if (
            not isinstance(proposal, ResumeProposal)
            or proposal.ref != ref
            or proposal.original_operation_id != operation_id
            or proposal.original_digest != intent.digest
            or proposal.remote_playlist_id != intent.playlist_id
            or proposal.state != "proposed"
            or proposal.digest != resume_digest(proposal)
        ):
            raise _blocked(
                "PROPOSAL_CHANGED", "The resume preview is stale or unavailable."
            )
        original = await self._proposals.get_retained_creation(
            binding, proposal.original_proposal, intent.digest, now=now
        )
        if original is None or proposal_digest(original) != intent.digest:
            raise _blocked(
                "OPERATION_RESULT_EXPIRED",
                "Original creation authority is unavailable.",
            )
        if (
            tuple(item.item for item in proposal.verified_prefix)
            + proposal.missing_suffix
            != original.items
        ):
            raise _blocked(
                "PROPOSAL_CHANGED",
                "Resume items do not match the original approved order.",
            )
        ceilings: dict[Endpoint, CallCeiling] = {
            "channels.list": CallCeiling(calls=1, attempts_per_call=3),
            "playlists.list": CallCeiling(calls=1, attempts_per_call=3),
            "playlistItems.list": CallCeiling(calls=2, attempts_per_call=3),
            "videos.list": CallCeiling(calls=1, attempts_per_call=3),
            "playlistItems.insert": CallCeiling(
                calls=len(proposal.missing_suffix), attempts_per_call=1
            ),
        }
        plan = WorkflowPlan(
            plan_id=uuid4().hex,
            project_id=project_id,
            binding=binding,
            quota_profile_id=self._profile.profile_id,
            endpoint_ceilings=ceilings,
            buckets={},
            candidate_cap=len(proposal.missing_suffix),
            page_cap=1,
            sample_cap=50,
            deadline=min(proposal.expires_at, now + _WRITE_LEASE),
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
            try:
                grant = await approval.request_grant(ctx, proposal, operation_id)
            except ApprovalRejected as error:
                await self._save(intent, resume_ref=None)
                raise _blocked(
                    "APPROVAL_REJECTED",
                    "Native resume approval was rejected or dismissed.",
                ) from error
            intent = approval.consume_for_claim(
                grant,
                proposal,
                operation_id,
                lambda consume: self._operations.claim_approved_resume(
                    intent, proposal, consume
                ),
            )
            try:
                prefix = await self._verified_prefix(
                    ctx, intent, original, proposal.remote_playlist_id
                )
                if prefix != proposal.verified_prefix:
                    raise _blocked(
                        "PROPOSAL_CHANGED", "Playlist changed after the resume preview."
                    )
                await self._verify_missing_videos(ctx, proposal)
            except BaseException:
                with CancelScope(shield=True):
                    await self._save(intent, state="partial")
                raise
            return await self._insert_suffix(ctx, intent, proposal, writes)
        finally:
            with CancelScope(shield=True):
                await self._ledger.release(reservation.reservation_id)

    async def _verify_missing_videos(
        self, ctx: RequestContext, proposal: ResumeProposal
    ) -> None:
        batch = await self._provider.get_videos(
            ctx, tuple(item.video_id for item in proposal.missing_suffix)
        )
        for item in proposal.missing_suffix:
            video = batch.videos.get(item.video_id)
            if (
                video is None
                or video.availability != "available"
                or video.live_status != "recorded"
                or video.duration_seconds != item.duration_seconds
                or video.title != item.title
                or video.language_evidence != "audio"
                or video.default_audio_language is None
                or normalize_language_tag(video.default_audio_language)
                != item.audio_language
            ):
                raise _blocked(
                    "PROPOSAL_CHANGED", "A missing video's approval evidence changed."
                )

    async def _insert_suffix(
        self,
        ctx: RequestContext,
        intent: OperationIntent,
        proposal: ResumeProposal,
        writes: YouTubeWriteProvider,
    ) -> OperationIntent:
        playlist = proposal.remote_playlist_id
        expected = [
            (item.playlist_item_id, item.item.video_id)
            for item in proposal.verified_prefix
        ]
        for position, item in enumerate(proposal.missing_suffix, start=len(expected)):
            step = WriteStep(
                endpoint="playlistItems.insert",
                position=position,
                planned_cost=self._profile.costs["playlistItems.insert"],
            )
            intent = await self._save(intent, write_steps=(*intent.write_steps, step))
            authority = ApprovedWriteContext(
                operation_id=intent.operation_id,
                reservation_id=ctx.reservation_id,
                binding=ctx.binding,
                proposal=proposal.ref,
                proposal_digest=proposal.digest,
                request_digest=compute_write_request_digest(
                    "playlistItems.insert",
                    params=INSERT_PARAMS,
                    json_body=item_request(playlist, item.video_id, position),
                ),
            )
            try:
                inserted = await writes.insert_playlist_item(
                    ctx, authority, playlist, item.video_id, position
                )
            except ContractError as error:
                unknown = error.detail.code == "OPERATION_UNKNOWN"
                return await self._save(
                    intent,
                    state="unknown" if unknown else "partial",
                    write_steps=(
                        *intent.write_steps[:-1],
                        step.model_copy(
                            update={
                                "outcome": "unknown" if unknown else "refused",
                            }
                        ),
                    ),
                )
            except BaseException:
                with CancelScope(shield=True):
                    await self._save(
                        intent,
                        state="unknown",
                        write_steps=(
                            *intent.write_steps[:-1],
                            step.model_copy(update={"outcome": "unknown"}),
                        ),
                    )
                raise
            expected.append((inserted.playlist_item_id, item.video_id))
            intent = await self._save(
                intent,
                write_steps=(
                    *intent.write_steps[:-1],
                    step.model_copy(
                        update={
                            "outcome": "saved",
                            "remote_id": inserted.playlist_item_id,
                        }
                    ),
                ),
            )
        try:
            page = await self._provider.list_playlist_items(ctx, playlist, 50)
        except ContractError:
            return await self._save(intent, state="verification_pending")
        except BaseException:
            with CancelScope(shield=True):
                await self._save(intent, state="verification_pending")
            raise
        verified = (
            page.next_page_token is None
            and page.omitted == 0
            and page.inaccessible == 0
            and [(entry.playlist_item_id, entry.video_id) for entry in page.items]
            == expected
            and all(
                entry.playlist_id == playlist and entry.position == index
                for index, entry in enumerate(page.items)
            )
        )
        return await self._save(
            intent, state="completed" if verified else "verification_pending"
        )
