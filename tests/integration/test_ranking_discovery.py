from datetime import timedelta
from pathlib import Path
from unittest.mock import create_autospec

import anyio
import pytest

from yt_intel.contracts.errors import ContractError
from yt_intel.contracts.models import (
    Channel,
    LibrarySnapshot,
    Page,
    PlaylistOccurrence,
    Video,
)
from yt_intel.contracts.provider import (
    ChannelBatch,
    ChannelByHandle,
    SearchHit,
    VideoBatch,
    YouTubeReadProvider,
)
from yt_intel.contracts.workflow import RequestContext
from yt_intel.services.discovery import DiscoveryBounds, DiscoveryService

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/contracts"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def snapshot() -> LibrarySnapshot:
    return LibrarySnapshot.model_validate_json(
        (FIXTURES / "library_snapshot.json").read_bytes()
    )


class FakeCancellation:
    def is_cancelled(self) -> bool:
        return False

    async def wait(self) -> None:
        await anyio.sleep_forever()


def fixture_context(snapshot: LibrarySnapshot, *, live: bool = False) -> RequestContext:
    binding = (
        snapshot.binding.model_copy(update={"mode": "live"})
        if live
        else snapshot.binding
    )
    return RequestContext(
        request_id="fixture-ranking",
        binding=binding,
        reservation_id="fixture-reservation",
        deadline=snapshot.fetched_at + timedelta(minutes=1),
        cancellation=FakeCancellation(),
    )


def search_page(*hits: SearchHit, next_token: str | None = None) -> Page[SearchHit]:
    return Page[SearchHit](
        items=hits,
        next_page_token=next_token,
        api_reported_total=None,
        omitted=0,
        inaccessible=0,
    )


def video_fixture(template: Video, video_id: str, **fields: object) -> Video:
    return Video.model_validate(
        {
            **template.model_dump(),
            "video_id": video_id,
            "canonical_url": f"https://www.youtube.com/watch?v={video_id}",
            **fields,
        }
    )


@pytest.mark.anyio
async def test_video_discovery_bounds_duplicate_search_and_hydration(
    snapshot: LibrarySnapshot,
):
    provider = create_autospec(YouTubeReadProvider, instance=True)
    ctx = fixture_context(snapshot)
    seed = next(iter(snapshot.videos.values()))
    related = video_fixture(seed, "synthetic01")
    omitted_id = "synthetic02"
    provider.get_videos.side_effect = [
        VideoBatch(videos={seed.video_id: seed}, omitted_ids=()),
        VideoBatch(videos={related.video_id: related}, omitted_ids=(omitted_id,)),
    ]
    seed_hit = SearchHit(video_id=seed.video_id, channel_id=seed.channel_id)
    related_hit = SearchHit(video_id=related.video_id, channel_id=related.channel_id)
    provider.search_videos.side_effect = [
        search_page(seed_hit, related_hit, next_token="fixture-page-two"),
        search_page(
            related_hit,
            SearchHit(video_id=omitted_id, channel_id=None),
            next_token="fixture-page-three",
        ),
    ]
    service = DiscoveryService(
        provider, DiscoveryBounds(video_candidates=2, search_pages=2)
    )
    result = await service.videos(ctx, seed.video_id, limit=1)
    assert [entry.video.video_id for entry in result.results] == [related.video_id]
    assert (
        result.coverage.retrieved,
        result.coverage.usable,
        result.coverage.unknown,
    ) == (2, 1, 1)
    assert (
        result.coverage.truncated
        and result.coverage.paginated
        and not result.coverage.complete
    )
    assert result.coverage.continuation_ref is None
    assert provider.search_videos.await_count == 2
    assert provider.search_videos.await_args_list[1].args[3] == "fixture-page-two"
    provider.get_videos.assert_awaited_with(ctx, (related.video_id, omitted_id))


@pytest.mark.anyio
async def test_invalid_limit_and_live_policy_fail_before_provider_access(
    snapshot: LibrarySnapshot,
):
    provider = create_autospec(YouTubeReadProvider, instance=True)
    service = DiscoveryService(provider)
    seed_id = next(iter(snapshot.videos))
    with pytest.raises(ContractError) as invalid:
        await service.videos(fixture_context(snapshot), seed_id, limit=51)
    assert invalid.value.detail.code == "INVALID_INPUT"
    with pytest.raises(ContractError) as live:
        await service.videos(fixture_context(snapshot, live=True), seed_id)
    assert live.value.detail.code == "POLICY_BLOCKED"
    assert not provider.mock_calls


