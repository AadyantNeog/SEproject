from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Literal

from yt_intel.contracts.approval import ApprovedWriteContext
from yt_intel.contracts.common import (
    ChannelId,
    Label,
    LanguageTag,
    Limit,
    NonNegative,
    PlaylistId,
    Text,
    VideoId,
)
from yt_intel.contracts.errors import ContractError, ErrorCode, ErrorDetail
from yt_intel.contracts.models import (
    Access,
    Channel,
    Coverage,
    Page,
    PlaylistOccurrence,
    SubscriptionSignal,
    Video,
)
from yt_intel.contracts.proposals import PlaylistBody
from yt_intel.contracts.provider import (
    ChannelBatch,
    ChannelByHandle,
    ChannelById,
    ChannelRef,
    CreatedPlaylist,
    InsertedPlaylistItem,
    LikedVideo,
    OwnedPlaylist,
    SearchHit,
    VideoBatch,
    YouTubeReadProvider,
    YouTubeWriteProvider,
)
from yt_intel.contracts.workflow import Clock, RequestContext
from yt_intel.domain.durations import parse_iso8601_duration
from yt_intel.domain.identifiers import (
    canonical_channel_url,
    canonical_video_url,
    parse_channel_ref,
    parse_video_id,
    validate_result_limit,
)
from yt_intel.domain.language import normalize_language_tag, parse_language_tag
from yt_intel.infrastructure.clock import SystemClock
from yt_intel.infrastructure.http import AccountedHttpExecutor

_MAX_BATCH_SIZE = 50
_MAX_DESCRIPTION_LEN = 10_000
_MAX_LABEL_LEN = 256
_MAX_TAGS = 500
_MAX_WARNINGS = 50
_OPAQUE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_REGION_CODE_RE = re.compile(r"^[A-Z]{2}$")
_INACCESSIBLE_TITLES = frozenset({"private video", "deleted video"})


def _provider_error(
    code: ErrorCode,
    message: str,
    *,
    safe_next_action: str,
    retryable: bool = False,
) -> ContractError:
    return ContractError(
        ErrorDetail(
            code=code,
            message=message,
            retryable=retryable,
            safe_next_action=safe_next_action,
        )
    )


def _as_mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return value
    return {}


def _as_str(value: object) -> str | None:
    if isinstance(value, str):
        return value
    return None


def _clean_label(value: object, *, fallback: str | None = None) -> str | None:
    raw = _as_str(value)
    if raw is None:
        return fallback
    stripped = raw.strip()
    if not stripped:
        return fallback
    if len(stripped) > _MAX_LABEL_LEN:
        return stripped[:_MAX_LABEL_LEN]
    return stripped


def _clean_description(value: object) -> str | None:
    raw = _as_str(value)
    if raw is None:
        return None
    if len(raw) > _MAX_DESCRIPTION_LEN:
        return raw[:_MAX_DESCRIPTION_LEN]
    return raw


def _parse_rfc3339(value: object) -> datetime | None:
    raw = _as_str(value)
    if not raw:
        return None
    normalized = raw.strip()
    if normalized.endswith(("Z", "z")):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def _parse_non_negative_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _extract_page_meta(
    payload: Mapping[str, object],
) -> tuple[list[Mapping[str, object]], str | None, int | None]:
    if "items" not in payload or not isinstance(payload["items"], list):
        raise _provider_error(
            "PROVIDER_UNAVAILABLE",
            "YouTube API response is missing a valid items list.",
            safe_next_action="Inspect provider diagnostics and retry later.",
        )
    raw_items = payload["items"]
    items: list[Mapping[str, object]] = []
    for entry in raw_items:
        if not isinstance(entry, Mapping):
            raise _provider_error(
                "PROVIDER_UNAVAILABLE",
                "YouTube API response contains a malformed non-object item.",
                safe_next_action="Inspect provider diagnostics and retry later.",
            )
        items.append(entry)

    raw_next = payload.get("nextPageToken")
    if raw_next is not None and not isinstance(raw_next, str):
        raise _provider_error(
            "PROVIDER_UNAVAILABLE",
            "YouTube API response contains a malformed nextPageToken.",
            safe_next_action="Inspect provider diagnostics and retry later.",
        )
    next_token = raw_next if raw_next else None

    raw_page_info = payload.get("pageInfo")
    if raw_page_info is not None and not isinstance(raw_page_info, Mapping):
        raise _provider_error(
            "PROVIDER_UNAVAILABLE",
            "YouTube API response contains a malformed pageInfo object.",
            safe_next_action="Inspect provider diagnostics and retry later.",
        )
    page_info = raw_page_info if isinstance(raw_page_info, Mapping) else {}
    total = _parse_non_negative_int(page_info.get("totalResults"))
    return items, next_token, total


