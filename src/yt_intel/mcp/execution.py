from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp_types import CallToolResult, TextContent, ToolAnnotations
from pydantic import ValidationError

from yt_intel.approval.grants import InMemoryGrantStore, InvalidGrant
from yt_intel.approval.native import NativeApprovalAdapter
from yt_intel.approval.service import ApprovalService, ApprovalUnavailable
from yt_intel.client_skills import project_file
from yt_intel.contracts.approval import ApprovalAdapter
from yt_intel.contracts.common import (
    Contract,
    Label,
    NonNegative,
    OpaqueId,
    PlaylistId,
    Positive,
    VideoId,
)
from yt_intel.contracts.errors import (
    ContractError,
    ErrorCode,
    ErrorDetail,
    ResultEnvelope,
    ResultStatus,
)
from yt_intel.contracts.proposals import PlaylistProposal, ProposalRef
from yt_intel.infrastructure.database import Database
from yt_intel.infrastructure.repositories import (
    OperationConflict,
    OperationIntent,
    SqliteOperationRepository,
    SqliteProposalRepository,
    StaleOperationUpdate,
)
from yt_intel.presentation.previews import render_proposal
from yt_intel.presentation.results import render_error
from yt_intel.providers.fixture import FixtureDataset
from yt_intel.providers.fixture_writes import (
    FixtureCreationProvider,
    FixturePlaylistWrites,
)
from yt_intel.providers.youtube_writes import YouTubeWriteAdapter
from yt_intel.services.creation import PlaylistCreationService

from .discovery import FixtureCancellation
from .workflows import FixtureWorkflowRuntime


class _PrepareInput(Contract):
    workflow_id: OpaqueId
    proposal_id: OpaqueId
    version: Positive

    def reference(self) -> ProposalRef:
        return ProposalRef(proposal_id=self.proposal_id, version=self.version)


class _CreateInput(_PrepareInput):
    operation_id: OpaqueId


class _OperationInput(Contract):
    operation_id: OpaqueId


class PendingItem(Contract):
    video_id: VideoId
    position: NonNegative
    duration_seconds: Positive
    outcome: Literal["not_attempted", "pending", "refused", "unknown"]


class CreationStatus(Contract):
    operation_id: OpaqueId
    proposal: ProposalRef | None
    state: Label
    playlist_id: PlaylistId | None
    playlist_url: str | None
    confirmed_items: NonNegative
    confirmed_duration_seconds: NonNegative | None
    pending_items: tuple[PendingItem, ...] = ()


def _status(intent: OperationIntent) -> CreationStatus:
    outcomes = {
        step.position: step.outcome
        for step in intent.write_steps
        if step.endpoint == "playlistItems.insert" and step.position is not None
    }
    confirmed = {
        position for position, outcome in outcomes.items() if outcome == "saved"
    }
    duration = (
        sum(intent.planned_items[position].duration_seconds for position in confirmed)
        if all(position < len(intent.planned_items) for position in confirmed)
        else None
    )
    pending = []
    if intent.state in {"partial", "unknown", "verification_pending"}:
        for position, item in enumerate(intent.planned_items):
            outcome = outcomes.get(position)
            if outcome != "saved":
                pending.append(
                    PendingItem(
                        video_id=item.video_id,
                        position=position,
                        duration_seconds=item.duration_seconds,
                        outcome=outcome if outcome is not None else "not_attempted",
                    )
                )
    return CreationStatus(
        operation_id=intent.operation_id,
        proposal=intent.proposal_ref,
        state=intent.state,
        playlist_id=intent.playlist_id,
        playlist_url=(
            f"https://www.youtube.com/playlist?list={intent.playlist_id}"
            if intent.playlist_id
            else None
        ),
        confirmed_items=len(confirmed),
        confirmed_duration_seconds=duration,
        pending_items=tuple(pending),
    )


def _problem(code: ErrorCode, message: str) -> ErrorDetail:
    return ErrorDetail(
        code=code,
        message=message,
        retryable=False,
        safe_next_action="Check the workflow, exact preview, or recorded operation.",
    )


