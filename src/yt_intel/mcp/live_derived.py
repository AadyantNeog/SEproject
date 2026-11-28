"""Live derived handlers (ADR-0011 step two): FR-1 to FR-4 and the FR-5 preview.

These run only when the reviewed D-02 record is resolved. `live.py` checks the
record before calling any handler here, and every shared service checks it
again through the injected `recorded_policy_check`, so a reverted record
closes the gate with zero provider calls.

Each handler reserves its whole bounded worst case on the persistent ledger
before the first provider call and releases the unused part afterwards. The
services and ranking are the same ones the fixture server uses.

A standalone playlist proposal is a stored preview only. Creation runs only
inside a `begin_workflow` session (see `live_creation.py`), which reserves the
whole video-to-playlist budget up front. Live recovery is not exposed.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import ceil
from sqlite3 import Error as SqliteError
from typing import Any
from uuid import uuid4

import anyio
from mcp_types import CallToolResult, TextContent
from pydantic import ValidationError

from yt_intel.analytics.periods import TimePeriod, validate_period_pair
from yt_intel.analytics.summaries import AnalysisReport
from yt_intel.auth.account import LocalAccountService
from yt_intel.contracts.common import (
    AccountBinding,
    Contract,
    Label,
    Limit,
    OpaqueId,
)
from yt_intel.contracts.errors import (
    ContractError,
    ErrorDetail,
    QuotaEstimate,
    ResultEnvelope,
)
from yt_intel.contracts.models import (
    CandidateSet,
    LibrarySource,
    RankedChannel,
    RankedVideo,
)
from yt_intel.contracts.proposals import PlaylistProposal
from yt_intel.contracts.workflow import (
    CallCeiling,
    Endpoint,
    RequestContext,
    WorkflowPlan,
)
from yt_intel.domain.constraints import parse_playlist_request, planning_error
from yt_intel.domain.derived import DerivedProcessingCheck
from yt_intel.domain.identifiers import parse_channel_ref, parse_video_id
from yt_intel.domain.profiles import PROFILE_VERSION
from yt_intel.domain.proposals import PlaylistPlanner
from yt_intel.infrastructure.quota import QuotaProfile, SqliteQuotaLedger
from yt_intel.infrastructure.repositories import (
    RepositoryConflict,
    SqliteProposalRepository,
    SqliteSnapshotRepository,
)
from yt_intel.presentation.previews import render_proposal
from yt_intel.presentation.results import render_error, render_ranked_results
from yt_intel.providers.youtube import LiveYouTubeReadProvider
from yt_intel.services.analysis import AnalysisService
from yt_intel.services.discovery import DiscoveryBounds, DiscoveryService
from yt_intel.services.fixture_candidates import FixtureCandidateSets
from yt_intel.services.library import LibraryService
from yt_intel.services.recommendations import (
    RecommendationFilters,
    RecommendationService,
)
from yt_intel.services.workflows import WorkflowService

from .recommendations import _error_response as _recommendation_error
from .recommendations import _recommendation_response

LIVE_CANDIDATE_SOURCE = "live-video-discovery"
LIVE_CONFIG_VERSION = "live-v1"
PREVIEW_ONLY_NOTE = (
    "Preview only: nothing is written to YouTube. To create a playlist, "
    "start the video-to-playlist workflow with begin_workflow."
)
WORKFLOW_PREVIEW_NOTE = (
    "Nothing is written to YouTube yet. Next: prepare_creation, then "
    "create_playlist, which asks for your approval in a native dialog."
)

_BOUNDS = DiscoveryBounds()
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
_RECOMMEND_CALLS: Mapping[Endpoint, int] = {
    "search.list": _BOUNDS.search_pages,
    "videos.list": ceil(_BOUNDS.video_candidates / 50),
}


class _VideoInput(Contract):
    video: Label
    limit: Limit = 10
    workflow_id: OpaqueId | None = None


class _ChannelInput(Contract):
    channel: Label
    limit: Limit = 10


class _RecommendInput(RecommendationFilters):
    snapshot_id: OpaqueId | None = None


class _AnalyseInput(Contract):
    snapshot_id: OpaqueId | None = None
    sources: tuple[LibrarySource, ...] | None = None
    period_a: TimePeriod | None = None
    period_b: TimePeriod | None = None


class _PreviewReferences(Contract):
    candidate_set_id: OpaqueId | None = None
    workflow_id: OpaqueId | None = None


class LiveVideoDiscoveryEnvelope(ResultEnvelope[tuple[RankedVideo, ...]]):
    candidate_set_id: OpaqueId | None = None


class _NotCancelled:
    def is_cancelled(self) -> bool:
        return False

    async def wait(self) -> None:
        await anyio.sleep_forever()


@dataclass(frozen=True, slots=True)
class LiveDerivedServices:
    accounts: LocalAccountService
    profile: QuotaProfile
    ledger: SqliteQuotaLedger
    provider: LiveYouTubeReadProvider
    library: LibraryService
    snapshots: SqliteSnapshotRepository
    proposals: SqliteProposalRepository
    candidate_sets: FixtureCandidateSets
    analysis: AnalysisService
    recommendations: RecommendationService
    planner: PlaylistPlanner
    permits: DerivedProcessingCheck
    project_id: str
    workflows: WorkflowService


def live_candidate_sets(
    cache: Any, permits: DerivedProcessingCheck
) -> FixtureCandidateSets:
    return FixtureCandidateSets(
        cache,
        permits=permits,
        source=LIVE_CANDIDATE_SOURCE,
        config_version=LIVE_CONFIG_VERSION,
    )


def _arguments(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    return dict((raw or {}).get("arguments") or {})


def _invalid(message: str, next_action: str) -> ContractError:
    return ContractError(
        ErrorDetail(
            code="INVALID_INPUT",
            message=message,
            retryable=False,
            safe_next_action=next_action,
        )
    )


def _unavailable(message: str, next_action: str) -> ContractError:
    return ContractError(
        ErrorDetail(
            code="CONTENT_UNAVAILABLE",
            message=message,
            retryable=False,
            safe_next_action=next_action,
        )
    )


def _storage_error() -> ContractError:
    return ContractError(
        ErrorDetail(
            code="PROVIDER_UNAVAILABLE",
            message="The local live database could not be accessed.",
            retryable=False,
            safe_next_action="Check access to the live database and try again.",
        )
    )


def _error[T](
    envelope: type[ResultEnvelope[T]], request_id: OpaqueId, problem: ErrorDetail
) -> CallToolResult:
    result = envelope(
        mode="live", request_id=request_id, status="error", data=None, error=problem
    )
    return CallToolResult(
        is_error=True,
        structured_content=result.model_dump(),
        content=[TextContent(type="text", text=render_error(problem, mode="live"))],
    )


@asynccontextmanager
async def _reserved(
    services: LiveDerivedServices,
    binding: AccountBinding,
    request_id: OpaqueId,
    kind: str,
    calls: Mapping[Endpoint, int],
    *,
    candidate_cap: int,
    sample_cap: int = 0,
) -> AsyncIterator[RequestContext]:
    """Reserve the bounded worst case before any call and always release it."""
    plan = WorkflowPlan(
        plan_id=f"live-{kind}-{request_id}",
        binding=binding,
        project_id=services.project_id,
        quota_profile_id=services.profile.profile_id,
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
    plan = plan.model_copy(update={"buckets": services.profile.required_buckets(plan)})
    reservation = await services.ledger.reserve(plan)
    try:
        yield RequestContext(
            request_id=request_id,
            binding=binding,
            reservation_id=reservation.reservation_id,
            deadline=min(plan.deadline, reservation.reset_at),
            cancellation=_NotCancelled(),
        )
    finally:
        with anyio.CancelScope(shield=True):
            await services.ledger.release(reservation.reservation_id)


def _ranked_result[T: (RankedVideo, RankedChannel)](
    envelope: ResultEnvelope[tuple[T, ...]], text: str
) -> CallToolResult:
    return CallToolResult(
        structured_content=envelope.model_dump(),
        content=[TextContent(type="text", text=text)],
    )


async def similar_videos(
    services: LiveDerivedServices, params: Mapping[str, Any] | None
) -> CallToolResult:
    request_id = uuid4().hex
    envelope = LiveVideoDiscoveryEnvelope
    try:
        try:
            args = _VideoInput.model_validate(_arguments(params))
        except ValidationError:
            raise _invalid(
                "Invalid discovery parameters.",
                "Use a video URL or ID and a limit from 1 to 50.",
            ) from None
        seed = parse_video_id(args.video)
        binding = await services.accounts.require_binding()
        if args.workflow_id is not None:
            # A workflow stage spends the reservation made by begin_workflow.
            async with services.workflows.stage(
                args.workflow_id,
                "find_similar_videos",
                binding=binding,
                request_id=request_id,
                cancellation=_NotCancelled(),
                video=seed,
            ) as access:
                discovery = await DiscoveryService(
                    services.provider, _BOUNDS, permits=services.permits
                ).videos(access.context, seed, limit=args.limit)
                reference = await services.candidate_sets.publish(
                    discovery, binding, now=datetime.now(UTC)
                )
                access.candidate_set_id = reference
        else:
            async with _reserved(
                services,
                binding,
                request_id,
                "similar-videos",
                _VIDEO_CALLS,
                candidate_cap=_BOUNDS.video_candidates,
            ) as context:
                discovery = await DiscoveryService(
                    services.provider, _BOUNDS, permits=services.permits
                ).videos(context, seed, limit=args.limit)
            reference = await services.candidate_sets.publish(
                discovery, binding, now=datetime.now(UTC)
            )
    except ContractError as error:
        return _error(envelope, request_id, error.detail)
    except (OSError, SqliteError):
        return _error(envelope, request_id, _storage_error().detail)
    result = envelope(
        mode="live",
        request_id=request_id,
        status="ok" if discovery.results else "empty",
        data=discovery.results,
        coverage=discovery.coverage,
        warnings=discovery.coverage.warnings,
        quota=QuotaEstimate(profile_id=services.profile.profile_id),
        candidate_set_id=reference,
    )
    text = render_ranked_results(
        discovery.results, mode="live", coverage=discovery.coverage
    )
    return _ranked_result(result, f"{text}\nCandidate set: {reference}")


async def similar_channels(
    services: LiveDerivedServices, params: Mapping[str, Any] | None
) -> CallToolResult:
    request_id = uuid4().hex
    envelope = ResultEnvelope[tuple[RankedChannel, ...]]
    try:
        try:
            args = _ChannelInput.model_validate(_arguments(params))
        except ValidationError:
            raise _invalid(
                "Invalid discovery parameters.",
                "Use a channel ID, handle or URL and a limit from 1 to 50.",
            ) from None
        seed = parse_channel_ref(args.channel)
        binding = await services.accounts.require_binding()
        async with _reserved(
            services,
            binding,
            request_id,
            "similar-channels",
            _CHANNEL_CALLS,
            candidate_cap=_BOUNDS.channel_candidates,
            sample_cap=1 + _BOUNDS.channel_candidates,
        ) as context:
            discovery = await DiscoveryService(
                services.provider, _BOUNDS, permits=services.permits
            ).channels(context, seed, limit=args.limit)
    except ContractError as error:
        return _error(envelope, request_id, error.detail)
    except (OSError, SqliteError):
        return _error(envelope, request_id, _storage_error().detail)
    result = envelope(
        mode="live",
        request_id=request_id,
        status="ok" if discovery.results else "empty",
        data=discovery.results,
        coverage=discovery.coverage,
        warnings=discovery.coverage.warnings,
        quota=QuotaEstimate(profile_id=services.profile.profile_id),
    )
    text = render_ranked_results(
        discovery.results, mode="live", coverage=discovery.coverage
    )
    return _ranked_result(result, text)


async def recommend(
    services: LiveDerivedServices, params: Mapping[str, Any] | None
) -> CallToolResult:
    request_id = uuid4().hex
    try:
        try:
            inputs = _RecommendInput.model_validate(_arguments(params))
        except ValidationError:
            raise _invalid(
                "Invalid recommendation parameters.",
                "Use the advertised filters and a limit from 1 to 50.",
            ) from None
        if inputs.snapshot_id is None:
            raise _unavailable(
                "Live recommendations need a library snapshot from this account.",
                "Run get_library and pass the snapshot ID it returns.",
            )
        binding = await services.accounts.require_binding()
        now = datetime.now(UTC)
        snapshot = await services.snapshots.get_snapshot(
            binding, inputs.snapshot_id, now=now
        )
        if snapshot is None:
            raise _unavailable(
                "The requested library snapshot is unavailable for the active account.",
                "Run get_library and use the snapshot ID it returns.",
            )
        service = services.recommendations
        query = service.search_query(snapshot, binding=binding, now=now, filters=inputs)
        async with _reserved(
            services,
            binding,
            request_id,
            "recommend",
            _RECOMMEND_CALLS,
            candidate_cap=_BOUNDS.video_candidates,
        ) as context:
            pool = await DiscoveryService(
                services.provider, _BOUNDS, permits=services.permits
            ).video_candidates(context, query)
            deadline = context.deadline
        if await services.accounts.require_binding() != binding:
            raise _unavailable(
                "The active account changed during the request.",
                "Run get_library again for the current account.",
            )
        candidates = CandidateSet(
            candidate_set_id=f"recommend-{request_id}",
            binding=binding,
            videos=pool.videos,
            source="live-profile-discovery",
            seed_video_id=None,
            topic=inputs.topic,
            coverage=pool.coverage.model_copy(
                update={
                    "limits": {
                        **pool.coverage.limits,
                        "candidates": _BOUNDS.video_candidates,
                    }
                }
            ),
            ranking_version=PROFILE_VERSION,
            config_version=LIVE_CONFIG_VERSION,
            created_at=now,
            expires_at=deadline,
        )
        result = service.recommend(
            snapshot, candidates, binding=binding, now=datetime.now(UTC), filters=inputs
        )
    except ContractError as error:
        return _recommendation_error(request_id, error.detail, mode="live")
    except (OSError, SqliteError, ValidationError):
        return _recommendation_error(request_id, _storage_error().detail, mode="live")
    return _recommendation_response(
        request_id,
        result,
        quota=QuotaEstimate(profile_id=services.profile.profile_id),
        mode="live",
    )


async def analyse(
    services: LiveDerivedServices, params: Mapping[str, Any] | None
) -> CallToolResult:
    request_id = uuid4().hex
    envelope = ResultEnvelope[AnalysisReport]
    try:
        raw = _arguments(params)
        if isinstance(raw.get("sources"), list):
            raw["sources"] = tuple(raw["sources"])
        try:
            parsed = _AnalyseInput.model_validate(raw)
        except ValidationError:
            raise _invalid(
                "Invalid analyse_library parameters.",
                "Provide an optional snapshot_id, optional sources, and optional "
                "non-overlapping UTC ISO-8601 period_a and period_b objects.",
            ) from None
        validate_period_pair(parsed.period_a, parsed.period_b)
        binding = await services.accounts.require_binding()
        if not services.permits(binding):
            # Check before collecting, so a closed gate makes zero provider calls.
            raise ContractError(
                ErrorDetail(
                    code="POLICY_BLOCKED",
                    message="Live derived library analytics is pending D-02 policy clearance.",
                    retryable=False,
                    safe_next_action="Record the instructor's D-02 direction first.",
                )
            )
        snapshot_id = parsed.snapshot_id
        if snapshot_id is None:
            collected = await services.library.collect(
                cancellation=_NotCancelled(), sources=parsed.sources
            )
            snapshot_id = collected.snapshot.snapshot_id
        outcome = await services.analysis.analyse_stored_snapshot(
            binding=binding,
            snapshot_id=snapshot_id,
            sources=parsed.sources,
            period_a=parsed.period_a,
            period_b=parsed.period_b,
        )
    except ContractError as error:
        return _error(envelope, request_id, error.detail)
    except (OSError, SqliteError):
        return _error(envelope, request_id, _storage_error().detail)
    result = envelope(
        mode="live",
        request_id=request_id,
        status="ok",
        data=outcome.report,
        warnings=outcome.report.warnings,
        quota=QuotaEstimate(profile_id=services.profile.profile_id),
    )
    return CallToolResult(
        structured_content=result.model_dump(),
        content=[TextContent(type="text", text=outcome.rendered_text)],
    )


async def propose(
    services: LiveDerivedServices, params: Mapping[str, Any] | None
) -> CallToolResult:
    request_id = uuid4().hex
    envelope = ResultEnvelope[PlaylistProposal]
    fields = _arguments(params)
    try:
        try:
            references = _PreviewReferences.model_validate(
                {
                    "candidate_set_id": fields.pop("candidate_set_id", None),
                    "workflow_id": fields.pop("workflow_id", None),
                }
            )
        except ValidationError as error:
            raise planning_error(
                "INVALID_INPUT",
                "Invalid workflow or candidate set reference.",
                "Use the candidate set ID returned by find_similar_videos.",
            ) from error
        if references.candidate_set_id is None:
            raise planning_error(
                "CONTENT_UNAVAILABLE",
                "Live playlist planning needs a candidate set from this account.",
                "Run find_similar_videos and pass the candidate set ID it returns.",
            )
        request = parse_playlist_request(fields)
        binding = await services.accounts.require_binding()
        status = await services.accounts.current()
        destination = (
            status.channel_title
            if status is not None and status.binding == binding
            else binding.channel_id
        )
        candidate_set_id = references.candidate_set_id

        async def plan_and_save() -> tuple[PlaylistProposal, CandidateSet]:
            now = datetime.now(UTC)
            candidates = await services.candidate_sets.load(
                candidate_set_id, binding, now=now
            )
            if candidates is None:
                raise planning_error(
                    "CONTENT_UNAVAILABLE",
                    "The requested candidate set is missing or expired.",
                    "Run find_similar_videos again and use the returned candidate set ID.",
                )
            proposal = services.planner.plan(
                request,
                candidates,
                binding=binding,
                destination_channel_title=destination,
                proposal_id=uuid4().hex,
                now=now,
            )
            try:
                await services.proposals.save_proposal(proposal)
            except (OSError, SqliteError, RepositoryConflict) as error:
                raise planning_error(
                    "PROVIDER_UNAVAILABLE",
                    "The proposal could not be saved to local storage.",
                    "Check access to the live database and try again.",
                ) from error
            return proposal, candidates

        if references.workflow_id is None:
            proposal, candidates = await plan_and_save()
            note = PREVIEW_ONLY_NOTE
        else:
            async with services.workflows.stage(
                references.workflow_id,
                "propose_playlist",
                binding=binding,
                request_id=request_id,
                cancellation=_NotCancelled(),
                candidate_set_id=candidate_set_id,
            ) as access:
                proposal, candidates = await plan_and_save()
                access.proposal_ref = proposal.ref
            note = WORKFLOW_PREVIEW_NOTE
    except ContractError as error:
        return _error(envelope, request_id, error.detail)
    except (OSError, SqliteError):
        return _error(envelope, request_id, _storage_error().detail)
    result = envelope(
        mode="live",
        request_id=request_id,
        status="ok",
        data=proposal,
        warnings=(*proposal.warnings, note),
        coverage=candidates.coverage,
    )
    return CallToolResult(
        structured_content=result.model_dump(),
        content=[
            TextContent(type="text", text=f"{render_proposal(proposal)}\n\n{note}")
        ],
    )
