from datetime import UTC, datetime, timedelta

from yt_intel.analytics.summaries import AnalysisConfig, summarise_library
from yt_intel.contracts.common import AccountBinding
from yt_intel.contracts.models import (
    Channel,
    ChannelSample,
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


def _video(
    vid: str,
    *,
    duration: int | None,
    channel_id: str | None = "UCaaaaaaaaaaaaaaaaaaaaaa",
    channel_title: str | None = "Channel A",
    category_id: str | None = "27",
) -> Video:
    return Video(
        video_id=vid,
        channel_id=channel_id,
        title=f"Video {vid}",
        channel_title=channel_title,
        canonical_url=f"https://www.youtube.com/watch?v={vid}",
        description=None,
        tags=None,
        category_id=category_id,
        published_at=NOW - timedelta(days=10),
        duration_seconds=duration,
        default_audio_language="en-US",
        default_metadata_language=None,
        language_evidence="audio",
        availability="available",
        live_status="recorded",
        fetched_at=NOW,
    )


def _retrieved_source() -> SourceCoverage:
    return SourceCoverage(
        state="retrieved",
        coverage=Coverage(
            complete=True,
            paginated=False,
            sampled=False,
            truncated=False,
            retrieved=4,
            usable=4,
            inaccessible=0,
            unknown=0,
            completeness_basis="Fixture oracle",
        ),
    )


def test_srs_hand_calculated_runtime_oracle_and_unknown_denominator() -> None:
    """Oracle from JESWIN.md & MASTER_PLAN: [240, 600, 600, 1200] -> mean 660, median 600, bands [1,2,1,0,0]."""
    v1 = _video(
        "oracle00001",
        duration=240,
        channel_id="UCbbbbbbbbbbbbbbbbbbbbbb",
        channel_title="Chan B",
        category_id="27",
    )
    v2 = _video(
        "oracle00002",
        duration=600,
        channel_id="UCaaaaaaaaaaaaaaaaaaaaaa",
        channel_title="Chan A",
        category_id="27",
    )
    v3 = _video(
        "oracle00003",
        duration=600,
        channel_id="UCbbbbbbbbbbbbbbbbbbbbbb",
        channel_title="Chan B",
        category_id="28",
    )
    v4 = _video(
        "oracle00004",
        duration=1200,
        channel_id="UCaaaaaaaaaaaaaaaaaaaaaa",
        channel_title="Chan A",
        category_id="28",
    )
    v5_unknown = _video(
        "oracle00005",
        duration=None,
        channel_id=None,
        channel_title=None,
        category_id=None,
    )
    v6_sub_sample = _video(
        "subSamp0006",
        duration=3600,
        channel_id="UCcccccccccccccccccccccc",
        channel_title="Chan C",
        category_id="20",
    )

    sub_channel = Channel(
        channel_id="UCcccccccccccccccccccccc",
        title="Chan C",
        canonical_url="https://www.youtube.com/channel/UCcccccccccccccccccccccc",
        handle="@chanc",
        description=None,
        uploads_playlist_id="UUcccccccccccccccccccccc",
        fetched_at=NOW,
    )
    sub_sample = ChannelSample(
        channel=sub_channel,
        video_ids=(v6_sub_sample.video_id,),
        attempted=1,
        usable=1,
        skipped=0,
        selection_rule_version="first-accessible-uploads-v1",
        coverage=Coverage(
            complete=True,
            paginated=False,
            sampled=True,
            truncated=False,
            retrieved=1,
            usable=1,
            inaccessible=0,
            unknown=0,
            completeness_basis="Sample",
        ),
    )

    snapshot = LibrarySnapshot(
        snapshot_id="snap-oracle-1",
        binding=BINDING,
        started_at=NOW,
        fetched_at=NOW,
        likes={
            v1.video_id: None,
            v2.video_id: None,
            v3.video_id: None,
        },
        subscriptions=(
            SubscriptionSignal(
                subscription_id="sub-1",
                channel_id=sub_channel.channel_id,
                subscribed_at=NOW - timedelta(days=5),
                topic_sample=sub_sample,
                coverage=sub_sample.coverage,
            ),
        ),
        owned_playlist_ids=("PL1",),
        playlist_occurrences=(
            PlaylistOccurrence(
                playlist_id="PL1",
                playlist_item_id="pli-1",
                video_id=v3.video_id,  # overlap with likes
                position=0,
                added_at=NOW - timedelta(days=2),
                accessibility="available",
            ),
            PlaylistOccurrence(
                playlist_id="PL1",
                playlist_item_id="pli-2",
                video_id=v4.video_id,
                position=1,
                added_at=NOW - timedelta(days=1),
                accessibility="available",
            ),
            PlaylistOccurrence(
                playlist_id="PL1",
                playlist_item_id="pli-3",
                video_id=v5_unknown.video_id,
                position=2,
                added_at=NOW - timedelta(days=1),
                accessibility="available",
            ),
        ),
        videos={v.video_id: v for v in (v1, v2, v3, v4, v5_unknown, v6_sub_sample)},
        sources={
            "likes": _retrieved_source(),
            "subscriptions": _retrieved_source(),
            "playlists": _retrieved_source(),
        },
        retained_until=NOW + timedelta(days=30),
    )

    report = summarise_library(snapshot)

    # Combined unique videos: 5 total (v1..v5), excluding subscription sample v6!
    comb = report.combined_videos
    assert comb.count == 5
    assert comb.denominator == 5
    assert comb.overlap_count == 1  # v3 in both likes and playlists
    assert comb.likes_only_count == 2
    assert comb.playlists_only_count == 2
    assert comb.excluded_subscription_sample_videos == 1

    # Exact oracle: known runtimes [240, 600, 600, 1200] + 1 unknown -> retrieved=5, known=4
    rt = comb.runtime
    assert rt.retrieved_count == 5
    assert rt.known_count == 4
    assert rt.unknown_count == 1
    assert rt.mean_seconds == 660.0
    assert rt.median_seconds == 600.0
    assert [b.count for b in rt.bands] == [1, 2, 1, 0, 0]

    # Stable ascending ID tie-break: UCaaa... and UCbbb... both have count 2 -> UCaaa... first!
    assert [b.bucket_id for b in comb.top_channels] == [
        "UCaaaaaaaaaaaaaaaaaaaaaa",
        "UCbbbbbbbbbbbbbbbbbbbbbb",
    ]
    assert comb.unknown_channel_count == 1
    assert comb.unknown_category_count == 1
    assert [b.bucket_id for b in comb.top_categories] == ["27", "28"]

    # Subscriptions reported by unique channel only, never video views
    assert report.subscriptions.count == 1
    assert report.subscriptions.channel_ids == ("UCcccccccccccccccccccccc",)
    assert report.activity_label == "accessible_collection_activity"


def test_empty_populations_return_null_mean_median_and_zero_counts() -> None:
    empty_snap = LibrarySnapshot(
        snapshot_id="snap-empty",
        binding=BINDING,
        started_at=NOW,
        fetched_at=NOW,
        likes={},
        subscriptions=(),
        owned_playlist_ids=(),
        playlist_occurrences=(),
        videos={},
        sources={
            "likes": _retrieved_source(),
            "subscriptions": _retrieved_source(),
            "playlists": _retrieved_source(),
        },
        retained_until=NOW + timedelta(days=30),
    )
    report = summarise_library(empty_snap, AnalysisConfig())
    assert report.combined_videos.count == 0
    assert report.combined_videos.runtime.mean_seconds is None
    assert report.combined_videos.runtime.median_seconds is None
    assert report.combined_videos.runtime.empty_reason == "no_known_positive_durations"
    assert [b.count for b in report.combined_videos.runtime.bands] == [0, 0, 0, 0, 0]