@pytest.mark.anyio
async def test_repeated_search_token_stops_with_explicit_empty_coverage(
    snapshot: LibrarySnapshot,
):
    provider = create_autospec(YouTubeReadProvider, instance=True)
    seed = next(iter(snapshot.videos.values()))
    provider.get_videos.return_value = VideoBatch(
        videos={seed.video_id: seed}, omitted_ids=()
    )
    provider.search_videos.return_value = search_page(
        SearchHit(video_id=seed.video_id, channel_id=seed.channel_id),
        next_token="repeat",
    )
    result = await DiscoveryService(provider).videos(
        fixture_context(snapshot), seed.video_id
    )
    assert result.results == ()
    assert result.coverage.truncated and result.coverage.paginated
    assert result.coverage.continuation_ref is None
    assert result.coverage.warnings == (
        "No accessible candidate had overlapping video metadata.",
    )
    assert provider.search_videos.await_count == 2
    provider.get_videos.assert_awaited_once()


@pytest.mark.anyio
async def test_missing_video_seed_returns_typed_error_without_search(
    snapshot: LibrarySnapshot,
):
    provider = create_autospec(YouTubeReadProvider, instance=True)
    seed_id = next(iter(snapshot.videos))
    provider.get_videos.return_value = VideoBatch(videos={}, omitted_ids=(seed_id,))
    with pytest.raises(ContractError) as error:
        await DiscoveryService(provider).videos(fixture_context(snapshot), seed_id)
    assert error.value.detail.code == "CONTENT_UNAVAILABLE"
    provider.search_videos.assert_not_awaited()


@pytest.mark.anyio
async def test_channel_discovery_samples_one_upload_page_per_channel(
    snapshot: LibrarySnapshot,
):
    provider = create_autospec(YouTubeReadProvider, instance=True)
    ctx = fixture_context(snapshot)
    template = next(iter(snapshot.videos.values()))

    def channel(letter: str, title: str) -> Channel:
        channel_id = "UC" + letter * 22
        return Channel(
            channel_id=channel_id,
            title=title,
            description="Compiler type theory",
            handle=None,
            uploads_playlist_id="UU" + letter * 22,
            fetched_at=template.fetched_at,
            canonical_url=f"https://www.youtube.com/channel/{channel_id}",
        )

    seed = channel("A", "Compiler seed")
    other = channel("B", "Compiler lessons")
    seed_ref = ChannelByHandle(handle="@compiler")
    provider.resolve_channel.return_value = seed
    provider.get_channels.return_value = ChannelBatch(
        channels={other.channel_id: other}, omitted_ids=()
    )
    provider.search_videos.return_value = search_page(
        SearchHit(video_id="synthetic01", channel_id=seed.channel_id),
        SearchHit(video_id="synthetic02", channel_id=other.channel_id),
        SearchHit(video_id="synthetic03", channel_id=other.channel_id),
    )
    vids = [
        video_fixture(
            template, video_id, channel_id=ch.channel_id, title="Compiler tutorials"
        )
        for video_id, ch in [("synthetic01", seed), ("synthetic02", other)]
    ]
    provider.get_videos.side_effect = [
        VideoBatch(videos={v.video_id: v}, omitted_ids=()) for v in vids
    ]

    def uploads(ch: Channel, video: Video) -> Page[PlaylistOccurrence]:
        return Page[PlaylistOccurrence](
            items=(
                PlaylistOccurrence(
                    playlist_id=ch.uploads_playlist_id,
                    playlist_item_id="fixture-item",
                    video_id=video.video_id,
                    position=0,
                    added_at=None,
                    accessibility="available",
                ),
            ),
            next_page_token="fixture-unread-uploads",
            api_reported_total=None,
            omitted=0,
            inaccessible=0,
        )

    provider.list_playlist_items.side_effect = [
        uploads(seed, vids[0]),
        uploads(other, vids[1]),
    ]
    result = await DiscoveryService(provider).channels(ctx, seed_ref, limit=50)
    assert [entry.sample.channel.channel_id for entry in result.results] == [
        other.channel_id
    ]
    assert result.results[0].sample.video_ids == (vids[1].video_id,)
    assert result.results[0].sample.coverage.truncated
    assert result.coverage.limits["channel_candidates"] == 10
    provider.resolve_channel.assert_awaited_once_with(ctx, seed_ref)
    provider.get_channels.assert_awaited_once_with(ctx, (other.channel_id,))
    assert [call.args for call in provider.list_playlist_items.await_args_list] == [
        (ctx, seed.uploads_playlist_id, 5),
        (ctx, other.uploads_playlist_id, 5),
    ]
