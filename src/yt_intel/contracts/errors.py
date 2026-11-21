from typing import Literal, Self

from pydantic import model_validator

from .common import Contract, Label, Mode, OpaqueId, VersionedContract
from .models import Coverage, Warnings

type ErrorCode = Literal[
    "INVALID_INPUT",
    "UNSUPPORTED_IDENTIFIER",
    "CONTENT_UNAVAILABLE",
    "INSUFFICIENT_DATA",
    "CLARIFICATION_REQUIRED",
    "NO_FEASIBLE_PLAYLIST",
    "AUTH_REQUIRED",
    "SCOPE_REQUIRED",
    "AUTH_REVOKED",
    "CHANNEL_REQUIRED",
    "ACCOUNT_MISMATCH",
    "POLICY_BLOCKED",
    "QUOTA_INSUFFICIENT",
    "QUOTA_EXHAUSTED",
    "RATE_LIMITED",
    "WORKFLOW_TIMEOUT",
    "PROVIDER_UNAVAILABLE",
    "APPROVAL_REQUIRED",
    "APPROVAL_REJECTED",
    "APPROVAL_EXPIRED",
    "PROPOSAL_CHANGED",
    "OPERATION_CONFLICT",
    "OPERATION_UNKNOWN",
    "OPERATION_RESULT_EXPIRED",
    "PARTIAL_WRITE",
    "VERIFICATION_PENDING",
    "LOCAL_DELETION_FAILED",
]
type ResultStatus = Literal["ok", "empty", "partial", "blocked", "error", "unknown"]


class ErrorDetail(Contract):
    code: ErrorCode
    message: Label
    retryable: bool
    safe_next_action: Label


class ContractError(Exception):
    """Service/provider failure carrying only information safe for the caller."""

    def __init__(self, detail: ErrorDetail) -> None:
        super().__init__(detail.message)
        self.detail = detail


class QuotaEstimate(Contract):
    estimated: Literal[True] = True
    profile_id: OpaqueId


class ResultEnvelope[T](VersionedContract):
    mode: Mode
    request_id: OpaqueId
    status: ResultStatus
    data: T | None
    warnings: Warnings = ()
    coverage: Coverage | None = None
    error: ErrorDetail | None = None
    quota: QuotaEstimate | None = None

    @model_validator(mode="after")
    def check_status(self) -> Self:
        if self.status in {"blocked", "error", "unknown"} and self.error is None:
            raise ValueError("failed or unknown results require a typed error")
        if self.status == "ok" and self.error is not None:
            raise ValueError("successful results cannot carry an error")
        return self
