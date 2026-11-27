from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from math import ceil
from pathlib import Path
from sqlite3 import Error as SqliteError
from typing import Annotated
from uuid import uuid4

import anyio
from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp_types import CallToolResult, TextContent, ToolAnnotations
from pydantic import ValidationError

from yt_intel.client_skills import project_file
from yt_intel.contracts.common import (
    AccountBinding,
    Contract,
    Label,
    Limit,
    OpaqueId,
    VideoId,
)
from yt_intel.contracts.errors import (
    ContractError,
    ErrorDetail,
    QuotaEstimate,
    ResultEnvelope,
)
from yt_intel.contracts.models import RankedChannel, RankedVideo
from yt_intel.contracts.workflow import (
    CallCeiling,
    Endpoint,
    RequestContext,
    WorkflowPlan,
)
from yt_intel.domain.identifiers import parse_channel_ref, parse_video_id
from yt_intel.infrastructure.database import Database
from yt_intel.infrastructure.quota import QuotaProfile, SqliteQuotaLedger
from yt_intel.presentation.results import render_error, render_ranked_results
from yt_intel.providers.fixture import FixtureDataset, FixtureYouTubeProvider
from yt_intel.services.discovery import (
    DiscoveryBounds,
    DiscoveryResult,
    DiscoveryService,
)
from yt_intel.services.fixture_candidates import FixtureCandidateSets
from yt_intel.services.workflows import StageAccess

from .workflows import FixtureWorkflowRuntime

_BOUNDS = DiscoveryBounds()
_FIXTURE_ACCOUNT = AccountBinding(
    installation_id="fixture-installation",
    credential_binding_id="fixture-binding",
    channel_id="UCfixture000000000000001",
    mode="fixture",
)
_VIDEO_CALLS: Mapping[Endpoint, int] = {
    "videos.list": 1 + ceil(_BOUNDS.video_candidates / 50),
    "search.list": _BOUNDS.search_pages,
}
_CHANNEL_CALLS: Mapping[Endpoint, int] = {
    "channels.list": 1 + ceil(_BOUNDS.channel_candidates / 50),
    "videos.list": 1 + _BOUNDS.channel_candidates,
    "playlistItems.list": 1 + _BOUNDS.channel_candidates,
    "search.list": _BOUNDS.search_pages,
}


class _VideoInput(Contract):
    video: Label
    limit: Limit = 10
    workflow_id: OpaqueId | None = None


class _ChannelInput(Contract):
    channel: Label
    limit: Limit = 10


class VideoDiscoveryEnvelope(ResultEnvelope[tuple[RankedVideo, ...]]):
    candidate_set_id: OpaqueId | None = None


def _discovery_input[T: Contract](model: type[T], ctx: Context[None, object]) -> T:
    # Validate the original arguments before using values the SDK may coerce.
    try:
        return model.model_validate(
            (ctx.request_context.params or {}).get("arguments", {})
        )
    except ValidationError:
        raise ContractError(
            ErrorDetail(
                code="INVALID_INPUT",
                message="Invalid discovery parameters.",
                retryable=False,
                safe_next_action="Use the advertised identifier and a limit from 1 to 50.",
            )
        ) from None


class FixtureCancellation:
    # The SDK cancels the handler task and its awaited transport on MCP cancellation.
    def is_cancelled(self) -> bool:
        return False

    async def wait(self) -> None:
        await anyio.sleep_forever()


