from datetime import timedelta
from math import hypot, log, sqrt
from pathlib import Path

import pytest

from yt_intel.contracts.errors import ContractError
from yt_intel.contracts.models import (
    CandidateSet,
    Channel,
    ChannelSample,
    Coverage,
    LibrarySnapshot,
    PlaylistOccurrence,
    SourceCoverage,
    SubscriptionSignal,
    Video,
)
from yt_intel.domain.profiles import build_profile, rank_recommendations
from yt_intel.services.recommendations import (
    RecommendationFilters,
    RecommendationService,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/contracts"
BASE = LibrarySnapshot.model_validate_json(
    (FIXTURES / "library_snapshot.json").read_bytes()
)
NOW = BASE.fetched_at
VIDEO = next(iter(BASE.videos.values()))
SERVICE = RecommendationService(
    lambda tag: (
        tag.casefold() if tag.casefold() in {"en", "en-us", "en-gb", "fr"} else None
    )
)


def video(index: int, title: str, **changes: object) -> Video:
    identifier = f"fixture{index:04d}"
    return Video.model_validate(
        {
            **VIDEO.model_dump(),
            "video_id": identifier,
            "canonical_url": f"https://www.youtube.com/watch?v={identifier}",
            "title": title,
            "description": None,
            "tags": None,
            **changes,
        }
    )


def coverage(count: int) -> Coverage:
    return Coverage(
        complete=True,
        paginated=False,
        sampled=False,
        truncated=False,
        retrieved=count,
        usable=count,
        inaccessible=0,
        unknown=0,
        limits={"candidates": 200},
        completeness_basis="Fixture collection",
    )


def occurrence(video_id: str, position: int) -> PlaylistOccurrence:
    return PlaylistOccurrence(
        playlist_id="fixture-playlist",
        playlist_item_id=f"fixture-item-{position}",
        video_id=video_id,
        position=position,
        added_at=None,
        accessibility="available",
    )


def library(
    liked: Video,
    playlist: Video | None = None,
    subscription: SubscriptionSignal | None = None,
) -> LibrarySnapshot:
    videos = {liked.video_id: liked}
    sources = dict(BASE.sources)
    if playlist is not None:
        videos[playlist.video_id] = playlist
        sources["playlists"] = SourceCoverage(state="retrieved", coverage=coverage(2))
    if subscription is not None:
        sources["subscriptions"] = SourceCoverage(
            state="retrieved", coverage=coverage(1)
        )
    return LibrarySnapshot.model_validate(
        {
            **BASE.model_dump(),
            "videos": videos,
            "likes": {liked.video_id: None},
            "sources": sources,
            "owned_playlist_ids": ("fixture-playlist",) if playlist is not None else (),
            "playlist_occurrences": (
                occurrence(playlist.video_id, 0),
                occurrence(playlist.video_id, 1),
            )
            if playlist is not None
            else (),
            "subscriptions": (subscription,) if subscription is not None else (),
        }
    )


def pool(*videos: Video, seed: str | None = None) -> CandidateSet:
    return CandidateSet(
        candidate_set_id="recommendation-fixture",
        binding=BASE.binding,
        videos=videos,
        source="synthetic",
        seed_video_id=seed,
        topic=None,
        coverage=coverage(len(videos)),
        ranking_version="ranking-v1",
        config_version="fixture-v1",
        created_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )


def test_three_families_contribute_the_planned_weights_and_report_sources():
    liked = video(1, "compiler")
    saved = video(2, "orchid")
    channel = Channel(
        channel_id=BASE.binding.channel_id,
        title="astronomy",
        canonical_url=f"https://www.youtube.com/channel/{BASE.binding.channel_id}",
        handle=None,
        description="astronomy",
        uploads_playlist_id=None,
        fetched_at=NOW,
    )
    sample = ChannelSample(
        channel=channel,
        video_ids=(),
        attempted=0,
        usable=0,
        skipped=0,
        selection_rule_version="fixture",
        coverage=coverage(0),
    )
    subscription = SubscriptionSignal(
        subscription_id="fixture-subscription",
        channel_id=channel.channel_id,
        subscribed_at=None,
        topic_sample=sample,
        coverage=coverage(1),
    )
    snapshot = library(liked, saved, subscription)
    compiler, orchid, astronomy = (
        video(3, "compiler"),
        video(4, "orchid"),
        video(5, "astronomy"),
    )
    seed = video(6, "compiler")
    result = SERVICE.recommend(
        snapshot,
        pool(astronomy, orchid, compiler, seed, liked, saved, seed=seed.video_id),
        binding=BASE.binding,
        now=NOW,
    )
    assert [rank.video.video_id for rank in result.results] == [
        compiler.video_id,
        orchid.video_id,
        astronomy.video_id,
    ]
    assert [rank.preference_sources for rank in result.results] == [
        ("likes",),
        ("playlists",),
        ("subscriptions",),
    ]
    norm = hypot(0.50, 0.30, 0.20)
    assert [rank.score for rank in result.results] == pytest.approx(
        [0.50 / norm, 0.30 / norm, 0.20 / norm]
    )
    assert "Subscription samples describe channel topics." in result.warnings
    assert [source.state for source in result.sources.values()] == ["retrieved"] * 3
    assert (
        SERVICE.search_query(snapshot, binding=BASE.binding, now=NOW)
        == "compiler orchid astronomy"
    )


def test_profile_reuses_one_document_for_shared_video_and_ignores_denied_payload():
    liked = video(1, "compiler")
    snapshot = library(liked, liked)
    profile = build_profile(snapshot)
    assert len(profile.documents) == 1
    assert profile.source_documents == {"likes": (0,), "playlists": (0,)}
    assert profile.excluded_video_ids == frozenset({liked.video_id})
    denied = snapshot.model_copy(
        update={
            "sources": {
                **snapshot.sources,
                "playlists": SourceCoverage(state="denied", coverage=None),
            }
        }
    )
    assert set(build_profile(denied).source_documents) == {"likes"}
    candidate = video(2, "compiler")
    result = SERVICE.recommend(denied, pool(candidate), binding=BASE.binding, now=NOW)
    assert result.results[0].score == pytest.approx(1.0)
    assert result.results[0].preference_sources == ("likes",)
    assert "Playlists source: denied." in result.warnings


def test_profile_and_candidates_share_idf_with_an_independent_oracle():
    profile = build_profile(library(video(1, "compiler syntax")))
    compiler = video(2, "compiler")
    syntax = video(3, "syntax lexer")
    results = rank_recommendations(profile, [syntax, compiler], limit=2)
    common = 1 + log(4 / 3)
    rare = 1 + log(4 / 2)
    assert [r.score for r in results] == pytest.approx(
        [1 / sqrt(2), common / (sqrt(2) * hypot(common, rare))]
    )


def test_explicit_filters_keep_remaining_duration_exact():
    snapshot = library(video(1, "database indexing"))
    first, bigger, fits = (
        video(2, "database indexing", duration_seconds=600),
        video(3, "database indexing", duration_seconds=600),
        video(4, "database indexing", duration_seconds=244),
    )
    sources = pool(
        fits,
        first,
        bigger,
        video(5, "database backups", duration_seconds=200),
        video(
            6, "database indexing", duration_seconds=50, default_audio_language="en-GB"
        ),
        video(7, "database indexing", duration_seconds=None),
        video(8, "database indexing", duration_seconds=601),
        video(
            9,
            "database indexing",
            duration_seconds=75,
            language_evidence="metadata_only",
            default_audio_language=None,
            default_metadata_language="en-US",
        ),
    )
    result = SERVICE.recommend(
        snapshot,
        sources,
        binding=BASE.binding,
        now=NOW,
        filters=RecommendationFilters(
            topic="indexing", max_video_seconds=600, total_seconds=900, language="en-US"
        ),
    )
    assert [entry.video.video_id for entry in result.results] == [
        first.video_id,
        fits.video_id,
    ]
    assert (result.total_seconds, result.unused_seconds) == (844, 56)


def test_no_usable_sources_requests_a_seed_or_topic():
    empty = BASE.model_copy(update={"likes": {}, "videos": {}})
    with pytest.raises(ContractError) as failure:
        SERVICE.search_query(empty, binding=BASE.binding, now=NOW)
    assert failure.value.detail.code == "INSUFFICIENT_DATA"
    assert "playlists: denied" in failure.value.detail.message
    assert "seed video or topic" in failure.value.detail.safe_next_action


def test_unknown_duration_is_usable_without_a_duration_constraint():
    snapshot = library(video(1, "indexing"))
    unknown = video(2, "indexing", duration_seconds=None)
    result = SERVICE.recommend(snapshot, pool(unknown), binding=BASE.binding, now=NOW)
    assert [entry.video.video_id for entry in result.results] == [unknown.video_id]
    assert result.total_seconds is None
    assert result.unused_seconds is None


def test_foreign_expired_and_live_inputs_are_rejected():
    foreign = BASE.binding.model_copy(update={"credential_binding_id": "fixture-other"})
    live = BASE.binding.model_copy(update={"mode": "live"})
    for snapshot, binding, now, code in [
        (BASE, foreign, NOW, "ACCOUNT_MISMATCH"),
        (BASE, BASE.binding, BASE.retained_until, "CONTENT_UNAVAILABLE"),
        (BASE.model_copy(update={"binding": live}), live, NOW, "POLICY_BLOCKED"),
    ]:
        with pytest.raises(ContractError) as failure:
            SERVICE.search_query(snapshot, binding=binding, now=now)
        assert failure.value.detail.code == code
