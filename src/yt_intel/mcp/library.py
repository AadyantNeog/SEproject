import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import anyio
from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp_types import CallToolResult, TextContent, ToolAnnotations
from pydantic import ValidationError

from yt_intel.analytics.periods import TimePeriod
from yt_intel.analytics.summaries import AnalysisReport
from yt_intel.client_skills import project_file
from yt_intel.contracts.account import (
    AccountService,
    AccountStatus,
    DisconnectResult,
)
from yt_intel.contracts.common import AccountBinding, Contract, Label, OpaqueId
from yt_intel.contracts.errors import (
    ContractError,
    ErrorDetail,
    QuotaEstimate,
    ResultEnvelope,
)
from yt_intel.contracts.models import Coverage, LibrarySource, Video
from yt_intel.contracts.workflow import (
    CallCeiling,
    QuotaLedger,
    RequestContext,
    WorkflowPlan,
)
from yt_intel.domain.identifiers import parse_video_id
from yt_intel.infrastructure.database import Database
from yt_intel.infrastructure.quota import QuotaProfile, SqliteQuotaLedger
from yt_intel.infrastructure.repositories import (
    SqliteAccountDataRepository,
    SqliteSnapshotRepository,
)
from yt_intel.presentation.results import render_error
from yt_intel.providers.fixture import FixtureDataset, FixtureYouTubeProvider
from yt_intel.services.analysis import AnalysisService
from yt_intel.services.library import LibraryBounds, LibraryService, LibrarySummary

_FIXTURE_ACCOUNT = AccountBinding(
    installation_id="fixture-installation",
    credential_binding_id="fixture-binding",
    channel_id="UCaaaaaaaaaaaaaaaaaaaaaa",
    mode="fixture",
)
_QUOTA_PROFILE_ID = "youtube-2026-11-16"


class _GetVideoInput(Contract):
    video: Label


class _GetLibraryInput(Contract):
    sources: tuple[LibrarySource, ...] | None = None
    continuation_ref: OpaqueId | None = None


class _AnalyseLibraryInput(Contract):
    snapshot_id: OpaqueId | None = None
    sources: tuple[LibrarySource, ...] | None = None
    period_a: TimePeriod | None = None
    period_b: TimePeriod | None = None


class _FixtureCancellation:
    def is_cancelled(self) -> bool:
        return False

    async def wait(self) -> None:
        await anyio.sleep_forever()


class _FixtureAccountService(AccountService):
    """In-memory synthetic fixture AccountService backed by Paul's SQLite deletion repo."""

    def __init__(
        self,
        binding: AccountBinding,
        account_data: SqliteAccountDataRepository,
    ) -> None:
        self._binding: AccountBinding | None = binding
        self._account_data = account_data

    async def current(self) -> AccountStatus | None:
        if self._binding is None:
            return None
        return AccountStatus(
            binding=self._binding,
            channel_title="Fixture Learning Channel",
            scopes=("https://www.googleapis.com/auth/youtube.readonly",),
        )

    async def require_binding(
        self, *, required_scopes: tuple[Label, ...] = ()
    ) -> AccountBinding:
        if self._binding is None:
            raise ContractError(
                ErrorDetail(
                    code="AUTH_REQUIRED",
                    message="Fixture account has been disconnected.",
                    retryable=False,
                    safe_next_action="Restart the fixture server to reconnect the synthetic account.",
                )
            )
        return self._binding

    async def disconnect(self, binding: AccountBinding) -> DisconnectResult:
        if self._binding is None:
            raise ContractError(
                ErrorDetail(
                    code="AUTH_REQUIRED",
                    message="No fixture account is currently connected.",
                    retryable=False,
                    safe_next_action="Nothing to disconnect.",
                )
            )
        if self._binding != binding:
            raise ContractError(
                ErrorDetail(
                    code="ACCOUNT_MISMATCH",
                    message="Foreign account binding cannot be disconnected.",
                    retryable=False,
                    safe_next_action="Inspect get_account_status for the active account.",
                )
            )
        await self._account_data.delete_account(binding)
        self._binding = None
        return DisconnectResult(
            local_data_removed=True,
            tokens_removed=True,
            revoked=False,
            warnings=(),
        )


