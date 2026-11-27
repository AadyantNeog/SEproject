from collections.abc import Callable
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
from yt_intel.contracts.common import Label, LanguageTag, Limit, OpaqueId, Positive
from yt_intel.contracts.errors import (
    ContractError,
    ErrorDetail,
    QuotaEstimate,
    ResultEnvelope,
)
from yt_intel.contracts.models import CandidateSet, LibrarySnapshot
from yt_intel.contracts.workflow import CallCeiling, RequestContext, WorkflowPlan
from yt_intel.domain.language import normalize_language_tag
from yt_intel.domain.profiles import PROFILE_VERSION
from yt_intel.presentation.results import render_error, render_ranked_results
from yt_intel.presentation.text import format_duration
from yt_intel.providers.fixture import FixtureDataset, FixtureYouTubeProvider
from yt_intel.services.discovery import DiscoveryBounds, DiscoveryService
from yt_intel.services.recommendations import (
    RecommendationFilters,
    RecommendationResult,
    RecommendationService,
)

from .discovery import FixtureCancellation
from .library import FixtureLibraryRuntime

_BOUNDS = DiscoveryBounds()


class RecommendationInput(RecommendationFilters):
    snapshot_id: OpaqueId | None = None


def register_fixture_recommendations(
    server: MCPServer[None],
    project_root: Path,
    library_runtime: Callable[[], FixtureLibraryRuntime] | None,
) -> None:
    fixture_root = Path("tests", "fixtures")
    snapshot_path = project_file(
        project_root, fixture_root / "contracts/library_snapshot.json"
    )
    candidates_path = project_file(
        project_root, fixture_root / "recommendations/candidates.json"
    )
    catalog_path = project_file(
        project_root, fixture_root / "youtube_reads/catalog.json"
    )

    bundled = None
    if snapshot_path.is_file() and candidates_path.is_file():
        snapshot = LibrarySnapshot.model_validate_json(snapshot_path.read_bytes())
        candidates = CandidateSet.model_validate_json(candidates_path.read_bytes())
        if snapshot.binding.mode != "fixture" or candidates.binding != snapshot.binding:
            raise ValueError(
                "recommendation fixtures must share a synthetic account binding"
            )
        bundled = (snapshot, candidates)
    dataset = (
        FixtureDataset.from_json_file(catalog_path)
        if library_runtime is not None and catalog_path.is_file()
        else None
    )
    if bundled is None and dataset is None:
        return
    service = RecommendationService(normalize_language_tag)

    @server.tool(
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False)
    )
    async def recommend_videos(
        ctx: Context[None, object],
        topic: Label | None = None,
        total_seconds: Positive | None = None,
        max_video_seconds: Positive | None = None,
        language: LanguageTag | None = None,
        limit: Limit = 10,
        snapshot_id: OpaqueId | None = None,
    ) -> Annotated[CallToolResult, ResultEnvelope[RecommendationResult]]:
        """Rank fixture recommendations from get_library's snapshot ID or a bundled example."""
        request_id = uuid4().hex
        # The signature advertises the flat MCP schema. Validate the original JSON
        # arguments before using values that the SDK might coerce.
        arguments = (ctx.request_context.params or {}).get("arguments", {})
        try:
            inputs = RecommendationInput.model_validate(arguments)
        except ValidationError:
            return _error_response(
                request_id,
                ErrorDetail(
                    code="INVALID_INPUT",
                    message="Invalid recommendation parameters.",
                    retryable=False,
                    safe_next_action="Use the advertised filters and a limit from 1 to 50.",
                ),
            )
        try:
            if bundled is not None and inputs.snapshot_id in (
                None,
                bundled[0].snapshot_id,
            ):
                example, candidates = bundled
                result = service.recommend(
                    example,
                    candidates,
                    binding=example.binding,
                    now=max(example.fetched_at, candidates.created_at),
                    filters=inputs,
                )
                return _recommendation_response(request_id, result)
            if inputs.snapshot_id is None or library_runtime is None or dataset is None:
                raise _snapshot_unavailable()
            runtime = library_runtime()
            result = await _recommend_from_library(
                service, runtime, dataset, inputs.snapshot_id, inputs, request_id
            )
            return _recommendation_response(
                request_id,
                result,
                quota=QuotaEstimate(profile_id=runtime.profile.profile_id),
            )
        except ContractError as error:
            return _error_response(request_id, error.detail)


def _snapshot_unavailable() -> ContractError:
    return ContractError(
        ErrorDetail(
            code="CONTENT_UNAVAILABLE",
            message="The requested library snapshot is unavailable for the active account.",
            retryable=False,
            safe_next_action="Run get_library and use the snapshot ID it returns.",
        )
    )


