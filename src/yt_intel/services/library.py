from __future__ import annotations

import uuid
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import ceil

from yt_intel.contracts.account import AccountService
from yt_intel.contracts.common import (
    AccountBinding,
    ChannelId,
    Contract,
    FrozenMap,
    Label,
    Limit,
    NonNegative,
    OpaqueId,
    PlaylistId,
    Positive,
    UtcDateTime,
    VideoId,
)
from yt_intel.contracts.errors import ContractError, ErrorCode, ErrorDetail
from yt_intel.contracts.models import (
    Channel,
    ChannelSample,
    Coverage,
    LibrarySnapshot,
    LibrarySource,
    PlaylistOccurrence,
    SourceCoverage,
    SubscriptionSignal,
    Video,
)
from yt_intel.contracts.provider import YouTubeReadProvider
from yt_intel.contracts.repositories import SnapshotRepository
from yt_intel.contracts.workflow import (
    CallCeiling,
    CancellationToken,
    Clock,
    Endpoint,
    QuotaLedger,
    RequestContext,
    WorkflowPlan,
)
from yt_intel.infrastructure.clock import SystemClock
from yt_intel.infrastructure.quota import QuotaProfile

_ALL_SOURCES: tuple[LibrarySource, ...] = ("likes", "subscriptions", "playlists")
_SAMPLE_RULE = "first-accessible-uploads-v1"
_CONTINUATION_TTL = timedelta(minutes=10)
_MAX_RETENTION = timedelta(days=30)
_DEFAULT_DEADLINE = timedelta(seconds=60)
_MAX_BATCH_SIZE = 50


class LibraryBounds(Contract):
    """Operational caps matching MASTER_PLAN defaults."""

    total_source_pages: Positive = 12
    initial_pages_per_source: Positive = 4
    page_size: Limit = 50
    owned_playlists_cap: Positive = 3
    subscription_sample_channels: Positive = 10
    uploads_per_channel: Limit = 5


class LibrarySummary(Contract):
    """Compact non-secret summary returned by get_library (no raw private dump)."""

    snapshot_id: OpaqueId
    fetched_at: UtcDateTime
    retained_until: UtcDateTime
    likes_count: NonNegative
    subscriptions_count: NonNegative
    owned_playlists_count: NonNegative
    playlist_occurrences_count: NonNegative
    unique_videos_count: NonNegative
    sources: FrozenMap[LibrarySource, SourceCoverage]
    continuation_ref: OpaqueId | None = None
    warnings: tuple[Label, ...] = ()


@dataclass(frozen=True, slots=True)
class _ContinuationState:
    continuation_ref: OpaqueId
    binding: AccountBinding
    requested_sources: tuple[LibrarySource, ...]
    snapshot_id: OpaqueId
    tokens: Mapping[LibrarySource, str | None]
    pending_playlists: tuple[PlaylistId, ...]
    playlist_sample_limited: bool
    seen_like_ids: frozenset[VideoId]
    seen_subscription_ids: frozenset[OpaqueId]
    seen_playlist_ids: frozenset[PlaylistId]
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class LibraryCollectionResult:
    snapshot: LibrarySnapshot
    summary: LibrarySummary
    continuation_ref: OpaqueId | None


def _lib_error(
    code: ErrorCode,
    message: str,
    *,
    safe_next_action: str,
    retryable: bool = False,
) -> ContractError:
    return ContractError(
        ErrorDetail(
            code=code,
            message=message,
            retryable=retryable,
            safe_next_action=safe_next_action,
        )
    )


def _normalize_sources(
    sources: Sequence[LibrarySource] | None,
) -> tuple[LibrarySource, ...]:
    if sources is None:
        return _ALL_SOURCES
    deduped = tuple(dict.fromkeys(sources))
    if not deduped:
        raise _lib_error(
            "INVALID_INPUT",
            "At least one library source must be requested.",
            safe_next_action="Specify one or more of likes, subscriptions, or playlists.",
        )
    invalid = [s for s in deduped if s not in _ALL_SOURCES]
    if invalid:
        raise _lib_error(
            "INVALID_INPUT",
            "Unsupported library source requested.",
            safe_next_action="Choose from likes, subscriptions, and playlists.",
        )
    return deduped


