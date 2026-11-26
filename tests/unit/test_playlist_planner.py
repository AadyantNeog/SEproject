from datetime import timedelta
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from yt_intel.contracts.errors import ContractError
from yt_intel.contracts.models import CandidateSet, Coverage, LibrarySnapshot, Video
from yt_intel.domain.constraints import (
    PlaylistRequest,
    audio_language_matches,
    parse_playlist_request,
)
from yt_intel.domain.proposals import PlaylistPlanner, proposal_digest

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/contracts"
SNAPSHOT = LibrarySnapshot.model_validate_json(
    (FIXTURES / "library_snapshot.json").read_bytes()
)
TEMPLATE = next(iter(SNAPSHOT.videos.values()))
NOW = SNAPSHOT.fetched_at
BINDING = SNAPSHOT.binding
REQUEST: dict[str, object] = {
    "topic": "database indexing",
    "total_seconds": 7200,
    "max_video_seconds": 1200,
    "language": "en",
    "title": "Indexing study",
}
_FIXTURE_TAGS = {"en", "en-us", "en-gb", "en-latn-us", "en-gb-x-us", "fr"}


def normalize_fixture_tag(tag: str) -> str | None:
    tag = tag.casefold()
    return tag if tag in _FIXTURE_TAGS else None


PLANNER = PlaylistPlanner(normalize_fixture_tag)


def candidate(index: int, duration: int | None, **changes: object) -> Video:
    video_id = f"fixture{index:04d}"
    return Video.model_validate(
        {
            **TEMPLATE.model_dump(),
            "video_id": video_id,
            "canonical_url": f"https://www.youtube.com/watch?v={video_id}",
            "title": "Database indexing",
            "description": None,
            "tags": None,
            "duration_seconds": duration,
            **changes,
        }
    )


def pool(*videos: Video, seed_video_id: str | None = None) -> CandidateSet:
    return CandidateSet(
        candidate_set_id="fixture-set",
        binding=BINDING,
        videos=videos,
        source="synthetic",
        seed_video_id=seed_video_id,
        topic=None,
        coverage=Coverage(
            complete=True,
            paginated=False,
            sampled=False,
            truncated=False,
            retrieved=len(videos),
            usable=len(videos),
            inaccessible=0,
            unknown=0,
            limits={"candidates": 200},
            completeness_basis="Fixture candidate list",
        ),
        ranking_version="ranking-v1",
        config_version="fixture-v1",
        created_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )


def plan(candidates: CandidateSet, **changes: object):
    return PLANNER.plan(
        parse_playlist_request({**REQUEST, **changes}),
        candidates,
        binding=BINDING,
        destination_channel_title="Fixture Learning",
        proposal_id="fixture-plan",
        now=NOW,
    )


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"duration_mode": "exact"}, "CLARIFICATION_REQUIRED"),
        ({"total_seconds": True}, "INVALID_INPUT"),
        ({"max_video_seconds": "1200"}, "INVALID_INPUT"),
        ({"confirmed": True}, "INVALID_INPUT"),
    ],
)
def test_request_errors_keep_hard_constraints(change, code):
    with pytest.raises(ContractError) as error:
        parse_playlist_request({**REQUEST, **change})
    assert error.value.detail.code == code


def test_missing_hard_constraints_need_clarification():
    with pytest.raises(ContractError) as error:
        parse_playlist_request({"title": "Indexing"})
    assert error.value.detail.code == "CLARIFICATION_REQUIRED"
    assert "max_video_seconds" in error.value.detail.message
    assert "language" in error.value.detail.message


def test_srs_example_excludes_1201_and_keeps_exact_unused_time():
    videos = [candidate(index, 1070) for index in range(1, 7)]
    result = plan(pool(candidate(7, 1201), *reversed(videos)))
    assert [item.video_id for item in result.items] == [
        video.video_id for video in videos
    ]
    assert (result.total_seconds, result.unused_seconds) == (6420, 780)
    assert result.exclusions == {"individual_duration_limit": 1}
    assert result.body.privacy == "private"
    assert result.expires_at == NOW + timedelta(minutes=10)
    assert result.digest == proposal_digest(result)


def test_topic_and_audio_filter_omitted_unverified_and_wrong_regions():
    good = candidate(1, 600, default_audio_language="en-Latn-US")
    wrong_region = candidate(2, 600, default_audio_language="en-GB-x-US")
    metadata_only = candidate(
        3,
        600,
        default_audio_language=None,
        default_metadata_language="en-US",
        language_evidence="metadata_only",
    )
    off_topic = candidate(4, 600, title="Orchid propagation")
    malformed = candidate(5, 600, default_audio_language="en_US")
    live = candidate(6, 600, live_status="live")
    unknown = candidate(7, None)
    seed = candidate(8, 600)
    result = plan(
        pool(
            good,
            wrong_region,
            metadata_only,
            off_topic,
            malformed,
            live,
            unknown,
            seed,
            seed_video_id=seed.video_id,
        ),
        language="en-US",
    )
    assert [item.video_id for item in result.items] == [good.video_id]
    assert result.items[0].audio_language == "en-Latn-US"
    assert result.exclusions == {
        "audio_language_mismatch": 1,
        "audio_language_unverified": 2,
        "topic_mismatch": 1,
        "recorded_status_not_verified": 1,
        "duration_unknown": 1,
        "seed_not_requested": 1,
    }
    assert audio_language_matches("en", "en-GB")
    assert not audio_language_matches("en-US", "en-GB-x-US")