def _error_result(
    problem: ErrorDetail, *, request_id: str, mode: str = "fixture"
) -> CallToolResult:
    envelope = ResultEnvelope[None](
        mode="fixture" if mode == "fixture" else "live",
        request_id=request_id,
        status="error",
        data=None,
        error=problem,
    )
    return CallToolResult(
        is_error=True,
        structured_content=envelope.model_dump(),
        content=[TextContent(type="text", text=render_error(problem, mode="fixture"))],
    )


def register_fixture_library(
    server: MCPServer[None],
    project_root: Path,
    fixture_db: Path | None,
) -> None:
    """Register Jeswin's get_video, get_library, get_account_status, and disconnect_account tools."""
    catalog_path = project_file(
        project_root, Path("tests/fixtures/libraries/library_catalog.json")
    )
    if not catalog_path.is_file():
        catalog_path = project_file(
            project_root, Path("tests/fixtures/youtube_reads/catalog.json")
        )
    profile_path = project_file(
        project_root, Path(f"config/quota-profiles/{_QUOTA_PROFILE_ID}.json")
    )
    if not catalog_path.is_file() or not profile_path.is_file():
        return

    dataset = FixtureDataset.from_json_file(catalog_path)
    profile = QuotaProfile.load(profile_path)
    runtime_holder: list[
        tuple[
            QuotaLedger,
            _FixtureAccountService,
            FixtureYouTubeProvider,
            LibraryService,
            AnalysisService,
        ]
    ] = []

    def _runtime() -> tuple[
        QuotaLedger,
        _FixtureAccountService,
        FixtureYouTubeProvider,
        LibraryService,
        AnalysisService,
    ]:
        if not runtime_holder:
            database = Database(fixture_db) if fixture_db is not None else Database()
            database.migrate()
            ledger: QuotaLedger = SqliteQuotaLedger(database, profile)
            snapshot_repo = SqliteSnapshotRepository(database)
            account_repo = SqliteAccountDataRepository(database)
            accounts = _FixtureAccountService(_FIXTURE_ACCOUNT, account_repo)
            provider = FixtureYouTubeProvider(dataset, quota_ledger=ledger)
            service = LibraryService(
                provider=provider,
                account_service=accounts,
                quota_ledger=ledger,
                quota_profile=profile,
                snapshot_repo=snapshot_repo,
                bounds=LibraryBounds(),
                project_id="fixture-project",
            )
            analysis = AnalysisService(snapshot_repo=snapshot_repo)
            runtime_holder.append((ledger, accounts, provider, service, analysis))
        return runtime_holder[0]

    @server.tool(
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False)
    )
    async def get_video(
        ctx: Context[None, object],
        video: str,
    ) -> Annotated[CallToolResult, ResultEnvelope[Video]]:
        """Fetch normalised metadata for one YouTube video URL or ID (read-only)."""
        request_id = uuid4().hex
        try:
            parsed = _GetVideoInput.model_validate(
                (ctx.request_context.params or {}).get("arguments", {})
            )
            video_id = parse_video_id(parsed.video)
            ledger, accounts, provider, _, _ = _runtime()
            binding = await accounts.require_binding()
            now = datetime.now(UTC)
            deadline = now + timedelta(seconds=30)
            plan = WorkflowPlan(
                plan_id=f"get-video-{uuid4().hex[:12]}",
                binding=binding,
                project_id="fixture-project",
                quota_profile_id=profile.profile_id,
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
            plan = plan.model_copy(update={"buckets": profile.required_buckets(plan)})
            reservation = await ledger.reserve(plan)
            try:
                req_ctx = RequestContext(
                    request_id=request_id,
                    binding=binding,
                    reservation_id=reservation.reservation_id,
                    deadline=deadline,
                    cancellation=_FixtureCancellation(),
                )
                batch = await provider.get_videos(req_ctx, (video_id,))
            finally:
                await ledger.release(reservation.reservation_id)
            item = batch.videos.get(video_id)
            if item is None:
                raise ContractError(
                    ErrorDetail(
                        code="CONTENT_UNAVAILABLE",
                        message="Requested video is unavailable in this fixture dataset.",
                        retryable=False,
                        safe_next_action="Supply an accessible video ID or URL.",
                    )
                )
        except ValidationError:
            return _error_result(
                ErrorDetail(
                    code="INVALID_INPUT",
                    message="get_video expects a single 'video' URL or ID string.",
                    retryable=False,
                    safe_next_action="Provide a valid YouTube video URL or 11-character ID.",
                ),
                request_id=request_id,
            )
        except ContractError as exc:
            return _error_result(exc.detail, request_id=request_id)

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
            mode="fixture",
            request_id=request_id,
            status="ok",
            data=item,
            warnings=item.evidence_warnings,
            coverage=coverage,
            quota=QuotaEstimate(profile_id=profile.profile_id),
        )
        return CallToolResult(
            structured_content=envelope.model_dump(),
            content=[
                TextContent(
                    type="text",
                    text=f"[fixture] {item.title} ({item.canonical_url})",
                )
            ],
        )

    @server.tool(
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False)
    )
    async def get_library(
        ctx: Context[None, object],
        sources: list[LibrarySource] | None = None,
        continuation_ref: str | None = None,
    ) -> Annotated[CallToolResult, ResultEnvelope[LibrarySummary]]:
        """Collect bounded authorised library signals and return a snapshot summary."""
        request_id = uuid4().hex
        try:
            raw_args = (ctx.request_context.params or {}).get("arguments") or {}
            if "sources" in raw_args and isinstance(raw_args["sources"], list):
                raw_args = {**raw_args, "sources": tuple(raw_args["sources"])}
            parsed = _GetLibraryInput.model_validate(raw_args)
            _, _, _, service, _ = _runtime()
            result = await service.collect(
                cancellation=_FixtureCancellation(),
                sources=parsed.sources,
                continuation_ref=parsed.continuation_ref,
            )
        except ValidationError:
            return _error_result(
                ErrorDetail(
                    code="INVALID_INPUT",
                    message="Invalid get_library parameters.",
                    retryable=False,
                    safe_next_action="Specify sources from likes, subscriptions, playlists and an optional continuation_ref.",
                ),
                request_id=request_id,
            )
        except ContractError as exc:
            return _error_result(exc.detail, request_id=request_id)

        envelope = ResultEnvelope[LibrarySummary](
            mode="fixture",
            request_id=request_id,
            status="ok",
            data=result.summary,
            warnings=result.summary.warnings,
            quota=QuotaEstimate(profile_id=profile.profile_id),
        )
        return CallToolResult(
            structured_content=envelope.model_dump(),
            content=[
                TextContent(
                    type="text",
                    text=(
                        f"[fixture] Snapshot {result.summary.snapshot_id}: "
                        f"{result.summary.likes_count} likes, "
                        f"{result.summary.subscriptions_count} subscriptions, "
                        f"{result.summary.playlist_occurrences_count} playlist occurrences "
                        f"({result.summary.unique_videos_count} unique videos)."
                    ),
                )
            ],
        )

    @server.tool(
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False)
    )
    async def get_account_status(
        ctx: Context[None, object],
    ) -> Annotated[CallToolResult, ResultEnvelope[AccountStatus | None]]:
        """Return non-secret authorisation and channel binding status."""
        request_id = uuid4().hex
        if (ctx.request_context.params or {}).get("arguments"):
            return _error_result(
                ErrorDetail(
                    code="INVALID_INPUT",
                    message="get_account_status does not accept arguments.",
                    retryable=False,
                    safe_next_action="Call get_account_status with empty arguments.",
                ),
                request_id=request_id,
            )
        _, accounts, _, _, _ = _runtime()
        status = await accounts.current()
        envelope = ResultEnvelope[AccountStatus | None](
            mode="fixture",
            request_id=request_id,
            status="ok" if status is not None else "empty",
            data=status,
        )
        text = (
            f"[fixture] Connected channel: {status.channel_title} ({status.binding.channel_id})"
            if status is not None
            else "[fixture] No account connected. Run `yt-intel auth --read` locally."
        )
        return CallToolResult(
            structured_content=envelope.model_dump(),
            content=[TextContent(type="text", text=text)],
        )

    @server.tool(
        annotations=ToolAnnotations(read_only_hint=False, open_world_hint=False)
    )
    async def disconnect_account(
        ctx: Context[None, object],
    ) -> Annotated[CallToolResult, ResultEnvelope[DisconnectResult]]:
        """Disconnect the active account and remove local account-bound data."""
        request_id = uuid4().hex
        if (ctx.request_context.params or {}).get("arguments"):
            return _error_result(
                ErrorDetail(
                    code="INVALID_INPUT",
                    message="disconnect_account does not accept arguments.",
                    retryable=False,
                    safe_next_action="Call disconnect_account with empty arguments.",
                ),
                request_id=request_id,
            )
        try:
            _, accounts, _, _, _ = _runtime()
            binding = await accounts.require_binding()
            result = await accounts.disconnect(binding)
        except ContractError as exc:
            return _error_result(exc.detail, request_id=request_id)

        envelope = ResultEnvelope[DisconnectResult](
            mode="fixture",
            request_id=request_id,
            status="ok",
            data=result,
        )
        return CallToolResult(
            structured_content=envelope.model_dump(),
            content=[
                TextContent(
                    type="text",
                    text=(
                        f"[fixture] Disconnected account (local_data_removed={result.local_data_removed}, "
                        f"tokens_removed={result.tokens_removed}, revoked={result.revoked})."
                    ),
                )
            ],
        )

    @server.tool(
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False)
    )
    async def analyse_library(
        ctx: Context[None, object],
        snapshot_id: str | None = None,
        sources: list[LibrarySource] | None = None,
        period_a: dict[str, object] | None = None,
        period_b: dict[str, object] | None = None,
    ) -> Annotated[CallToolResult, ResultEnvelope[AnalysisReport]]:
        """Analyse an authorised library snapshot with optional valid-timestamp period comparison."""
        request_id = uuid4().hex
        try:
            raw_args = (ctx.request_context.params or {}).get("arguments") or {}
            parsed = _AnalyseLibraryInput.model_validate_json(json.dumps(raw_args))
            _, accounts, _, library_service, analysis_service = _runtime()
            binding = await accounts.require_binding()
            target_snapshot_id = parsed.snapshot_id
            if target_snapshot_id is None:
                collected = await library_service.collect(
                    cancellation=_FixtureCancellation(),
                    sources=parsed.sources,
                )
                target_snapshot_id = collected.snapshot.snapshot_id
            outcome = await analysis_service.analyse_stored_snapshot(
                binding=binding,
                snapshot_id=target_snapshot_id,
                sources=parsed.sources,
                period_a=parsed.period_a,
                period_b=parsed.period_b,
            )
        except ValidationError:
            return _error_result(
                ErrorDetail(
                    code="INVALID_INPUT",
                    message="Invalid analyse_library parameters.",
                    retryable=False,
                    safe_next_action=(
                        "Provide an optional snapshot_id, optional sources, and optional "
                        "non-overlapping UTC ISO-8601 period_a and period_b objects."
                    ),
                ),
                request_id=request_id,
            )
        except ContractError as exc:
            return _error_result(exc.detail, request_id=request_id)

        envelope = ResultEnvelope[AnalysisReport](
            mode="fixture",
            request_id=request_id,
            status="ok",
            data=outcome.report,
            warnings=outcome.report.warnings,
            quota=QuotaEstimate(profile_id=profile.profile_id),
        )
        return CallToolResult(
            structured_content=envelope.model_dump(),
            content=[TextContent(type="text", text=outcome.rendered_text)],
        )
