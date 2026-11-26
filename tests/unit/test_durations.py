import pytest

from yt_intel.contracts.errors import ContractError
from yt_intel.domain.durations import (
    ParsedDuration,
    format_duration,
    parse_iso8601_duration,
    parse_positive_seconds,
)


@pytest.mark.parametrize(
    ("raw", "expected_seconds"),
    [
        ("PT20M", 1200),
        ("PT20M1S", 1201),
        ("P1DT2H3M4S", 93784),
        ("PT1S", 1),
        ("PT1H", 3600),
        ("P2D", 172800),
        ("PT0H20M0S", 1200),
    ],
)
def test_parse_iso8601_duration_exact_seconds(raw: str, expected_seconds: int) -> None:
    assert parse_iso8601_duration(raw) == ParsedDuration(
        seconds=expected_seconds, warning=None
    )


@pytest.mark.parametrize(
    ("raw", "expected_warning"),
    [
        (None, "duration_missing"),
        ("", "duration_missing"),
        ("   ", "duration_missing"),
        ("PT0S", "duration_zero"),
        ("P0D", "duration_zero"),
        ("P0DT0H0M0S", "duration_zero"),
        ("-PT5M", "duration_negative"),
        ("PT-5M", "duration_negative"),
        ("PT1.5S", "duration_non_integral"),
        ("PT1,5S", "duration_non_integral"),
        ("P1Y", "duration_unsupported_calendar_unit"),
        ("P1M", "duration_unsupported_calendar_unit"),
        ("P2W", "duration_unsupported_calendar_unit"),
        ("P1YT10M", "duration_unsupported_calendar_unit"),
        ("P", "duration_malformed"),
        ("PT", "duration_malformed"),
        ("P1DT", "duration_malformed"),
        ("20M", "duration_malformed"),
        ("pt20m", "duration_malformed"),
    ],
)
def test_parse_iso8601_duration_unknown_and_malformed_warnings(
    raw: str | None, expected_warning: str
) -> None:
    parsed = parse_iso8601_duration(raw)
    assert parsed.seconds is None
    assert parsed.warning == expected_warning


def test_parse_positive_seconds_rejects_booleans_and_non_positive() -> None:
    assert parse_positive_seconds(1) == 1
    assert parse_positive_seconds(7200) == 7200
    for bad in (True, False, 0, -10, 12.5, "1200", None):
        with pytest.raises(ContractError) as exc:
            parse_positive_seconds(bad)
        assert exc.value.detail.code == "INVALID_INPUT"


def test_format_duration_display_strings() -> None:
    assert format_duration(5) == "0:05"
    assert format_duration(65) == "1:05"
    assert format_duration(1200) == "20:00"
    assert format_duration(1201) == "20:01"
    assert format_duration(3661) == "1:01:01"