def test_topic_requires_cosine_threshold_as_well_as_matching_term():
    weak = candidate(
        1,
        600,
        title="Database indexing "
        + " ".join(f"unrelated{index}" for index in range(16)),
        description=" ".join(f"z{index}" for index in range(410)),
    )
    with pytest.raises(ContractError) as error:
        plan(pool(weak))
    assert error.value.detail.code == "NO_FEASIBLE_PLAYLIST"


def test_packing_skips_larger_items_that_do_not_fit_and_preserves_a_seed_when_requested():
    seed = candidate(1, 600)
    too_long_after_first = candidate(2, 600)
    fits = candidate(3, 300)
    result = plan(
        pool(seed, fits, too_long_after_first, seed_video_id=seed.video_id),
        total_seconds=900,
        include_seed=True,
    )
    assert [item.video_id for item in result.items] == [seed.video_id, fits.video_id]
    assert result.exclusions == {"remaining_duration_limit": 1}


def test_proposal_digest_binds_material_fields_and_preserves_approved_input_on_revision():
    candidates = pool(candidate(1, 400), candidate(2, 350))
    proposal = plan(candidates)
    approved = proposal.model_copy(update={"state": "approved"})
    replacement_request = PlaylistRequest.model_validate(
        {**REQUEST, "title": "Revised indexing"}
    )
    revised = PLANNER.revise(
        approved,
        replacement_request,
        candidates,
        binding=BINDING,
        destination_channel_title="Fixture Learning",
        now=NOW + timedelta(seconds=1),
    )
    assert approved.state == "approved"
    assert revised.superseded.state == "superseded"
    assert revised.superseded.digest == proposal.digest
    assert revised.replacement.state == "proposed"
    assert revised.replacement.ref.proposal_id == proposal.ref.proposal_id
    assert revised.replacement.ref.version == 2
    assert revised.replacement.digest != proposal.digest
    assert proposal_digest(approved) == proposal.digest
    assert (
        proposal_digest(
            proposal.model_copy(update={"items": tuple(reversed(proposal.items))})
        )
        != proposal.digest
    )
    assert (
        proposal_digest(
            proposal.model_copy(update={"created_at": NOW + timedelta(seconds=1)})
        )
        == proposal.digest
    )


def test_packing_caps_at_fifty_and_keeps_stable_id_order():
    videos = [candidate(index, 1) for index in range(1, 56)]
    result = plan(pool(*reversed(videos)))
    assert tuple(item.video_id for item in result.items) == tuple(
        video.video_id for video in videos[:50]
    )
    assert result.exclusions == {"item_limit": 5}


def test_live_plan_is_policy_blocked():
    live = BINDING.model_copy(update={"mode": "live"})
    candidates = pool(candidate(1, 500)).model_copy(update={"binding": live})
    with pytest.raises(ContractError) as error:
        PLANNER.plan(
            parse_playlist_request(REQUEST),
            candidates,
            binding=live,
            destination_channel_title="Fixture Learning",
            proposal_id="fixture-plan",
            now=NOW,
        )
    assert error.value.detail.code == "POLICY_BLOCKED"


def test_expired_and_foreign_candidate_sets_fail_closed():
    candidates = pool(candidate(1, 500))
    request = parse_playlist_request(REQUEST)
    foreign = BINDING.model_copy(update={"credential_binding_id": "fixture-other"})
    for binding, now, code in [
        (foreign, NOW, "ACCOUNT_MISMATCH"),
        (BINDING, candidates.expires_at, "CONTENT_UNAVAILABLE"),
    ]:
        with pytest.raises(ContractError) as error:
            PLANNER.plan(
                request,
                candidates,
                binding=binding,
                destination_channel_title="Fixture Learning",
                proposal_id="fixture-plan",
                now=now,
            )
        assert error.value.detail.code == code


@given(
    st.lists(st.integers(min_value=1, max_value=125), min_size=1, max_size=65),
    st.integers(min_value=1, max_value=1500),
)
@settings(max_examples=35, deadline=None)
def test_packing_is_deterministic_and_within_all_duration_bounds(durations, total):
    videos = [
        candidate(index, duration) for index, duration in enumerate(durations, start=1)
    ]
    if min(durations) > min(total, 120):
        with pytest.raises(ContractError) as error:
            plan(pool(*videos), total_seconds=total, max_video_seconds=120)
        assert error.value.detail.code == "NO_FEASIBLE_PLAYLIST"
        return
    result = plan(pool(*videos), total_seconds=total, max_video_seconds=120)
    reverse = plan(pool(*reversed(videos)), total_seconds=total, max_video_seconds=120)
    assert result.items == reverse.items
    assert result.digest == reverse.digest
    assert 1 <= len(result.items) <= 50
    assert len({item.video_id for item in result.items}) == len(result.items)
    assert all(0 < item.duration_seconds <= 120 for item in result.items)
    assert result.total_seconds == sum(item.duration_seconds for item in result.items)
    assert result.unused_seconds == total - result.total_seconds >= 0
