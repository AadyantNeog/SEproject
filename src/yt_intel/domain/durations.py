from __future__ import annotations

import re
from dataclasses import dataclass

from yt_intel.contracts.errors import ContractError, ErrorDetail

_ISO_DURATION_RE = re.compile(
    r"^P"
    r"(?:(?P<days>\d+)D)?"
    r"(?:(?P<time>T)"
    r"(?:(?P<hours>\d+)H)?"
    r"(?:(?P<minutes>\d+)M)?"
    r"(?:(?P<seconds>\d+)S)?"
    r")?$"
)
_CALENDAR_UNIT_RE = re.compile(r"^P(?:\d+[YMW]|.*?(?:[YW]|M(?=.*T)))")
_NON_INTEGRAL_RE = re.compile(r"\d[.,]\d")


@dataclass(frozen=True, slots=True)
class ParsedDuration:
    """Result of parsing an API ISO 8601 duration into exact positive seconds."""

    seconds: int | None
    warning: str | None = None


def parse_iso8601_duration(raw: str | None) -> ParsedDuration:
    """Parse YouTube API ISO 8601 day/hour/minute/second durations into exact integer seconds.

    Missing, zero, negative, non-integral, calendar-unit (Y/M/W), and malformed values
    return ``seconds=None`` with an explicit warning code rather than rounding or guessing.
    """
    if raw is None:
        return ParsedDuration(seconds=None, warning="duration_missing")
    if not isinstance(raw, str):
        return ParsedDuration(seconds=None, warning="duration_malformed")

    value = raw.strip()
    if not value:
        return ParsedDuration(seconds=None, warning="duration_missing")
    if "-" in value:
        return ParsedDuration(seconds=None, warning="duration_negative")
    if _NON_INTEGRAL_RE.search(value):
        return ParsedDuration(seconds=None, warning="duration_non_integral")

    match = _ISO_DURATION_RE.fullmatch(value)
    if match is None:
        if _CALENDAR_UNIT_RE.match(value):
            return ParsedDuration(
                seconds=None, warning="duration_unsupported_calendar_unit"
            )
        return ParsedDuration(seconds=None, warning="duration_malformed")

    days_str = match.group("days")
    time_marker = match.group("time")
    hours_str = match.group("hours")
    minutes_str = match.group("minutes")
    seconds_str = match.group("seconds")

    if time_marker is not None and not any((hours_str, minutes_str, seconds_str)):
        return ParsedDuration(seconds=None, warning="duration_malformed")
    if not any((days_str, hours_str, minutes_str, seconds_str)):
        return ParsedDuration(seconds=None, warning="duration_malformed")

    total = (
        int(days_str or 0) * 86_400
        + int(hours_str or 0) * 3_600
        + int(minutes_str or 0) * 60
        + int(seconds_str or 0)
    )
    if total == 0:
        return ParsedDuration(seconds=None, warning="duration_zero")
    return ParsedDuration(seconds=total, warning=None)


def parse_positive_seconds(value: object, *, field_name: str = "duration") -> int:
    """Validate a user-supplied positive integer duration in seconds (rejects booleans)."""
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ContractError(
            ErrorDetail(
                code="INVALID_INPUT",
                message=f"{field_name} must be a positive integer number of seconds.",
                retryable=False,
                safe_next_action=f"Provide a positive whole number of seconds for {field_name}.",
            )
        )
    return value


def format_duration(seconds: int) -> str:
    """Format exact positive integer seconds for display only (never for constraints)."""
    validated = parse_positive_seconds(seconds, field_name="seconds")
    hours, rem = divmod(validated, 3_600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"