async def _recommend_from_library(
    service: RecommendationService,
    runtime: FixtureLibraryRuntime,
    dataset: FixtureDataset,
    snapshot_id: OpaqueId,
    filters: RecommendationFilters,
    request_id: OpaqueId,
) -> RecommendationResult:
    binding = await runtime.accounts.require_binding()
    now = datetime.now(UTC)
    try:
        snapshot = await runtime.snapshots.get_snapshot(binding, snapshot_id, now=now)
    except (OSError, SqliteError, ValidationError) as error:
        raise ContractError(
            ErrorDetail(
                code="PROVIDER_UNAVAILABLE",
                message="The local library snapshot could not be loaded.",
                retryable=False,
                safe_next_action="Check the fixture database and run get_library again.",
            )
        ) from error
    if snapshot is None:
        raise _snapshot_unavailable()
    query = service.search_query(snapshot, binding=binding, now=now, filters=filters)
    plan = WorkflowPlan(
        plan_id=f"recommend-{request_id}",
        binding=binding,
        project_id=runtime.project_id,
        quota_profile_id=runtime.profile.profile_id,
        endpoint_ceilings={
            "search.list": CallCeiling(calls=_BOUNDS.search_pages, attempts_per_call=3),
            "videos.list": CallCeiling(
                calls=ceil(_BOUNDS.video_candidates / 50), attempts_per_call=3
            ),
        },
        buckets={},
        candidate_cap=_BOUNDS.video_candidates,
        page_cap=_BOUNDS.search_pages,
        sample_cap=0,
        deadline=now + timedelta(seconds=60),
        cancellation_policy="cooperative",
        reconciliation_allowance={},
    )
    plan = plan.model_copy(update={"buckets": runtime.profile.required_buckets(plan)})
    reservation = await runtime.ledger.reserve(plan)
    provider: FixtureYouTubeProvider | None = None
    try:
        provider = FixtureYouTubeProvider(dataset, quota_ledger=runtime.ledger)
        pool = await DiscoveryService(provider, _BOUNDS).video_candidates(
            RequestContext(
                request_id=request_id,
                binding=binding,
                reservation_id=reservation.reservation_id,
                deadline=plan.deadline,
                cancellation=FixtureCancellation(),
            ),
            query,
        )
    finally:
        with anyio.CancelScope(shield=True):
            try:
                if provider is not None:
                    await provider.aclose()
            finally:
                await runtime.ledger.release(reservation.reservation_id)

    if await runtime.accounts.require_binding() != binding:
        raise _snapshot_unavailable()
    candidates = CandidateSet(
        candidate_set_id=f"recommend-{request_id}",
        binding=binding,
        videos=pool.videos,
        source="fixture-profile-discovery",
        seed_video_id=None,
        topic=filters.topic,
        coverage=pool.coverage.model_copy(
            update={
                "limits": {
                    **pool.coverage.limits,
                    "candidates": _BOUNDS.video_candidates,
                }
            }
        ),
        ranking_version=PROFILE_VERSION,
        config_version="fixture-v1",
        created_at=now,
        expires_at=plan.deadline,
    )
    return service.recommend(
        snapshot, candidates, binding=binding, now=datetime.now(UTC), filters=filters
    )


def _error_response(request_id: str, problem: ErrorDetail) -> CallToolResult:
    envelope = ResultEnvelope[RecommendationResult](
        mode="fixture", request_id=request_id, status="error", data=None, error=problem
    )
    return CallToolResult(
        is_error=True,
        structured_content=envelope.model_dump(),
        content=[TextContent(type="text", text=render_error(problem, mode="fixture"))],
    )


def _recommendation_response(
    request_id: str, result: RecommendationResult, *, quota: QuotaEstimate | None = None
) -> CallToolResult:
    envelope = ResultEnvelope[RecommendationResult](
        mode="fixture",
        request_id=request_id,
        status="ok" if result.results else "empty",
        data=result,
        coverage=result.candidate_coverage,
        warnings=result.warnings,
        quota=quota,
    )
    text = render_ranked_results(
        result.results,
        mode="fixture",
        coverage=result.candidate_coverage,
        warnings=result.warnings,
    )
    sources = ", ".join(
        f"{name}: {source.state.replace('_', ' ')}"
        for name, source in result.sources.items()
    )
    lines = [text, f"Preference source states: {sources}."]
    if result.total_seconds is not None and result.unused_seconds is not None:
        lines.extend(
            [
                f"Total duration: {format_duration(result.total_seconds)}",
                f"Unused time: {format_duration(result.unused_seconds)}",
            ]
        )
    return CallToolResult(
        structured_content=envelope.model_dump(),
        content=[TextContent(type="text", text="\n".join(lines))],
    )
