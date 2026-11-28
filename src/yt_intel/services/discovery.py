from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

from pydantic import TypeAdapter, ValidationError

from yt_intel.contracts.common import Contract, Limit, Positive, VideoId
from yt_intel.contracts.errors import ContractError, ErrorCode, ErrorDetail
from yt_intel.contracts.models import (
    Channel,
    ChannelSample,
    Coverage,
    PlaylistOccurrence,
    RankedChannel,
    RankedVideo,
    Video,
)
from yt_intel.contracts.provider import ChannelRef, SearchHit, YouTubeReadProvider
from yt_intel.contracts.workflow import RequestContext
from yt_intel.domain.derived import DerivedProcessingCheck, fixture_only
from yt_intel.domain.ranking import ChannelCorpus, rank_channels, rank_videos, tokenize

_VIDEO_ID = TypeAdapter(VideoId)
_CHANNEL_REF = TypeAdapter(ChannelRef)
_LIMIT = TypeAdapter(Limit)
_SAMPLE_RULE = "first-accessible-uploads-v1"

type DiscoveryProgress = Callable[[int, str], Awaitable[None]]


class DiscoveryBounds(Contract):
    video_candidates: Positive = 200
    channel_candidates: Positive = 10
    search_pages: Positive = 4
    page_size: Limit = 50
    uploads_per_channel: Limit = 5


@dataclass(frozen=True, slots=True)
class DiscoveryResult[T]:
    results: tuple[T, ...]
    coverage: Coverage


@dataclass(frozen=True, slots=True)
class VideoDiscoveryResult(DiscoveryResult[RankedVideo]):
    seed: Video
    candidates: tuple[Video, ...]


@dataclass(frozen=True, slots=True)
class VideoCandidatePool:
    videos: tuple[Video, ...]
    coverage: Coverage


@dataclass(frozen=True, slots=True)
class _SearchPool:
    ids: tuple[str, ...]
    paginated: bool
    truncated: bool
    inaccessible: int
    omitted: int


def _failure(code: ErrorCode, message: str, next_action: str) -> ContractError:
    return ContractError(
        ErrorDetail(
            code=code, message=message, retryable=False, safe_next_action=next_action
        )
    )


def _fixture_context(
    ctx: RequestContext, permits: DerivedProcessingCheck = fixture_only
) -> None:
    if not permits(ctx.binding):
        raise _failure(
            "POLICY_BLOCKED",
            "Live metadata ranking is pending policy clearance.",
            "Use a synthetic fixture account.",
        )


def _query(fields: Sequence[str]) -> str:
    terms = dict.fromkeys(token for field in fields for token in tokenize(field))
    parts: list[str] = []
    size = 0
    for term in terms:
        size += len(term) + bool(parts)
        if len(parts) == 8 or size > 256:
            break
        parts.append(term)
    if not parts:
        raise _failure(
            "INSUFFICIENT_DATA",
            "The seed has no usable metadata for a search query.",
            "Try a different seed with descriptive metadata.",
        )
    return " ".join(parts)


