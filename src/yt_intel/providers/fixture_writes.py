import json
from dataclasses import dataclass, field
from typing import Literal
from uuid import uuid4

import httpx

from yt_intel.contracts.common import ChannelId
from yt_intel.contracts.workflow import QuotaLedger
from yt_intel.providers.fixture import FixtureDataset, FixtureYouTubeProvider


@dataclass
class _StoredPlaylist:
    items: list[dict[str, object]] = field(default_factory=list)


class FixturePlaylistWrites:
    """Synthetic append-only playlist transport for the accounted HTTP executor."""

    def __init__(
        self,
        channel_id: ChannelId,
        *,
        fail_at: int | None = None,
        fault: Literal["reject", "timeout_after_insert"] = "reject",
    ) -> None:
        self._channel_id = channel_id
        self._fail_at = fail_at
        self._fault = fault
        self._playlists: dict[str, _StoredPlaylist] = {}
        self._requests: list[httpx.Request] = []

    @property
    def requests(self) -> tuple[httpx.Request, ...]:
        return tuple(self._requests)

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._dispatch)

    def handles(self, request: httpx.Request) -> bool:
        path = request.url.path
        return (
            request.method == "POST"
            and path in {"/youtube/v3/playlists", "/youtube/v3/playlistItems"}
        ) or (
            request.method == "GET"
            and path == "/youtube/v3/playlistItems"
            and request.url.params.get("playlistId", "") in self._playlists
        )

    def _dispatch(self, request: httpx.Request) -> httpx.Response:
        self._requests.append(request)
        path = request.url.path
        if request.method == "POST" and path == "/youtube/v3/playlists":
            body = json.loads(request.content)
            playlist_id = f"PLfixture{uuid4().hex}"
            self._playlists[playlist_id] = _StoredPlaylist()
            return httpx.Response(
                200,
                json={
                    "id": playlist_id,
                    "snippet": {**body["snippet"], "channelId": self._channel_id},
                    "status": body["status"],
                },
            )
        if path != "/youtube/v3/playlistItems":
            return httpx.Response(404)
        if request.method == "GET":
            playlist = self._playlists.get(request.url.params.get("playlistId", ""))
            if playlist is None:
                return httpx.Response(404)
            return httpx.Response(200, json={"items": playlist.items})
        if request.method != "POST":
            return httpx.Response(405)
        snippet = json.loads(request.content)["snippet"]
        playlist = self._playlists.get(snippet["playlistId"])
        if playlist is None:
            return httpx.Response(404)
        position = snippet["position"]
        if position != len(playlist.items):
            return httpx.Response(400)
        if position == self._fail_at and self._fault == "reject":
            return httpx.Response(
                400, json={"error": {"errors": [{"reason": "invalidValue"}]}}
            )
        item: dict[str, object] = {
            "id": f"{snippet['playlistId']}-item-{position}",
            "snippet": {**snippet, "channelId": self._channel_id},
        }
        playlist.items.append(item)
        if position == self._fail_at and self._fault == "timeout_after_insert":
            raise httpx.ReadTimeout(
                "Synthetic timeout after insertion", request=request
            )
        return httpx.Response(200, json=item)


class FixtureCreationProvider(FixtureYouTubeProvider):
    """Combine the fixture catalog and playlist simulator behind one executor."""

    def __init__(
        self,
        dataset: FixtureDataset,
        *,
        quota_ledger: QuotaLedger,
        simulator: FixturePlaylistWrites,
    ) -> None:
        self._simulator = simulator
        self._write_transport = simulator.transport()
        super().__init__(dataset, quota_ledger=quota_ledger)

    def _handle_request(self, request: httpx.Request) -> httpx.Response:
        if self._simulator.handles(request):
            return self._write_transport.handle_request(request)
        return super()._handle_request(request)
