import pytest

from yt_intel.contracts.errors import ContractError
from yt_intel.contracts.provider import ChannelByHandle, ChannelById
from yt_intel.domain.identifiers import (
    canonical_channel_url,
    canonical_video_url,
    parse_channel_ref,
    parse_video_id,
    validate_result_limit,
)

VALID_VIDEO_ID = "dQw4w9WgXcQ"
VALID_CHANNEL_ID = "UC_x5XG1OV2P6uZZ5FSM9Ttw"


@pytest.mark.parametrize(
    "raw",
    [
        VALID_VIDEO_ID,
        f"  {VALID_VIDEO_ID}  ",
        f"https://www.youtube.com/watch?v={VALID_VIDEO_ID}",
        f"https://youtube.com/watch?v={VALID_VIDEO_ID}&t=42s",
        f"https://m.youtube.com/watch?list=PL123&v={VALID_VIDEO_ID}",
        f"https://music.youtube.com/watch?v={VALID_VIDEO_ID}",
        f"https://www.youtube-nocookie.com/embed/{VALID_VIDEO_ID}",
        f"https://www.youtube.com/shorts/{VALID_VIDEO_ID}",
        f"https://www.youtube.com/live/{VALID_VIDEO_ID}",
        f"https://www.youtube.com/v/{VALID_VIDEO_ID}",
        f"https://youtu.be/{VALID_VIDEO_ID}",
        f"https://youtu.be/{VALID_VIDEO_ID}?si=abc123",
        f"http://www.youtube.com/watch?v={VALID_VIDEO_ID}",
    ],
)
def test_parse_video_id_accepts_supported_ids_and_urls(raw: str) -> None:
    assert parse_video_id(raw) == VALID_VIDEO_ID
    assert (
        canonical_video_url(raw) == f"https://www.youtube.com/watch?v={VALID_VIDEO_ID}"
    )


@pytest.mark.parametrize(
    ("raw", "expected_code"),
    [
        ("", "INVALID_INPUT"),
        ("   ", "INVALID_INPUT"),
        (12345678901, "INVALID_INPUT"),
        ("shortid", "INVALID_INPUT"),
        ("toolongvideoid123", "INVALID_INPUT"),
        (f"{VALID_VIDEO_ID}\n", "INVALID_INPUT"),
        ("https://example.com/watch?v=" + VALID_VIDEO_ID, "UNSUPPORTED_IDENTIFIER"),
        (
            "https://youtube.com.evil.com/watch?v=" + VALID_VIDEO_ID,
            "UNSUPPORTED_IDENTIFIER",
        ),
        (
            "https://user:pass@www.youtube.com/watch?v=" + VALID_VIDEO_ID,
            "UNSUPPORTED_IDENTIFIER",
        ),
        (
            "https://www.youtube.com:8443/watch?v=" + VALID_VIDEO_ID,
            "UNSUPPORTED_IDENTIFIER",
        ),
        ("ftp://www.youtube.com/watch?v=" + VALID_VIDEO_ID, "UNSUPPORTED_IDENTIFIER"),
        ("javascript:alert(1)", "UNSUPPORTED_IDENTIFIER"),
        ("https://www.youtube.com/watch", "INVALID_INPUT"),
        (
            f"https://www.youtube.com/watch?v={VALID_VIDEO_ID}&v=abc12345678",
            "INVALID_INPUT",
        ),
        (f"https://youtu.be/{VALID_VIDEO_ID}/extra", "INVALID_INPUT"),
        (f"https://www.youtube.com/shorts/{VALID_VIDEO_ID}/extra", "INVALID_INPUT"),
    ],
)
def test_parse_video_id_rejects_invalid_or_untrusted_inputs(
    raw: object, expected_code: str
) -> None:
    with pytest.raises(ContractError) as exc:
        parse_video_id(raw)
    assert exc.value.detail.code == expected_code
    assert exc.value.detail.retryable is False


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (VALID_CHANNEL_ID, ChannelById(channel_id=VALID_CHANNEL_ID)),
        (
            f"https://www.youtube.com/channel/{VALID_CHANNEL_ID}",
            ChannelById(channel_id=VALID_CHANNEL_ID),
        ),
        (
            f"https://m.youtube.com/channel/{VALID_CHANNEL_ID}/videos",
            ChannelById(channel_id=VALID_CHANNEL_ID),
        ),
        ("@GoogleDevelopers", ChannelByHandle(handle="@GoogleDevelopers")),
        (
            "https://www.youtube.com/@GoogleDevelopers",
            ChannelByHandle(handle="@GoogleDevelopers"),
        ),
        (
            "https://youtube.com/@GoogleDevelopers/about",
            ChannelByHandle(handle="@GoogleDevelopers"),
        ),
    ],
)
def test_parse_channel_ref_accepts_ids_handles_and_urls(
    raw: str, expected: ChannelById | ChannelByHandle
) -> None:
    assert parse_channel_ref(raw) == expected


def test_canonical_channel_url() -> None:
    assert (
        canonical_channel_url(VALID_CHANNEL_ID)
        == f"https://www.youtube.com/channel/{VALID_CHANNEL_ID}"
    )
    with pytest.raises(ContractError) as exc:
        canonical_channel_url("@GoogleDevelopers")
    assert exc.value.detail.code == "INVALID_INPUT"


@pytest.mark.parametrize(
    ("raw", "expected_code"),
    [
        ("", "INVALID_INPUT"),
        ("@", "INVALID_INPUT"),
        ("not-a-channel", "INVALID_INPUT"),
        ("https://www.youtube.com/c/LegacyChannel", "UNSUPPORTED_IDENTIFIER"),
        ("https://www.youtube.com/user/LegacyUser", "UNSUPPORTED_IDENTIFIER"),
        ("https://www.youtube.com/AmbiguousCustom", "UNSUPPORTED_IDENTIFIER"),
        ("https://example.com/@GoogleDevelopers", "UNSUPPORTED_IDENTIFIER"),
        ("https://youtu.be/@GoogleDevelopers", "UNSUPPORTED_IDENTIFIER"),
        ("https://www.youtube.com/channel/badid", "INVALID_INPUT"),
        ("https://www.youtube.com/@GoogleDevelopers/unknown/sub", "INVALID_INPUT"),
    ],
)
def test_parse_channel_ref_rejects_ambiguous_or_unknown_hosts(
    raw: str, expected_code: str
) -> None:
    with pytest.raises(ContractError) as exc:
        parse_channel_ref(raw)
    assert exc.value.detail.code == expected_code


def test_validate_result_limit_bounds_and_rejects_booleans() -> None:
    assert validate_result_limit(1) == 1
    assert validate_result_limit(50) == 50
    for bad in (True, False, 0, -1, 51, "10", 10.0, None):
        with pytest.raises(ContractError) as exc:
            validate_result_limit(bad)
        assert exc.value.detail.code == "INVALID_INPUT"
