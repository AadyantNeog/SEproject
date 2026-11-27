from collections.abc import Awaitable, Callable, Mapping
from contextlib import AsyncExitStack
from datetime import UTC, datetime, timedelta
from math import ceil
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import anyio
from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp_types import CallToolResult, TextContent, ToolAnnotations
from pydantic import ValidationError

from yt_intel.client_skills import project_file
from yt_intel.contracts.common import AccountBinding, Contract, Label, Limit, OpaqueId
from yt_intel.contracts.errors import ContractError, ErrorDetail, ResultEnvelope
from yt_intel.contracts.models import RankedChannel, RankedVideo
from yt_intel.contracts.workflow import (
    Endpoint,
    QuotaReservation,
    RequestContext,
    WorkflowPlan,
)
from yt_intel.domain.identifiers import parse_channel_ref, parse_video_id
from yt_intel.presentation.results import render_error, render_ranked_results
from yt_intel.providers.fixture import FixtureDataset, FixtureYouTubeProvider
from yt_intel.services.discovery import (
    DiscoveryBounds,
    DiscoveryResult,
    DiscoveryService,
)
from yt_intel.services.fixture_candidates import FixtureCandidateSets

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


class _FixtureAttemptBudget:
    """Preallocate a single synthetic request's read attempts for MockTransport."""

    def __init__(self, context: RequestContext, calls: Mapping[Endpoint, int]) -> None:
        self._context = context
        # The fixture executor allows at most three attempts per read.
        self._remaining = {endpoint: count * 3 for endpoint, count in calls.items()}

    async def reserve(self, plan: WorkflowPlan) -> QuotaReservation:
        raise NotImplementedError("Only standalone synthetic reads are supported")

    async def debit_attempt(
        self, ctx: RequestContext, endpoint: Endpoint, attempt_id: str
    ) -> None:
        if ctx is not self._context or self._remaining.get(endpoint, 0) == 0:
            raise ContractError(
                ErrorDetail(
                    code="QUOTA_INSUFFICIENT",
                    message="The synthetic discovery attempt budget is exhausted.",
                    retryable=False,
                    safe_next_action="Check the fixture and discovery bounds.",
                )
            )
        self._remaining[endpoint] -= 1

    async def release(self, reservation_id: str) -> None:
        raise NotImplementedError("The synthetic budget is discarded after the read")


def register_fixture_discovery(
    server: MCPServer[None],
    project_root: Path,
    candidate_sets: FixtureCandidateSets,
    workflows: FixtureWorkflowRuntime | None = None,
) -> None:
    catalog_path = project_file(
        project_root, Path("tests/fixtures/youtube_reads/catalog.json")
    )
    if not catalog_path.is_file():
        return
    dataset = FixtureDataset.from_json_file(catalog_path)

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

        async def rank(
            service: DiscoveryService, request: RequestContext
        ) -> tuple[DiscoveryResult[RankedVideo], OpaqueId]:
            args = _discovery_input(_VideoInput, ctx)
            discovery = await service.videos(
                request, parse_video_id(args.video), limit=args.limit
            )
            # Let a client cancellation interrupt the request before caching results.
            await anyio.lowlevel.checkpoint()
            reference = await candidate_sets.publish(
                discovery, request.binding, now=datetime.now(UTC)
            )
            return discovery, reference

        return await _run_discovery(
            ctx,
            dataset,
            _VIDEO_CALLS,
            rank,
            VideoDiscoveryEnvelope,
            workflows=workflows,
        )

    @server.tool(
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False)
    )
    async def find_similar_channels(
        ctx: Context[None, object], channel: Label, limit: Limit = 10
    ) -> Annotated[CallToolResult, ResultEnvelope[tuple[RankedChannel, ...]]]:
        """Rank sampled synthetic channels by channel ID, handle or YouTube URL."""

        async def rank(
            service: DiscoveryService, request: RequestContext
        ) -> tuple[DiscoveryResult[RankedChannel], None]:
            args = _discovery_input(_ChannelInput, ctx)
            discovery = await service.channels(
                request, parse_channel_ref(args.channel), limit=args.limit
            )
            return discovery, None

        return await _run_discovery(
            ctx,
            dataset,
            _CHANNEL_CALLS,
            rank,
            ResultEnvelope[tuple[RankedChannel, ...]],
        )


async def _run_discovery[T: (RankedVideo, RankedChannel)](
    ctx: Context[None, object],
    dataset: FixtureDataset,
    calls: Mapping[Endpoint, int],
    rank: Callable[
        [DiscoveryService, RequestContext],
        Awaitable[tuple[DiscoveryResult[T], OpaqueId | None]],
    ],
    envelope: type[ResultEnvelope[tuple[T, ...]]],
    *,
    workflows: FixtureWorkflowRuntime | None = None,
) -> CallToolResult:
    async def report_progress(completed: int, message: str) -> None:
        await ctx.report_progress(completed, 3, message)

    request = RequestContext(
        request_id=uuid4().hex,
        binding=_FIXTURE_ACCOUNT,
        reservation_id=uuid4().hex,
        deadline=datetime.now(UTC) + timedelta(seconds=60),
        cancellation=FixtureCancellation(),
    )
    try:
        async with AsyncExitStack() as stack:
            access = None
            ledger = _FixtureAttemptBudget(request, calls)
            if envelope is VideoDiscoveryEnvelope:
                args = _discovery_input(_VideoInput, ctx)
                if args.workflow_id is not None:
                    if workflows is None:
                        raise ContractError(
                            ErrorDetail(
                                code="INVALID_INPUT",
                                message="Workflow session is unavailable.",
                                retryable=False,
                                safe_next_action="Start a fixture workflow.",
                            )
                        )
                    access = await stack.enter_async_context(
                        workflows.service.stage(
                            args.workflow_id,
                            "find_similar_videos",
                            binding=workflows.binding,
                            request_id=request.request_id,
                            cancellation=request.cancellation,
                            video=parse_video_id(args.video),
                        )
                    )
                    request = access.context
            provider = FixtureYouTubeProvider(
                dataset,
                quota_ledger=workflows.ledger
                if access is not None and workflows is not None
                else ledger,
            )
            try:
                ranked, candidate_set_id = await rank(
                    DiscoveryService(provider, _BOUNDS, progress=report_progress),
                    request,
                )
                if access is not None:
                    access.candidate_set_id = candidate_set_id
            finally:
                with anyio.CancelScope(shield=True):
                    await provider.aclose()
    except ContractError as error:
        result = envelope(
            mode="fixture",
            request_id=request.request_id,
            status="error",
            data=None,
            error=error.detail,
        )
        return CallToolResult(
            is_error=True,
            structured_content=result.model_dump(),
            content=[
                TextContent(
                    type="text", text=render_error(error.detail, mode="fixture")
                )
            ],
        )
    result = envelope(
        mode="fixture",
        request_id=request.request_id,
        status="ok" if ranked.results else "empty",
        data=ranked.results,
        coverage=ranked.coverage,
        warnings=ranked.coverage.warnings,
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
