from datetime import UTC, datetime, timedelta
from pathlib import Path

import anyio
import httpx
import pytest

from yt_intel.contracts.approval import ApprovedWriteContext
from yt_intel.contracts.common import AccountBinding
from yt_intel.contracts.errors import ContractError
from yt_intel.contracts.proposals import PlaylistBody, ProposalRef
from yt_intel.contracts.provider import (
    ChannelByHandle,
    ChannelById,
    CreatedPlaylist,
    InsertedPlaylistItem,
)
from yt_intel.contracts.workflow import (
    Endpoint,
    QuotaReservation,
    RequestContext,
    WorkflowPlan,
)
from yt_intel.infrastructure.http import (
    AccountedHttpExecutor,
    compute_write_request_digest,
)
from yt_intel.providers.fixture import (
    FixtureDataset,
    FixtureFault,
    FixtureYouTubeProvider,
)
from yt_intel.providers.youtube import LiveYouTubeProvider, LiveYouTubeReadProvider
from yt_intel.services.discovery import DiscoveryBounds, DiscoveryService

CATALOG_PATH = (
    Path(__file__).resolve().parents[1] / "fixtures/youtube_reads/catalog.json"
)
NOW = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)


class _NeverCancelled:
    def is_cancelled(self) -> bool:
        return False

    async def wait(self) -> None:
        await anyio.sleep_forever()


class _FixedClock:
    def __init__(self, now: datetime = NOW) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class _FakeQuotaLedger:
    def __init__(self) -> None:
        self.debits: list[tuple[Endpoint, str]] = []

    async def reserve(self, plan: WorkflowPlan) -> QuotaReservation:
        raise NotImplementedError

    async def debit_attempt(
        self, ctx: RequestContext, endpoint: Endpoint, attempt_id: str
    ) -> None:
        self.debits.append((endpoint, attempt_id))

    async def release(self, reservation_id: str) -> None:
        raise NotImplementedError


def _make_ctx(*, mode: str = "fixture") -> RequestContext:
    return RequestContext(
        request_id="req-prov-1",
        binding=AccountBinding(
            installation_id="inst-1",
            credential_binding_id="cred-1",
            channel_id="UCaaaaaaaaaaaaaaaaaaaaaa",
            mode=mode,  # type: ignore[arg-type]
        ),
        reservation_id="res-prov-1",
        deadline=NOW + timedelta(seconds=60),
        cancellation=_NeverCancelled(),
    )


def _dummy_write_authority(ctx: RequestContext) -> ApprovedWriteContext:
    return ApprovedWriteContext(
        operation_id="op-prov-1",
        reservation_id=ctx.reservation_id,
        binding=ctx.binding,
        proposal=ProposalRef(proposal_id="prop-1", version=1),
        proposal_digest="a" * 64,
        request_digest="b" * 64,
    )


