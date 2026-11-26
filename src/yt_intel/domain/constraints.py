from collections.abc import Callable, Mapping
from itertools import takewhile
from typing import Literal

from pydantic import ValidationError

from yt_intel.contracts.common import Label, LanguageTag, Positive
from yt_intel.contracts.errors import ContractError, ErrorCode, ErrorDetail
from yt_intel.contracts.proposals import PlaylistBody

type NormalizeLanguageTag = Callable[[str], str | None]


class PlaylistRequest(PlaylistBody):
    topic: Label
    total_seconds: Positive
    max_video_seconds: Positive
    language: LanguageTag
    duration_mode: Literal["max"] = "max"
    include_seed: bool = False


def planning_error(code: ErrorCode, message: str, next_action: str) -> ContractError:
    return ContractError(
        ErrorDetail(
            code=code, message=message, retryable=False, safe_next_action=next_action
        )
    )


def parse_playlist_request(fields: Mapping[str, object]) -> PlaylistRequest:
    if fields.get("duration_mode") == "exact":
        raise planning_error(
            "CLARIFICATION_REQUIRED",
            "An exact playlist duration is unsupported.",
            "Confirm the requested duration can be used as a maximum.",
        )
    try:
        return PlaylistRequest.model_validate(dict(fields))
    except ValidationError as error:
        missing = [
            str(issue["loc"][0])
            for issue in error.errors()
            if issue["type"] == "missing"
        ]
        if missing:
            raise planning_error(
                "CLARIFICATION_REQUIRED",
                f"Missing playlist fields: {', '.join(missing)}.",
                "Ask for the missing values and submit a structured request.",
            ) from None
        raise planning_error(
            "INVALID_INPUT",
            "Invalid playlist request fields or constraints.",
            "Use positive integer seconds, a language tag, a title and supported privacy.",
        ) from None


def audio_language_matches(requested: str, audio: str) -> bool:
    """Compare tags already validated by the shared language normalizer."""
    requested_parts = requested.casefold().split("-")
    audio_parts = audio.casefold().split("-")
    if requested_parts[0] != audio_parts[0]:
        return False
    if any(len(part) == 1 for part in requested_parts):
        return requested_parts == audio_parts
    qualifiers = takewhile(lambda part: len(part) > 1, audio_parts[1:])
    return all(
        any(part == expected for part in qualifiers) for expected in requested_parts[1:]
    )