def _validate_opaque_id(raw: object, *, field_name: str) -> str:
    if not isinstance(raw, str) or not _OPAQUE_ID_RE.fullmatch(raw):
        raise _provider_error(
            "INVALID_INPUT",
            f"Invalid {field_name} identifier.",
            safe_next_action=f"Provide a valid YouTube {field_name} identifier.",
        )
    return raw


def _dedupe_preserve_order[T](values: Sequence[T]) -> tuple[T, ...]:
    return tuple(dict.fromkeys(values))


def _chunked[T](values: Sequence[T], size: int) -> list[tuple[T, ...]]:
    return [tuple(values[i : i + size]) for i in range(0, len(values), size)]


def normalize_video_item(
    item: Mapping[str, object], *, fetched_at: datetime
) -> Video | None:
    """Normalize one YouTube Data API v3 videos.list item into a strict Video DTO."""
    raw_id = item.get("id")
    try:
        video_id = parse_video_id(raw_id)
    except ContractError:
        return None

    snippet = _as_mapping(item.get("snippet"))
    content_details = _as_mapping(item.get("contentDetails"))
    status = _as_mapping(item.get("status"))

    warnings: list[str] = []

    raw_channel_id = snippet.get("channelId")
    channel_id: ChannelId | None = None
    if raw_channel_id is not None:
        try:
            ref = parse_channel_ref(raw_channel_id)
            if isinstance(ref, ChannelById):
                channel_id = ref.channel_id
            else:
                warnings.append("channel_id_invalid")
        except ContractError:
            warnings.append("channel_id_invalid")

    title = _clean_label(snippet.get("title"))
    if title is None:
        title = "(untitled video)"
        warnings.append("title_missing")

    channel_title = _clean_label(snippet.get("channelTitle"))
    description = _clean_description(snippet.get("description"))

    tags: tuple[str, ...] | None = None
    raw_tags = snippet.get("tags")
    if isinstance(raw_tags, list):
        cleaned_tags = [
            cleaned
            for entry in raw_tags
            if (cleaned := _clean_label(entry)) is not None
        ][:_MAX_TAGS]
        tags = tuple(cleaned_tags)

    raw_cat = _as_str(snippet.get("categoryId"))
    category_id = (
        raw_cat if raw_cat is not None and _OPAQUE_ID_RE.fullmatch(raw_cat) else None
    )

    published_at = _parse_rfc3339(snippet.get("publishedAt"))
    if snippet.get("publishedAt") is not None and published_at is None:
        warnings.append("published_at_malformed")

    parsed_duration = parse_iso8601_duration(_as_str(content_details.get("duration")))
    if parsed_duration.warning is not None:
        warnings.append(parsed_duration.warning)

    default_audio = _clean_label(snippet.get("defaultAudioLanguage"))
    default_meta = _clean_label(snippet.get("defaultLanguage"))
    language_evidence: Literal["audio", "metadata_only", "unknown"]
    if default_audio is not None:
        language_evidence = "audio"
        if normalize_language_tag(default_audio) is None:
            warnings.append("audio_language_malformed")
    elif default_meta is not None:
        language_evidence = "metadata_only"
        warnings.append("audio_language_missing_metadata_only")
    else:
        language_evidence = "unknown"
        warnings.append("language_unknown")

    live_raw = (_as_str(snippet.get("liveBroadcastContent")) or "").casefold()
    live_status: Literal["recorded", "live", "upcoming", "unknown"]
    if live_raw == "none":
        live_status = "recorded"
    elif live_raw == "live":
        live_status = "live"
    elif live_raw == "upcoming":
        live_status = "upcoming"
    else:
        live_status = "unknown"

    privacy_status = (_as_str(status.get("privacyStatus")) or "").casefold()
    upload_status = (_as_str(status.get("uploadStatus")) or "").casefold()
    availability: Access
    if privacy_status == "private" or upload_status in {
        "deleted",
        "rejected",
        "failed",
    }:
        availability = "inaccessible"
    elif status:
        availability = "available"
    else:
        availability = "available"

    return Video(
        video_id=video_id,
        channel_id=channel_id,
        title=title,
        channel_title=channel_title,
        canonical_url=canonical_video_url(video_id),
        description=description,
        tags=tags,
        category_id=category_id,
        published_at=published_at,
        duration_seconds=parsed_duration.seconds,
        default_audio_language=default_audio,
        default_metadata_language=default_meta,
        language_evidence=language_evidence,
        availability=availability,
        live_status=live_status,
        fetched_at=fetched_at,
        evidence_warnings=tuple(warnings[:_MAX_WARNINGS]),
    )


