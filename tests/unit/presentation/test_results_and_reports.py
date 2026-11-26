import json
from pathlib import Path

from yt_intel.contracts.errors import ResultEnvelope
from yt_intel.contracts.models import (
    Channel,
    ChannelSample,
    Coverage,
    RankedChannel,
    RankedVideo,
    Video,
)
from yt_intel.presentation.reports import ReportSection, render_report
from yt_intel.presentation.results import render_error, render_ranked_results

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "contracts"


def fixture_coverage() -> Coverage:
    return Coverage(
        complete=False,
        paginated=True,
        sampled=True,
        truncated=True,
        retrieved=8,
        usable=7,
        inaccessible=1,
        unknown=2,
        limits={"videos": 8},
        sampled_sources=("subscriptions",),
        completeness_basis="First available page",
        continuation_ref="fixture-next",
        warnings=("Budget reached",),
    )


def test_ranked_results_preserve_supplied_order_scores_and_unknowns():
    payload = json.loads((FIXTURES / "video.json").read_bytes())
    payload.update(
        title="<b>Fixture video</b>",
        duration_seconds=None,
        default_audio_language=None,
        default_metadata_language="en",
        language_evidence="metadata_only",
        evidence_warnings=["Audio field missing"],
    )
    video = Video.model_validate_json(json.dumps(payload))
    second = RankedVideo(
        rank=2,
        video=video,
        score=0.123456789,
        ranking_version="v1",
        reason="Title words matched",
        matched_terms=("example",),
        preference_sources=("likes",),
    )
    first = second.model_copy(update={"rank": 1, "score": 0.5})
    text = render_ranked_results(
        (second, first), mode="fixture", coverage=fixture_coverage(), surface="markdown"
    )
    assert text.index("Rank 2:") < text.index("Rank 1:")
    assert "Project score: 0.123456789" in text
    assert "Duration: unknown" in text
    assert "Audio language: unknown" in text
    assert "Metadata language: en" in text
    assert "Audio field missing" in text
    assert "Preference sources: likes" in text
    assert "Sampled: yes" in text
    assert "Unknown: 2" in text
    assert r"\<b\>Fixture video\<\/b\>" in text
    assert video.canonical_url in text


def test_channel_result_discloses_sample_and_coverage():
    video = Video.model_validate_json((FIXTURES / "video.json").read_bytes())
    channel_id = video.channel_id
    assert channel_id is not None
    channel = Channel(
        channel_id=channel_id,
        title="Fixture channel",
        canonical_url=f"https://www.youtube.com/channel/{channel_id}",
        handle=None,
        description=None,
        uploads_playlist_id=None,
        fetched_at=video.fetched_at,
    )
    sample = ChannelSample(
        channel=channel,
        video_ids=(video.video_id,),
        attempted=2,
        usable=1,
        skipped=1,
        selection_rule_version="recent-v1",
        coverage=fixture_coverage(),
    )
    result = RankedChannel(
        rank=1,
        sample=sample,
        score=0.5,
        ranking_version="v1",
        reason="Example match",
        sample_limitations=("Only two candidates attempted",),
    )
    text = render_ranked_results((result,), mode="fixture")
    assert channel.canonical_url in text
    assert "Channel sample: 1 usable, 2 attempted, 1 skipped" in text
    assert "Selection rule: recent-v1" in text
    assert "Sample limitation: Only two candidates attempted" in text
    assert "Basis: First available page" in text


def test_empty_ranking_keeps_the_supplied_warning():
    text = render_ranked_results((), mode="live", warnings=("No eligible candidates",))
    assert "Mode: live" in text
    assert "No results returned." in text
    assert "Warning: No eligible candidates" in text


def test_error_keeps_stable_code_and_action():
    result = ResultEnvelope[None].model_validate_json(
        (FIXTURES / "error.json").read_bytes()
    )
    error = result.error
    assert error is not None
    output = render_error(error, mode=result.mode)
    assert f"Error {error.code}: {error.message}" in output
    assert "Retryable: no" in output
    assert f"Next action: {error.safe_next_action}" in output


def test_report_preserves_counts_denominators_and_undefined_comparisons():
    sections = (
        ReportSection(
            "Playlist items",
            (("Count", "2 of 5 playlist occurrences"), ("Unknown timestamp", "1")),
        ),
        ReportSection(
            "Period comparison",
            (
                ("Timestamp basis", "playlist item added date"),
                ("Change from zero", "undefined"),
            ),
        ),
    )
    text = render_report(
        sections,
        mode="fixture",
        coverage=fixture_coverage(),
        warnings=("Source\nLabel changed",),
    )
    assert text.index("Playlist items") < text.index("Period comparison")
    assert "Count: 2 of 5 playlist occurrences" in text
    assert "Unknown timestamp: 1" in text
    assert "Timestamp basis: playlist item added date" in text
    assert "Change from zero: undefined" in text
    assert "Inaccessible: 1" in text
    assert r"Warning: Source\u000aLabel changed" in text
