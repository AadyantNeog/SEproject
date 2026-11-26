import pytest

from yt_intel.contracts.errors import ContractError
from yt_intel.domain.constraints import audio_language_matches
from yt_intel.domain.language import (
    language_tag_matches,
    normalize_language_tag,
    parse_language_tag,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("en", "en"),
        ("EN-us", "en-US"),
        ("en-gb", "en-GB"),
        ("en-latn-us", "en-Latn-US"),
        ("es-419", "es-419"),
        ("zh-hans-cn", "zh-Hans-CN"),
        ("en-GB-x-US", "en-GB-x-us"),
        ("de-ch-1996", "de-CH-1996"),
        ("en-u-ca-gregory", "en-u-ca-gregory"),
    ],
)
def test_normalize_language_tag_canonicalizes_valid_bcp47(
    raw: str, expected: str
) -> None:
    assert normalize_language_tag(raw) == expected
    assert parse_language_tag(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "e",
        "123",
        "en_US",
        "en US",
        "en-",
        "-en",
        "en--US",
        "en-x",
        "en-u",
        "en-US-Latn",
        "en-US-GB",
        "en-u-ca-u-tz",
        "en-1996-1996",
        "a" * 65,
    ],
)
def test_normalize_language_tag_rejects_invalid_tags(raw: str) -> None:
    assert normalize_language_tag(raw) is None
    with pytest.raises(ContractError) as exc:
        parse_language_tag(raw)
    assert exc.value.detail.code == "INVALID_INPUT"


def test_language_matching_is_strict_and_compatible_with_constraints() -> None:
    assert language_tag_matches("en", "en")
    assert language_tag_matches("en", "en-US")
    assert language_tag_matches("en", "en-GB")
    assert language_tag_matches("en-US", "en-Latn-US")
    assert not language_tag_matches("en-US", "en")
    assert not language_tag_matches("en-US", "en-GB")
    assert not language_tag_matches("en-US", "en-GB-x-US")
    assert not language_tag_matches("en", "fr")
    assert not language_tag_matches("en", None)
    assert not language_tag_matches("en", "en_US")

    # Verify compatibility with A2-04's audio_language_matches helper.
    for req, cand in [
        ("en", "en-GB"),
        ("en-US", "en-Latn-US"),
        ("en-US", "en-GB-x-US"),
    ]:
        norm_req = parse_language_tag(req)
        norm_cand = parse_language_tag(cand)
        assert audio_language_matches(norm_req, norm_cand) == language_tag_matches(
            req, cand
        )