def _failure(request_id: OpaqueId, error: Exception) -> CallToolResult:
    if isinstance(error, ContractError):
        detail = error.detail
    elif isinstance(error, (OperationConflict, StaleOperationUpdate)):
        detail = _problem(
            "OPERATION_CONFLICT", "The prepared operation is no longer current."
        )
    elif isinstance(error, InvalidGrant):
        detail = _problem("APPROVAL_EXPIRED", "The approval is no longer current.")
    elif isinstance(error, ApprovalUnavailable):
        detail = _problem(
            "APPROVAL_REQUIRED", "The native approval decision was unavailable."
        )
    else:
        detail = _problem("INVALID_INPUT", "Invalid execution tool arguments.")
    return _response(request_id, "blocked", detail=detail)


def _response(
    request_id: OpaqueId,
    status: ResultStatus,
    *,
    intent: OperationIntent | None = None,
    detail: ErrorDetail | None = None,
    text: str | None = None,
) -> CallToolResult:
    data = _status(intent) if intent is not None else None
    result = ResultEnvelope[CreationStatus](
        mode="fixture",
        request_id=request_id,
        status=status,
        data=data,
        error=detail,
    )
    result_text = render_error(detail, mode="fixture") if detail is not None else text
    if result_text is None:
        result_text = (
            f"Fixture operation state: {data.state}." if data else "Fixture operation."
        )
    if data is not None and text is None:
        progress = [f"Confirmed items: {data.confirmed_items}."]
        if data.confirmed_duration_seconds is not None:
            progress.append(
                f"Confirmed duration: {data.confirmed_duration_seconds} seconds."
            )
        if data.playlist_url:
            progress.append(f"Fixture playlist: {data.playlist_url}")
        progress.extend(
            f"Unconfirmed item {item.position + 1}: {item.video_id} ({item.outcome})."
            for item in data.pending_items
        )
        result_text = "\n".join((result_text, *progress))
    return CallToolResult(
        is_error=status in {"blocked", "error", "unknown"},
        structured_content=result.model_dump(),
        content=[TextContent(type="text", text=result_text)],
    )


def _creation_response(request_id: OpaqueId, intent: OperationIntent) -> CallToolResult:
    if intent.state == "rejected":
        return _response(
            request_id,
            "blocked",
            intent=intent,
            detail=_problem(
                "APPROVAL_REJECTED", "Native approval was rejected or dismissed."
            ),
        )
    if intent.state == "unknown":
        return _response(
            request_id,
            "unknown",
            intent=intent,
            detail=_problem(
                "OPERATION_UNKNOWN", "The outcome requires reconciliation."
            ),
        )
    if intent.state in {"partial", "verification_pending"}:
        return _response(request_id, "partial", intent=intent)
    if intent.state != "completed":
        return _response(
            request_id,
            "error",
            intent=intent,
            detail=_problem(
                "PROVIDER_UNAVAILABLE", "The fixture operation did not complete."
            ),
        )
    return _response(request_id, "ok", intent=intent)


