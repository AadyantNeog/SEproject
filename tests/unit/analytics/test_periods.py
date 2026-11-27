from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from yt_intel.analytics.periods import TimePeriod, compare_periods
from yt_intel.contracts.common import AccountBinding
from yt_intel.contracts.errors import ContractError
from yt_intel.contracts.models import (
    Coverage,
    LibrarySnapshot,
    PlaylistOccurrence,
    SourceCoverage,
    SubscriptionSignal,
    Video,
)

NOW = datetime(2026, 11, 27, 12, 0, tzinfo=UTC)
BINDING = AccountBinding(
    installation_id="fixture-inst",
    credential_binding_id="fixture-cred",
    channel_id="UCaaaaaaaaaaaaaaaaaaaaaa",
    mode="fixture",
)


def _src() -> SourceCoverage:
    return SourceCoverage(
        state="retrieved",
        coverage=Coverage(
            complete=True,
            paginated=False,
            sampled=False,
            truncated=False,
            retrieved=1,
            usable=1,
            inaccessible=0,
            unknown=0,
            completeness_basis="Fixture",
        ),
    )


def _snapshot() -> LibrarySnapshot:
    # Video published inside Period A, but playlist occurrence has added_at=None:
    # period comparison MUST NOT substitute video.published_at!
    v_pub_in_a = Video(
        video_id="pubInA00001",
        channel_id="UCaaaaaaaaaaaaaaaaaaaaaa",
        title="Published in A",
        channel_title="Chan A",
        canonical_url="https://www.youtube.com/watch?v=pubInA00001",
        description=None,
        tags=None,
        category_id="27",
        published_at=datetime(2026, 10, 15, 0, 0, tzinfo=UTC),
        duration_seconds=600,
        default_audio_language="en",
        default_metadata_language=None,
        language_evidence="audio",
        availability="available",
        live_status="recorded",
        fetched_at=NOW,
    )
    sub_cov = Coverage(
        complete=True,
        paginated=False,
        sampled=False,
        truncated=False,
        retrieved=1,
        usable=1,
        inaccessible=0,
        unknown=0,
        completeness_basis="Sub",
    )
    return LibrarySnapshot(
        snapshot_id="snap-periods-1",
        binding=BINDING,
        started_at=NOW,
        fetched_at=NOW,
        likes={v_pub_in_a.video_id: None},
        subscriptions=(
            # Exactly at Period B start -> included in Period B (start-inclusive)
            SubscriptionSignal(
                subscription_id="sub-b-start",
                channel_id="UCbbbbbbbbbbbbbbbbbbbbbb",
                subscribed_at=datetime(2026, 11, 1, 0, 0, tzinfo=UTC),
                topic_sample=None,
                coverage=sub_cov,
            ),
            # Missing subscribed_at -> counted as unknown_timestamp_count
            SubscriptionSignal(
                subscription_id="sub-unknown",
                channel_id="UCcccccccccccccccccccccc",
                subscribed_at=None,
                topic_sample=None,
                coverage=sub_cov,
            ),
        ),
        owned_playlist_ids=("PL1",),
        playlist_occurrences=(
            # Exactly at Period A start -> included in Period A
            PlaylistOccurrence(
                playlist_id="PL1",
                playlist_item_id="pli-a-start",
                video_id="pubInA00001",
                position=0,
                added_at=datetime(2026, 10, 1, 0, 0, tzinfo=UTC),
                accessibility="available",
            ),
            # Exactly at Period A end (= Period B start) -> excluded from A, included in B!
            PlaylistOccurrence(
                playlist_id="PL1",
                playlist_item_id="pli-boundary",
                video_id="pubInA00001",
                position=1,
                added_at=datetime(2026, 11, 1, 0, 0, tzinfo=UTC),
                accessibility="available",
            ),
            # Inside Period B
            PlaylistOccurrence(
                playlist_id="PL1",
                playlist_item_id="pli-b-mid",
                video_id="pubInA00001",
                position=2,
                added_at=datetime(2026, 11, 15, 0, 0, tzinfo=UTC),
                accessibility="available",
            ),
            # Missing added_at -> MUST NOT use video.published_at (2026-10-15)!
            PlaylistOccurrence(
                playlist_id="PL1",
                playlist_item_id="pli-no-ts",
                video_id="pubInA00001",
                position=3,
                added_at=None,
                accessibility="available",
            ),
        ),
        videos={v_pub_in_a.video_id: v_pub_in_a},
        sources={
            "likes": _src(),
            "subscriptions": _src(),
            "playlists": _src(),
        },
        retained_until=NOW + timedelta(days=30),
    )


