from collections.abc import Callable
from secrets import token_urlsafe
from typing import Protocol

from yt_intel.contracts.approval import (
    ApprovableProposal,
    ApprovalAdapter,
    ApprovalGrant,
    ApprovalGrantStore,
)
from yt_intel.contracts.common import AccountBinding, OpaqueId, UtcDateTime
from yt_intel.contracts.workflow import Clock, RequestContext
from yt_intel.infrastructure.clock import SystemClock

from .grants import MAX_GRANT_LIFETIME, InvalidGrant, new_grant_id


class ApprovalUnavailable(RuntimeError):
    """The native helper could not provide a trustworthy response."""


class ApprovalRejected(RuntimeError):
    """The person rejected the exact proposal or closed the dialog."""


class CurrentProposalSource(Protocol):
    async def get_current_proposal(
        self, binding: AccountBinding, proposal_id: OpaqueId, *, now: UtcDateTime
    ) -> ApprovableProposal | None: ...


class ApprovalService:
    def __init__(
        self,
        adapter: ApprovalAdapter,
        grants: ApprovalGrantStore,
        proposals: CurrentProposalSource,
        clock: Clock | None = None,
    ) -> None:
        self._adapter = adapter
        self._grants = grants
        self._proposals = proposals
        self._clock = clock or SystemClock()

    async def request_grant(
        self,
        ctx: RequestContext,
        proposal: ApprovableProposal,
        operation_id: OpaqueId,
    ) -> ApprovalGrant:
        now = self._clock.now()
        if (
            ctx.binding != proposal.binding
            or proposal.state != "proposed"
            or now >= proposal.expires_at
            or now >= ctx.deadline
            or ctx.cancellation.is_cancelled()
        ):
            raise ApprovalUnavailable(
                "proposal or approval request is no longer current"
            )
        await self._require_current(proposal)
        challenge = token_urlsafe(32)
        decision = await self._adapter.request_decision(
            ctx, proposal, operation_id, challenge
        )
        observed = self._clock.now()
        if (
            decision.challenge_ref != challenge
            or decision.operation_id != operation_id
            or decision.proposal != proposal.ref
            or decision.proposal_digest != proposal.digest
            or decision.binding != proposal.binding
            or decision.observed_at < now
            or decision.observed_at > observed
            or observed >= proposal.expires_at
            or observed >= ctx.deadline
            or ctx.cancellation.is_cancelled()
        ):
            raise ApprovalUnavailable(
                "native helper response is stale or does not match"
            )
        if decision.decision != "approve":
            raise ApprovalRejected("native approval was rejected or dismissed")
        await self._require_current(proposal)
        issued_at = self._clock.now()
        if issued_at >= ctx.deadline or ctx.cancellation.is_cancelled():
            raise ApprovalUnavailable("approval request is no longer current")
        expiry = min(now + MAX_GRANT_LIFETIME, proposal.expires_at)
        grant = ApprovalGrant(
            grant_id=new_grant_id(),
            operation_id=operation_id,
            proposal=proposal.ref,
            proposal_digest=proposal.digest,
            binding=proposal.binding,
            created_at=issued_at,
            expires_at=expiry,
        )
        if grant.expires_at <= issued_at:
            raise ApprovalUnavailable(
                "proposal expired before approval could be granted"
            )
        self._grants.issue(grant)
        return grant

    async def _require_current(self, proposal: ApprovableProposal) -> None:
        if not await self._is_current(proposal):
            raise ApprovalUnavailable("proposal changed; open a new preview")

    async def _is_current(self, proposal: ApprovableProposal) -> bool:
        current = await self._proposals.get_current_proposal(
            proposal.binding, proposal.ref.proposal_id, now=self._clock.now()
        )
        return (
            current is not None and current.state == "proposed" and current == proposal
        )

    async def consume(
        self, grant: ApprovalGrant, proposal: ApprovableProposal, operation_id: OpaqueId
    ) -> ApprovalGrant:
        if not await self._is_current(proposal):
            raise InvalidGrant("proposal changed; open a new preview")
        return self._consume(grant, proposal, operation_id)

    def consume_for_claim[T](
        self,
        grant: ApprovalGrant,
        proposal: ApprovableProposal,
        operation_id: OpaqueId,
        claim: Callable[[Callable[[], ApprovalGrant]], T],
    ) -> T:
        """The claim transaction must verify the current proposal before consuming."""
        return claim(lambda: self._consume(grant, proposal, operation_id))

    def _consume(
        self, grant: ApprovalGrant, proposal: ApprovableProposal, operation_id: OpaqueId
    ) -> ApprovalGrant:
        return self._grants.consume(
            grant_id=grant.grant_id,
            operation_id=operation_id,
            proposal=proposal.ref,
            proposal_digest=proposal.digest,
            binding=proposal.binding,
            now=self._clock.now(),
        )