def register_fixture_discovery(
    server: MCPServer[None],
    project_root: Path,
    fixture_db: Path | None,
    candidate_sets: FixtureCandidateSets,
    workflows: FixtureWorkflowRuntime | None,
) -> None:
    catalog_path = project_file(
        project_root, Path("tests/fixtures/youtube_reads/catalog.json")
    )
    profile_path = project_file(
        project_root, Path("config/quota-profiles/youtube-2026-11-16.json")
    )
    if not catalog_path.is_file() or not profile_path.is_file():
        return
    dataset = FixtureDataset.from_json_file(catalog_path)
    profile = (
        workflows.profile if workflows is not None else QuotaProfile.load(profile_path)
    )
    ledger: SqliteQuotaLedger | None = None

    def quota_ledger() -> SqliteQuotaLedger:
        nonlocal ledger
        if workflows is not None:
            return workflows.ledger
        if ledger is None:
            ledger = SqliteQuotaLedger(Database(fixture_db), profile)
        return ledger

    @server.tool(
        annotations=ToolAnnotations(
            read_only_hint=False, destructive_hint=False, open_world_hint=False
        )
    )
    async def find_similar_videos(
        ctx: Context[None, object],
        video: Label,
        limit: Limit = 10,
        workflow_id: OpaqueId | None = None,
    ) -> Annotated[CallToolResult, VideoDiscoveryEnvelope]:
        """Rank fixture videos and save their candidate set for playlist planning."""
        try:
            args = _discovery_input(_VideoInput, ctx)
            seed = parse_video_id(args.video)
            composed = None
            if args.workflow_id is not None:
                if workflows is None:
                    raise _workflow_unavailable()
                composed = (workflows, args.workflow_id, seed)
        except ContractError as error:
            return _discovery_error(VideoDiscoveryEnvelope, uuid4().hex, error.detail)

        async def rank(
            service: DiscoveryService, request: RequestContext
        ) -> tuple[DiscoveryResult[RankedVideo], OpaqueId]:
            discovery = await service.videos(request, seed, limit=args.limit)
            # Let a client cancellation interrupt the request before caching results.
            await anyio.lowlevel.checkpoint()
            reference = await candidate_sets.publish(
                discovery, request.binding, now=datetime.now(UTC)
            )
            return discovery, reference

        return await _run_discovery(
            ctx,
            dataset,
            quota_ledger,
            profile,
            _VIDEO_CALLS,
            rank,
            VideoDiscoveryEnvelope,
            candidate_cap=_BOUNDS.video_candidates,
            composed=composed,
        )

    @server.tool(
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False)
    )
    async def find_similar_channels(
        ctx: Context[None, object], channel: Label, limit: Limit = 10
    ) -> Annotated[CallToolResult, ResultEnvelope[tuple[RankedChannel, ...]]]:
        """Rank sampled synthetic channels by channel ID, handle or YouTube URL."""
        envelope = ResultEnvelope[tuple[RankedChannel, ...]]
        try:
            args = _discovery_input(_ChannelInput, ctx)
            seed = parse_channel_ref(args.channel)
        except ContractError as error:
            return _discovery_error(envelope, uuid4().hex, error.detail)

        async def rank(
            service: DiscoveryService, request: RequestContext
        ) -> tuple[DiscoveryResult[RankedChannel], None]:
            discovery = await service.channels(request, seed, limit=args.limit)
            return discovery, None

        return await _run_discovery(
            ctx,
            dataset,
            quota_ledger,
            profile,
            _CHANNEL_CALLS,
            rank,
            envelope,
            candidate_cap=_BOUNDS.channel_candidates,
            sample_cap=1 + _BOUNDS.channel_candidates,
        )