def normalize_channel_item(
    item: Mapping[str, object], *, fetched_at: datetime
) -> Channel | None:
    """Normalize one YouTube Data API v3 channels.list item into a strict Channel DTO."""
    try:
        ref = parse_channel_ref(item.get("id"))
    except ContractError:
        return None
    if not isinstance(ref, ChannelById):
        return None
    channel_id = ref.channel_id

    snippet = _as_mapping(item.get("snippet"))
    content_details = _as_mapping(item.get("contentDetails"))
    related = _as_mapping(content_details.get("relatedPlaylists"))

    title = _clean_label(snippet.get("title")) or "(untitled channel)"
    custom_url = _clean_label(snippet.get("customUrl"))
    handle = (
        custom_url if custom_url is not None and custom_url.startswith("@") else None
    )
    description = _clean_description(snippet.get("description"))

    raw_uploads = _as_str(related.get("uploads"))
    uploads_playlist_id = (
        raw_uploads
        if raw_uploads is not None and _OPAQUE_ID_RE.fullmatch(raw_uploads)
        else None
    )

    return Channel(
        channel_id=channel_id,
        title=title,
        canonical_url=canonical_channel_url(channel_id),
        handle=handle,
        description=description,
        uploads_playlist_id=uploads_playlist_id,
        fetched_at=fetched_at,
    )


def normalize_search_item(item: Mapping[str, object]) -> SearchHit | None:
    """Normalize one YouTube Data API v3 search.list item into a SearchHit."""
    id_block = _as_mapping(item.get("id"))
    raw_video_id = id_block.get("videoId")
    try:
        video_id = parse_video_id(raw_video_id)
    except ContractError:
        return None

    snippet = _as_mapping(item.get("snippet"))
    channel_id: ChannelId | None = None
    raw_channel_id = snippet.get("channelId")
    if raw_channel_id is not None:
        try:
            ref = parse_channel_ref(raw_channel_id)
            if isinstance(ref, ChannelById):
                channel_id = ref.channel_id
        except ContractError:
            channel_id = None

    return SearchHit(video_id=video_id, channel_id=channel_id)


def normalize_subscription_item(
    item: Mapping[str, object], *, fetched_at: datetime
) -> SubscriptionSignal | None:
    """Normalize one YouTube Data API v3 subscriptions.list item."""
    raw_sub_id = _as_str(item.get("id"))
    if raw_sub_id is None or not _OPAQUE_ID_RE.fullmatch(raw_sub_id):
        return None

    snippet = _as_mapping(item.get("snippet"))
    resource_id = _as_mapping(snippet.get("resourceId"))
    try:
        ref = parse_channel_ref(resource_id.get("channelId"))
    except ContractError:
        return None
    if not isinstance(ref, ChannelById):
        return None

    subscribed_at = _parse_rfc3339(snippet.get("publishedAt"))
    coverage = Coverage(
        complete=True,
        paginated=False,
        sampled=False,
        truncated=False,
        retrieved=1,
        usable=1,
        inaccessible=0,
        unknown=0,
        completeness_basis="Single subscription signal without upload topic sample",
    )
    return SubscriptionSignal(
        subscription_id=raw_sub_id,
        channel_id=ref.channel_id,
        subscribed_at=subscribed_at,
        topic_sample=None,
        coverage=coverage,
    )


def normalize_owned_playlist_item(item: Mapping[str, object]) -> OwnedPlaylist | None:
    """Normalize one YouTube Data API v3 playlists.list item."""
    raw_id = _as_str(item.get("id"))
    if raw_id is None or not _OPAQUE_ID_RE.fullmatch(raw_id):
        return None
    snippet = _as_mapping(item.get("snippet"))
    try:
        ref = parse_channel_ref(snippet.get("channelId"))
    except ContractError:
        return None
    if not isinstance(ref, ChannelById):
        return None
    title = _clean_label(snippet.get("title")) or "(untitled playlist)"
    return OwnedPlaylist(
        playlist_id=raw_id,
        channel_id=ref.channel_id,
        title=title,
    )