class DiscoveryService:
    """Read workflows using a server-issued context whose budget was reserved upstream."""

    def __init__(
        self,
        provider: YouTubeReadProvider,
        bounds: DiscoveryBounds = DiscoveryBounds(),
        *,
        progress: DiscoveryProgress | None = None,
        permits: DerivedProcessingCheck = fixture_only,
    ) -> None:
        self._provider = provider
        self._permits = permits
        self._bounds = bounds
        self._progress = progress

    async def _report_progress(self, completed: int, message: str) -> None:
        if self._progress is not None:
            await self._progress(completed, message)

    async def videos(
        self, ctx: RequestContext, seed_id: VideoId, *, limit: int = 10
    ) -> VideoDiscoveryResult:
        try:
            seed_id = _VIDEO_ID.validate_python(seed_id, strict=True)
            limit = _LIMIT.validate_python(limit, strict=True)
        except ValidationError:
            raise _failure(
                "INVALID_INPUT",
                "Expected a normalized video ID and a limit from 1 to 50.",
                "Correct the ID or result limit.",
            ) from None
        _fixture_context(ctx, self._permits)
        seed_batch = await self._provider.get_videos(ctx, (seed_id,))
        seed = seed_batch.videos.get(seed_id)
        if seed is None or seed.availability != "available":
            raise _failure(
                "CONTENT_UNAVAILABLE",
                "The seed video is unavailable in this context.",
                "Choose an accessible seed video.",
            )
        await self._report_progress(1, "Loaded the seed video.")

        candidates = await self.video_candidates(
            ctx,
            _query((seed.title, seed.description or "", *(seed.tags or ())[:32])),
            exclude_video_id=seed_id,
        )
        await self._report_progress(2, "Collected candidate video metadata.")
        results = rank_videos(seed, candidates.videos, limit=limit)
        coverage = candidates.coverage
        if not results:
            coverage = coverage.model_copy(
                update={
                    "warnings": (
                        "No accessible candidate had overlapping video metadata.",
                    )
                }
            )
        return VideoDiscoveryResult(results, coverage, seed, candidates.videos)

    async def video_candidates(
        self,
        ctx: RequestContext,
        query: str,
        *,
        exclude_video_id: VideoId | None = None,
    ) -> VideoCandidatePool:
        """Hydrate a bounded search for a server-derived query under the caller's reservation."""
        _fixture_context(ctx, self._permits)
        pool = await self._search(
            ctx,
            query,
            lambda hit: hit.video_id,
            exclude_video_id,
            self._bounds.video_candidates,
        )
        usable = []
        inaccessible = pool.inaccessible
        unknown = pool.omitted
        if pool.ids:
            candidates = await self._provider.get_videos(ctx, pool.ids)
            for video_id in pool.ids:
                video = candidates.videos.get(video_id)
                if video is None or video.availability == "unknown":
                    unknown += 1
                elif video.availability == "inaccessible":
                    inaccessible += 1
                else:
                    usable.append(video)
        return VideoCandidatePool(
            tuple(usable),
            self._coverage(
                pool,
                len(usable),
                inaccessible,
                unknown,
                {"video_candidates": self._bounds.video_candidates},
                (),
            ),
        )

    async def channels(
        self, ctx: RequestContext, seed_ref: ChannelRef, *, limit: int = 10
    ) -> DiscoveryResult[RankedChannel]:
        try:
            seed_ref = _CHANNEL_REF.validate_python(seed_ref, strict=True)
            limit = _LIMIT.validate_python(limit, strict=True)
        except ValidationError:
            raise _failure(
                "INVALID_INPUT",
                "Expected a normalized channel reference and a limit from 1 to 50.",
                "Correct the channel reference or result limit.",
            ) from None
        _fixture_context(ctx, self._permits)
        channel = await self._provider.resolve_channel(ctx, seed_ref)
        seed = await self._sample(ctx, channel)
        if not seed.supporting_document():
            raise _failure(
                "INSUFFICIENT_DATA",
                "The seed channel has no comparable description or upload text.",
                "Choose a channel with a description or accessible uploads.",
            )
        await self._report_progress(1, "Loaded the seed channel and its upload sample.")

        query = _query(
            (
                channel.description or "",
                channel.title,
                *(video.title for video in seed.videos),
            )
        )
        pool = await self._search(
            ctx,
            query,
            lambda hit: hit.channel_id,
            channel.channel_id,
            self._bounds.channel_candidates,
        )
        entries = []
        unknown = pool.omitted
        if pool.ids:
            channels = await self._provider.get_channels(ctx, pool.ids)
            for channel_id in pool.ids:
                candidate = channels.channels.get(channel_id)
                if candidate is None:
                    unknown += 1
                else:
                    entries.append(await self._sample(ctx, candidate))
        await self._report_progress(
            2, "Collected candidate channels and upload samples."
        )
        results = rank_channels(seed, entries, limit=limit)
        return DiscoveryResult(
            results,
            self._coverage(
                pool,
                len(entries),
                pool.inaccessible,
                unknown,
                {
                    "channel_candidates": self._bounds.channel_candidates,
                    "uploads_per_channel": self._bounds.uploads_per_channel,
                },
                ()
                if results
                else ("No comparable candidate channel had overlapping metadata.",),
                sampled=True,
            ),
        )

    async def _search(
        self,
        ctx: RequestContext,
        query: str,
        identify: Callable[[SearchHit], str | None],
        seed_id: str | None,
        cap: int,
    ) -> _SearchPool:
        ids: dict[str, None] = {}
        token = None
        seen_tokens: set[str] = set()
        inaccessible = omitted = 0
        for page_index in range(self._bounds.search_pages):
            page = await self._provider.search_videos(
                ctx, query, self._bounds.page_size, token
            )
            inaccessible += page.inaccessible
            omitted += page.omitted
            for hit in page.items:
                key = identify(hit)
                if key is None:
                    omitted += 1
                elif key != seed_id and key not in ids:
                    if len(ids) == cap:
                        return _SearchPool(
                            tuple(ids), page_index > 0, True, inaccessible, omitted
                        )
                    ids[key] = None
            token = page.next_page_token
            if token is None or token in seen_tokens or len(ids) == cap:
                break
            seen_tokens.add(token)
        return _SearchPool(
            tuple(ids), page_index > 0, token is not None, inaccessible, omitted
        )

    async def _sample(self, ctx: RequestContext, channel: Channel) -> ChannelCorpus:
        warnings = []
        entries: tuple[PlaylistOccurrence, ...] = ()
        truncated = False
        inaccessible = unknown = 0
        if channel.uploads_playlist_id is None:
            warnings.append("Uploads playlist unavailable.")
        else:
            page = await self._provider.list_playlist_items(
                ctx, channel.uploads_playlist_id, self._bounds.uploads_per_channel
            )
            entries = page.items[: self._bounds.uploads_per_channel]
            truncated = page.next_page_token is not None or len(entries) < len(
                page.items
            )
            inaccessible, unknown = page.inaccessible, page.omitted

        ids: dict[str, None] = {}
        for row in entries:
            if row.accessibility == "inaccessible":
                inaccessible += 1
            elif row.video_id is None or row.accessibility == "unknown":
                unknown += 1
            else:
                ids[row.video_id] = None
        videos = []
        if ids:
            batch = await self._provider.get_videos(ctx, tuple(ids))
            for video_id in ids:
                video = batch.videos.get(video_id)
                if video is None:
                    unknown += 1
                elif video.availability == "inaccessible":
                    inaccessible += 1
                elif (
                    video.availability == "unknown"
                    or video.channel_id != channel.channel_id
                ):
                    unknown += 1
                else:
                    videos.append(video)
        if not channel.description:
            warnings.append("Channel description unavailable.")
        if not videos:
            warnings.append("No usable videos in the bounded uploads sample.")
        coverage = Coverage(
            complete=channel.uploads_playlist_id is not None and not truncated,
            paginated=False,
            sampled=True,
            truncated=truncated,
            retrieved=len(entries),
            usable=len(videos),
            inaccessible=inaccessible,
            unknown=unknown,
            limits={"uploads_per_channel": self._bounds.uploads_per_channel},
            sampled_sources=("uploads",),
            completeness_basis="First returned uploads page",
            warnings=tuple(warnings),
        )
        sample = ChannelSample(
            channel=channel,
            video_ids=tuple(video.video_id for video in videos),
            attempted=len(entries),
            usable=len(videos),
            skipped=len(entries) - len(videos),
            selection_rule_version=_SAMPLE_RULE,
            coverage=coverage,
        )
        return ChannelCorpus(sample, tuple(videos))

    def _coverage(
        self,
        pool: _SearchPool,
        usable: int,
        inaccessible: int,
        unknown: int,
        limits: dict[str, int],
        warnings: tuple[str, ...],
        *,
        sampled: bool = False,
    ) -> Coverage:
        return Coverage(
            complete=not pool.truncated,
            paginated=pool.paginated,
            sampled=sampled,
            truncated=pool.truncated,
            retrieved=len(pool.ids),
            usable=usable,
            inaccessible=inaccessible,
            unknown=unknown,
            limits={
                **limits,
                "search_pages": self._bounds.search_pages,
                "page_size": self._bounds.page_size,
            },
            sampled_sources=("uploads",) if sampled else (),
            completeness_basis="Unique hydration targets from bounded video search",
            warnings=warnings,
        )
