from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from statistics import median
from typing import Literal

from yt_intel.contracts.common import (
    AccountBinding,
    ChannelId,
    Contract,
    FrozenMap,
    Label,
    Limit,
    NonNegative,
    OpaqueId,
    UtcDateTime,
    VersionedContract,
    VideoId,
)
from yt_intel.contracts.models import (
    LibrarySnapshot,
    LibrarySource,
    SourceCoverage,
    Video,
    Warnings,
)

from .periods import PeriodComparison, TimePeriod, compare_periods

ANALYTICS_VERSION = "analytics-v1"
_DURATION_BANDS: tuple[tuple[str, int, int | None], ...] = (
    ("[0,300)", 0, 300),
    ("[300,900)", 300, 900),
    ("[900,1800)", 900, 1800),
    ("[1800,3600)", 1800, 3600),
    ("[3600,infinity)", 3600, None),
)


class AnalysisConfig(Contract):
    top_limit: Limit = 10
    sources: tuple[LibrarySource, ...] = ("likes", "subscriptions", "playlists")


class RankedBucket(Contract):
    bucket_id: Label
    label: Label
    count: NonNegative
    percentage: float | None
    denominator: NonNegative


class DurationBandCount(Contract):
    band: Label
    min_seconds: NonNegative
    max_seconds: NonNegative | None
    count: NonNegative


class RuntimeStats(Contract):
    population_kind: Label
    source: Label
    retrieved_count: NonNegative
    known_count: NonNegative
    unknown_count: NonNegative
    deduplication_rule: Label
    mean_seconds: float | None
    median_seconds: float | None
    bands: tuple[DurationBandCount, ...]
    empty_reason: Label | None = None


class LikesPopulationSummary(Contract):
    population_kind: Literal["unique_liked_videos"] = "unique_liked_videos"
    source: Literal["likes"] = "likes"
    count: NonNegative
    denominator: NonNegative
    unknown_metadata_count: NonNegative
    deduplication_rule: Label = "unique_video_id"
    timestamp_basis: Label = "like_event_timestamps_unavailable"
    runtime: RuntimeStats


class PlaylistPopulationSummary(Contract):
    population_kind: Literal["playlist_item_occurrences"] = "playlist_item_occurrences"
    source: Literal["playlists"] = "playlists"
    selected_playlists_count: NonNegative
    occurrence_count: NonNegative
    unique_video_count: NonNegative
    inaccessible_occurrence_count: NonNegative
    unknown_metadata_count: NonNegative
    deduplication_rule: Label = "occurrences_preserved_unique_count_reported_separately"
    timestamp_basis: Label = "playlist_item.added_at"
    runtime: RuntimeStats


class CombinedPopulationSummary(Contract):
    population_kind: Literal["combined_unique_collection_videos"] = (
        "combined_unique_collection_videos"
    )
    source: Literal["likes_and_playlists"] = "likes_and_playlists"
    count: NonNegative
    denominator: NonNegative
    overlap_count: NonNegative
    likes_only_count: NonNegative
    playlists_only_count: NonNegative
    excluded_subscription_sample_videos: NonNegative
    unknown_channel_count: NonNegative
    unknown_category_count: NonNegative
    deduplication_rule: Label = "unique_video_id_excluding_subscription_samples"
    top_channels: tuple[RankedBucket, ...]
    top_categories: tuple[RankedBucket, ...]
    runtime: RuntimeStats


class SubscriptionPopulationSummary(Contract):
    population_kind: Literal["unique_subscribed_channels"] = (
        "unique_subscribed_channels"
    )
    source: Literal["subscriptions"] = "subscriptions"
    count: NonNegative
    denominator: NonNegative
    unknown_timestamp_count: NonNegative
    deduplication_rule: Label = "unique_channel_id_never_video_views"
    timestamp_basis: Label = "subscription.subscribed_at"
    channel_ids: tuple[ChannelId, ...]


class AnalysisReport(VersionedContract):
    report_id: OpaqueId
    binding: AccountBinding
    snapshot_id: OpaqueId
    report_version: Label = ANALYTICS_VERSION
    generated_at: UtcDateTime
    activity_label: Literal["accessible_collection_activity"] = (
        "accessible_collection_activity"
    )
    evidence_disclaimer: Label = (
        "Summarises accessible collection metadata only; not watch history, "
        "watch time, completion, or learning progress."
    )
    likes: LikesPopulationSummary
    playlists: PlaylistPopulationSummary
    combined_videos: CombinedPopulationSummary
    subscriptions: SubscriptionPopulationSummary
    period_comparison: PeriodComparison | None = None
    sources: FrozenMap[LibrarySource, SourceCoverage]
    warnings: Warnings = ()