def test_fixture_provider_reads_normalize_videos_channels_library_and_categories() -> (
    None
):
    async def _run() -> None:
        dataset = FixtureDataset.from_json_file(CATALOG_PATH)
        ledger = _FakeQuotaLedger()
        ctx = _make_ctx(mode="fixture")

        async with FixtureYouTubeProvider(
            dataset, quota_ledger=ledger, clock=_FixedClock()
        ) as provider:
            # get_videos with duplicates and an omitted ID (never fabricated)
            batch = await provider.get_videos(
                ctx,
                (
                    "vidIndex001",
                    "vidIndex002",
                    "vidLive0003",
                    "vidPriv0004",
                    "vidOmit0009",
                    "vidIndex001",
                ),
            )
            assert set(batch.videos) == {
                "vidIndex001",
                "vidIndex002",
                "vidLive0003",
                "vidPriv0004",
            }
            assert batch.omitted_ids == ("vidOmit0009",)

            v1 = batch.videos["vidIndex001"]
            assert v1.duration_seconds == 1200
            assert v1.language_evidence == "audio"
            assert v1.default_audio_language == "en-US"
            assert v1.availability == "available"
            assert v1.live_status == "recorded"

            v2 = batch.videos["vidIndex002"]
            assert v2.duration_seconds == 1201
            assert v2.language_evidence == "metadata_only"
            assert v2.default_audio_language is None
            assert v2.default_metadata_language == "en-GB"

            v3 = batch.videos["vidLive0003"]
            assert v3.duration_seconds is None
            assert v3.live_status == "live"
            assert v3.language_evidence == "unknown"
            assert "duration_zero" in v3.evidence_warnings

            v4 = batch.videos["vidPriv0004"]
            assert v4.availability == "inaccessible"

            # resolve_channel by ID and by @handle
            ch_id = await provider.resolve_channel(
                ctx, ChannelById(channel_id="UCaaaaaaaaaaaaaaaaaaaaaa")
            )
            ch_handle = await provider.resolve_channel(
                ctx, ChannelByHandle(handle="@QueryCraft")
            )
            assert ch_id.handle == "@SystemsStudyLab"
            assert ch_handle.channel_id == "UCbbbbbbbbbbbbbbbbbbbbbb"
            assert ch_handle.uploads_playlist_id == "UUbbbbbbbbbbbbbbbbbbbbbb"

            # Missing channel raises CONTENT_UNAVAILABLE
            with pytest.raises(ContractError) as missing_ch:
                await provider.resolve_channel(
                    ctx, ChannelByHandle(handle="@NonExistentChannel")
                )
            assert missing_ch.value.detail.code == "CONTENT_UNAVAILABLE"

            # get_my_channels
            mine = await provider.get_my_channels(ctx)
            assert len(mine) == 1
            assert mine[0].channel_id == "UCaaaaaaaaaaaaaaaaaaaaaa"

            # search_videos pagination & omitted non-video search item
            p1 = await provider.search_videos(
                ctx, "database indexing", 50, language_hint="en"
            )
            assert [h.video_id for h in p1.items] == ["vidIndex001", "vidIndex002"]
            assert p1.next_page_token == "search-page-2"
            p2 = await provider.search_videos(
                ctx, "database indexing", 50, page_token=p1.next_page_token
            )
            assert [h.video_id for h in p2.items] == ["vidIndex002", "vidOmit0009"]
            assert p2.omitted == 1
            assert p2.next_page_token is None

            # list_likes keeps liked_at=None and counts inaccessible video
            likes_1 = await provider.list_likes(ctx, 50)
            assert len(likes_1.items) == 1
            assert likes_1.items[0].liked_at is None
            likes_2 = await provider.list_likes(
                ctx, 50, page_token=likes_1.next_page_token
            )
            assert likes_2.inaccessible == 1
            assert likes_2.items[0].video.availability == "inaccessible"

            # list_subscriptions preserves subscribed_at
            subs = await provider.list_subscriptions(ctx, 50)
            assert len(subs.items) == 1
            assert subs.items[0].channel_id == "UCbbbbbbbbbbbbbbbbbbbbbb"
            assert subs.items[0].subscribed_at == datetime(
                2026, 9, 15, 12, 0, tzinfo=UTC
            )

            # list_my_playlists & list_playlist_items (preserves deleted placeholder)
            pls = await provider.list_my_playlists(ctx, 50)
            assert len(pls.items) == 1
            assert pls.items[0].playlist_id == "PLstudy0001"
            items_page = await provider.list_playlist_items(ctx, "PLstudy0001", 50)
            assert len(items_page.items) == 2
            assert items_page.items[0].accessibility == "available"
            assert items_page.items[0].added_at == datetime(
                2026, 11, 1, 8, 0, tzinfo=UTC
            )
            assert items_page.items[1].accessibility == "inaccessible"
            assert items_page.inaccessible == 1

            # get_category_labels
            cats = await provider.get_category_labels(ctx, "us")
            assert cats == {"27": "Education", "28": "Science & Technology"}

            # Every read was debited through QuotaLedger and recorded in audit_log
            assert len(ledger.debits) == len(provider.audit_log)
            assert len(provider.audit_log) > 0

    anyio.run(_run)


