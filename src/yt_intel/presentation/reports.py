from collections.abc import Sequence
from dataclasses import dataclass

from yt_intel.contracts.common import Mode
from yt_intel.contracts.models import Coverage

from .text import TextSurface, coverage_lines, display_text, mode_label, render_lines


@dataclass(frozen=True)
class ReportSection:
    """Ordered display fields supplied by the analytics adapter."""

    title: str
    fields: tuple[tuple[str, str], ...]


def render_report(
    sections: Sequence[ReportSection],
    *,
    mode: Mode,
    coverage: Coverage | None = None,
    warnings: Sequence[str] = (),
    surface: TextSurface = "plain",
) -> str:
    """Display source and comparison fields computed by the report owner."""
    lines = ["Library analysis", mode_label(mode)]
    for section in sections:
        lines.extend(["", display_text(section.title, surface)])
        for label, value in section.fields:
            lines.append(
                f"- {display_text(label, surface)}: {display_text(value, surface)}"
            )
    if coverage is not None:
        lines.extend(coverage_lines(coverage, surface))
    lines.extend(f"Warning: {display_text(warning, surface)}" for warning in warnings)
    return render_lines(lines, surface)
