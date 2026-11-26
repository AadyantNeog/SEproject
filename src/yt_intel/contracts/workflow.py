from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal, Protocol, Self, runtime_checkable

from pydantic import Field, model_validator

from .common import (
    AccountBinding,
    Contract,
    FrozenMap,
    Label,
    NonNegative,
    OpaqueId,
    Positive,
    UtcDateTime,
    VersionedContract,
)

type Endpoint = Literal[
    "videos.list",
    "channels.list",
    "search.list",
    "subscriptions.list",
    "playlists.list",
    "playlistItems.list",
    "videoCategories.list",
    "playlists.insert",
    "playlistItems.insert",
]
type BucketVector = FrozenMap[OpaqueId, NonNegative]
type AttemptCount = Annotated[int, Field(ge=1, le=3)]


class CallCeiling(Contract):
    calls: Positive
    attempts_per_call: AttemptCount


class WorkflowPlan(VersionedContract):
    plan_id: OpaqueId
    binding: AccountBinding
    project_id: OpaqueId
    quota_profile_id: OpaqueId
    endpoint_ceilings: FrozenMap[Endpoint, CallCeiling]
    buckets: BucketVector
    candidate_cap: NonNegative
    page_cap: NonNegative
    sample_cap: NonNegative
    deadline: UtcDateTime
    cancellation_policy: Label
    reconciliation_allowance: FrozenMap[Endpoint, NonNegative]

    @model_validator(mode="after")
    def check_attempts(self) -> Self:
        write_endpoints: tuple[Endpoint, ...] = (
            "playlists.insert",
            "playlistItems.insert",
        )
        for endpoint in write_endpoints:
            ceiling = self.endpoint_ceilings.get(endpoint)
            if ceiling is not None and ceiling.attempts_per_call != 1:
                raise ValueError("write calls have exactly one attempt")
            if self.reconciliation_allowance.get(endpoint, 0):
                raise ValueError("reconciliation allowance is for reads")
        return self


class QuotaReservation(Contract):
    reservation_id: OpaqueId
    plan_id: OpaqueId
    project_id: OpaqueId
    quota_profile_id: OpaqueId
    reset_at: UtcDateTime
    reserved: BucketVector


class WorkflowSession(VersionedContract):
    workflow_id: OpaqueId
    kind: Label
    stage: Label
    plan: WorkflowPlan
    reservation_id: OpaqueId
    next_stages: tuple[Label, ...]
    spent_attempts: FrozenMap[Endpoint, NonNegative]
    remaining_attempts: FrozenMap[Endpoint, NonNegative]
    idle_expires_at: UtcDateTime


class CancellationToken(Protocol):
    def is_cancelled(self) -> bool: ...
    async def wait(self) -> None: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


@dataclass(frozen=True, slots=True, kw_only=True)
class RequestContext:
    request_id: OpaqueId
    binding: AccountBinding
    reservation_id: OpaqueId
    deadline: UtcDateTime
    cancellation: CancellationToken
    workflow_id: OpaqueId | None = None


class QuotaLedger(Protocol):
    async def reserve(self, plan: WorkflowPlan) -> QuotaReservation: ...
    async def debit_attempt(
        self, ctx: RequestContext, endpoint: Endpoint, attempt_id: OpaqueId
    ) -> None: ...
    async def release(self, reservation_id: OpaqueId) -> None: ...


@runtime_checkable
class CallQuotaLedger(QuotaLedger, Protocol):
    """Quota accounting for logical calls and upstream exhaustion."""

    async def debit_call_attempt(
        self,
        ctx: RequestContext,
        endpoint: Endpoint,
        attempt_id: OpaqueId,
        *,
        call_id: OpaqueId,
        attempt_number: int,
    ) -> int: ...

    async def mark_exhausted(
        self, ctx: RequestContext, endpoint: Endpoint, attempt_id: OpaqueId
    ) -> None: ...
