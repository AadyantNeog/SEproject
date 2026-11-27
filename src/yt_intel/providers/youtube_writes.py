from typing import Literal

from pydantic import ConfigDict, ValidationError

from yt_intel.contracts.approval import ApprovedWriteContext
from yt_intel.contracts.common import (
    ChannelId,
    Contract,
    NonNegative,
    OpaqueId,
    PlaylistId,
    VideoId,
)
from yt_intel.contracts.errors import ContractError, ErrorDetail
from yt_intel.contracts.proposals import PlaylistBody, Privacy
from yt_intel.contracts.provider import CreatedPlaylist, InsertedPlaylistItem
from yt_intel.contracts.workflow import RequestContext
from yt_intel.infrastructure.http import AccountedHttpExecutor

CREATE_PARAMS = {"part": "snippet,status"}
INSERT_PARAMS = {"part": "snippet"}


def playlist_request(body: PlaylistBody) -> dict[str, object]:
    return {
        "snippet": {"title": body.title, "description": body.description},
        "status": {"privacyStatus": body.privacy},
    }


def item_request(
    playlist_id: PlaylistId, video_id: VideoId, position: NonNegative
) -> dict[str, object]:
    return {
        "snippet": {
            "playlistId": playlist_id,
            "resourceId": {"kind": "youtube#video", "videoId": video_id},
            "position": position,
        }
    }


class _WireResponse(Contract):
    model_config = ConfigDict(extra="ignore", strict=True, frozen=True)


class _PlaylistSnippet(_WireResponse):
    channelId: ChannelId
    title: str
    description: str


class _PlaylistStatus(_WireResponse):
    privacyStatus: Privacy


class _PlaylistResponse(_WireResponse):
    id: PlaylistId
    snippet: _PlaylistSnippet
    status: _PlaylistStatus


class _VideoResource(_WireResponse):
    kind: Literal["youtube#video"]
    videoId: VideoId


class _ItemSnippet(_WireResponse):
    playlistId: PlaylistId
    position: NonNegative
    resourceId: _VideoResource


class _ItemResponse(_WireResponse):
    id: OpaqueId
    snippet: _ItemSnippet


def _unknown() -> ContractError:
    return ContractError(
        ErrorDetail(
            code="OPERATION_UNKNOWN",
            message="YouTube returned a write response that could not be verified.",
            retryable=False,
            safe_next_action="Reconcile the operation before making another write.",
        )
    )


class YouTubeWriteAdapter:
    """Serialize exact approved write bodies through the shared executor."""

    def __init__(self, executor: AccountedHttpExecutor) -> None:
        self._executor = executor

    async def create_playlist(
        self, ctx: RequestContext, authority: ApprovedWriteContext, body: PlaylistBody
    ) -> CreatedPlaylist:
        response = await self._executor.execute_youtube(
            ctx,
            "playlists.insert",
            params=CREATE_PARAMS,
            json_body=playlist_request(body),
            authority=authority,
        )
        try:
            created = _PlaylistResponse.model_validate(response.payload)
        except ValidationError:
            raise _unknown() from None
        if (
            created.snippet.channelId != ctx.binding.channel_id
            or created.snippet.title != body.title
            or created.snippet.description != body.description
            or created.status.privacyStatus != body.privacy
        ):
            raise _unknown()
        return CreatedPlaylist(
            playlist_id=created.id, channel_id=created.snippet.channelId, body=body
        )

    async def insert_playlist_item(
        self,
        ctx: RequestContext,
        authority: ApprovedWriteContext,
        playlist_id: PlaylistId,
        video_id: VideoId,
        position: NonNegative,
    ) -> InsertedPlaylistItem:
        response = await self._executor.execute_youtube(
            ctx,
            "playlistItems.insert",
            params=INSERT_PARAMS,
            json_body=item_request(playlist_id, video_id, position),
            authority=authority,
        )
        try:
            inserted = _ItemResponse.model_validate(response.payload)
        except ValidationError:
            raise _unknown() from None
        if (
            inserted.snippet.playlistId != playlist_id
            or inserted.snippet.resourceId.videoId != video_id
            or inserted.snippet.position != position
        ):
            raise _unknown()
        return InsertedPlaylistItem(playlist_item_id=inserted.id, position=position)
