from collections.abc import Mapping
from typing import Annotated, Literal, Protocol

from pydantic import Field, StringConstraints

from .approval import ApprovedWriteContext
from .common import (
    ChannelId,
    Contract,
    FrozenMap,
    Label,
    LanguageTag,
    Limit,
    NonNegative,
    OpaqueId,
    PlaylistId,
    Text,
    UtcDateTime,
    VideoId,
)
from .models import Channel, Page, PlaylistOccurrence, SubscriptionSignal, Video
from .proposals import PlaylistBody, Privacy
from .workflow import RequestContext


class ChannelById(Contract):
    kind: Literal["id"] = "id"
    channel_id: ChannelId


class ChannelByHandle(Contract):
    kind: Literal["handle"] = "handle"
    handle: Annotated[str, StringConstraints(pattern=r"^@[^\s/?#]+$", max_length=128)]


type ChannelRef = Annotated[ChannelById | ChannelByHandle, Field(discriminator="kind")]


class VideoBatch(Contract):
    videos: FrozenMap[VideoId, Video]
    omitted_ids: tuple[VideoId, ...]


class ChannelBatch(Contract):
    channels: FrozenMap[ChannelId, Channel]
    omitted_ids: tuple[ChannelId, ...]


class SearchHit(Contract):
    video_id: VideoId
    channel_id: ChannelId | None


class LikedVideo(Contract):
    video: Video
    liked_at: UtcDateTime | None


class OwnedPlaylist(Contract):
    playlist_id: PlaylistId
    channel_id: ChannelId
    title: Label
    privacy: Privacy | None = None


class CreatedPlaylist(Contract):
    playlist_id: PlaylistId
    channel_id: ChannelId
    body: PlaylistBody


class InsertedPlaylistItem(Contract):
    playlist_item_id: OpaqueId
    position: NonNegative


class YouTubeReadProvider(Protocol):
    async def get_videos(
        self, ctx: RequestContext, video_ids: tuple[VideoId, ...]
    ) -> VideoBatch: ...
    async def resolve_channel(
        self, ctx: RequestContext, channel: ChannelRef
    ) -> Channel: ...
    async def get_channels(
        self, ctx: RequestContext, channel_ids: tuple[ChannelId, ...]
    ) -> ChannelBatch: ...
    async def get_my_channels(self, ctx: RequestContext) -> tuple[Channel, ...]: ...
    async def search_videos(
        self,
        ctx: RequestContext,
        query: Label,
        page_size: Limit,
        page_token: Text | None = None,
        language_hint: LanguageTag | None = None,
    ) -> Page[SearchHit]: ...
    async def list_likes(
        self, ctx: RequestContext, page_size: Limit, page_token: Text | None = None
    ) -> Page[LikedVideo]: ...
    async def list_subscriptions(
        self, ctx: RequestContext, page_size: Limit, page_token: Text | None = None
    ) -> Page[SubscriptionSignal]: ...
    async def list_my_playlists(
        self, ctx: RequestContext, page_size: Limit, page_token: Text | None = None
    ) -> Page[OwnedPlaylist]: ...
    async def list_playlist_items(
        self,
        ctx: RequestContext,
        playlist_id: PlaylistId,
        page_size: Limit,
        page_token: Text | None = None,
    ) -> Page[PlaylistOccurrence]: ...
    async def get_category_labels(
        self, ctx: RequestContext, region_code: str
    ) -> Mapping[str, str]: ...


class YouTubeWriteProvider(Protocol):
    async def create_playlist(
        self,
        ctx: RequestContext,
        authority: ApprovedWriteContext,
        body: PlaylistBody,
    ) -> CreatedPlaylist: ...
    async def insert_playlist_item(
        self,
        ctx: RequestContext,
        authority: ApprovedWriteContext,
        playlist_id: PlaylistId,
        video_id: VideoId,
        position: NonNegative,
    ) -> InsertedPlaylistItem: ...


class YouTubeProvider(YouTubeReadProvider, YouTubeWriteProvider, Protocol):
    """Combined interface for the read dispatcher and guarded write adapters."""