def _build_library_plan(
    *,
    binding: AccountBinding,
    sources: tuple[LibrarySource, ...],
    bounds: LibraryBounds,
    deadline: datetime,
    project_id: OpaqueId,
    profile: QuotaProfile,
    pending_playlists: tuple[PlaylistId, ...],
) -> WorkflowPlan:
    """Compute conservative worst-case WorkflowPlan before any provider call."""
    ceilings: dict[Endpoint, CallCeiling] = {}
    source_pages = min(bounds.initial_pages_per_source, bounds.total_source_pages)
    video_hydration_calls = 0

    if "likes" in sources:
        # Likes uses videos.list(myRating=like)
        video_hydration_calls += source_pages

    if "subscriptions" in sources:
        ceilings["subscriptions.list"] = CallCeiling(
            calls=source_pages, attempts_per_call=3
        )
        # Bounded channel hydration + upload playlist sampling + upload video hydration
        ceilings["channels.list"] = CallCeiling(
            calls=max(1, ceil(bounds.subscription_sample_channels / _MAX_BATCH_SIZE)),
            attempts_per_call=3,
        )
        sub_pl_calls = bounds.subscription_sample_channels
        ceilings["playlistItems.list"] = CallCeiling(
            calls=sub_pl_calls, attempts_per_call=3
        )
        video_hydration_calls += bounds.subscription_sample_channels

    if "playlists" in sources:
        if pending_playlists:
            item_pages = min(len(pending_playlists), source_pages)
        else:
            ceilings["playlists.list"] = CallCeiling(calls=1, attempts_per_call=3)
            item_pages = min(bounds.owned_playlists_cap, source_pages - 1)
        if item_pages:
            existing_pi = ceilings.get("playlistItems.list")
            ceilings["playlistItems.list"] = CallCeiling(
                calls=item_pages + (existing_pi.calls if existing_pi else 0),
                attempts_per_call=3,
            )
            video_hydration_calls += ceil(
                item_pages * bounds.page_size / _MAX_BATCH_SIZE
            )

    if video_hydration_calls > 0:
        ceilings["videos.list"] = CallCeiling(
            calls=video_hydration_calls, attempts_per_call=3
        )

    plan = WorkflowPlan(
        plan_id=f"library-{uuid.uuid4().hex[:12]}",
        binding=binding,
        project_id=project_id,
        quota_profile_id=profile.profile_id,
        endpoint_ceilings=ceilings,
        buckets={},
        candidate_cap=0,
        page_cap=bounds.total_source_pages,
        sample_cap=bounds.subscription_sample_channels,
        deadline=deadline,
        cancellation_policy="cooperative",
        reconciliation_allowance={},
    )
    return plan.model_copy(update={"buckets": profile.required_buckets(plan)})


