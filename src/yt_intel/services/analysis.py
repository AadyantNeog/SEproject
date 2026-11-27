from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC

from yt_intel.analytics.periods import (
    TimePeriod,
    validate_period_pair,
)
from yt_intel.analytics.summaries import (
    AnalysisConfig,
    AnalysisReport,
    summarise_library,
)
from yt_intel.contracts.common import AccountBinding, OpaqueId
from yt_intel.contracts.errors import ContractError, ErrorCode, ErrorDetail
from yt_intel.contracts.models import LibrarySnapshot, LibrarySource
from yt_intel.contracts.repositories import SnapshotRepository
from yt_intel.contracts.workflow import Clock
from yt_intel.infrastructure.clock import SystemClock
from yt_intel.presentation.reports import ReportSection, render_report


@dataclass(frozen=True, slots=True)
class AnalysisOutcome:
    report: AnalysisReport
    rendered_text: str


def _analysis_error(
    code: ErrorCode, message: str, *, safe_next_action: str
) -> ContractError:
    return ContractError(
        ErrorDetail(
            code=code,
            message=message,
            retryable=False,
            safe_next_action=safe_next_action,
        )
    )


def build_report_sections(report: AnalysisReport) -> tuple[ReportSection, ...]:
    """Convert an AnalysisReport into ordered ReportSections for Aadyant's renderer."""
    comb = report.combined_videos
    rt = comb.runtime
    mean_str = f"{rt.mean_seconds:.1f}s" if rt.mean_seconds is not None else "unknown"
    med_str = (
        f"{rt.median_seconds:.1f}s" if rt.median_seconds is not None else "unknown"
    )
    band_str = ", ".join(f"{b.band}={b.count}" for b in rt.bands)

    sections: list[ReportSection] = [
        ReportSection(
            title="Accessible collection overview",
            fields=(
                ("Scope", report.evidence_disclaimer),
                ("Snapshot", report.snapshot_id),
                ("Likes (unique videos)", str(report.likes.count)),
                (
                    "Playlists (occurrences / unique)",
                    f"{report.playlists.occurrence_count} / {report.playlists.unique_video_count}",
                ),
                (
                    "Combined unique videos (overlap)",
                    f"{comb.count} (overlap: {comb.overlap_count})",
                ),
                ("Subscriptions (unique channels)", str(report.subscriptions.count)),
            ),
        ),
        ReportSection(
            title="Runtime preferences (combined unique videos)",
            fields=(
                (
                    "Known positive durations / retrieved",
                    f"{rt.known_count} / {rt.retrieved_count} (unknown: {rt.unknown_count})",
                ),
                ("Mean / median", f"{mean_str} / {med_str}"),
                ("Duration bands", band_str),
            ),
        ),
    ]
    if report.period_comparison is not None:
        pc = report.period_comparison
        period_fields: list[tuple[str, str]] = [
            (
                "Period A",
                f"{pc.period_a.start.isoformat()} to {pc.period_a.end.isoformat()}",
            ),
            (
                "Period B",
                f"{pc.period_b.start.isoformat()} to {pc.period_b.end.isoformat()}",
            ),
        ]
        if pc.playlist_additions is not None:
            pa = pc.playlist_additions
            pa_pct = (
                f"{pa.percent_change:.1f}%"
                if pa.percent_change is not None
                else f"undefined ({pa.percent_change_reason})"
            )
            period_fields.append(
                (
                    "Playlist additions (added_at)",
                    f"A={pa.count_a}, B={pa.count_b}, diff={pa.absolute_difference:+d}, change={pa_pct}",
                )
            )
        if pc.subscription_creations is not None:
            sc = pc.subscription_creations
            sc_pct = (
                f"{sc.percent_change:.1f}%"
                if sc.percent_change is not None
                else f"undefined ({sc.percent_change_reason})"
            )
            period_fields.append(
                (
                    "Subscription creations (subscribed_at)",
                    f"A={sc.count_a}, B={sc.count_b}, diff={sc.absolute_difference:+d}, change={sc_pct}",
                )
            )
        if pc.likes_trend is not None:
            period_fields.append(("Likes trend", pc.likes_trend.explanation))
        sections.append(
            ReportSection(
                title="Period comparison (UTC [start, end))",
                fields=tuple(period_fields),
            )
        )
    return tuple(sections)


class AnalysisService:
    """Validate policy/account/snapshot expiry and invoke pure FR-4 analytics."""

    def __init__(
        self,
        *,
        snapshot_repo: SnapshotRepository,
        clock: Clock | None = None,
    ) -> None:
        self._snapshots = snapshot_repo
        self._clock: Clock = clock if clock is not None else SystemClock()

    def analyse_snapshot(
        self,
        snapshot: LibrarySnapshot,
        *,
        binding: AccountBinding,
        sources: Sequence[LibrarySource] | None = None,
        period_a: TimePeriod | None = None,
        period_b: TimePeriod | None = None,
    ) -> AnalysisOutcome:
        if binding.mode != "fixture":
            raise _analysis_error(
                "POLICY_BLOCKED",
                "Live derived library analytics is pending D-02 policy clearance.",
                safe_next_action="Use a synthetic fixture account until policy clearance is recorded.",
            )
        if snapshot.binding != binding:
            raise _analysis_error(
                "ACCOUNT_MISMATCH",
                "Snapshot belongs to a different account binding.",
                safe_next_action="Analyse a snapshot collected under the active account.",
            )
        now = self._clock.now().astimezone(UTC)
        if snapshot.retained_until <= now:
            raise _analysis_error(
                "CONTENT_UNAVAILABLE",
                "Library snapshot has expired past its retention limit.",
                safe_next_action="Collect a fresh library snapshot with get_library.",
            )
        validate_period_pair(period_a, period_b)

        config = (
            AnalysisConfig(sources=tuple(dict.fromkeys(sources)))
            if sources is not None
            else AnalysisConfig()
        )
        report = summarise_library(
            snapshot,
            config,
            report_id=f"rep-{uuid.uuid4().hex[:12]}",
            period_a=period_a,
            period_b=period_b,
        )
        text = render_report(
            build_report_sections(report),
            mode=binding.mode,
            warnings=report.warnings,
        )
        return AnalysisOutcome(report=report, rendered_text=text)

    async def analyse_stored_snapshot(
        self,
        *,
        binding: AccountBinding,
        snapshot_id: OpaqueId,
        sources: Sequence[LibrarySource] | None = None,
        period_a: TimePeriod | None = None,
        period_b: TimePeriod | None = None,
    ) -> AnalysisOutcome:
        validate_period_pair(period_a, period_b)
        now = self._clock.now().astimezone(UTC)
        snapshot = await self._snapshots.get_snapshot(binding, snapshot_id, now=now)
        if snapshot is None:
            raise _analysis_error(
                "CONTENT_UNAVAILABLE",
                "Requested library snapshot was not found, expired, or belongs to another account.",
                safe_next_action="Run get_library to create a fresh snapshot and pass its snapshot_id.",
            )
        return self.analyse_snapshot(
            snapshot,
            binding=binding,
            sources=sources,
            period_a=period_a,
            period_b=period_b,
        )
