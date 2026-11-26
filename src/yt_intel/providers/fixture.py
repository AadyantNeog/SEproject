from __future__ import annotations

import json
from collections import deque
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import anyio
import httpx

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
from yt_intel.contracts.errors import ContractError, ErrorDetail
from yt_intel.contracts.models import (
    Channel,
    Page,
    PlaylistOccurrence,
    SubscriptionSignal,
)
from yt_intel.contracts.proposals import PlaylistBody
from yt_intel.contracts.provider import (
    ChannelBatch,
    ChannelRef,
    CreatedPlaylist,
    InsertedPlaylistItem,
    LikedVideo,
    OwnedPlaylist,
    SearchHit,
    VideoBatch,
    YouTubeProvider,
    YouTubeWriteProvider,
)
from yt_intel.contracts.workflow import Clock, Endpoint, QuotaLedger, RequestContext
from yt_intel.infrastructure.clock import SystemClock
from yt_intel.infrastructure.http import AccountedHttpExecutor, AttemptRecord
from yt_intel.providers.youtube import LiveYouTubeReadProvider

_PATH_TO_ENDPOINT: Mapping[tuple[str, str], Endpoint] = {
    ("GET", "/youtube/v3/videos"): "videos.list",
    ("GET", "/youtube/v3/channels"): "channels.list",
    ("GET", "/youtube/v3/search"): "search.list",
    ("GET", "/youtube/v3/subscriptions"): "subscriptions.list",
    ("GET", "/youtube/v3/playlists"): "playlists.list",
    ("GET", "/youtube/v3/playlistItems"): "playlistItems.list",
    ("GET", "/youtube/v3/videoCategories"): "videoCategories.list",
    ("POST", "/youtube/v3/playlists"): "playlists.insert",
    ("POST", "/youtube/v3/playlistItems"): "playlistItems.insert",
}


@dataclass(frozen=True, slots=True)
class FixtureFault:
    """One scripted transport or HTTP fault for a specific endpoint."""

    endpoint: Endpoint
    kind: Literal["http", "timeout", "network_error"]
    status_code: int = 500
    body: Mapping[str, object] | None = None
    headers: Mapping[str, str] | None = None


@dataclass(frozen=True, slots=True)
class ProviderAuditEntry:
    """Safe audit record emitted for every provider call in fixture mode."""

    method: str
    endpoint: Endpoint | None
    params: Mapping[str, str]
    status_code: int | None
    outcome: str
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class FixtureDataset:
    """API-shaped synthetic YouTube Data API v3 fixture dataset."""

    videos: Mapping[str, Mapping[str, object]]
    channels: Mapping[str, Mapping[str, object]]
    my_channels: tuple[Mapping[str, object], ...] = ()
    search_pages: Mapping[str, Mapping[str, object]] = None  # type: ignore[assignment]
    likes_pages: Mapping[str, Mapping[str, object]] = None  # type: ignore[assignment]
    subscriptions_pages: Mapping[str, Mapping[str, object]] = None  # type: ignore[assignment]
    playlists_pages: Mapping[str, Mapping[str, object]] = None  # type: ignore[assignment]
    playlist_items_pages: Mapping[str, Mapping[str, Mapping[str, object]]] = None  # type: ignore[assignment]
    categories: Mapping[str, tuple[Mapping[str, object], ...]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.search_pages is None:
            object.__setattr__(self, "search_pages", {})
        if self.likes_pages is None:
            object.__setattr__(self, "likes_pages", {})
        if self.subscriptions_pages is None:
            object.__setattr__(self, "subscriptions_pages", {})
        if self.playlists_pages is None:
            object.__setattr__(self, "playlists_pages", {})
        if self.playlist_items_pages is None:
            object.__setattr__(self, "playlist_items_pages", {})
        if self.categories is None:
            object.__setattr__(self, "categories", {})

    @classmethod
    def from_json_file(cls, path: Path) -> FixtureDataset:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, Mapping):
            raise ValueError("fixture dataset JSON must be an object")
        categories_raw = raw.get("categories") or {}
        categories = {
            str(region).upper(): tuple(items)
            for region, items in categories_raw.items()
        }
        return cls(
            videos=dict(raw.get("videos") or {}),
            channels=dict(raw.get("channels") or {}),
            my_channels=tuple(raw.get("my_channels") or ()),
            search_pages=dict(raw.get("search_pages") or {}),
            likes_pages=dict(raw.get("likes_pages") or {}),
            subscriptions_pages=dict(raw.get("subscriptions_pages") or {}),
            playlists_pages=dict(raw.get("playlists_pages") or {}),
            playlist_items_pages=dict(raw.get("playlist_items_pages") or {}),
            categories=categories,
        )