def normalize_playlist_item_occurrence(
    item: Mapping[str, object], *, requested_playlist_id: PlaylistId
) -> PlaylistOccurrence | None:
    """Normalize one YouTube Data API v3 playlistItems.list item.

    Preserves private/deleted placeholder entries as ``accessibility="inaccessible"``
    and keeps ``added_at`` strictly from ``playlistItem.snippet.publishedAt``.
    """
    raw_item_id = _as_str(item.get("id"))
    if raw_item_id is None or not _OPAQUE_ID_RE.fullmatch(raw_item_id):
        return None

    snippet = _as_mapping(item.get("snippet"))
    content_details = _as_mapping(item.get("contentDetails"))
    status = _as_mapping(item.get("status"))
    resource_id = _as_mapping(snippet.get("resourceId"))

    raw_playlist_id = _as_str(snippet.get("playlistId"))
    playlist_id = (
        raw_playlist_id
        if raw_playlist_id is not None and _OPAQUE_ID_RE.fullmatch(raw_playlist_id)
        else requested_playlist_id
    )

    raw_video_id = resource_id.get("videoId") or content_details.get("videoId")
    video_id: VideoId | None = None
    if raw_video_id is not None:
        try:
            video_id = parse_video_id(raw_video_id)
        except ContractError:
            video_id = None

    position = _parse_non_negative_int(snippet.get("position"))
    added_at = _parse_rfc3339(snippet.get("publishedAt"))

    privacy = (_as_str(status.get("privacyStatus")) or "").casefold()
    title = (_as_str(snippet.get("title")) or "").strip().casefold()
    accessibility: Access
    if (
        privacy in {"private", "privacystatusunspecified"}
        or title in _INACCESSIBLE_TITLES
    ):
        accessibility = "inaccessible"
    elif video_id is None:
        accessibility = "unknown"
    else:
        accessibility = "available"

    return PlaylistOccurrence(
        playlist_id=playlist_id,
        playlist_item_id=raw_item_id,
        video_id=video_id,
        position=position,
        added_at=added_at,
        accessibility=accessibility,
    )