def register_fixture_execution(
    server: MCPServer[None],
    project_root: Path,
    fixture_db: Path | None,
    workflows: FixtureWorkflowRuntime,
    *,
    approval_adapter: ApprovalAdapter | None = None,
) -> None:
    path = project_file(project_root, Path("tests/fixtures/youtube_reads/catalog.json"))
    if not path.is_file():
        return
    dataset = replace(
        FixtureDataset.from_json_file(path),
        my_channels=(
            {
                "id": workflows.binding.channel_id,
                "snippet": {"title": "Synthetic Database Lessons"},
            },
        ),
    )
    simulator = FixturePlaylistWrites(workflows.binding.channel_id)
    grants = InMemoryGrantStore()
    adapter = (
        approval_adapter if approval_adapter is not None else NativeApprovalAdapter()
    )

    @asynccontextmanager
    async def creation() -> AsyncIterator[
        tuple[PlaylistCreationService, SqliteProposalRepository]
    ]:
        database = Database(fixture_db)
        proposals = SqliteProposalRepository(database)
        async with FixtureCreationProvider(
            dataset, quota_ledger=workflows.ledger, simulator=simulator
        ) as provider:
            yield (
                PlaylistCreationService(
                    proposals,
                    SqliteOperationRepository(database),
                    ApprovalService(adapter, grants, proposals),
                    workflows.ledger,
                    workflows.profile,
                    provider,
                    YouTubeWriteAdapter(provider.executor),
                ),
                proposals,
            )

    @server.tool(
        annotations=ToolAnnotations(read_only_hint=False, open_world_hint=False)
    )
    async def prepare_creation(
        ctx: Context[None, object],
        workflow_id: OpaqueId,
        proposal_id: OpaqueId,
        version: Positive,
    ) -> Annotated[CallToolResult, ResultEnvelope[CreationStatus]]:
        """Prepare an operation for the exact preview saved in a fixture workflow."""
        request_id = uuid4().hex
        try:
            inputs = _PrepareInput.model_validate(
                (ctx.request_context.params or {}).get("arguments", {})
            )
            ref = inputs.reference()
            async with (
                workflows.service.stage(
                    inputs.workflow_id,
                    "prepare_creation",
                    binding=workflows.binding,
                    request_id=request_id,
                    cancellation=FixtureCancellation(),
                    proposal_ref=ref,
                ) as access,
                creation() as (service, proposals),
            ):
                intent = await service.prepare(
                    access.context.binding, ref, workflow_id=access.context.workflow_id
                )
                proposal = await proposals.get_proposal(
                    workflows.binding, ref, now=datetime.now(UTC)
                )
                if not isinstance(proposal, PlaylistProposal):
                    raise ContractError(
                        _problem(
                            "PROPOSAL_CHANGED", "The exact preview is unavailable."
                        )
                    )
                access.operation_id = intent.operation_id
            return _response(
                request_id, "ok", intent=intent, text=render_proposal(proposal)
            )
        except (
            ValidationError,
            ContractError,
            OperationConflict,
            StaleOperationUpdate,
        ) as error:
            return _failure(request_id, error)

    @server.tool(
        annotations=ToolAnnotations(read_only_hint=False, open_world_hint=False)
    )
    async def create_playlist(
        ctx: Context[None, object],
        workflow_id: OpaqueId,
        proposal_id: OpaqueId,
        version: Positive,
        operation_id: OpaqueId,
    ) -> Annotated[CallToolResult, ResultEnvelope[CreationStatus]]:
        """Request native approval for the prepared fixture operation and use its reserved quota."""
        request_id = uuid4().hex
        try:
            inputs = _CreateInput.model_validate(
                (ctx.request_context.params or {}).get("arguments", {})
            )
            ref = inputs.reference()
            recorded = await SqliteOperationRepository(
                Database(fixture_db)
            ).get_operation(workflows.binding, inputs.operation_id)
            if (
                recorded is not None
                and recorded.workflow_id == inputs.workflow_id
                and recorded.proposal_ref == ref
                and recorded.state
                in {
                    "completed",
                    "rejected",
                    "partial",
                    "unknown",
                    "verification_pending",
                    "expired",
                    "failed",
                    "failed_preflight",
                }
            ):
                return _creation_response(request_id, recorded)
            async with (
                workflows.service.stage(
                    inputs.workflow_id,
                    "create_playlist",
                    binding=workflows.binding,
                    request_id=request_id,
                    cancellation=FixtureCancellation(),
                    proposal_ref=ref,
                    operation_id=inputs.operation_id,
                ) as access,
                creation() as (service, _),
            ):
                intent = await service.create_in_workflow(
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
            return _failure(request_id, error)
        return _creation_response(request_id, intent)

    @server.tool(
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False)
    )
    async def get_operation(
        ctx: Context[None, object],
        operation_id: OpaqueId,
    ) -> Annotated[CallToolResult, ResultEnvelope[CreationStatus]]:
        """Read recorded status for a fixture playlist operation."""
        request_id = uuid4().hex
        try:
            inputs = _OperationInput.model_validate(
                (ctx.request_context.params or {}).get("arguments", {})
            )
        except ValidationError as error:
            return _failure(request_id, error)
        operations = SqliteOperationRepository(Database(fixture_db))
        intent = await operations.get_operation(workflows.binding, inputs.operation_id)
        if intent is None:
            return _response(
                request_id,
                "blocked",
                detail=_problem(
                    "CONTENT_UNAVAILABLE", "The fixture operation is unavailable."
                ),
            )
        return _response(request_id, "ok", intent=intent)
