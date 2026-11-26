from __future__ import annotations

import re
from urllib.parse import parse_qs, unquote, urlsplit

from yt_intel.contracts.common import VideoId
from yt_intel.contracts.errors import ContractError, ErrorCode, ErrorDetail
from yt_intel.contracts.provider import ChannelByHandle, ChannelById, ChannelRef

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_CHANNEL_ID_RE = re.compile(r"^UC[A-Za-z0-9_-]{22}$")
_HANDLE_RE = re.compile(r"^@[^\s/?#]{1,127}$")
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")

_MAX_INPUT_LENGTH = 2048

_YOUTUBE_VIDEO_HOSTS = frozenset(
    {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
        "youtube-nocookie.com",
        "www.youtube-nocookie.com",
    }
)
_SHORT_VIDEO_HOSTS = frozenset({"youtu.be", "www.youtu.be"})
_YOUTUBE_CHANNEL_HOSTS = frozenset(
    {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
    }
)
_VIDEO_PATH_PREFIXES = frozenset({"shorts", "embed", "live", "v"})
_CHANNEL_TABS = frozenset(
    {
        "featured",
        "videos",
        "shorts",
        "streams",
        "live",
        "playlists",
        "community",
        "posts",
        "about",
    }
)
_ALLOWED_SCHEMES = frozenset({"https", "http"})


def _id_error(code: ErrorCode, message: str, next_action: str) -> ContractError:
    return ContractError(
        ErrorDetail(
            code=code,
            message=message,
            retryable=False,
            safe_next_action=next_action,
        )
    )


def _validate_raw_text(raw: object, kind: str) -> str:
    if not isinstance(raw, str):
        raise _id_error(
            "INVALID_INPUT",
            f"Expected a string {kind} identifier or YouTube URL.",
            f"Provide a valid YouTube {kind} ID or URL as text.",
        )
    if _CONTROL_CHARS_RE.search(raw):
        raise _id_error(
            "INVALID_INPUT",
            f"The {kind} identifier contains invalid control characters.",
            f"Provide a clean YouTube {kind} ID or URL without control characters.",
        )
    cleaned = raw.strip()
    if not cleaned:
        raise _id_error(
            "INVALID_INPUT",
            f"The {kind} identifier cannot be empty.",
            f"Provide a valid YouTube {kind} ID or URL.",
        )
    if len(cleaned) > _MAX_INPUT_LENGTH:
        raise _id_error(
            "INVALID_INPUT",
            f"The {kind} input exceeds the maximum supported length.",
            f"Provide a standard YouTube {kind} ID or canonical URL.",
        )
    return cleaned


def _looks_like_url(value: str) -> bool:
    if "://" in value or value.startswith("//"):
        return True
    if "/" in value or "?" in value or "#" in value:
        return True
    lowered = value.casefold()
    return any(
        lowered.startswith(prefix)
        for prefix in ("javascript:", "data:", "file:", "ftp:", "mailto:")
    )


def _parse_url_parts(raw: str, kind: str) -> tuple[str, list[str], str]:
    parsed = urlsplit(raw)
    scheme = parsed.scheme.casefold()
    if scheme not in _ALLOWED_SCHEMES:
        raise _id_error(
            "UNSUPPORTED_IDENTIFIER",
            f"Unsupported URL scheme for YouTube {kind}.",
            f"Provide an official https://www.youtube.com {kind} URL or raw ID.",
        )
    if parsed.username is not None or parsed.password is not None:
        raise _id_error(
            "UNSUPPORTED_IDENTIFIER",
            "URLs containing credentials or userinfo are not permitted.",
            f"Remove userinfo and provide a standard YouTube {kind} URL or ID.",
        )
    try:
        port = parsed.port
    except ValueError:
        raise _id_error(
            "INVALID_INPUT",
            "Malformed port in URL.",
            f"Provide a standard YouTube {kind} URL or ID.",
        ) from None
    if port is not None and not (
        (scheme == "https" and port == 443) or (scheme == "http" and port == 80)
    ):
        raise _id_error(
            "UNSUPPORTED_IDENTIFIER",
            "Non-standard ports are not supported for YouTube URLs.",
            f"Provide a standard YouTube {kind} URL or ID.",
        )
    host = (parsed.hostname or "").casefold()
    if not host:
        raise _id_error(
            "UNSUPPORTED_IDENTIFIER",
            "URL is missing a YouTube hostname.",
            f"Provide a standard YouTube {kind} URL or ID.",
        )
    segments = [unquote(part) for part in parsed.path.split("/") if part]
    return host, segments, parsed.query