class LiveYouTubeReadProvider(YouTubeReadProvider):
    """Official YouTube Data API v3 read provider over AccountedHttpExecutor."""

    def __init__(
        self,
        executor: AccountedHttpExecutor,
        *,
        clock: Clock | None = None,
        expected_mode: Literal["live", "fixture"] = "live",
    ) -> None:
        self._executor = executor
        self._clock: Clock = clock if clock is not None else SystemClock()
        self._expected_mode = expected_mode

    def _require_mode(self, ctx: RequestContext) -> None:
        if ctx.binding.mode != self._expected_mode:
            raise _provider_error(
                "ACCOUNT_MISMATCH",
                f"Provider expects {self._expected_mode}-mode account bindings; received {ctx.binding.mode}.",
                safe_next_action=f"Use a {self._expected_mode}-mode account binding with this provider.",
            )

    async def get_videos(
        self, ctx: RequestContext, video_ids: tuple[VideoId, ...]
    ) -> VideoBatch:
        self._require_mode(ctx)
        validated = _dedupe_preserve_order(
            [parse_video_id(video_id) for video_id in video_ids]
        )
        if not validated:
            return VideoBatch(videos={}, omitted_ids=())

        videos: dict[VideoId, Video] = {}
        fetched_at = self._clock.now().astimezone(UTC)
        for batch in _chunked(validated, _MAX_BATCH_SIZE):
            resp = await self._executor.execute_youtube(
                ctx,
                "videos.list",
                params={
                    "part": "snippet,contentDetails,status",
                    "id": ",".join(batch),
                },
            )
            raw_items, _, _ = _extract_page_meta(resp.payload)
            for raw in raw_items:
                normalized = normalize_video_item(raw, fetched_at=fetched_at)
                if normalized is not None:
                    videos[normalized.video_id] = normalized

        omitted = tuple(vid for vid in validated if vid not in videos)
        return VideoBatch(videos=videos, omitted_ids=omitted)

    async def resolve_channel(
        self, ctx: RequestContext, channel: ChannelRef
    ) -> Channel:
        self._require_mode(ctx)
        params: dict[str, str] = {"part": "snippet,contentDetails"}
        if isinstance(channel, ChannelById):
            ref = parse_channel_ref(channel.channel_id)
            if not isinstance(ref, ChannelById):
                raise _provider_error(
                    "INVALID_INPUT",
                    "Expected a valid UC... channel ID.",
                    safe_next_action="Provide a 24-character UC... channel ID.",
                )
            params["id"] = ref.channel_id
        elif isinstance(channel, ChannelByHandle):
            ref = parse_channel_ref(channel.handle)
            if not isinstance(ref, ChannelByHandle):
                raise _provider_error(
                    "INVALID_INPUT",
                    "Expected a valid @handle.",
                    safe_next_action="Provide a valid YouTube @handle.",
                )
            params["forHandle"] = ref.handle
        else:
            raise _provider_error(
                "INVALID_INPUT",
                "Unsupported channel reference type.",
                safe_next_action="Provide a UC... channel ID or @handle.",
            )

        resp = await self._executor.execute_youtube(ctx, "channels.list", params=params)
        raw_items, _, _ = _extract_page_meta(resp.payload)
        fetched_at = self._clock.now().astimezone(UTC)
        for raw in raw_items:
            normalized = normalize_channel_item(raw, fetched_at=fetched_at)
            if normalized is not None:
                return normalized
        raise _provider_error(
            "CONTENT_UNAVAILABLE",
            "Requested YouTube channel could not be resolved or is unavailable.",
            safe_next_action="Verify the channel ID or @handle and try again.",
        )

    async def get_channels(
        self, ctx: RequestContext, channel_ids: tuple[ChannelId, ...]
    ) -> ChannelBatch:
        self._require_mode(ctx)
        validated_list: list[ChannelId] = []
        for raw_id in channel_ids:
            ref = parse_channel_ref(raw_id)
            if not isinstance(ref, ChannelById):
                raise _provider_error(
                    "INVALID_INPUT",
                    "get_channels requires 24-character UC... channel IDs.",
                    safe_next_action="Resolve handles first and pass UC... channel IDs.",
                )
            validated_list.append(ref.channel_id)

        validated = _dedupe_preserve_order(validated_list)
        if not validated:
            return ChannelBatch(channels={}, omitted_ids=())

        channels: dict[ChannelId, Channel] = {}
        fetched_at = self._clock.now().astimezone(UTC)
        for batch in _chunked(validated, _MAX_BATCH_SIZE):
            resp = await self._executor.execute_youtube(
                ctx,
                "channels.list",
                params={
                    "part": "snippet,contentDetails",
                    "id": ",".join(batch),
                },
            )
            raw_items, _, _ = _extract_page_meta(resp.payload)
            for raw in raw_items:
                normalized = normalize_channel_item(raw, fetched_at=fetched_at)
                if normalized is not None:
                    channels[normalized.channel_id] = normalized

        omitted = tuple(cid for cid in validated if cid not in channels)
        return ChannelBatch(channels=channels, omitted_ids=omitted)

    async def get_my_channels(self, ctx: RequestContext) -> tuple[Channel, ...]:
        self._require_mode(ctx)
        resp = await self._executor.execute_youtube(
            ctx,
            "channels.list",
            params={
                "part": "snippet,contentDetails",
                "mine": "true",
                "maxResults": str(_MAX_BATCH_SIZE),
            },
        )
        raw_items, _, _ = _extract_page_meta(resp.payload)
        fetched_at = self._clock.now().astimezone(UTC)
        channels: list[Channel] = []
        for raw in raw_items:
            normalized = normalize_channel_item(raw, fetched_at=fetched_at)
            if normalized is not None:
                channels.append(normalized)
        return tuple(channels)

    async def search_videos(
        self,
        ctx: RequestContext,
        query: Label,
        page_size: Limit,
        page_token: Text | None = None,
        language_hint: LanguageTag | None = None,
    ) -> Page[SearchHit]:
        self._require_mode(ctx)
        cleaned_query = _clean_label(query)
        if cleaned_query is None:
            raise _provider_error(
                "INVALID_INPUT",
                "Search query cannot be empty.",
                safe_next_action="Provide a non-empty search query.",
            )
        limit = validate_result_limit(page_size)
        params: dict[str, str] = {
            "part": "snippet",
            "type": "video",
            "q": cleaned_query,
            "maxResults": str(limit),
        }
        if page_token is not None:
            params["pageToken"] = page_token
        if language_hint is not None:
            params["relevanceLanguage"] = parse_language_tag(language_hint)

        resp = await self._executor.execute_youtube(ctx, "search.list", params=params)
        raw_items, next_token, total = _extract_page_meta(resp.payload)
        hits: list[SearchHit] = []
        omitted = 0
        for raw in raw_items[:limit]:
            hit = normalize_search_item(raw)
            if hit is None:
                omitted += 1
            else:
                hits.append(hit)
        reasons = ("non_video_or_malformed_search_item",) if omitted else ()
        return Page[SearchHit](
            items=tuple(hits),
            next_page_token=next_token,
            api_reported_total=total,
            omitted=omitted,
            inaccessible=0,
            reason_codes=reasons,
        )

    async def list_likes(
        self,
        ctx: RequestContext,
        page_size: Limit,
        page_token: Text | None = None,
    ) -> Page[LikedVideo]:
        self._require_mode(ctx)
        limit = validate_result_limit(page_size)
        params: dict[str, str] = {
            "part": "snippet,contentDetails,status",
            "myRating": "like",
            "maxResults": str(limit),
        }
        if page_token is not None:
            params["pageToken"] = page_token

        resp = await self._executor.execute_youtube(ctx, "videos.list", params=params)
        raw_items, next_token, total = _extract_page_meta(resp.payload)
        fetched_at = self._clock.now().astimezone(UTC)
        liked: list[LikedVideo] = []
        omitted = 0
        inaccessible = 0
        for raw in raw_items[:limit]:
            video = normalize_video_item(raw, fetched_at=fetched_at)
            if video is None:
                omitted += 1
                continue
            if video.availability == "inaccessible":
                inaccessible += 1
            # YouTube Data API v3 does not expose reliable like-event timestamps.
            liked.append(LikedVideo(video=video, liked_at=None))
        reasons: list[str] = []
        if omitted:
            reasons.append("omitted_malformed_like_item")
        if inaccessible:
            reasons.append("inaccessible_liked_video")
        return Page[LikedVideo](
            items=tuple(liked),
            next_page_token=next_token,
            api_reported_total=total,
            omitted=omitted,
            inaccessible=inaccessible,
            reason_codes=tuple(reasons),
        )

    async def list_subscriptions(
        self,
        ctx: RequestContext,
        page_size: Limit,
        page_token: Text | None = None,
    ) -> Page[SubscriptionSignal]:
        self._require_mode(ctx)
        limit = validate_result_limit(page_size)
        params: dict[str, str] = {
            "part": "snippet",
            "mine": "true",
            "maxResults": str(limit),
        }
        if page_token is not None:
            params["pageToken"] = page_token

        resp = await self._executor.execute_youtube(
            ctx, "subscriptions.list", params=params
        )
        raw_items, next_token, total = _extract_page_meta(resp.payload)
        fetched_at = self._clock.now().astimezone(UTC)
        signals: list[SubscriptionSignal] = []
        omitted = 0
        for raw in raw_items[:limit]:
            sig = normalize_subscription_item(raw, fetched_at=fetched_at)
            if sig is None:
                omitted += 1
            else:
                signals.append(sig)
        reasons = ("omitted_malformed_subscription_item",) if omitted else ()
        return Page[SubscriptionSignal](
            items=tuple(signals),
            next_page_token=next_token,
            api_reported_total=total,
            omitted=omitted,
            inaccessible=0,
            reason_codes=reasons,
        )

    async def list_my_playlists(
        self,
        ctx: RequestContext,
        page_size: Limit,
        page_token: Text | None = None,
    ) -> Page[OwnedPlaylist]:
        self._require_mode(ctx)
        limit = validate_result_limit(page_size)
        params: dict[str, str] = {
            "part": "snippet,contentDetails",
            "mine": "true",
            "maxResults": str(limit),
        }
        if page_token is not None:
            params["pageToken"] = page_token

        resp = await self._executor.execute_youtube(
            ctx, "playlists.list", params=params
        )
        raw_items, next_token, total = _extract_page_meta(resp.payload)
        playlists: list[OwnedPlaylist] = []
        omitted = 0
        for raw in raw_items[:limit]:
            pl = normalize_owned_playlist_item(raw)
            if pl is None:
                omitted += 1
            else:
                playlists.append(pl)
        reasons = ("omitted_malformed_playlist_item",) if omitted else ()
        return Page[OwnedPlaylist](
            items=tuple(playlists),
            next_page_token=next_token,
            api_reported_total=total,
            omitted=omitted,
            inaccessible=0,
            reason_codes=reasons,
        )

    async def list_playlist_items(
        self,
        ctx: RequestContext,
        playlist_id: PlaylistId,
        page_size: Limit,
        page_token: Text | None = None,
    ) -> Page[PlaylistOccurrence]:
        self._require_mode(ctx)
        valid_playlist_id = _validate_opaque_id(playlist_id, field_name="playlist")
        limit = validate_result_limit(page_size)
        params: dict[str, str] = {
            "part": "snippet,contentDetails,status",
            "playlistId": valid_playlist_id,
            "maxResults": str(limit),
        }
        if page_token is not None:
            params["pageToken"] = page_token

        resp = await self._executor.execute_youtube(
            ctx, "playlistItems.list", params=params
        )
        raw_items, next_token, total = _extract_page_meta(resp.payload)
        occurrences: list[PlaylistOccurrence] = []
        omitted = 0
        inaccessible = 0
        for raw in raw_items[:limit]:
            occ = normalize_playlist_item_occurrence(
                raw, requested_playlist_id=valid_playlist_id
            )
            if occ is None:
                omitted += 1
                continue
            if occ.accessibility == "inaccessible":
                inaccessible += 1
            occurrences.append(occ)
        reasons: list[str] = []
        if omitted:
            reasons.append("omitted_malformed_playlist_occurrence")
        if inaccessible:
            reasons.append("inaccessible_playlist_occurrence")
        return Page[PlaylistOccurrence](
            items=tuple(occurrences),
            next_page_token=next_token,
            api_reported_total=total,
            omitted=omitted,
            inaccessible=inaccessible,
            reason_codes=tuple(reasons),
        )

    async def get_category_labels(
        self, ctx: RequestContext, region_code: str
    ) -> Mapping[str, str]:
        self._require_mode(ctx)
        if not isinstance(region_code, str) or not _REGION_CODE_RE.fullmatch(
            region_code.strip().upper()
        ):
            raise _provider_error(
                "INVALID_INPUT",
                "Region code must be a two-letter ISO 3166-1 alpha-2 code.",
                safe_next_action="Provide a two-letter region code such as 'US' or 'IN'.",
            )
        normalized_region = region_code.strip().upper()
        resp = await self._executor.execute_youtube(
            ctx,
            "videoCategories.list",
            params={"part": "snippet", "regionCode": normalized_region},
        )
        raw_items, _, _ = _extract_page_meta(resp.payload)
        labels: dict[str, str] = {}
        for entry in raw_items:
            cat_id = _as_str(entry.get("id"))
            title = _clean_label(_as_mapping(entry.get("snippet")).get("title"))
            if cat_id and title:
                labels[cat_id] = title
        return labels