def test_get_videos_and_get_channels_batch_in_chunks_of_50() -> None:
    async def _run() -> None:
        video_ids = tuple(f"vidBatch{i:03d}" for i in range(55))
        channel_ids = tuple(f"UC{'a' * 20}{i:02d}" for i in range(55))
        seen_video_batches: list[int] = []
        seen_channel_batches: list[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            ids = [x for x in request.url.params.get("id", "").split(",") if x]
            if request.url.path == "/youtube/v3/videos":
                assert "maxResults" not in request.url.params
                seen_video_batches.append(len(ids))
                return httpx.Response(
                    200,
                    json={
                        "items": [
                            {
                                "id": vid,
                                "snippet": {
                                    "title": f"Video {vid}",
                                    "liveBroadcastContent": "none",
                                },
                                "contentDetails": {"duration": "PT5M"},
                                "status": {"privacyStatus": "public"},
                            }
                            for vid in ids
                            if vid != "vidBatch054"
                        ]
                    },
                )
            seen_channel_batches.append(len(ids))
            page_size = int(request.url.params.get("maxResults", "5"))
            available = [cid for cid in ids if cid != channel_ids[-1]]
            payload: dict[str, object] = {
                "items": [
                    {"id": cid, "snippet": {"title": f"Channel {cid}"}}
                    for cid in available[:page_size]
                ]
            }
            if len(available) > page_size:
                payload["nextPageToken"] = "more-channels"
            return httpx.Response(
                200,
                json=payload,
            )

        ledger = _FakeQuotaLedger()
        ctx = _make_ctx(mode="live")
        async with AccountedHttpExecutor(
            quota_ledger=ledger,
            transport=httpx.MockTransport(handler),
            clock=_FixedClock(),
        ) as executor:
            provider = LiveYouTubeReadProvider(executor, clock=_FixedClock())
            v_batch = await provider.get_videos(ctx, video_ids)
            c_batch = await provider.get_channels(ctx, channel_ids)

            assert seen_video_batches == [50, 5]
            assert seen_channel_batches == [50, 5]
            assert len(v_batch.videos) == 54
            assert v_batch.omitted_ids == ("vidBatch054",)
            assert len(c_batch.channels) == 54
            assert c_batch.omitted_ids == (channel_ids[-1],)
            assert len(ledger.debits) == 4

            # Empty inputs make zero calls
            empty_v = await provider.get_videos(ctx, ())
            empty_c = await provider.get_channels(ctx, ())
            assert empty_v.videos == {} and empty_v.omitted_ids == ()
            assert empty_c.channels == {} and empty_c.omitted_ids == ()
            assert len(ledger.debits) == 4

    anyio.run(_run)


def test_fixture_provider_rejects_live_mode_and_supports_fault_scripts() -> None:
    async def _run() -> None:
        dataset = FixtureDataset.from_json_file(CATALOG_PATH)
        ledger = _FakeQuotaLedger()
        live_ctx = _make_ctx(mode="live")
        fixture_ctx = _make_ctx(mode="fixture")

        async with FixtureYouTubeProvider(
            dataset,
            quota_ledger=ledger,
            clock=_FixedClock(),
            faults=(
                FixtureFault(endpoint="videos.list", kind="http", status_code=503),
                FixtureFault(
                    endpoint="search.list",
                    kind="http",
                    status_code=403,
                    body={"error": {"errors": [{"reason": "quotaExceeded"}]}},
                ),
            ),
        ) as provider:
            # Fixture provider refuses live-mode binding with zero debits/calls
            with pytest.raises(ContractError) as mode_err:
                await provider.get_videos(live_ctx, ("vidIndex001",))
            assert mode_err.value.detail.code == "ACCOUNT_MISMATCH"
            assert ledger.debits == []
            assert provider.audit_log == ()

            # Transient 503 on videos.list recovers on retry through AccountedHttpExecutor
            batch = await provider.get_videos(fixture_ctx, ("vidIndex001",))
            assert "vidIndex001" in batch.videos
            assert len(ledger.debits) == 2

            # quotaExceeded on search.list fails immediately without retry
            with pytest.raises(ContractError) as quota_err:
                await provider.search_videos(fixture_ctx, "indexing", 10)
            assert quota_err.value.detail.code == "QUOTA_EXHAUSTED"
            assert len(ledger.debits) == 3

    anyio.run(_run)


def test_write_adapter_composition_fails_closed_when_absent_and_delegates_when_attached() -> (
    None
):
    async def _run() -> None:
        dataset = FixtureDataset.from_json_file(CATALOG_PATH)
        ctx = _make_ctx(mode="fixture")
        authority = _dummy_write_authority(ctx)
        body = PlaylistBody(title="Study", description="Desc", privacy="private")

        async with FixtureYouTubeProvider(
            dataset, quota_ledger=_FakeQuotaLedger(), clock=_FixedClock()
        ) as unconfigured:
            with pytest.raises(ContractError) as exc:
                await unconfigured.create_playlist(ctx, authority, body)
            assert exc.value.detail.code == "PROVIDER_UNAVAILABLE"
            assert exc.value.detail.retryable is False

            writes: tuple[tuple[Endpoint, dict[str, str], dict[str, object]], ...] = (
                (
                    "playlists.insert",
                    {"part": "snippet,status"},
                    {
                        "snippet": {"title": "Study"},
                        "status": {"privacyStatus": "private"},
                    },
                ),
                (
                    "playlistItems.insert",
                    {"part": "snippet"},
                    {
                        "snippet": {
                            "playlistId": "PLcreated01",
                            "position": 0,
                            "resourceId": {
                                "kind": "youtube#video",
                                "videoId": "vidIndex001",
                            },
                        }
                    },
                ),
            )
            for endpoint, write_params, write_body in writes:
                write_auth = ApprovedWriteContext(
                    operation_id="op-direct-1",
                    reservation_id=ctx.reservation_id,
                    binding=ctx.binding,
                    proposal=ProposalRef(proposal_id="prop-1", version=1),
                    proposal_digest="a" * 64,
                    request_digest=compute_write_request_digest(
                        endpoint, params=write_params, json_body=write_body
                    ),
                )
                with pytest.raises(ContractError) as direct_err:
                    await unconfigured.executor.execute_youtube(
                        ctx,
                        endpoint,
                        params=write_params,
                        json_body=write_body,
                        authority=write_auth,
                    )
                detail = direct_err.value.detail
                assert detail.code == "PROVIDER_UNAVAILABLE"
                assert detail.retryable is False
                assert "does not support" in detail.message
                assert "reconcile" not in detail.safe_next_action.casefold()
                audit = unconfigured.audit_log[-1]
                assert audit.status_code == 405
                assert audit.outcome == "unsupported_fixture_write"
                assert audit.error_code == detail.code
            assert len(unconfigured.audit_log) == 2

        class _StubWriteAdapter:
            async def create_playlist(
                self,
                ctx: RequestContext,
                authority: ApprovedWriteContext,
                body: PlaylistBody,
            ) -> CreatedPlaylist:
                return CreatedPlaylist(
                    playlist_id="PLcreated01",
                    channel_id=ctx.binding.channel_id,
                    body=body,
                )

            async def insert_playlist_item(
                self,
                ctx: RequestContext,
                authority: ApprovedWriteContext,
                playlist_id: str,
                video_id: str,
                position: int,
            ) -> InsertedPlaylistItem:
                return InsertedPlaylistItem(
                    playlist_item_id="pli-new-1", position=position
                )

        async with FixtureYouTubeProvider(
            dataset,
            quota_ledger=_FakeQuotaLedger(),
            clock=_FixedClock(),
            write_adapter=_StubWriteAdapter(),
        ) as composed:
            created = await composed.create_playlist(ctx, authority, body)
            inserted = await composed.insert_playlist_item(
                ctx, authority, created.playlist_id, "vidIndex001", 0
            )
            assert created.playlist_id == "PLcreated01"
            assert inserted.playlist_item_id == "pli-new-1"

        # LiveYouTubeProvider also fails closed without a write adapter (using live ctx)
        live_ctx = _make_ctx(mode="live")
        live_authority = _dummy_write_authority(live_ctx)
        async with AccountedHttpExecutor(
            quota_ledger=_FakeQuotaLedger(),
            transport=httpx.MockTransport(lambda req: httpx.Response(200, json={})),
            clock=_FixedClock(),
        ) as executor:
            live = LiveYouTubeProvider(executor, clock=_FixedClock())
            with pytest.raises(ContractError) as exc:
                await live.insert_playlist_item(
                    live_ctx, live_authority, "PLcreated01", "vidIndex001", 0
                )
            assert exc.value.detail.code == "PROVIDER_UNAVAILABLE"

    anyio.run(_run)


def test_live_provider_rejects_fixture_mode_requests_before_debit_or_dispatch() -> None:
    async def _run() -> None:
        ledger = _FakeQuotaLedger()
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json={"items": []})

        fixture_ctx = _make_ctx(mode="fixture")
        async with AccountedHttpExecutor(
            quota_ledger=ledger,
            transport=httpx.MockTransport(handler),
            clock=_FixedClock(),
        ) as executor:
            provider = LiveYouTubeProvider(executor, clock=_FixedClock())
            with pytest.raises(ContractError) as exc:
                await provider.get_videos(fixture_ctx, ("vidIndex001",))
            assert exc.value.detail.code == "ACCOUNT_MISMATCH"
            with pytest.raises(ContractError) as exc_search:
                await provider.search_videos(fixture_ctx, "indexing", 10)
            assert exc_search.value.detail.code == "ACCOUNT_MISMATCH"
            with pytest.raises(ContractError) as exc_write:
                await provider.create_playlist(
                    fixture_ctx,
                    _dummy_write_authority(fixture_ctx),
                    PlaylistBody(title="Study", description="", privacy="private"),
                )
            assert exc_write.value.detail.code == "ACCOUNT_MISMATCH"
            assert ledger.debits == []
            assert calls == 0

    anyio.run(_run)