def parse_video_id(raw: object) -> VideoId:
    """Parse a raw YouTube video ID or official YouTube/youtu.be video URL locally."""
    value = _validate_raw_text(raw, "video")
    if _VIDEO_ID_RE.fullmatch(value):
        return value
    if not _looks_like_url(value):
        raise _id_error(
            "INVALID_INPUT",
            "Invalid YouTube video ID format.",
            "Provide an 11-character YouTube video ID or an official YouTube watch/youtu.be URL.",
        )

    host, segments, query = _parse_url_parts(value, "video")
    candidate: str | None = None

    if host in _SHORT_VIDEO_HOSTS:
        if len(segments) == 1:
            candidate = segments[0]
    elif host in _YOUTUBE_VIDEO_HOSTS:
        if segments == ["watch"]:
            params = parse_qs(query, keep_blank_values=True)
            values = params.get("v")
            if values is not None and len(values) == 1:
                candidate = values[0]
        elif len(segments) == 2 and segments[0].casefold() in _VIDEO_PATH_PREFIXES:
            candidate = segments[1]
    else:
        raise _id_error(
            "UNSUPPORTED_IDENTIFIER",
            "Only official YouTube and youtu.be hosts are accepted; arbitrary URLs are not fetched.",
            "Provide a youtube.com watch URL, a youtu.be link, or an 11-character video ID.",
        )

    if candidate is None or not _VIDEO_ID_RE.fullmatch(candidate):
        raise _id_error(
            "INVALID_INPUT",
            "Could not extract a valid 11-character YouTube video ID from the URL.",
            "Provide a youtube.com/watch?v=<id> URL, a youtu.be/<id> link, or an 11-character video ID.",
        )
    return candidate


def canonical_video_url(video_id: str) -> str:
    """Return the canonical HTTPS watch URL for a validated video ID."""
    validated = parse_video_id(video_id)
    return f"https://www.youtube.com/watch?v={validated}"


def _validate_handle(handle: str) -> ChannelByHandle:
    if not _HANDLE_RE.fullmatch(handle) or _CONTROL_CHARS_RE.search(handle):
        raise _id_error(
            "INVALID_INPUT",
            "Invalid YouTube channel handle format.",
            "Provide a handle like @channelname, a UC... channel ID, or a youtube.com/channel/UC... URL.",
        )
    return ChannelByHandle(handle=handle)


def parse_channel_ref(raw: object) -> ChannelRef:
    """Parse a YouTube channel ID, @handle, or supported channel URL locally."""
    value = _validate_raw_text(raw, "channel")
    if _CHANNEL_ID_RE.fullmatch(value):
        return ChannelById(channel_id=value)
    if value.startswith("@") and not _looks_like_url(value):
        return _validate_handle(value)
    if not _looks_like_url(value):
        raise _id_error(
            "INVALID_INPUT",
            "Invalid YouTube channel ID or @handle format.",
            "Provide a UC... channel ID, an @handle, or an official youtube.com channel URL.",
        )

    host, segments, _ = _parse_url_parts(value, "channel")
    if host not in _YOUTUBE_CHANNEL_HOSTS:
        raise _id_error(
            "UNSUPPORTED_IDENTIFIER",
            "Only official youtube.com channel hosts are accepted; arbitrary URLs are not fetched.",
            "Provide a youtube.com/channel/UC... URL, a youtube.com/@handle URL, a UC... ID, or an @handle.",
        )
    if not segments:
        raise _id_error(
            "INVALID_INPUT",
            "YouTube URL does not identify a channel.",
            "Provide a youtube.com/channel/UC... URL, a youtube.com/@handle URL, a UC... ID, or an @handle.",
        )

    first = segments[0]
    first_lower = first.casefold()

    if first_lower == "channel":
        if len(segments) == 2 or (
            len(segments) == 3 and segments[2].casefold() in _CHANNEL_TABS
        ):
            channel_id = segments[1]
            if _CHANNEL_ID_RE.fullmatch(channel_id):
                return ChannelById(channel_id=channel_id)
        raise _id_error(
            "INVALID_INPUT",
            "Invalid YouTube /channel/ URL; expected a 24-character UC... channel ID.",
            "Provide a youtube.com/channel/UC... URL, a UC... channel ID, or an @handle.",
        )

    if first.startswith("@"):
        if len(segments) == 1 or (
            len(segments) == 2 and segments[1].casefold() in _CHANNEL_TABS
        ):
            return _validate_handle(first)
        raise _id_error(
            "INVALID_INPUT",
            "Unsupported channel URL path after @handle.",
            "Provide a youtube.com/@handle URL, an @handle, or a UC... channel ID.",
        )

    if first_lower in {"c", "user"}:
        raise _id_error(
            "UNSUPPORTED_IDENTIFIER",
            f"Legacy YouTube /{first_lower}/ channel URLs are ambiguous and not supported.",
            "Provide the channel's @handle or 24-character UC... channel ID instead.",
        )

    if len(segments) == 1:
        raise _id_error(
            "UNSUPPORTED_IDENTIFIER",
            "Ambiguous legacy custom channel URLs are not supported.",
            "Provide the channel's @handle or 24-character UC... channel ID instead.",
        )

    raise _id_error(
        "INVALID_INPUT",
        "YouTube URL does not match a supported channel format.",
        "Provide a youtube.com/channel/UC... URL, a youtube.com/@handle URL, a UC... ID, or an @handle.",
    )


def canonical_channel_url(channel_id: str) -> str:
    """Return the canonical HTTPS channel URL for a validated UC... channel ID."""
    ref = parse_channel_ref(channel_id)
    if not isinstance(ref, ChannelById):
        raise _id_error(
            "INVALID_INPUT",
            "Canonical channel URLs require a UC... channel ID.",
            "Resolve the channel handle to a UC... channel ID first.",
        )
    return f"https://www.youtube.com/channel/{ref.channel_id}"


def validate_result_limit(value: object) -> int:
    """Validate an integer result limit in the SRS 1..50 range without coercing booleans."""
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 50:
        raise _id_error(
            "INVALID_INPUT",
            "Result limit must be an integer between 1 and 50.",
            "Specify a whole-number limit from 1 to 50.",
        )
    return value