def _compute_runtime_stats(
    videos: Sequence[Video | None],
    *,
    population_kind: str,
    source: str,
    deduplication_rule: str,
) -> RuntimeStats:
    retrieved = len(videos)
    known: list[int] = []
    for video in videos:
        if (
            video is not None
            and video.duration_seconds is not None
            and video.duration_seconds > 0
        ):
            known.append(video.duration_seconds)

    known_count = len(known)
    unknown_count = retrieved - known_count

    band_counts: list[DurationBandCount] = []
    for label, lo, hi in _DURATION_BANDS:
        if hi is None:
            cnt = sum(1 for d in known if d >= lo)
        else:
            cnt = sum(1 for d in known if lo <= d < hi)
        band_counts.append(
            DurationBandCount(band=label, min_seconds=lo, max_seconds=hi, count=cnt)
        )

    if known_count > 0:
        mean_val: float | None = sum(known) / known_count
        median_val: float | None = float(median(known))
        empty_reason: str | None = None
    else:
        mean_val = None
        median_val = None
        empty_reason = "no_known_positive_durations"

    return RuntimeStats(
        population_kind=population_kind,
        source=source,
        retrieved_count=retrieved,
        known_count=known_count,
        unknown_count=unknown_count,
        deduplication_rule=deduplication_rule,
        mean_seconds=mean_val,
        median_seconds=median_val,
        bands=tuple(band_counts),
        empty_reason=empty_reason,
    )


def _rank_buckets(
    pairs: Iterable[tuple[str, str]],
    *,
    denominator: int,
    limit: int,
) -> tuple[RankedBucket, ...]:
    counts: Counter[str] = Counter()
    labels: dict[str, str] = {}
    for bucket_id, label in pairs:
        counts[bucket_id] += 1
        labels.setdefault(bucket_id, label)

    # Descending count, then ascending stable ID tie-break.
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]
    return tuple(
        RankedBucket(
            bucket_id=bid,
            label=labels[bid],
            count=cnt,
            percentage=(cnt / denominator * 100.0) if denominator > 0 else None,
            denominator=denominator,
        )
        for bid, cnt in ordered
    )


