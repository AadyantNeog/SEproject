"""Live video-to-playlist workflow and guarded playlist creation.

The only path to a live write is this sequence: `begin_workflow`, then
`get_video`, `find_similar_videos`, `propose_playlist`, `prepare_creation`
and `create_playlist`, all with the same `workflow_id`.

- **Quota up front.** `begin_workflow` reserves the whole worst-case budget
  before the seed is fetched, including 50 item inserts. Every stage spends
  that one reservation.
- **Human approval.** `create_playlist` asks for a decision in the
  server-owned native dialog for the exact stored proposal. The grant is
  bound to the account, the proposal digest and version, and the operation.
  It expires and is used once. No tool argument can mint approval.
- **Guarded writes.** The shared creation service persists intent before
  dispatch, makes one attempt per write and records partial or unknown
  outcomes. It never retries an ambiguous write automatically.
- **Gates.** Every step needs the reviewed D-02 record to be resolved and the
  `youtube.force-ssl` write scope (`yt-intel auth --enable-writes`).

Live recovery, resume and reconciliation are not exposed. An unknown or
partial live result is reported with `get_operation` for a human to
reconcile in YouTube.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from sqlite3 import Error as SqliteError
from typing import Any, Literal
from uuid import uuid4

import anyio
from mcp_types import CallToolResult, TextContent
from pydantic import ValidationError

from yt_intel.approval.grants import InvalidGrant
from yt_intel.approval.service import ApprovalUnavailable
from yt_intel.auth.oauth import YOUTUBE_READONLY_SCOPE, YOUTUBE_WRITE_SCOPE
from yt_intel.contracts.common import AccountBinding, Contract, OpaqueId
from yt_intel.contracts.errors import ContractError, ErrorDetail, ResultEnvelope
from yt_intel.contracts.proposals import PlaylistProposal
from yt_intel.domain.identifiers import parse_video_id
from yt_intel.infrastructure.repositories import (
    OperationConflict,
    OperationResultExpired,
    SqliteOperationRepository,
    StaleOperationUpdate,
)
from yt_intel.presentation.previews import render_proposal
from yt_intel.presentation.results import render_error
from yt_intel.services.creation import PlaylistCreationService

from .execution import (
    _CreateInput,
    _creation_response,
    _failure,
    _OperationInput,
    _PrepareInput,
    _problem,
    _response,
)
from .live_derived import LiveDerivedServices
from .workflows import WorkflowStarted

LIVE_PROJECT_ID = "default-project"
WRITE_SCOPES = (YOUTUBE_READONLY_SCOPE, YOUTUBE_WRITE_SCOPE)
_FINISHED = {
    "completed",
    "rejected",
    "partial",
    "unknown",
    "verification_pending",
    "expired",
    "failed",
    "failed_preflight",
}


class _BeginInput(Contract):
    kind: Literal["video_to_playlist"]
    video: str | None = None


class _NotCancelled:
    def is_cancelled(self) -> bool:
        return False

    async def wait(self) -> None:
        await anyio.sleep_forever()


@dataclass(frozen=True, slots=True)
class LiveWriteServices:
    derived: LiveDerivedServices
    creation: PlaylistCreationService
    operations: SqliteOperationRepository


def _arguments(params: Mapping[str, Any] | None) -> dict[str, Any]:
    return dict((params or {}).get("arguments") or {})


async def write_binding(services: LiveWriteServices) -> AccountBinding:
    """The saved live account, which must hold the write scope."""
    return await services.derived.accounts.require_binding(required_scopes=WRITE_SCOPES)


def _workflow_error(request_id: OpaqueId, problem: ErrorDetail) -> CallToolResult:
    result = ResultEnvelope[WorkflowStarted](
        mode="live", request_id=request_id, status="blocked", data=None, error=problem
    )
    return CallToolResult(
        is_error=True,
        structured_content=result.model_dump(),
        content=[TextContent(type="text", text=render_error(problem, mode="live"))],
    )


async def begin(
    services: LiveWriteServices, params: Mapping[str, Any] | None
) -> CallToolResult:
    request_id = uuid4().hex
    try:
        try:
            inputs = _BeginInput.model_validate(_arguments(params))
        except ValidationError:
            raise ContractError(
                ErrorDetail(
                    code="INVALID_INPUT",
                    message="Invalid workflow input.",
                    retryable=False,
                    safe_next_action="Use video_to_playlist and an optional YouTube video.",
                )
            ) from None
        seed = parse_video_id(inputs.video) if inputs.video is not None else None
        binding = await write_binding(services)
        session = await services.derived.workflows.begin_video_to_playlist(
            binding, LIVE_PROJECT_ID, seed
        )
    except ContractError as error:
        return _workflow_error(request_id, error.detail)
    except (OSError, SqliteError):
        return _workflow_error(
            request_id,
            ErrorDetail(
                code="PROVIDER_UNAVAILABLE",
                message="The live quota ledger could not be accessed.",
                retryable=False,
                safe_next_action="Check access to the live database and try again.",
            ),
        )
    result = ResultEnvelope[WorkflowStarted](
        mode="live",
        request_id=request_id,
        status="ok",
        data=WorkflowStarted(
            workflow_id=session.workflow_id,
            reserved=session.plan.buckets,
            expires_at=session.idle_expires_at,
        ),
    )
    reserved = ", ".join(
        f"{bucket} {units}" for bucket, units in session.plan.buckets.items()
    )
    return CallToolResult(
        structured_content=result.model_dump(),
        content=[
            TextContent(
                type="text",
                text=(
                    f"Mode: live\nReserved workflow {session.workflow_id} "
                    f"({reserved} units) until {session.idle_expires_at.isoformat()}.\n"
                    "Next: get_video, find_similar_videos and propose_playlist with "
                    "this workflow_id."
                ),
            )
        ],
    )


async def prepare(
    services: LiveWriteServices, params: Mapping[str, Any] | None
) -> CallToolResult:
    request_id = uuid4().hex
    try:
        inputs = _PrepareInput.model_validate(_arguments(params))
        ref = inputs.reference()
        binding = await write_binding(services)
        async with services.derived.workflows.stage(
            inputs.workflow_id,
            "prepare_creation",
            binding=binding,
            request_id=request_id,
            cancellation=_NotCancelled(),
            proposal_ref=ref,
        ) as access:
            intent = await services.creation.prepare(
                binding, ref, workflow_id=access.context.workflow_id
            )
            proposal = await services.derived.proposals.get_proposal(
                binding, ref, now=datetime.now(UTC)
            )
            if not isinstance(proposal, PlaylistProposal):
                raise ContractError(
                    _problem("PROPOSAL_CHANGED", "The exact preview is unavailable.")
                )
            access.operation_id = intent.operation_id
    except (
        ValidationError,
        ContractError,
        OperationConflict,
        StaleOperationUpdate,
    ) as error:
        return _failure(request_id, error, mode="live")
    text = (
        f"{render_proposal(proposal)}\n\nPrepared operation {intent.operation_id}. "
        "Next: create_playlist opens a native approval dialog on this computer. "
        "Nothing is written unless you approve this exact preview there."
    )
    return _response(request_id, "ok", intent=intent, text=text, mode="live")


async def create(
    services: LiveWriteServices, params: Mapping[str, Any] | None
) -> CallToolResult:
    request_id = uuid4().hex
    try:
        inputs = _CreateInput.model_validate(_arguments(params))
        ref = inputs.reference()
        binding = await write_binding(services)
        recorded = await services.operations.get_operation(binding, inputs.operation_id)
        if (
            recorded is not None
            and recorded.workflow_id == inputs.workflow_id
            and recorded.proposal_ref == ref
            and recorded.state in _FINISHED
        ):
            # A repeated call returns the recorded result and never writes again.
            return _creation_response(request_id, recorded, mode="live")
        async with services.derived.workflows.stage(
            inputs.workflow_id,
            "create_playlist",
            binding=binding,
            request_id=request_id,
            cancellation=_NotCancelled(),
            proposal_ref=ref,
            operation_id=inputs.operation_id,
        ) as access:
            intent = await services.creation.create_in_workflow(
                access.context, ref, inputs.operation_id
            )
    except (
        ValidationError,
        ContractError,
        ApprovalUnavailable,
        InvalidGrant,
        OperationConflict,
        StaleOperationUpdate,
    ) as error:
        return _failure(request_id, error, mode="live")
    return _creation_response(request_id, intent, mode="live")


async def operation(
    services: LiveWriteServices, params: Mapping[str, Any] | None
) -> CallToolResult:
    request_id = uuid4().hex
    try:
        inputs = _OperationInput.model_validate(_arguments(params))
        binding = await services.derived.accounts.require_binding()
        intent = await services.operations.get_recovery_operation(
            binding, inputs.operation_id
        )
    except (ValidationError, ContractError, OperationResultExpired) as error:
        return _failure(request_id, error, mode="live")
    if intent is None:
        return _response(
            request_id,
            "blocked",
            detail=_problem(
                "CONTENT_UNAVAILABLE", "The live operation is unavailable."
            ),
            mode="live",
        )
    return _response(request_id, "ok", intent=intent, mode="live")
