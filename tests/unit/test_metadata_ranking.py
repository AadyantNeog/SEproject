from collections import Counter
from math import hypot, log
from pathlib import Path

import pytest

from yt_intel.contracts.models import Channel, ChannelSample, Coverage, Video
from yt_intel.domain.ranking import (
    ChannelCorpus,
    build_video_document,
    cosine_similarity,
    rank_channels,
    rank_videos,
    tfidf_vectors,
    tokenize,
)


@pytest.fixture
def video() -> Video:
    path = Path(__file__).resolve().parents[1] / "fixtures/contracts/video.json"
    return Video.model_validate_json(path.read_bytes())


def candidate(seed: Video, video_id: str, **fields: object) -> Video:
    return Video.model_validate(
        {
            **seed.model_dump(),
            "video_id": video_id,
            "canonical_url": f"https://www.youtube.com/watch?v={video_id}",
            **fields,
        }
    )


def test_terms_preserve_normalized_technical_words_and_versions():
    assert tokenize("THE Ｃ＋＋ and C# v2.13.0 3.13 café") == (
        "c++",
        "c#",
        "v2.13.0",
        "3.13",
        "café",
    )
    assert tokenize("compiler late", max_chars=8) == ("compiler",)


def test_video_fields_have_documented_term_weights(video: Video):
    authored = video.model_copy(
        update={
            "title": "compiler compiler",
            "description": "syntax",
            "tags": ("types",),
        }
    )
    assert build_video_document(authored) == {"compiler": 6, "syntax": 1, "types": 2}


def test_shared_tfidf_matches_hand_calculated_cosine():
    seed, related, unrelated = tfidf_vectors(
        [
            Counter({"python": 1}),
            Counter({"python": 1, "compiler": 1}),
            Counter({"gardening": 1}),
        ]
    )
    python_idf = log(4 / 3) + 1
    compiler_idf = log(4 / 2) + 1
    assert cosine_similarity(seed, related) == pytest.approx(
        python_idf / hypot(python_idf, compiler_idf)
    )
    assert cosine_similarity(seed, unrelated) == 0.0


def test_video_ranking_ties_and_missing_evidence_are_explicit(video: Video):
    seed = video.model_copy(
        update={
            "title": "compiler types",
            "description": None,
            "tags": None,
            "category_id": "27",
        }
    )
    first = candidate(seed, "synthetic01")
    second = candidate(seed, "synthetic02")
    mismatch = candidate(seed, "synthetic03", title="orchid gardening")
    unknown = candidate(seed, "synthetic04", category_id=None)
    output = rank_videos(seed, [second, mismatch, first, first, seed, unknown], limit=3)
    assert [item.video.video_id for item in output] == [
        "synthetic01",
        "synthetic02",
        "synthetic04",
    ]
    assert output[0].score == pytest.approx(1)
    assert "Same category" in output[0].reason
    assert output[0].matched_terms == ("compiler", "types")
    assert (
        "Category evidence unavailable. Score uses text only."
        in output[2].evidence_warnings
    )
    assert "Candidate tags unavailable." in output[0].evidence_warnings


def test_category_weight_applies_only_when_known(video: Video):
    seed = video.model_copy(
        update={
            "title": "compiler",
            "description": None,
            "tags": None,
            "category_id": "27",
        }
    )
    different = candidate(seed, "synthetic05", category_id="20")
    same = candidate(seed, "synthetic06")
    result = rank_videos(seed, [different, same], limit=2)
    assert [item.video.video_id for item in result] == ["synthetic06", "synthetic05"]
    assert result[0].score == pytest.approx(1)
    assert result[1].score == pytest.approx(0.9)


def test_channel_ranking_requires_supporting_evidence_and_breaks_ties(video: Video):
    coverage = Coverage(
        complete=True,
        paginated=False,
        sampled=True,
        truncated=False,
        retrieved=0,
        usable=0,
        inaccessible=0,
        unknown=0,
        completeness_basis="Fixture",
    )

    def entry(ch: str, description: str | None) -> ChannelCorpus:
        channel_id = "UC" + ch * 22
        channel = Channel(
            channel_id=channel_id,
            title="Compiler examples",
            description=description,
            handle=None,
            uploads_playlist_id=None,
            fetched_at=video.fetched_at,
            canonical_url=f"https://www.youtube.com/channel/{channel_id}",
        )
        return ChannelCorpus(
            ChannelSample(
                channel=channel,
                video_ids=(),
                attempted=0,
                usable=0,
                skipped=0,
                selection_rule_version="fixture-v1",
                coverage=coverage,
            ),
            (),
        )

    seed = entry("Z", "compiler type theory")
    first = entry("A", "compiler type theory")
    second = entry("B", "compiler type theory")
    unsupported = entry("C", None)
    results = rank_channels(seed, [second, unsupported, first, seed], limit=2)
    assert [item.sample.channel.channel_id for item in results] == [
        "UC" + "A" * 22,
        "UC" + "B" * 22,
    ]
    assert results[0].score == pytest.approx(results[1].score)
    assert rank_channels(unsupported, [seed], limit=2) == ()