async def _run_discovery[T: (RankedVideo, RankedChannel)](
    ctx: Context[None, object],
    dataset: FixtureDataset,
    quota_ledger: Callable[[], SqliteQuotaLedger],
    profile: QuotaProfile,
    calls: Mapping[Endpoint, int],
    rank: Callable[
        [DiscoveryService, RequestContext],
        Awaitable[tuple[DiscoveryResult[T], OpaqueId | None]],
    ],
    envelope: type[ResultEnvelope[tuple[T, ...]]],
    *,
    candidate_cap: int,
    sample_cap: int = 0,
    composed: tuple[FixtureWorkflowRuntime, OpaqueId, VideoId] | None = None,
) -> CallToolResult:
    async def report_progress(completed: int, message: str) -> None:
        await ctx.report_progress(completed, 3, message)

    request_id = uuid4().hex
    try:
        ledger = quota_ledger()
        if composed is None:
            stage = _standalone_stage(
                ledger,
                profile,
                request_id,
                calls,
                candidate_cap=candidate_cap,
                sample_cap=sample_cap,
            )
        else:
            runtime, workflow_id, seed = composed
            stage = runtime.service.stage(
                workflow_id,
                "find_similar_videos",
                binding=_FIXTURE_ACCOUNT,
                request_id=request_id,
                cancellation=FixtureCancellation(),
                video=seed,
            )
        async with stage as access:
            provider = FixtureYouTubeProvider(dataset, quota_ledger=ledger)
            try:
                ranked, candidate_set_id = await rank(
                    DiscoveryService(provider, _BOUNDS, progress=report_progress),
                    access.context,
                )
                access.candidate_set_id = candidate_set_id
            finally:
                with anyio.CancelScope(shield=True):
                    await provider.aclose()
    except ContractError as error:
        return _discovery_error(envelope, request_id, error.detail)
    except (OSError, SqliteError):
        return _discovery_error(
            envelope,
            request_id,
            ErrorDetail(
                code="PROVIDER_UNAVAILABLE",
                message="The local discovery quota ledger could not be accessed.",
                retryable=False,
                safe_next_action="Check access to the fixture database and try again.",
            ),
        )

    result = envelope(
        mode="fixture",
        request_id=request_id,
        status="ok" if ranked.results else "empty",
        data=ranked.results,
        coverage=ranked.coverage,
        warnings=ranked.coverage.warnings,
        quota=QuotaEstimate(profile_id=profile.profile_id),
    )
    text = render_ranked_results(
        ranked.results, mode="fixture", coverage=ranked.coverage
    )
    if isinstance(result, VideoDiscoveryEnvelope) and candidate_set_id is not None:
        result = result.model_copy(update={"candidate_set_id": candidate_set_id})
        text += f"\nCandidate set: {candidate_set_id}"
    await report_progress(3, "Discovery complete.")
    return CallToolResult(
        structured_content=result.model_dump(),
        content=[TextContent(type="text", text=text)],
    )


@asynccontextmanager
async def _standalone_stage(
    ledger: SqliteQuotaLedger,
    profile: QuotaProfile,
    request_id: OpaqueId,
    calls: Mapping[Endpoint, int],
    *,
    candidate_cap: int,
    sample_cap: int,
) -> AsyncIterator[StageAccess]:
    plan = WorkflowPlan(
        plan_id=f"discovery-{request_id}",
        binding=_FIXTURE_ACCOUNT,
        project_id="fixture-project",
        quota_profile_id=profile.profile_id,
        endpoint_ceilings={
            endpoint: CallCeiling(calls=count, attempts_per_call=3)
            for endpoint, count in calls.items()
        },
        buckets={},
        candidate_cap=candidate_cap,
        page_cap=_BOUNDS.search_pages,
        sample_cap=sample_cap,
        deadline=datetime.now(UTC) + timedelta(seconds=60),
        cancellation_policy="stop and release unused quota",
        reconciliation_allowance={},
    )
    try:
        plan = plan.model_copy(update={"buckets": profile.required_buckets(plan)})
    except ValueError as error:
        raise ContractError(
            ErrorDetail(
                code="INVALID_INPUT",
                message="The quota profile does not cover the discovery plan.",
                retryable=False,
                safe_next_action="Check the configured quota profile and try again.",
            ),
        ) from error
    reservation = await ledger.reserve(plan)
    try:
        yield StageAccess(
            context=RequestContext(
                request_id=request_id,
                binding=plan.binding,
                reservation_id=reservation.reservation_id,
                deadline=min(plan.deadline, reservation.reset_at),
                cancellation=FixtureCancellation(),
            ),
        )
    finally:
        with anyio.CancelScope(shield=True):
            await ledger.release(reservation.reservation_id)


def _workflow_unavailable() -> ContractError:
    return ContractError(
        ErrorDetail(
            code="INVALID_INPUT",
            message="Workflow session is unavailable.",
            retryable=False,
            safe_next_action="Start a fixture workflow and follow its stage order.",
        )
    )


def _discovery_error[T: (RankedVideo, RankedChannel)](
    envelope: type[ResultEnvelope[tuple[T, ...]]],
    request_id: OpaqueId,
    problem: ErrorDetail,
) -> CallToolResult:
    result = envelope(
        mode="fixture", request_id=request_id, status="error", data=None, error=problem
    )
    return CallToolResult(
        is_error=True,
        structured_content=result.model_dump(),
        content=[TextContent(type="text", text=render_error(problem, mode="fixture"))],
    )
