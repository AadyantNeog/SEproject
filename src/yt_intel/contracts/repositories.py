from typing import Protocol

from .approval import ApprovableProposal
from .common import AccountBinding, Digest, OpaqueId, UtcDateTime
from .models import LibrarySnapshot
from .proposals import ProposalRef


class AccountDataRepository(Protocol):
    """Account deletion leaves project-level quota accounting intact."""

    async def delete_account(self, binding: AccountBinding) -> None: ...
    async def purge_expired(self, now: UtcDateTime) -> None: ...


class SnapshotRepository(Protocol):
    async def save_snapshot(self, snapshot: LibrarySnapshot) -> None: ...
    async def get_snapshot(
        self, binding: AccountBinding, snapshot_id: OpaqueId, *, now: UtcDateTime
    ) -> LibrarySnapshot | None: ...


class ProposalRepository(Protocol):
    async def save_proposal(self, proposal: ApprovableProposal) -> None: ...
    async def get_proposal(
        self, binding: AccountBinding, ref: ProposalRef, *, now: UtcDateTime
    ) -> ApprovableProposal | None: ...


class OperationRepository[T](Protocol):
    async def get_operation(
        self, binding: AccountBinding, operation_id: OpaqueId
    ) -> T | None: ...
    async def claim_operation(
        self, binding: AccountBinding, operation_id: OpaqueId, digest: Digest
    ) -> T: ...


class CacheRepository(Protocol):
    async def get(
        self, binding: AccountBinding, key: Digest, *, now: UtcDateTime
    ) -> bytes | None: ...
    async def put(
        self,
        binding: AccountBinding,
        key: Digest,
        value: bytes,
        *,
        expires_at: UtcDateTime,
        retained_until: UtcDateTime,
    ) -> None: ...