def _require_fixture_mode(ctx: RequestContext) -> None:
    if ctx.binding.mode != "fixture":
        raise ContractError(
            ErrorDetail(
                code="ACCOUNT_MISMATCH",
                message="Fixture provider cannot serve live-mode account bindings.",
                retryable=False,
                safe_next_action="Use a fixture-mode account binding for synthetic fixture runs.",
            )
        )


class FixtureYouTubeProvider(YouTubeProvider):
    """Offline synthetic fixture provider routed through AccountedHttpExecutor.

    Cannot read live credentials or fall through to live network transport.
    Emits an audit trail of every attempted request and supports scripted faults
    and pluggable fixture write adapters (P2-04).
    """

    def __init__(
        self,
        dataset: FixtureDataset,
        *,
        quota_ledger: QuotaLedger,
        clock: Clock | None = None,
        faults: Sequence[FixtureFault] = (),
        write_adapter: YouTubeWriteProvider | None = None,
        sleep: Callable[[float], Awaitable[None]] = anyio.sleep,
        jitter: Callable[[], float] | None = None,
        base_backoff_seconds: float = 0.0,
        max_backoff_seconds: float = 0.0,
    ) -> None:
        self._dataset = dataset
        self._write_adapter = write_adapter
        self._clock: Clock = clock if clock is not None else SystemClock()
        self._fault_queues: dict[Endpoint, deque[FixtureFault]] = {}
        for fault in faults:
            self._fault_queues.setdefault(fault.endpoint, deque()).append(fault)
        self._audit: list[ProviderAuditEntry] = []
        self._attempts: list[AttemptRecord] = []

        self._executor = AccountedHttpExecutor(
            quota_ledger=quota_ledger,
            auth_headers=None,
            transport=httpx.MockTransport(self._handle_request),
            clock=self._clock,
            sleep=sleep,
            jitter=jitter if jitter is not None else (lambda: 0.0),
            base_backoff_seconds=base_backoff_seconds,
            max_backoff_seconds=max_backoff_seconds,
            on_attempt=self._on_attempt,
        )
        self._reader = LiveYouTubeReadProvider(self._executor, clock=self._clock)

    @property
    def executor(self) -> AccountedHttpExecutor:
        """Expose the fixture-bound executor for Paul's fixture write adapter."""
        return self._executor

    @property
    def audit_log(self) -> tuple[ProviderAuditEntry, ...]:
        return tuple(self._audit)

    @property
    def attempt_records(self) -> tuple[AttemptRecord, ...]:
        return tuple(self._attempts)

    async def aclose(self) -> None:
        await self._executor.aclose()

    async def __aenter__(self) -> FixtureYouTubeProvider:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    def _on_attempt(self, record: AttemptRecord) -> None:
        self._attempts.append(record)

    def _handle_request(self, request: httpx.Request) -> httpx.Response:
        endpoint = _PATH_TO_ENDPOINT.get((request.method.upper(), request.url.path))
        params = dict(request.url.params.multi_items())
        if endpoint is None:
            self._audit.append(
                ProviderAuditEntry(
                    method=request.method,
                    endpoint=None,
                    params=params,
                    status_code=404,
                    outcome="unmapped_route",
                    error_code="UNSUPPORTED_IDENTIFIER",
                )
            )
            return httpx.Response(
                404, json={"error": {"message": "Unmapped fixture route"}}
            )

        queue = self._fault_queues.get(endpoint)
        if queue:
            fault = queue.popleft()
            if fault.kind == "timeout":
                self._audit.append(
                    ProviderAuditEntry(
                        method=request.method,
                        endpoint=endpoint,
                        params=params,
                        status_code=None,
                        outcome="timeout",
                        error_code="WORKFLOW_TIMEOUT",
                    )
                )
                raise httpx.ReadTimeout("scripted fixture timeout", request=request)
            if fault.kind == "network_error":
                self._audit.append(
                    ProviderAuditEntry(
                        method=request.method,
                        endpoint=endpoint,
                        params=params,
                        status_code=None,
                        outcome="network_error",
                        error_code="PROVIDER_UNAVAILABLE",
                    )
                )
                raise httpx.ConnectError(
                    "scripted fixture network error", request=request
                )
            self._audit.append(
                ProviderAuditEntry(
                    method=request.method,
                    endpoint=endpoint,
                    params=params,
                    status_code=fault.status_code,
                    outcome="scripted_http_fault",
                )
            )
            return httpx.Response(
                fault.status_code,
                json=dict(fault.body) if fault.body is not None else {},
                headers=dict(fault.headers) if fault.headers is not None else None,
            )

        payload = self._dispatch_read(endpoint, params)
        self._audit.append(
            ProviderAuditEntry(
                method=request.method,
                endpoint=endpoint,
                params=params,
                status_code=200,
                outcome="ok",
            )
        )
        return httpx.Response(200, json=payload)

    def _dispatch_read(
        self, endpoint: Endpoint, params: Mapping[str, str]
    ) -> dict[str, object]:
        page_token = params.get("pageToken", "")
        if endpoint == "videos.list":
            if params.get("myRating") == "like":
                return dict(self._dataset.likes_pages.get(page_token, {"items": []}))
            raw_ids = params.get("id", "")
            requested_ids = [vid for vid in raw_ids.split(",") if vid]
            items = [
                dict(self._dataset.videos[vid])
                for vid in requested_ids
                if vid in self._dataset.videos
            ]
            return {"items": items, "pageInfo": {"totalResults": len(items)}}

        if endpoint == "channels.list":
            if params.get("mine") == "true":
                items = [dict(ch) for ch in self._dataset.my_channels]
                return {"items": items, "pageInfo": {"totalResults": len(items)}}
            if "forHandle" in params:
                target = params["forHandle"].casefold()
                if not target.startswith("@"):
                    target = f"@{target}"
                matched: list[dict[str, object]] = []
                for ch in self._dataset.channels.values():
                    snippet = ch.get("snippet")
                    if (
                        isinstance(snippet, Mapping)
                        and str(snippet.get("customUrl", "")).casefold() == target
                    ):
                        matched.append(dict(ch))
                return {"items": matched, "pageInfo": {"totalResults": len(matched)}}
            raw_ids = params.get("id", "")
            requested_ids = [cid for cid in raw_ids.split(",") if cid]
            items = [
                dict(self._dataset.channels[cid])
                for cid in requested_ids
                if cid in self._dataset.channels
            ]
            return {"items": items, "pageInfo": {"totalResults": len(items)}}

        if endpoint == "search.list":
            page = self._dataset.search_pages.get(page_token)
            if page is None:
                return {"items": []}
            return dict(page)

        if endpoint == "subscriptions.list":
            return dict(
                self._dataset.subscriptions_pages.get(page_token, {"items": []})
            )

        if endpoint == "playlists.list":
            return dict(self._dataset.playlists_pages.get(page_token, {"items": []}))

        if endpoint == "playlistItems.list":
            playlist_id = params.get("playlistId", "")
            pages = self._dataset.playlist_items_pages.get(playlist_id, {})
            return dict(pages.get(page_token, {"items": []}))

        if endpoint == "videoCategories.list":
            region = params.get("regionCode", "").upper()
            cats = [dict(cat) for cat in self._dataset.categories.get(region, ())]
            return {"items": cats}

        return {"items": []}

    async def get_videos(
        self, ctx: RequestContext, video_ids: tuple[VideoId, ...]
    ) -> VideoBatch:
        _require_fixture_mode(ctx)
        return await self._reader.get_videos(ctx, video_ids)

    async def resolve_channel(
        self, ctx: RequestContext, channel: ChannelRef
    ) -> Channel:
        _require_fixture_mode(ctx)
        return await self._reader.resolve_channel(ctx, channel)

    async def get_channels(
        self, ctx: RequestContext, channel_ids: tuple[ChannelId, ...]
    ) -> ChannelBatch:
        _require_fixture_mode(ctx)
        return await self._reader.get_channels(ctx, channel_ids)

    async def get_my_channels(self, ctx: RequestContext) -> tuple[Channel, ...]:
        _require_fixture_mode(ctx)
        return await self._reader.get_my_channels(ctx)

    async def search_videos(
        self,
        ctx: RequestContext,
        query: Label,
        page_size: Limit,
        page_token: Text | None = None,
        language_hint: LanguageTag | None = None,
    ) -> Page[SearchHit]:
        _require_fixture_mode(ctx)
        return await self._reader.search_videos(
            ctx, query, page_size, page_token=page_token, language_hint=language_hint
        )

    async def list_likes(
        self,
        ctx: RequestContext,
        page_size: Limit,
        page_token: Text | None = None,
    ) -> Page[LikedVideo]:
        _require_fixture_mode(ctx)
        return await self._reader.list_likes(ctx, page_size, page_token=page_token)

    async def list_subscriptions(
        self,
        ctx: RequestContext,
        page_size: Limit,
        page_token: Text | None = None,
    ) -> Page[SubscriptionSignal]:
        _require_fixture_mode(ctx)
        return await self._reader.list_subscriptions(
            ctx, page_size, page_token=page_token
        )

    async def list_my_playlists(
        self,
        ctx: RequestContext,
        page_size: Limit,
        page_token: Text | None = None,
    ) -> Page[OwnedPlaylist]:
        _require_fixture_mode(ctx)
        return await self._reader.list_my_playlists(
            ctx, page_size, page_token=page_token
        )

    async def list_playlist_items(
        self,
        ctx: RequestContext,
        playlist_id: PlaylistId,
        page_size: Limit,
        page_token: Text | None = None,
    ) -> Page[PlaylistOccurrence]:
        _require_fixture_mode(ctx)
        return await self._reader.list_playlist_items(
            ctx, playlist_id, page_size, page_token=page_token
        )

    async def get_category_labels(
        self, ctx: RequestContext, region_code: str
    ) -> Mapping[str, str]:
        _require_fixture_mode(ctx)
        return await self._reader.get_category_labels(ctx, region_code)

    async def create_playlist(
        self,
        ctx: RequestContext,
        authority: ApprovedWriteContext,
        body: PlaylistBody,
    ) -> CreatedPlaylist:
        _require_fixture_mode(ctx)
        if self._write_adapter is None:
            raise ContractError(
                ErrorDetail(
                    code="APPROVAL_REQUIRED",
                    message="Fixture write adapter is not configured on this provider.",
                    retryable=False,
                    safe_next_action="Attach Paul's fixture write adapter to execute synthetic playlist writes.",
                )
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
        _require_fixture_mode(ctx)
        if self._write_adapter is None:
            raise ContractError(
                ErrorDetail(
                    code="APPROVAL_REQUIRED",
                    message="Fixture write adapter is not configured on this provider.",
                    retryable=False,
                    safe_next_action="Attach Paul's fixture write adapter to execute synthetic playlist item writes.",
                )
            )
        return await self._write_adapter.insert_playlist_item(
            ctx, authority, playlist_id, video_id, position
        )