def summarise_library(
    snapshot: LibrarySnapshot,
    config: AnalysisConfig = AnalysisConfig(),
    *,
    report_id: OpaqueId | None = None,
    period_a: TimePeriod | None = None,
    period_b: TimePeriod | None = None,
) -> AnalysisReport:
    """Pure FR-4 collection summary and optional non-overlapping period comparison.

    Performs zero network, OAuth, database, or approval side effects.
    """
    include_likes = "likes" in config.sources
    include_playlists = "playlists" in config.sources
    include_subs = "subscriptions" in config.sources

    like_ids: tuple[VideoId, ...] = tuple(snapshot.likes) if include_likes else ()
    like_videos = [snapshot.videos.get(vid) for vid in like_ids]
    like_unknown_meta = sum(1 for v in like_videos if v is None)
    likes_summary = LikesPopulationSummary(
        count=len(like_ids),
        denominator=len(like_ids),
        unknown_metadata_count=like_unknown_meta,
        runtime=_compute_runtime_stats(
            like_videos,
            population_kind="unique_liked_videos",
            source="likes",
            deduplication_rule="unique_video_id",
        ),
    )

    occurrences = snapshot.playlist_occurrences if include_playlists else ()
    inaccessible_occ = sum(1 for o in occurrences if o.accessibility == "inaccessible")
    playlist_unique_ids = tuple(
        dict.fromkeys(
            o.video_id
            for o in occurrences
            if o.video_id is not None and o.accessibility != "inaccessible"
        )
    )
    playlist_unique_videos = [snapshot.videos.get(vid) for vid in playlist_unique_ids]
    playlist_unknown_meta = sum(1 for v in playlist_unique_videos if v is None)
    playlists_summary = PlaylistPopulationSummary(
        selected_playlists_count=(
            len(snapshot.owned_playlist_ids) if include_playlists else 0
        ),
        occurrence_count=len(occurrences),
        unique_video_count=len(playlist_unique_ids),
        inaccessible_occurrence_count=inaccessible_occ,
        unknown_metadata_count=playlist_unknown_meta,
        runtime=_compute_runtime_stats(
            playlist_unique_videos,
            population_kind="unique_playlist_videos",
            source="playlists",
            deduplication_rule="unique_accessible_video_id",
        ),
    )

    # Combined unique videos across likes and playlists ONLY — exclude subscription samples!
    like_set = set(like_ids)
    playlist_set = set(playlist_unique_ids)
    combined_ids = tuple(dict.fromkeys((*like_ids, *playlist_unique_ids)))
    combined_set = set(combined_ids)
    overlap_count = len(like_set & playlist_set)
    likes_only = len(like_set - playlist_set)
    playlists_only = len(playlist_set - like_set)

    sample_only_ids = {
        vid
        for sig in snapshot.subscriptions
        if sig.topic_sample is not None
        for vid in sig.topic_sample.video_ids
        if vid not in combined_set
    }

    combined_videos = [snapshot.videos.get(vid) for vid in combined_ids]
    channel_pairs: list[tuple[str, str]] = []
    category_pairs: list[tuple[str, str]] = []
    unknown_channels = 0
    unknown_categories = 0
    for video in combined_videos:
        if video is None or video.channel_id is None:
            unknown_channels += 1
        else:
            channel_pairs.append(
                (video.channel_id, video.channel_title or video.channel_id)
            )
        if video is None or video.category_id is None:
            unknown_categories += 1
        else:
            category_pairs.append((video.category_id, f"Category {video.category_id}"))

    combined_denom = len(combined_ids)
    combined_summary = CombinedPopulationSummary(
        count=combined_denom,
        denominator=combined_denom,
        overlap_count=overlap_count,
        likes_only_count=likes_only,
        playlists_only_count=playlists_only,
        excluded_subscription_sample_videos=len(sample_only_ids),
        unknown_channel_count=unknown_channels,
        unknown_category_count=unknown_categories,
        top_channels=_rank_buckets(
            channel_pairs, denominator=combined_denom, limit=config.top_limit
        ),
        top_categories=_rank_buckets(
            category_pairs, denominator=combined_denom, limit=config.top_limit
        ),
        runtime=_compute_runtime_stats(
            combined_videos,
            population_kind="combined_unique_collection_videos",
            source="likes_and_playlists",
            deduplication_rule="unique_video_id_excluding_subscription_samples",
        ),
    )

    subs = snapshot.subscriptions if include_subs else ()
    unique_sub_channels = tuple(dict.fromkeys(sig.channel_id for sig in subs))
    unknown_sub_ts = sum(1 for sig in subs if sig.subscribed_at is None)
    subs_summary = SubscriptionPopulationSummary(
        count=len(unique_sub_channels),
        denominator=len(unique_sub_channels),
        unknown_timestamp_count=unknown_sub_ts,
        channel_ids=unique_sub_channels,
    )

    comparison: PeriodComparison | None = None
    if period_a is not None or period_b is not None:
        if period_a is None or period_b is None:
            raise ValueError("both period_a and period_b are required for comparison")
        comparison = compare_periods(
            snapshot, period_a, period_b, sources=config.sources
        )

    warnings: list[str] = []
    for src_name, src_cov in snapshot.sources.items():
        if src_name in config.sources and src_cov.state in {"denied", "unavailable"}:
            warnings.append(
                f"Source '{src_name}' was {src_cov.state} in this snapshot."
            )
        elif src_name in config.sources and src_cov.state == "not_requested":
            warnings.append(
                f"Source '{src_name}' was not requested in this snapshot; "
                "its counts are not evidence of zero activity."
            )
    if combined_summary.runtime.unknown_count > 0:
        warnings.append(
            f"{combined_summary.runtime.unknown_count} of {combined_summary.runtime.retrieved_count} "
            "combined videos had unknown or non-positive duration and were excluded from runtime statistics."
        )

    return AnalysisReport(
        report_id=report_id or f"rep-{snapshot.snapshot_id}",
        binding=snapshot.binding,
        snapshot_id=snapshot.snapshot_id,
        generated_at=snapshot.fetched_at,
        likes=likes_summary,
        playlists=playlists_summary,
        combined_videos=combined_summary,
        subscriptions=subs_summary,
        period_comparison=comparison,
        sources=snapshot.sources,
        warnings=tuple(warnings),
    )
