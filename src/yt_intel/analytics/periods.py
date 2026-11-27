from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Literal, Self

from pydantic import model_validator

from yt_intel.contracts.common import Contract, Label, NonNegative, UtcDateTime
from yt_intel.contracts.errors import ContractError, ErrorDetail
from yt_intel.contracts.models import LibrarySnapshot, LibrarySource

_ALL_SOURCES: tuple[LibrarySource, ...] = ("likes", "subscriptions", "playlists")


class TimePeriod(Contract):
    """Half-open UTC interval [start, end) — start-inclusive, end-exclusive."""

    start: UtcDateTime
    end: UtcDateTime

    @model_validator(mode="after")
    def check_order(self) -> Self:
        if self.start >= self.end:
            raise ValueError("period start must be strictly before period end")
        return self

    def contains(self, timestamp: datetime) -> bool:
        return self.start <= timestamp < self.end


class PeriodMetricComparison(Contract):
    metric: Literal["playlist_additions", "subscription_creations"]
    population_kind: Label
    timestamp_basis: Label
    count_a: NonNegative
    count_b: NonNegative
    absolute_difference: int
    percent_change: float | None
    percent_change_reason: Label | None = None
    unknown_timestamp_count: NonNegative
    note: Label | None = None


class UnavailableTrend(Contract):
    source: Literal["likes"] = "likes"
    available: Literal[False] = False
    reason: Label = "like_event_timestamps_unavailable"
    explanation: Label = (
        "YouTube Data API v3 does not provide reliable like-event timestamps; "
        "video publication dates are never substituted."
    )


class PeriodComparison(Contract):
    """Comparison of valid event timestamps across two non-overlapping UTC periods."""

    period_a: TimePeriod
    period_b: TimePeriod
    sources: tuple[LibrarySource, ...] = _ALL_SOURCES
    interval_convention: Literal["utc_start_inclusive_end_exclusive"] = (
        "utc_start_inclusive_end_exclusive"
    )
    playlist_additions: PeriodMetricComparison | None = None
    subscription_creations: PeriodMetricComparison | None = None
    likes_trend: UnavailableTrend | None = None


def validate_non_overlapping_periods(
    period_a: TimePeriod, period_b: TimePeriod
) -> None:
    """Reject overlapping UTC [start, end) intervals with corrective guidance."""
    if period_a.start < period_b.end and period_b.start < period_a.end:
        raise ContractError(
            ErrorDetail(
                code="INVALID_INPUT",
                message="Comparison periods must not overlap.",
                retryable=False,
                safe_next_action="Supply two non-overlapping UTC [start, end) intervals.",
            )
        )


def validate_period_pair(
    period_a: TimePeriod | None, period_b: TimePeriod | None
) -> tuple[TimePeriod, TimePeriod] | None:
    """Validate an optional pair of non-overlapping UTC [start, end) intervals."""
    if period_a is None and period_b is None:
        return None
    if period_a is None or period_b is None:
        raise ContractError(
            ErrorDetail(
                code="INVALID_INPUT",
                message="Both period_a and period_b must be provided for period comparison.",
                retryable=False,
                safe_next_action="Supply two non-overlapping UTC [start, end) intervals or omit both.",
            )
        )
    validate_non_overlapping_periods(period_a, period_b)
    return (period_a, period_b)


def _build_metric(
    *,
    metric: Literal["playlist_additions", "subscription_creations"],
    population_kind: str,
    timestamp_basis: str,
    timestamps: list[datetime | None],
    period_a: TimePeriod,
    period_b: TimePeriod,
) -> PeriodMetricComparison:
    count_a = 0
    count_b = 0
    unknown_ts = 0
    for ts in timestamps:
        if ts is None:
            unknown_ts += 1
            continue
        if period_a.contains(ts):
            count_a += 1
        elif period_b.contains(ts):
            count_b += 1

    abs_diff = count_b - count_a
    percent_change: float | None
    percent_reason: str | None
    if count_a > 0:
        percent_change = ((count_b - count_a) / count_a) * 100.0
        percent_reason = None
    else:
        percent_change = None
        percent_reason = "undefined_zero_baseline"

    note: str | None = None
    if count_a == 0 and count_b == 0:
        note = "No supported timestamped events fell inside either comparison period."

    return PeriodMetricComparison(
        metric=metric,
        population_kind=population_kind,
        timestamp_basis=timestamp_basis,
        count_a=count_a,
        count_b=count_b,
        absolute_difference=abs_diff,
        percent_change=percent_change,
        percent_change_reason=percent_reason,
        unknown_timestamp_count=unknown_ts,
        note=note,
    )


def compare_periods(
    snapshot: LibrarySnapshot,
    period_a: TimePeriod,
    period_b: TimePeriod,
    *,
    sources: Sequence[LibrarySource] = _ALL_SOURCES,
) -> PeriodComparison:
    """Pure comparison of playlist-addition and subscription-creation timestamps.

    Strictly uses ``PlaylistOccurrence.added_at`` and ``SubscriptionSignal.subscribed_at``,
    respecting the selected ``sources``. Never substitutes ``Video.published_at`` or
    ``LibrarySnapshot.fetched_at``.

    Only sources the snapshot actually retrieved are compared. A denied,
    unavailable or unrequested source yields ``None`` rather than zero
    counts, because missing evidence is not evidence of no activity.
    """
    validate_non_overlapping_periods(period_a, period_b)
    selected = tuple(
        source
        for source in dict.fromkeys(sources)
        if source in snapshot.sources and snapshot.sources[source].state == "retrieved"
    )

    playlist_additions: PeriodMetricComparison | None = None
    if "playlists" in selected:
        playlist_timestamps = [occ.added_at for occ in snapshot.playlist_occurrences]
        playlist_additions = _build_metric(
            metric="playlist_additions",
            population_kind="selected_playlist_item_occurrences",
            timestamp_basis="playlist_item.added_at",
            timestamps=playlist_timestamps,
            period_a=period_a,
            period_b=period_b,
        )

    subscription_creations: PeriodMetricComparison | None = None
    if "subscriptions" in selected:
        subscription_timestamps = [sig.subscribed_at for sig in snapshot.subscriptions]
        subscription_creations = _build_metric(
            metric="subscription_creations",
            population_kind="unique_subscribed_channels",
            timestamp_basis="subscription.subscribed_at",
            timestamps=subscription_timestamps,
            period_a=period_a,
            period_b=period_b,
        )

    likes_trend = UnavailableTrend() if "likes" in selected else None

    return PeriodComparison(
        period_a=period_a,
        period_b=period_b,
        sources=selected,
        playlist_additions=playlist_additions,
        subscription_creations=subscription_creations,
        likes_trend=likes_trend,
    )
