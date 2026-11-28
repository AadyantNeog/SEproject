"""Live MCP composition: the authorised account, the OAuth vault and official API reads.

It wires the real pieces together: the saved OAuth account from
`yt-intel auth`, its OS-protected vault, the quota-accounted HTTP executor,
the persistent SQLite ledger and the official YouTube Data API read
provider. The non-derived tools are account status, disconnect,
single-video metadata and authorised library retrieval.

Derived processing is similarity (FR-1, FR-2), recommendations (FR-3),
analysis (FR-4) and the playlist proposal built on FR-1 (FR-5). It depends on
D-02. Until a human records a D-02 resolution in the reviewed record, those
tools return `POLICY_BLOCKED` with zero provider calls. Once it is resolved,
they run the live handlers in `live_derived.py` (ADR-0011 step two). They
never fall back to fixtures.

`begin_workflow` and live playlist creation are not part of this build, so
`propose_playlist` stores a preview only. No tool here can create, modify or
delete anything on YouTube.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

import anyio
import httpx
from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp_types import CallToolResult, TextContent, ToolAnnotations
from pydantic import ValidationError

from yt_intel.analytics.summaries import AnalysisReport
from yt_intel.auth.account import JsonAccountStateStore, LocalAccountService
from yt_intel.auth.oauth import OAuthClient, load_oauth_client_config
from yt_intel.auth.vault import KeyringTokenVault
from yt_intel.contracts.account import AccountStatus, DisconnectResult, TokenVault
from yt_intel.contracts.common import (
    Contract,
    Label,
    LanguageTag,
    Limit,
    OpaqueId,
    Positive,
)
from yt_intel.contracts.errors import (
    ContractError,
    ErrorDetail,
    QuotaEstimate,
    ResultEnvelope,
)
from yt_intel.contracts.models import Coverage, LibrarySource, RankedChannel, Video
from yt_intel.contracts.proposals import PlaylistProposal, Privacy
from yt_intel.contracts.workflow import CallCeiling, Clock, RequestContext, WorkflowPlan
from yt_intel.domain.identifiers import parse_video_id
from yt_intel.domain.language import normalize_language_tag
from yt_intel.domain.proposals import PlaylistPlanner
from yt_intel.infrastructure.database import Database
from yt_intel.infrastructure.http import AccountedHttpExecutor
from yt_intel.infrastructure.quota import QuotaProfile, SqliteQuotaLedger
from yt_intel.infrastructure.repositories import (
    SqliteAccountDataRepository,
    SqliteCacheRepository,
    SqliteProposalRepository,
    SqliteSnapshotRepository,
)
from yt_intel.policy import D02_RECORD, policy_resolved, recorded_policy_check
from yt_intel.presentation.results import render_error
from yt_intel.providers.youtube import LiveYouTubeReadProvider
from yt_intel.services.analysis import AnalysisService
from yt_intel.services.library import LibraryBounds, LibraryService, LibrarySummary
from yt_intel.services.recommendations import (
    RecommendationResult,
    RecommendationService,
)

from . import live_derived
from .live_derived import LiveDerivedServices, live_candidate_sets

LIVE_PROJECT_ID = "default-project"
QUOTA_PROFILE = Path("config/quota-profiles/youtube-2026-11-16.json")
DERIVED_TOOLS = (
    "find_similar_videos",
    "find_similar_channels",
    "recommend_videos",
    "analyse_library",
    "begin_workflow",
    "propose_playlist",
)
LIVE_DERIVED_TOOLS = tuple(tool for tool in DERIVED_TOOLS if tool != "begin_workflow")
_READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=True)


class LiveStatus(Contract):
    provider: Literal["live"] = "live"
    account_connected: bool
    d02_resolved: bool
    available_tools: tuple[str, ...]
    blocked_tools: tuple[str, ...]


class _GetVideoInput(Contract):
    video: Label


class _GetLibraryInput(Contract):
    sources: tuple[LibrarySource, ...] | None = None
    continuation_ref: OpaqueId | None = None


class _NotCancelled:
    def is_cancelled(self) -> bool:
        return False

    async def wait(self) -> None:
        await anyio.sleep_forever()


@dataclass(frozen=True, slots=True)
class LiveRuntime:
    accounts: LocalAccountService
    profile: QuotaProfile
    ledger: SqliteQuotaLedger
    provider: LiveYouTubeReadProvider
    library: LibraryService
    executors: tuple[AccountedHttpExecutor, ...]
    policy_path: Path
    derived: LiveDerivedServices


def _envelope_result[T](
    envelope: ResultEnvelope[T], text: str, *, is_error: bool = False
) -> CallToolResult:
    return CallToolResult(
        is_error=is_error,
        structured_content=envelope.model_dump(),
        content=[TextContent(type="text", text=text)],
    )


def _error(problem: ErrorDetail, request_id: OpaqueId) -> CallToolResult:
    envelope = ResultEnvelope[None](
        mode="live", request_id=request_id, status="error", data=None, error=problem
    )
    return _envelope_result(envelope, render_error(problem, mode="live"), is_error=True)


def _blocked(runtime: LiveRuntime, tool: str) -> CallToolResult:
    request_id = uuid4().hex
    if not policy_resolved(runtime.policy_path):
        problem = ErrorDetail(
            code="POLICY_BLOCKED",
            message=(
                f"{tool} uses derived processing of live YouTube data, which is "
                "disabled until D-02 has a recorded resolution."
            ),
            retryable=False,
            safe_next_action=(
                "Use the fixture server for this feature, or record the instructor's "
                "D-02 direction first."
            ),
        )
    else:
        problem = ErrorDetail(
            code="PROVIDER_UNAVAILABLE",
            message=f"{tool} is not available in live mode in this build.",
            retryable=False,
            safe_next_action="Use the fixture server for this feature.",
        )
    envelope = ResultEnvelope[None](
        mode="live", request_id=request_id, status="blocked", data=None, error=problem
    )
    return _envelope_result(envelope, render_error(problem, mode="live"), is_error=True)


def build_live_runtime(
    *,
    project_root: Path,
    database_path: Path,
    client_secrets_path: Path,
    account_state_path: Path | None = None,
    vault: TokenVault | None = None,
    policy_path: Path | None = None,
    clock: Clock | None = None,
    oauth_transport: httpx.AsyncBaseTransport | None = None,
    api_transport: httpx.AsyncBaseTransport | None = None,
) -> LiveRuntime:
    """Compose live services. No network or vault access happens here."""
    database = Database(database_path)
    database.migrate()
    profile = QuotaProfile.load(project_root / QUOTA_PROFILE)
    ledger = SqliteQuotaLedger(database, profile, clock=clock)
    oauth_executor = AccountedHttpExecutor(
        quota_ledger=ledger, transport=oauth_transport, clock=clock
    )
    accounts = LocalAccountService(
        installation_id="local-cli",
        mode="live",
        vault=vault if vault is not None else KeyringTokenVault(),
        oauth_client=OAuthClient(
            load_oauth_client_config(client_secrets_path), oauth_executor, clock=clock
        ),
        account_data=SqliteAccountDataRepository(database, clock=clock),
        clock=clock,
        state_store=JsonAccountStateStore(
            account_state_path or database_path.with_name("account-live.json")
        ),
    )
    read_executor = AccountedHttpExecutor(
        quota_ledger=ledger, auth_headers=accounts, transport=api_transport, clock=clock
    )
    provider = LiveYouTubeReadProvider(read_executor, clock=clock)
    resolved_policy = policy_path or project_root / D02_RECORD
    permits = recorded_policy_check(resolved_policy)
    snapshots = SqliteSnapshotRepository(database, clock=clock)
    library = LibraryService(
        provider=provider,
        account_service=accounts,
        quota_ledger=ledger,
        quota_profile=profile,
        snapshot_repo=snapshots,
        clock=clock,
        bounds=LibraryBounds(),
        project_id=LIVE_PROJECT_ID,
    )
    derived = LiveDerivedServices(
        accounts=accounts,
        profile=profile,
        ledger=ledger,
        provider=provider,
        library=library,
        snapshots=snapshots,
        proposals=SqliteProposalRepository(database, clock=clock),
        candidate_sets=live_candidate_sets(
            lambda: SqliteCacheRepository(database, clock=clock), permits
        ),
        analysis=AnalysisService(snapshot_repo=snapshots, clock=clock, permits=permits),
        recommendations=RecommendationService(normalize_language_tag, permits=permits),
        planner=PlaylistPlanner(normalize_language_tag, permits=permits),
        permits=permits,
        project_id=LIVE_PROJECT_ID,
    )
    return LiveRuntime(
        accounts=accounts,
        profile=profile,
        ledger=ledger,
        provider=provider,
        library=library,
        executors=(oauth_executor, read_executor),
        policy_path=resolved_policy,
        derived=derived,
    )


def build_live_server(runtime: LiveRuntime) -> MCPServer[None]:
    server: MCPServer[None] = MCPServer("YouTube Video Intelligence (live)")
    available = (
        "live_status",
        "get_account_status",
        "disconnect_account",
        "get_video",
        "get_library",
    )

    @server.tool(
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False)
    )
    async def live_status() -> Annotated[CallToolResult, ResultEnvelope[LiveStatus]]:
        """Report live-mode readiness: account, D-02 state and which tools are blocked."""
        resolved = policy_resolved(runtime.policy_path)
        status = LiveStatus(
            account_connected=await runtime.accounts.current() is not None,
            d02_resolved=resolved,
            available_tools=(*available, *LIVE_DERIVED_TOOLS)
            if resolved
            else available,
            blocked_tools=("begin_workflow",) if resolved else DERIVED_TOOLS,
        )
        envelope = ResultEnvelope[LiveStatus](
            mode="live", request_id=uuid4().hex, status="ok", data=status
        )
        text = (
            "Mode: live\n"
            f"Account connected: {'yes' if status.account_connected else 'no'}\n"
            f"D-02 resolved: {'yes' if status.d02_resolved else 'no'}\n"
            f"Available: {', '.join(status.available_tools)}\n"
            f"Blocked: {', '.join(status.blocked_tools)}"
        )
        return _envelope_result(envelope, text)

    @server.tool(
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False)
    )
    async def get_account_status() -> Annotated[
        CallToolResult, ResultEnvelope[AccountStatus | None]
    ]:
        """Return the non-secret binding and scopes of the saved live account."""
        status = await runtime.accounts.current()
        envelope = ResultEnvelope[AccountStatus | None](
            mode="live",
            request_id=uuid4().hex,
            status="ok" if status is not None else "empty",
            data=status,
        )
        text = (
            f"Mode: live\nConnected channel: {status.binding.channel_id} "
            f"(scopes: {', '.join(status.scopes)})"
            if status is not None
            else "Mode: live\nNo account connected. Run `yt-intel auth --read` locally."
        )
        return _envelope_result(envelope, text)

    @server.tool(
        annotations=ToolAnnotations(read_only_hint=False, open_world_hint=True)
    )
    async def disconnect_account() -> Annotated[
        CallToolResult, ResultEnvelope[DisconnectResult]
    ]:
        """Revoke the live account and delete its tokens and local data."""
        request_id = uuid4().hex
        try:
            binding = await runtime.accounts.require_binding()
            result = await runtime.accounts.disconnect(binding)
        except ContractError as error:
            return _error(error.detail, request_id)
        envelope = ResultEnvelope[DisconnectResult](
            mode="live",
            request_id=request_id,
            status="ok",
            data=result,
            warnings=tuple(warning.message for warning in result.warnings),
        )
        text = (
            "Mode: live\nDisconnected "
            f"(revoked={result.revoked}, tokens_removed={result.tokens_removed}, "
            f"local_data_removed={result.local_data_removed})."
        )
        return _envelope_result(envelope, text)

    @server.tool(annotations=_READ_ONLY)
    async def get_video(
        ctx: Context[None, object], video: str
    ) -> Annotated[CallToolResult, ResultEnvelope[Video]]:
        """Fetch official metadata for one YouTube video URL or ID (read-only)."""
        request_id = uuid4().hex
        try:
            inputs = _GetVideoInput.model_validate(
                (ctx.request_context.params or {}).get("arguments", {})
            )
            video_id = parse_video_id(inputs.video)
            binding = await runtime.accounts.require_binding()
            deadline = datetime.now(UTC) + timedelta(seconds=30)
            plan = WorkflowPlan(
                plan_id=f"live-get-video-{uuid4().hex[:12]}",
                binding=binding,
                project_id=LIVE_PROJECT_ID,
                quota_profile_id=runtime.profile.profile_id,
                endpoint_ceilings={
                    "videos.list": CallCeiling(calls=1, attempts_per_call=3)
                },
                buckets={},
                candidate_cap=1,
                page_cap=1,
                sample_cap=0,
                deadline=deadline,
                cancellation_policy="cooperative",
                reconciliation_allowance={},
            )
            plan = plan.model_copy(
                update={"buckets": runtime.profile.required_buckets(plan)}
            )
            reservation = await runtime.ledger.reserve(plan)
            try:
                batch = await runtime.provider.get_videos(
                    RequestContext(
                        request_id=request_id,
                        binding=binding,
                        reservation_id=reservation.reservation_id,
                        deadline=deadline,
                        cancellation=_NotCancelled(),
                    ),
                    (video_id,),
                )
            finally:
                with anyio.CancelScope(shield=True):
                    await runtime.ledger.release(reservation.reservation_id)
            item = batch.videos.get(video_id)
            if item is None:
                raise ContractError(
                    ErrorDetail(
                        code="CONTENT_UNAVAILABLE",
                        message="The video is private, deleted or unavailable.",
                        retryable=False,
                        safe_next_action="Supply an accessible video ID or URL.",
                    )
                )
        except ValidationError:
            return _error(
                ErrorDetail(
                    code="INVALID_INPUT",
                    message="get_video expects a single 'video' URL or ID string.",
                    retryable=False,
                    safe_next_action="Provide a valid YouTube video URL or ID.",
                ),
                request_id,
            )
        except ContractError as error:
            return _error(error.detail, request_id)
        coverage = Coverage(
            complete=True,
            paginated=False,
            sampled=False,
            truncated=False,
            retrieved=1,
            usable=1 if item.availability == "available" else 0,
            inaccessible=1 if item.availability == "inaccessible" else 0,
            unknown=1 if item.availability == "unknown" else 0,
            limits={"videos": 1},
            completeness_basis="Single video lookup",
        )
        envelope = ResultEnvelope[Video](
            mode="live",
            request_id=request_id,
            status="ok",
            data=item,
            warnings=item.evidence_warnings,
            coverage=coverage,
            quota=QuotaEstimate(profile_id=runtime.profile.profile_id),
        )
        return _envelope_result(
            envelope, f"Mode: live\n{item.title} ({item.canonical_url})"
        )

    @server.tool(annotations=_READ_ONLY)
    async def get_library(
        ctx: Context[None, object],
        sources: list[LibrarySource] | None = None,
        continuation_ref: str | None = None,
    ) -> Annotated[CallToolResult, ResultEnvelope[LibrarySummary]]:
        """Collect bounded authorised likes, subscriptions and playlists (read-only)."""
        request_id = uuid4().hex
        try:
            raw = dict((ctx.request_context.params or {}).get("arguments") or {})
            if isinstance(raw.get("sources"), list):
                raw["sources"] = tuple(raw["sources"])
            parsed = _GetLibraryInput.model_validate(raw)
            result = await runtime.library.collect(
                cancellation=_NotCancelled(),
                sources=parsed.sources,
                continuation_ref=parsed.continuation_ref,
            )
        except ValidationError:
            return _error(
                ErrorDetail(
                    code="INVALID_INPUT",
                    message="Invalid get_library parameters.",
                    retryable=False,
                    safe_next_action="Use sources from likes, subscriptions and playlists.",
                ),
                request_id,
            )
        except ContractError as error:
            return _error(error.detail, request_id)
        summary = result.summary
        envelope = ResultEnvelope[LibrarySummary](
            mode="live",
            request_id=request_id,
            status="ok",
            data=summary,
            warnings=summary.warnings,
            quota=QuotaEstimate(profile_id=runtime.profile.profile_id),
        )
        text = (
            f"Mode: live\nSnapshot {summary.snapshot_id}: {summary.likes_count} likes, "
            f"{summary.subscriptions_count} subscriptions, "
            f"{summary.playlist_occurrences_count} playlist occurrences."
        )
        return _envelope_result(envelope, text)

    # Derived tools. Each checks the reviewed D-02 record on every call, before
    # any provider call, and the shared services check it again.
    def _params(ctx: Context[None, object]) -> dict[str, object]:
        return dict(ctx.request_context.params or {})

    @server.tool(annotations=_READ_ONLY)
    async def find_similar_videos(
        ctx: Context[None, object],
        video: Label,
        limit: Limit = 10,
        workflow_id: OpaqueId | None = None,
    ) -> Annotated[CallToolResult, live_derived.LiveVideoDiscoveryEnvelope]:
        """Rank live videos similar to a seed video (FR-1). Needs D-02 resolved."""
        if not policy_resolved(runtime.policy_path):
            return _blocked(runtime, "find_similar_videos")
        return await live_derived.similar_videos(runtime.derived, _params(ctx))

    @server.tool(annotations=_READ_ONLY)
    async def find_similar_channels(
        ctx: Context[None, object], channel: Label, limit: Limit = 10
    ) -> Annotated[CallToolResult, ResultEnvelope[tuple[RankedChannel, ...]]]:
        """Rank live channels similar to a seed channel (FR-2). Needs D-02 resolved."""
        if not policy_resolved(runtime.policy_path):
            return _blocked(runtime, "find_similar_channels")
        return await live_derived.similar_channels(runtime.derived, _params(ctx))

    @server.tool(annotations=_READ_ONLY)
    async def recommend_videos(
        ctx: Context[None, object],
        topic: Label | None = None,
        total_seconds: Positive | None = None,
        max_video_seconds: Positive | None = None,
        language: LanguageTag | None = None,
        limit: Limit = 10,
        snapshot_id: OpaqueId | None = None,
    ) -> Annotated[CallToolResult, ResultEnvelope[RecommendationResult]]:
        """Recommend live videos from a get_library snapshot (FR-3). Needs D-02 resolved."""
        if not policy_resolved(runtime.policy_path):
            return _blocked(runtime, "recommend_videos")
        return await live_derived.recommend(runtime.derived, _params(ctx))

    @server.tool(annotations=_READ_ONLY)
    async def analyse_library(
        ctx: Context[None, object],
        snapshot_id: str | None = None,
        sources: list[LibrarySource] | None = None,
        period_a: dict[str, object] | None = None,
        period_b: dict[str, object] | None = None,
    ) -> Annotated[CallToolResult, ResultEnvelope[AnalysisReport]]:
        """Analyse an authorised live library snapshot (FR-4). Needs D-02 resolved."""
        if not policy_resolved(runtime.policy_path):
            return _blocked(runtime, "analyse_library")
        return await live_derived.analyse(runtime.derived, _params(ctx))

    @server.tool(
        annotations=ToolAnnotations(read_only_hint=False, open_world_hint=False)
    )
    async def begin_workflow(
        kind: Literal["video_to_playlist"], video: str | None = None
    ) -> Annotated[CallToolResult, ResultEnvelope[None]]:
        """Not available in live mode: the workflow ends in a live write."""
        return _blocked(runtime, "begin_workflow")

    @server.tool(
        annotations=ToolAnnotations(
            read_only_hint=False, destructive_hint=False, open_world_hint=False
        )
    )
    async def propose_playlist(
        ctx: Context[None, object],
        title: str | None = None,
        topic: str | None = None,
        total_seconds: Positive | None = None,
        max_video_seconds: Positive | None = None,
        language: LanguageTag | None = None,
        description: str = "",
        privacy: Privacy = "private",
        duration_mode: Literal["max", "exact"] = "max",
        include_seed: bool = False,
        candidate_set_id: OpaqueId | None = None,
        workflow_id: OpaqueId | None = None,
    ) -> Annotated[CallToolResult, ResultEnvelope[PlaylistProposal]]:
        """Preview a playlist from a live candidate set (FR-5 planning). Preview only."""
        if not policy_resolved(runtime.policy_path):
            return _blocked(runtime, "propose_playlist")
        return await live_derived.propose(runtime.derived, _params(ctx))

    return server
