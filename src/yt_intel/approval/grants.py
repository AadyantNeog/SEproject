from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from secrets import token_urlsafe
from threading import Lock

from yt_intel.contracts.approval import ApprovalGrant
from yt_intel.contracts.common import AccountBinding, Digest, OpaqueId, UtcDateTime
from yt_intel.contracts.proposals import ProposalRef

MAX_GRANT_LIFETIME = timedelta(minutes=10)


class InvalidGrant(RuntimeError):
    """The grant is absent, stale, expired, mismatched, or already consumed."""


class InMemoryGrantStore:
    """Atomic, process-local grants; a restart invalidates every unconsumed grant."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._grants: dict[OpaqueId, ApprovalGrant] = {}
        self._operation_grants: dict[OpaqueId, OpaqueId] = {}

    def issue(self, grant: ApprovalGrant) -> None:
        lifetime = grant.expires_at - grant.created_at
        if not timedelta(0) < lifetime <= MAX_GRANT_LIFETIME:
            raise ValueError(
                "grant lifetime must be positive and no more than ten minutes"
            )
        if grant.consumed_at is not None:
            raise ValueError("a consumed grant cannot be issued")
        with self._lock:
            previous = self._operation_grants.get(grant.operation_id)
            if previous is not None:
                self._grants.pop(previous, None)
            self._grants[grant.grant_id] = grant
            self._operation_grants[grant.operation_id] = grant.grant_id

    def consume(
        self,
        *,
        grant_id: OpaqueId,
        operation_id: OpaqueId,
        proposal: ProposalRef,
        proposal_digest: Digest,
        binding: AccountBinding,
        now: UtcDateTime,
    ) -> ApprovalGrant:
        with self._lock:
            grant = self._grants.get(grant_id)
            if (
                grant is None
                or grant.consumed_at is not None
                or grant.operation_id != operation_id
                or grant.proposal != proposal
                or grant.proposal_digest != proposal_digest
                or grant.binding != binding
                or now >= grant.expires_at
                or now < grant.created_at
                or self._operation_grants.get(operation_id) != grant_id
            ):
                raise InvalidGrant(
                    "approval grant is invalid, stale, or already consumed"
                )
            consumed = replace(grant, consumed_at=now)
            self._grants[grant_id] = consumed
            self._operation_grants.pop(operation_id, None)
            return consumed


def new_grant_id() -> OpaqueId:
    return token_urlsafe(32)
