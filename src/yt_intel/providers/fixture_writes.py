import json
from dataclasses import dataclass, field
from typing import Any, Literal, cast
from uuid import uuid4

import httpx

from yt_intel.contracts.common import ChannelId
from yt_intel.contracts.workflow import QuotaLedger
from yt_intel.infrastructure.database import Database
from yt_intel.providers.fixture import FixtureDataset, FixtureYouTubeProvider


@dataclass
class _StoredPlaylist:
    body: dict[str, object]
    items: list[dict[str, object]] = field(default_factory=list)


class FixturePlaylistWrites:
    """Synthetic append-only playlist transport for the accounted HTTP executor."""

    def __init__(
        self,
        channel_id: ChannelId,
        *,
        fail_at: int | None = None,
        fault: Literal["reject", "timeout_after_insert"] = "reject",
        database: Database | None = None,
    ) -> None:
        self._channel_id = channel_id
        self._fail_at = fail_at
        self._fault = fault
        self._database = database
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
            (
                request.method == "POST"
                and path in {"/youtube/v3/playlists", "/youtube/v3/playlistItems"}
            )
            or (
                request.method == "GET"
                and path == "/youtube/v3/playlists"
                and request.url.params.get("mine") == "true"
            )
            or (
                request.method == "GET"
                and path == "/youtube/v3/playlistItems"
                and self._get(request.url.params.get("playlistId", "")) is not None
            )
        )

    def _dispatch(self, request: httpx.Request) -> httpx.Response:
        self._requests.append(request)
        path = request.url.path
        if request.method == "POST" and path == "/youtube/v3/playlists":
            body = json.loads(request.content)
            playlist_id = f"PLfixture{uuid4().hex}"
            self._create(playlist_id, body)
            return httpx.Response(
                200,
                json={
                    "id": playlist_id,
                    "snippet": {**body["snippet"], "channelId": self._channel_id},
                    "status": body["status"],
                },
            )
        if request.method == "GET" and path == "/youtube/v3/playlists":
            parts = request.url.params.get("part", "").split(",")
            return httpx.Response(
                200, json={"items": self._owned(include_status="status" in parts)}
            )
        if path != "/youtube/v3/playlistItems":
            return httpx.Response(404)
        if request.method == "GET":
            playlist = self._get(request.url.params.get("playlistId", ""))
            if playlist is None:
                return httpx.Response(404)
            return httpx.Response(200, json={"items": playlist.items})
        if request.method != "POST":
            return httpx.Response(405)
        snippet = json.loads(request.content)["snippet"]
        playlist = self._get(snippet["playlistId"])
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
        if not self._append(snippet["playlistId"], position, item):
            return httpx.Response(400)
        if position == self._fail_at and self._fault == "timeout_after_insert":
            raise httpx.ReadTimeout(
                "Synthetic timeout after insertion", request=request
            )
        return httpx.Response(200, json=item)

    def _create(self, playlist_id: str, body: dict[str, object]) -> None:
        if self._database is None:
            self._playlists[playlist_id] = _StoredPlaylist(body)
            return
        with self._database.transaction() as connection:
            connection.execute(
                "INSERT INTO fixture_remote_playlists VALUES (?, ?, ?)",
                (playlist_id, self._channel_id, json.dumps(body)),
            )

    def _get(self, playlist_id: str) -> _StoredPlaylist | None:
        if self._database is None:
            return self._playlists.get(playlist_id)
        with self._database.transaction(immediate=False) as connection:
            row = connection.execute(
                "SELECT body FROM fixture_remote_playlists WHERE playlist_id = ? AND channel_id = ?",
                (playlist_id, self._channel_id),
            ).fetchone()
            if row is None:
                return None
            items = connection.execute(
                "SELECT payload FROM fixture_remote_items WHERE playlist_id = ? ORDER BY position",
                (playlist_id,),
            )
            return _StoredPlaylist(
                json.loads(row["body"]), [json.loads(item["payload"]) for item in items]
            )

    def _owned(self, *, include_status: bool) -> list[dict[str, object]]:
        if self._database is None:
            records = [
                (identifier, playlist.body)
                for identifier, playlist in self._playlists.items()
            ]
        else:
            with self._database.transaction(immediate=False) as connection:
                records = [
                    (row["playlist_id"], json.loads(row["body"]))
                    for row in connection.execute(
                        "SELECT playlist_id, body FROM fixture_remote_playlists WHERE channel_id = ? "
                        "ORDER BY rowid DESC LIMIT 50",
                        (self._channel_id,),
                    )
                ]
        return [
            {
                "id": identifier,
                "snippet": {
                    **cast(dict[str, Any], body["snippet"]),
                    "channelId": self._channel_id,
                },
                **({"status": body.get("status")} if include_status else {}),
            }
            for identifier, body in records[:50]
        ]

    def _append(self, playlist_id: str, position: int, item: dict[str, object]) -> bool:
        if self._database is None:
            self._playlists[playlist_id].items.append(item)
            return True
        with self._database.transaction() as connection:
            cursor = connection.execute(
                "INSERT INTO fixture_remote_items SELECT ?, ?, ? WHERE "
                "(SELECT count(*) FROM fixture_remote_items WHERE playlist_id = ?) = ? "
                "AND EXISTS (SELECT 1 FROM fixture_remote_playlists WHERE playlist_id = ? AND channel_id = ?) "
                "ON CONFLICT DO NOTHING",
                (
                    playlist_id,
                    position,
                    json.dumps(item),
                    playlist_id,
                    position,
                    playlist_id,
                    self._channel_id,
                ),
            )
            return cursor.rowcount == 1


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