@pytest.mark.parametrize(
    "bad_payload",
    [
        {},
        {"items": "not-a-list"},
        {"items": ["not-an-object"]},
        {"items": [], "nextPageToken": 123},
        {"items": [], "pageInfo": "bad"},
    ],
)
def test_malformed_api_responses_fail_clearly(
    bad_payload: dict[str, object],
) -> None:
    async def _run() -> None:
        live_ctx = _make_ctx(mode="live")
        async with AccountedHttpExecutor(
            quota_ledger=_FakeQuotaLedger(),
            transport=httpx.MockTransport(
                lambda req: httpx.Response(200, json=bad_payload)
            ),
            clock=_FixedClock(),
        ) as executor:
            provider = LiveYouTubeReadProvider(executor, clock=_FixedClock())
            with pytest.raises(ContractError) as exc:
                await provider.get_videos(live_ctx, ("vidIndex001",))
            assert exc.value.detail.code == "PROVIDER_UNAVAILABLE"
            assert exc.value.detail.retryable is False

    anyio.run(_run)


def test_fixture_provider_integrates_with_aadyant_discovery_service() -> None:
    async def _run() -> None:
        dataset = FixtureDataset.from_json_file(CATALOG_PATH)
        ledger = _FakeQuotaLedger()
        ctx = _make_ctx(mode="fixture")

        async with FixtureYouTubeProvider(
            dataset, quota_ledger=ledger, clock=_FixedClock()
        ) as provider:
            service = DiscoveryService(
                provider, DiscoveryBounds(video_candidates=10, search_pages=2)
            )
            video_results = await service.videos(ctx, "vidIndex001", limit=5)
            assert [r.video.video_id for r in video_results.results] == ["vidIndex002"]
            assert video_results.coverage.unknown >= 1

            channel_results = await service.channels(
                ctx, ChannelByHandle(handle="@SystemsStudyLab"), limit=5
            )
            assert [r.sample.channel.channel_id for r in channel_results.results] == [
                "UCbbbbbbbbbbbbbbbbbbbbbb"
            ]
            assert len(ledger.debits) == len(provider.audit_log)

    anyio.run(_run)