class LiveYouTubeProvider(LiveYouTubeReadProvider):
    """Combined live provider composing Jeswin's reads with Paul's write adapter."""

    def __init__(
        self,
        executor: AccountedHttpExecutor,
        *,
        write_adapter: YouTubeWriteProvider | None = None,
        clock: Clock | None = None,
    ) -> None:
        super().__init__(executor, clock=clock, expected_mode="live")
        self._write_adapter = write_adapter

    async def create_playlist(
        self,
        ctx: RequestContext,
        authority: ApprovedWriteContext,
        body: PlaylistBody,
    ) -> CreatedPlaylist:
        self._require_mode(ctx)
        if self._write_adapter is None:
            raise _provider_error(
                "PROVIDER_UNAVAILABLE",
                "Playlist write adapter is not configured on this live provider.",
                safe_next_action="Configure the guarded write adapter before executing approved writes.",
            )
        return await self._write_adapter.create_playlist(ctx, authority, body)

    async def insert_playlist_item(
        self,
        ctx: RequestContext,
        authority: ApprovedWriteContext,
        playlist_id: PlaylistId,
        video_id: VideoId,
        position: NonNegative,
    ) -> InsertedPlaylistItem:
        self._require_mode(ctx)
        if self._write_adapter is None:
            raise _provider_error(
                "PROVIDER_UNAVAILABLE",
                "Playlist write adapter is not configured on this live provider.",
                safe_next_action="Configure the guarded write adapter before executing approved writes.",
            )
        return await self._write_adapter.insert_playlist_item(
            ctx, authority, playlist_id, video_id, position
        )
