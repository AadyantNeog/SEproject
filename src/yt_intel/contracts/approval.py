from dataclasses import dataclass
from typing import Literal, Protocol

from .common import AccountBinding, Digest, OpaqueId, UtcDateTime
from .proposals import PlaylistProposal, ProposalRef, ResumeProposal
from .workflow import RequestContext

type ApprovableProposal = PlaylistProposal | ResumeProposal


@dataclass(frozen=True, slots=True, kw_only=True)
class HumanDecision:
    challenge_ref: OpaqueId
    response_ref: OpaqueId
    operation_id: OpaqueId
    proposal: ProposalRef
    proposal_digest: Digest
    binding: AccountBinding
    decision: Literal["approve", "reject"]
    observed_at: UtcDateTime


@dataclass(frozen=True, slots=True, kw_only=True)
class ApprovalGrant:
    grant_id: OpaqueId
    operation_id: OpaqueId
    proposal: ProposalRef
    proposal_digest: Digest
    binding: AccountBinding
    created_at: UtcDateTime
    expires_at: UtcDateTime
    consumed_at: UtcDateTime | None = None
    source: Literal["native-human"] = "native-human"


@dataclass(frozen=True, slots=True, kw_only=True)
class ApprovedWriteContext:
    """Internal context for one exact request after atomic grant consumption."""

    operation_id: OpaqueId
    reservation_id: OpaqueId
    binding: AccountBinding
    proposal: ProposalRef
    proposal_digest: Digest
    request_digest: Digest


class ApprovalAdapter(Protocol):
    async def request_decision(
        self,
        ctx: RequestContext,
        proposal: ApprovableProposal,
        operation_id: OpaqueId,
        challenge_ref: OpaqueId,
    ) -> HumanDecision: ...


class ApprovalGrantStore(Protocol):
    """Process-private storage for grants awaiting one atomic consumption."""

    def issue(self, grant: ApprovalGrant) -> None: ...

    def consume(
        self,
        *,
        grant_id: OpaqueId,
        operation_id: OpaqueId,
        proposal: ProposalRef,
        proposal_digest: Digest,
        binding: AccountBinding,
        now: UtcDateTime,
    ) -> ApprovalGrant: ...