def test_half_open_utc_boundaries_zero_baselines_and_no_publication_substitution() -> (
    None
):
    snap = _snapshot()
    period_a = TimePeriod(
        start=datetime(2026, 10, 1, 0, 0, tzinfo=UTC),
        end=datetime(2026, 11, 1, 0, 0, tzinfo=UTC),
    )
    period_b = TimePeriod(
        start=datetime(2026, 11, 1, 0, 0, tzinfo=UTC),
        end=datetime(2026, 12, 1, 0, 0, tzinfo=UTC),
    )

    comp = compare_periods(snap, period_a, period_b)

    # Playlist additions: A has 1 (start-inclusive; end-exclusive; missing added_at NOT substituted!)
    # B has 2 (boundary at 2026-11-01 + mid Nov) -> diff=+1, pct=+100.0%
    pa = comp.playlist_additions
    assert pa.timestamp_basis == "playlist_item.added_at"
    assert pa.count_a == 1
    assert pa.count_b == 2
    assert pa.absolute_difference == 1
    assert pa.percent_change == 100.0
    assert pa.unknown_timestamp_count == 1

    # Subscriptions: A has 0, B has 1 -> zero baseline yields percent_change=None!
    sc = comp.subscription_creations
    assert sc.timestamp_basis == "subscription.subscribed_at"
    assert sc.count_a == 0
    assert sc.count_b == 1
    assert sc.absolute_difference == 1
    assert sc.percent_change is None
    assert sc.percent_change_reason == "undefined_zero_baseline"
    assert sc.unknown_timestamp_count == 1

    # Likes trend is always explicitly unavailable
    assert comp.likes_trend.available is False
    assert comp.likes_trend.reason == "like_event_timestamps_unavailable"


def test_empty_periods_zero_to_zero_keeps_percent_change_undefined() -> None:
    snap = _snapshot()
    p1 = TimePeriod(
        start=datetime(2025, 1, 1, tzinfo=UTC),
        end=datetime(2025, 2, 1, tzinfo=UTC),
    )
    p2 = TimePeriod(
        start=datetime(2025, 2, 1, tzinfo=UTC),
        end=datetime(2025, 3, 1, tzinfo=UTC),
    )
    comp = compare_periods(snap, p1, p2)
    assert comp.playlist_additions.count_a == 0
    assert comp.playlist_additions.count_b == 0
    assert comp.playlist_additions.absolute_difference == 0
    assert comp.playlist_additions.percent_change is None
    assert comp.playlist_additions.percent_change_reason == "undefined_zero_baseline"


def test_rejects_naive_inverted_and_overlapping_periods() -> None:
    with pytest.raises(ValidationError):
        TimePeriod(
            start=datetime(2026, 10, 1),  # naive!
            end=datetime(2026, 11, 1, tzinfo=UTC),
        )
    with pytest.raises(ValidationError):
        TimePeriod(
            start=datetime(2026, 11, 1, tzinfo=UTC),
            end=datetime(2026, 11, 1, tzinfo=UTC),
        )

    p1 = TimePeriod(
        start=datetime(2026, 10, 1, tzinfo=UTC),
        end=datetime(2026, 11, 10, tzinfo=UTC),
    )
    p2 = TimePeriod(
        start=datetime(2026, 11, 1, tzinfo=UTC),
        end=datetime(2026, 12, 1, tzinfo=UTC),
    )
    with pytest.raises(ContractError) as exc:
        compare_periods(_snapshot(), p1, p2)
    assert exc.value.detail.code == "INVALID_INPUT"
