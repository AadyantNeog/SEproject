from collections.abc import Sequence

from yt_intel.contracts.common import Mode
from yt_intel.contracts.errors import ErrorDetail
from yt_intel.contracts.models import Coverage, RankedChannel, RankedVideo

from .text import (
    TextSurface,
    coverage_lines,
    display_text,
    format_duration,
    mode_label,
    render_lines,
)


def render_ranked_results(
    results: Sequence[RankedVideo | RankedChannel],
    *,
    mode: Mode,
    coverage: Coverage | None = None,
    warnings: Sequence[str] = (),
    surface: TextSurface = "plain",
) -> str:
    lines = ["Ranked results", mode_label(mode), ""]
    if not results:
        lines.append("No results returned.")
    for result in results:
        lines.extend(
            _video_lines(result, surface)
            if isinstance(result, RankedVideo)
            else _channel_lines(result, surface)
        )
    if coverage is not None:
        lines.extend(coverage_lines(coverage, surface))
    lines.extend(f"Warning: {display_text(warning, surface)}" for warning in warnings)
    return render_lines(lines, surface)


def _video_lines(result: RankedVideo, surface: TextSurface) -> list[str]:
    video = result.video
    duration = (
        "unknown"
        if video.duration_seconds is None
        else format_duration(video.duration_seconds)
    )
    lines = [
        f"Rank {result.rank}: {display_text(video.title, surface)}",
        f"Channel: {display_text(video.channel_title or 'unknown', surface)}",
        f"URL: {video.canonical_url}",
        f"Duration: {duration}",
        f"Project score: {result.score}",
        f"Ranking version: {display_text(result.ranking_version, surface)}",
        f"Reason: {display_text(result.reason, surface)}",
    ]
    if video.language_evidence == "audio":
        lines.append(
            f"Audio language (API evidence): {display_text(video.default_audio_language or 'unknown', surface)}"
        )
    elif video.language_evidence == "metadata_only":
        lines.append(
            f"Metadata language: {display_text(video.default_metadata_language or 'unknown', surface)}"
        )
        lines.append("Audio language: unknown")
    else:
        lines.append("Audio language: unknown")
    if result.matched_terms:
        lines.append(
            "Matched terms: "
            + ", ".join(display_text(term, surface) for term in result.matched_terms)
        )
    if result.preference_sources:
        lines.append(f"Preference sources: {', '.join(result.preference_sources)}")
    lines.extend(
        f"Evidence warning: {display_text(warning, surface)}"
        for warning in (*video.evidence_warnings, *result.evidence_warnings)
    )
    return [*lines, ""]


def _channel_lines(result: RankedChannel, surface: TextSurface) -> list[str]:
    sample = result.sample
    lines = [
        f"Rank {result.rank}: {display_text(sample.channel.title, surface)}",
        f"URL: {sample.channel.canonical_url}",
        f"Project score: {result.score}",
        f"Ranking version: {display_text(result.ranking_version, surface)}",
        f"Reason: {display_text(result.reason, surface)}",
        f"Channel sample: {sample.usable} usable, {sample.attempted} attempted, {sample.skipped} skipped",
        f"Selection rule: {display_text(sample.selection_rule_version, surface)}",
    ]
    lines.extend(
        f"Sample limitation: {display_text(warning, surface)}"
        for warning in result.sample_limitations
    )
    return [*lines, *coverage_lines(sample.coverage, surface), ""]


def render_error(
    error: ErrorDetail, *, mode: Mode, surface: TextSurface = "plain"
) -> str:
    can_retry = "yes" if error.retryable else "no"
    return render_lines(
        [
            mode_label(mode),
            f"Error {display_text(error.code, surface)}: {display_text(error.message, surface)}",
            f"Retryable: {can_retry}",
            f"Next action: {display_text(error.safe_next_action, surface)}",
        ],
        surface,
    )