class LibraryService:
    """Authorised library retrieval with source fairness, bounds, and opaque continuation."""

    def __init__(
        self,
        *,
        provider: YouTubeReadProvider,
        account_service: AccountService,
        quota_ledger: QuotaLedger,
        quota_profile: QuotaProfile,
        snapshot_repo: SnapshotRepository,
        clock: Clock | None = None,
        bounds: LibraryBounds = LibraryBounds(),
        project_id: OpaqueId = "default-project",
    ) -> None:
        self._provider = provider
        self._accounts = account_service
        self._ledger = quota_ledger
        self._snapshots = snapshot_repo
        self._clock: Clock = clock if clock is not None else SystemClock()
        self._bounds = bounds
        self._project_id = project_id
        self._profile = quota_profile
        self._continuations: dict[OpaqueId, _ContinuationState] = {}

    async def collect(
        self,
        *,
        cancellation: CancellationToken,
        sources: Sequence[LibrarySource] | None = None,
        continuation_ref: OpaqueId | None = None,
        required_scopes: tuple[Label, ...] = (),
    ) -> LibraryCollectionResult:
        """Collect bounded authorised library signals and persist an immutable snapshot."""
        requested = _normalize_sources(sources)
        binding = await self._accounts.require_binding(required_scopes=required_scopes)
        now = self._clock.now().astimezone(UTC)

        prior_state: _ContinuationState | None = None
        if continuation_ref is not None:
            prior_state = self._resolve_continuation(
                continuation_ref, binding=binding, requested=requested, now=now
            )

        # A present cursor with no page token means the source has not started.
        tokens = (
            dict.fromkeys(requested)
            if prior_state is None
            else dict(prior_state.tokens)
        )
        pending_playlists = prior_state.pending_playlists if prior_state else ()
        active_sources = tuple(
            src
            for src in requested
            if src in tokens or (src == "playlists" and pending_playlists)
        )
        # A small page budget can postpone an entire source to the next request.
        active_sources = tuple(
            sorted(
                active_sources,
                key=lambda src: src not in tokens or tokens[src] is not None,
            )
        )
        deadline = now + _DEFAULT_DEADLINE
        plan = _build_library_plan(
            binding=binding,
            sources=active_sources,
            bounds=self._bounds,
            deadline=deadline,
            project_id=self._project_id,
            profile=self._profile,
            pending_playlists=pending_playlists,
        )
        reservation = await self._ledger.reserve(plan)
        try:
            ctx = RequestContext(
                request_id=f"lib-{uuid.uuid4().hex[:12]}",
                binding=binding,
                reservation_id=reservation.reservation_id,
                deadline=deadline,
                cancellation=cancellation,
            )
            return await self._collect_with_context(
                ctx,
                requested=requested,
                active_sources=active_sources,
                tokens=tokens,
                pending_playlists=deque(pending_playlists),
                started_at=now,
                prior=prior_state,
            )
        finally:
            await self._ledger.release(reservation.reservation_id)

    def _resolve_continuation(
        self,
        continuation_ref: OpaqueId,
        *,
        binding: AccountBinding,
        requested: tuple[LibrarySource, ...],
        now: datetime,
    ) -> _ContinuationState:
        state = self._continuations.get(continuation_ref)
        if state is None:
            raise _lib_error(
                "CONTENT_UNAVAILABLE",
                "Library continuation handle was not found.",
                safe_next_action="Start a fresh library collection without continuation_ref.",
            )
        if state.binding != binding:
            raise _lib_error(
                "ACCOUNT_MISMATCH",
                "Continuation handle belongs to a different account binding.",
                safe_next_action="Start a library collection under the currently connected account.",
            )
        if state.expires_at <= now:
            self._continuations.pop(continuation_ref, None)
            raise _lib_error(
                "CONTENT_UNAVAILABLE",
                "Library continuation handle has expired.",
                safe_next_action="Start a fresh library collection.",
            )
        if state.requested_sources != requested:
            raise _lib_error(
                "INVALID_INPUT",
                "Continuation request sources must match the original library request.",
                safe_next_action="Pass the same sources list or omit continuation_ref to start fresh.",
            )
        return state

    async def _collect_with_context(
        self,
        ctx: RequestContext,
        *,
        requested: tuple[LibrarySource, ...],
        active_sources: tuple[LibrarySource, ...],
        tokens: dict[LibrarySource, str | None],
        pending_playlists: deque[PlaylistId],
        started_at: datetime,
        prior: _ContinuationState | None,
    ) -> LibraryCollectionResult:
        likes: dict[VideoId, datetime | None] = {}
        videos: dict[VideoId, Video] = {}
        subscriptions_raw: list[SubscriptionSignal] = []
        owned_playlist_ids: list[PlaylistId] = []
        playlist_occurrences: list[PlaylistOccurrence] = []
        item_video_ids: list[VideoId] = []

        seen_likes = set(prior.seen_like_ids) if prior is not None else set()
        seen_subs = set(prior.seen_subscription_ids) if prior is not None else set()
        seen_pls = set(prior.seen_playlist_ids) if prior is not None else set()

        pages_used: dict[LibrarySource, int] = {src: 0 for src in active_sources}
        source_state: dict[LibrarySource, SourceCoverage] = {}
        source_stats: dict[LibrarySource, dict[str, int]] = {
            src: {"retrieved": 0, "usable": 0, "inaccessible": 0, "unknown": 0}
            for src in active_sources
        }
        source_warnings: dict[LibrarySource, list[str]] = {
            src: [] for src in active_sources
        }
        total_pages_used = 0
        all_warnings: list[str] = []

        # Finish a carried playlist sample before listing another page in a later request.
        playlists_fetched = bool(pending_playlists)
        playlist_sample_limited = prior.playlist_sample_limited if prior else False

        # Round-robin fairness loop: each requested source gets 1 page before any gets a 2nd.
        while total_pages_used < self._bounds.total_source_pages:
            progressed = False
            for src in active_sources:
                if total_pages_used >= self._bounds.total_source_pages:
                    break
                if pages_used[src] >= self._bounds.initial_pages_per_source:
                    continue
                sample_playlist = src == "playlists" and bool(pending_playlists)
                if not sample_playlist and (
                    src not in tokens or (src == "playlists" and playlists_fetched)
                ):
                    continue

                progressed = True
                pages_used[src] += 1
                total_pages_used += 1

                if src == "likes":
                    try:
                        page = await self._provider.list_likes(
                            ctx, self._bounds.page_size, page_token=tokens["likes"]
                        )
                    except ContractError as exc:
                        self._record_source_failure(
                            src, exc, source_state, all_warnings
                        )
                        del tokens[src]
                        continue
                    source_stats["likes"]["inaccessible"] += page.inaccessible
                    source_stats["likes"]["unknown"] += page.omitted
                    for entry in page.items:
                        if entry.video.video_id in seen_likes:
                            continue
                        seen_likes.add(entry.video.video_id)
                        likes[entry.video.video_id] = entry.liked_at
                        videos[entry.video.video_id] = entry.video
                        source_stats["likes"]["retrieved"] += 1
                        if entry.video.availability == "available":
                            source_stats["likes"]["usable"] += 1
                    if page.next_page_token is None:
                        del tokens[src]
                    else:
                        tokens[src] = page.next_page_token

                elif src == "subscriptions":
                    try:
                        sub_page = await self._provider.list_subscriptions(
                            ctx,
                            self._bounds.page_size,
                            page_token=tokens["subscriptions"],
                        )
                    except ContractError as exc:
                        self._record_source_failure(
                            src, exc, source_state, all_warnings
                        )
                        del tokens[src]
                        continue
                    source_stats["subscriptions"]["inaccessible"] += (
                        sub_page.inaccessible
                    )
                    source_stats["subscriptions"]["unknown"] += sub_page.omitted
                    for sig in sub_page.items:
                        if sig.subscription_id in seen_subs:
                            continue
                        seen_subs.add(sig.subscription_id)
                        subscriptions_raw.append(sig)
                        source_stats["subscriptions"]["retrieved"] += 1
                        source_stats["subscriptions"]["usable"] += 1
                    if sub_page.next_page_token is None:
                        del tokens[src]
                    else:
                        tokens[src] = sub_page.next_page_token

                elif sample_playlist:
                    playlist_id = pending_playlists.popleft()
                    owned_playlist_ids.append(playlist_id)
                    try:
                        items_page = await self._provider.list_playlist_items(
                            ctx, playlist_id, self._bounds.page_size
                        )
                    except ContractError as exc:
                        playlist_sample_limited = True
                        source_warnings[src].append(
                            f"Playlist {playlist_id} items unavailable ({exc.detail.code})."
                        )
                        continue
                    if items_page.next_page_token is not None:
                        playlist_sample_limited = True
                        source_warnings[src].append(
                            f"Playlist {playlist_id} was sampled from its first item page."
                        )
                    source_stats[src]["unknown"] += items_page.omitted
                    for occ in items_page.items:
                        playlist_occurrences.append(occ)
                        source_stats[src]["retrieved"] += 1
                        if occ.accessibility == "inaccessible":
                            source_stats[src]["inaccessible"] += 1
                        elif occ.video_id is not None:
                            source_stats[src]["usable"] += 1
                            item_video_ids.append(occ.video_id)
                        else:
                            source_stats[src]["unknown"] += 1

                else:
                    playlists_fetched = True
                    try:
                        pl_page = await self._provider.list_my_playlists(
                            ctx, self._bounds.page_size, page_token=tokens["playlists"]
                        )
                    except ContractError as exc:
                        self._record_source_failure(
                            src, exc, source_state, all_warnings
                        )
                        del tokens[src]
                        continue
                    if pl_page.next_page_token is None:
                        del tokens[src]
                    else:
                        tokens[src] = pl_page.next_page_token
                    unsampled = list(
                        dict.fromkeys(
                            pl.playlist_id
                            for pl in pl_page.items
                            if pl.playlist_id not in seen_pls
                        )
                    )
                    selected = unsampled[: self._bounds.owned_playlists_cap]
                    seen_pls.update(selected)
                    pending_playlists.extend(selected)
                    if len(unsampled) > len(selected):
                        playlist_sample_limited = True
                        source_warnings[src].append(
                            f"Selected first {len(selected)} of {len(unsampled)} unsampled owned playlists in returned order."
                        )

            if not progressed:
                break

        unique_to_hydrate = tuple(
            dict.fromkeys(vid for vid in item_video_ids if vid not in videos)
        )
        if unique_to_hydrate:
            try:
                batch = await self._provider.get_videos(ctx, unique_to_hydrate)
                videos.update(batch.videos)
                source_stats["playlists"]["unknown"] += len(batch.omitted_ids)
            except ContractError as exc:
                source_warnings["playlists"].append(
                    f"Playlist video hydration degraded ({exc.detail.code})."
                )

        # Bounded subscription topic sampling (first N accessible subscribed channels,
        # up to 5 uploads each). Samples are channel-topic evidence, not engagement events.
        enriched_subscriptions: list[SubscriptionSignal] = []
        if subscriptions_raw:
            sample_targets = subscriptions_raw[
                : self._bounds.subscription_sample_channels
            ]
            target_channel_ids: tuple[ChannelId, ...] = tuple(
                dict.fromkeys(sig.channel_id for sig in sample_targets)
            )
            channel_map = {}
            try:
                ch_batch = await self._provider.get_channels(ctx, target_channel_ids)
                channel_map = dict(ch_batch.channels)
            except ContractError as exc:
                source_warnings["subscriptions"].append(
                    f"Subscription channel hydration skipped ({exc.detail.code})."
                )

            sampled_ids = {sig.subscription_id for sig in sample_targets}
            for sig in subscriptions_raw:
                if sig.subscription_id not in sampled_ids:
                    enriched_subscriptions.append(sig)
                    continue
                ch = channel_map.get(sig.channel_id)
                if ch is None or ch.uploads_playlist_id is None:
                    enriched_subscriptions.append(sig)
                    continue
                sample = await self._sample_channel_uploads(ctx, ch, videos)
                enriched_subscriptions.append(
                    sig.model_copy(update={"topic_sample": sample})
                )

        remaining_sources = set(tokens)
        if pending_playlists:
            remaining_sources.add("playlists")
        snapshot_id = f"snap-{uuid.uuid4().hex[:16]}"
        fetched_at = self._clock.now().astimezone(UTC)
        if fetched_at < started_at:
            fetched_at = started_at
        retained_until = fetched_at + _MAX_RETENTION

        next_cont_ref = f"cont-{uuid.uuid4().hex[:16]}" if remaining_sources else None

        # Finalize SourceCoverage for all three required library sources.
        final_sources: dict[LibrarySource, SourceCoverage] = {}
        for src in _ALL_SOURCES:
            if src not in active_sources:
                final_sources[src] = SourceCoverage(
                    state="not_requested", coverage=None
                )
            elif src in source_state:
                final_sources[src] = source_state[src]
            else:
                st = source_stats[src]
                truncated = src in remaining_sources or (
                    src == "playlists" and playlist_sample_limited
                )
                cont = next_cont_ref if src in remaining_sources else None
                resumed_source = prior is not None and (
                    prior.tokens.get(src) is not None
                    or (src == "playlists" and bool(prior.pending_playlists))
                )
                cov = Coverage(
                    complete=not truncated,
                    paginated=pages_used[src] > 1 or resumed_source,
                    sampled=(src in {"subscriptions", "playlists"}),
                    truncated=truncated,
                    retrieved=st["retrieved"],
                    usable=min(st["usable"], st["retrieved"]),
                    inaccessible=st["inaccessible"],
                    unknown=st["unknown"],
                    limits={
                        "pages_budget": self._bounds.initial_pages_per_source,
                        "page_size": self._bounds.page_size,
                    },
                    sampled_sources=(src,)
                    if src in {"subscriptions", "playlists"}
                    else (),
                    completeness_basis=(
                        f"Bounded {src} retrieval ({pages_used[src]} pages within budget)"
                    ),
                    continuation_ref=cont,
                    warnings=tuple(source_warnings[src]),
                )
                final_sources[src] = SourceCoverage(
                    state="retrieved" if pages_used[src] else "unavailable",
                    coverage=cov,
                )

        snapshot = LibrarySnapshot(
            snapshot_id=snapshot_id,
            binding=ctx.binding,
            started_at=started_at,
            fetched_at=fetched_at,
            likes=likes,
            subscriptions=tuple(enriched_subscriptions),
            owned_playlist_ids=tuple(owned_playlist_ids),
            playlist_occurrences=tuple(playlist_occurrences),
            videos=videos,
            sources=final_sources,
            retained_until=retained_until,
        )
        await self._snapshots.save_snapshot(snapshot)
        if next_cont_ref is not None:
            self._continuations[next_cont_ref] = _ContinuationState(
                continuation_ref=next_cont_ref,
                binding=ctx.binding,
                requested_sources=requested,
                snapshot_id=snapshot_id,
                tokens=tokens,
                pending_playlists=tuple(pending_playlists),
                playlist_sample_limited=playlist_sample_limited,
                seen_like_ids=frozenset(seen_likes),
                seen_subscription_ids=frozenset(seen_subs),
                seen_playlist_ids=frozenset(seen_pls),
                expires_at=fetched_at + _CONTINUATION_TTL,
            )

        summary = LibrarySummary(
            snapshot_id=snapshot.snapshot_id,
            fetched_at=snapshot.fetched_at,
            retained_until=snapshot.retained_until,
            likes_count=len(snapshot.likes),
            subscriptions_count=len(snapshot.subscriptions),
            owned_playlists_count=len(snapshot.owned_playlist_ids),
            playlist_occurrences_count=len(snapshot.playlist_occurrences),
            unique_videos_count=len(snapshot.videos),
            sources=snapshot.sources,
            continuation_ref=next_cont_ref,
            warnings=tuple(all_warnings),
        )
        return LibraryCollectionResult(
            snapshot=snapshot,
            summary=summary,
            continuation_ref=next_cont_ref,
        )

    async def _sample_channel_uploads(
        self,
        ctx: RequestContext,
        channel: Channel,
        videos: dict[VideoId, Video],
    ) -> ChannelSample | None:
        if channel.uploads_playlist_id is None:
            return None
        try:
            page = await self._provider.list_playlist_items(
                ctx, channel.uploads_playlist_id, self._bounds.uploads_per_channel
            )
        except ContractError:
            return None

        entries = page.items[: self._bounds.uploads_per_channel]
        candidate_ids: list[VideoId] = []
        inaccessible = page.inaccessible
        unknown = page.omitted
        for occ in entries:
            if occ.accessibility == "inaccessible":
                inaccessible += 1
            elif occ.video_id is None or occ.accessibility == "unknown":
                unknown += 1
            else:
                candidate_ids.append(occ.video_id)

        unique_ids = tuple(dict.fromkeys(candidate_ids))
        missing_ids = tuple(vid for vid in unique_ids if vid not in videos)
        if missing_ids:
            try:
                batch = await self._provider.get_videos(ctx, missing_ids)
                videos.update(batch.videos)
                unknown += len(batch.omitted_ids)
            except ContractError:
                pass

        usable_ids = tuple(
            vid
            for vid in unique_ids
            if vid in videos and videos[vid].availability == "available"
        )
        truncated = page.next_page_token is not None or len(entries) < len(page.items)
        coverage = Coverage(
            complete=not truncated,
            paginated=False,
            sampled=True,
            truncated=truncated,
            retrieved=len(entries),
            usable=len(usable_ids),
            inaccessible=inaccessible,
            unknown=unknown,
            limits={"uploads_per_channel": self._bounds.uploads_per_channel},
            sampled_sources=("uploads",),
            completeness_basis="Bounded first uploads page for subscribed channel topic sample",
        )
        return ChannelSample(
            channel=channel,
            video_ids=usable_ids,
            attempted=len(entries),
            usable=len(usable_ids),
            skipped=len(entries) - len(usable_ids),
            selection_rule_version=_SAMPLE_RULE,
            coverage=coverage,
        )

    @staticmethod
    def _record_source_failure(
        src: LibrarySource,
        exc: ContractError,
        source_state: dict[LibrarySource, SourceCoverage],
        all_warnings: list[str],
    ) -> None:
        if exc.detail.code in {"SCOPE_REQUIRED", "AUTH_REQUIRED", "AUTH_REVOKED"}:
            source_state[src] = SourceCoverage(state="denied", coverage=None)
            all_warnings.append(
                f"Library source '{src}' was denied ({exc.detail.code})."
            )
        else:
            source_state[src] = SourceCoverage(state="unavailable", coverage=None)
            all_warnings.append(
                f"Library source '{src}' was unavailable ({exc.detail.code})."
            )
