import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import anyio
import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from yt_intel.contracts.account import AccountService, AccountStatus, DisconnectResult
from yt_intel.contracts.common import AccountBinding, Label
from yt_intel.contracts.errors import ContractError
from yt_intel.domain.language import normalize_language_tag
from yt_intel.infrastructure.database import Database
from yt_intel.infrastructure.quota import QuotaProfile, SqliteQuotaLedger
from yt_intel.infrastructure.repositories import SqliteSnapshotRepository
from yt_intel.providers.fixture import (
    FixtureDataset,
    FixtureFault,
    FixtureYouTubeProvider,
)
from yt_intel.services.library import LibraryBounds, LibraryService
from yt_intel.services.recommendations import RecommendationService

ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = ROOT / "tests/fixtures/libraries/library_catalog.json"
PROFILE_PATH = ROOT / "config/quota-profiles/youtube-2026-11-16.json"
NOW = datetime(2026, 11, 27, 12, 0, tzinfo=UTC)


class _MutableClock:
    def __init__(self, now: datetime = NOW) -> None:
        self.current = now

    def now(self) -> datetime:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current = self.current + timedelta(seconds=seconds)


class _NeverCancelled:
    def is_cancelled(self) -> bool:
        return False

    async def wait(self) -> None:
        await anyio.sleep_forever()


class _StaticAccountService(AccountService):
    def __init__(self, binding: AccountBinding) -> None:
        self.binding = binding

    async def current(self) -> AccountStatus | None:
        return AccountStatus(
            binding=self.binding,
            channel_title="Fixture Learning Channel",
            scopes=("https://www.googleapis.com/auth/youtube.readonly",),
        )

    async def require_binding(
        self, *, required_scopes: tuple[Label, ...] = ()
    ) -> AccountBinding:
        return self.binding

    async def disconnect(self, binding: AccountBinding) -> DisconnectResult:
        return DisconnectResult(
            local_data_removed=True, tokens_removed=True, revoked=False
        )


def _binding(cred_id: str = "fixture-cred-1") -> AccountBinding:
    return AccountBinding(
        installation_id="fixture-inst",
        credential_binding_id=cred_id,
        channel_id="UCaaaaaaaaaaaaaaaaaaaaaa",
        mode="fixture",
    )


def test_library_collection_enforces_fairness_bounds_dedup_and_feeds_recommendations(
    tmp_path: Path,
) -> None:
    async def _run() -> None:
        clock = _MutableClock(NOW)
        db = Database(tmp_path / "lib.sqlite3")
        db.migrate()
        profile = QuotaProfile.load(PROFILE_PATH)
        ledger = SqliteQuotaLedger(db, profile, clock=clock)
        snapshot_repo = SqliteSnapshotRepository(db, clock=clock)
        dataset = FixtureDataset.from_json_file(CATALOG_PATH)
        accounts = _StaticAccountService(_binding())

        async with FixtureYouTubeProvider(
            dataset, quota_ledger=ledger, clock=clock
        ) as provider:
            service = LibraryService(
                provider=provider,
                account_service=accounts,
                quota_ledger=ledger,
                snapshot_repo=snapshot_repo,
                clock=clock,
                bounds=LibraryBounds(
                    total_source_pages=12,
                    initial_pages_per_source=1,
                    owned_playlists_cap=3,
                ),
            )
            result = await service.collect(cancellation=_NeverCancelled())
            snap = result.snapshot

            # All three sources retrieved; playlists selected first 3 of 4 in returned order
            assert set(snap.sources) == {"likes", "subscriptions", "playlists"}
            assert all(s.state == "retrieved" for s in snap.sources.values())
            assert snap.owned_playlist_ids == (
                "PLowned0001",
                "PLowned0002",
                "PLowned0003",
            )
            # Deleted placeholder preserved as inaccessible occurrence
            assert any(
                occ.accessibility == "inaccessible" for occ in snap.playlist_occurrences
            )
            # Likes and playlists overlap on libVid00001, deduplicated in snap.videos
            assert "libVid00001" in snap.likes
            assert snap.likes["libVid00001"] is None
            assert "libVid00001" in snap.videos
            assert "libVid00002" in snap.videos
            assert "libVid00003" in snap.videos
            # Subscription channel topic sample populated (channel-topic evidence)
            assert len(snap.subscriptions) == 1
            assert snap.subscriptions[0].topic_sample is not None
            assert snap.subscriptions[0].topic_sample.video_ids == ("libVid00004",)
            # Snapshot persisted in Paul's real SQLite repository
            stored = await snapshot_repo.get_snapshot(
                snap.binding, snap.snapshot_id, now=clock.now()
            )
            assert stored == snap

            # Opaque continuation handle issued (never leaks raw Google page token!)
            assert result.continuation_ref is not None
            assert result.continuation_ref.startswith("cont-")
            assert "raw-google-likes-page-2" not in result.summary.model_dump_json()

            # Direct interoperability with Aadyant's RecommendationService (no translation!)
            rec_service = RecommendationService(normalize_language_tag)
            query = rec_service.search_query(
                snap, binding=snap.binding, now=clock.now()
            )
            assert query.strip() != ""

            # Resume continuation -> fetches page 2 of likes without duplicating page 1
            resumed = await service.collect(
                cancellation=_NeverCancelled(),
                continuation_ref=result.continuation_ref,
            )
            assert "libVid00003" in resumed.snapshot.likes
            assert "libVid00001" not in resumed.snapshot.likes
            assert resumed.continuation_ref is None

            # Foreign account cannot resume another user's continuation handle
            accounts.binding = _binding("foreign-cred")
            with pytest.raises(ContractError) as foreign_err:
                await service.collect(
                    cancellation=_NeverCancelled(),
                    continuation_ref=result.continuation_ref,
                )
            assert foreign_err.value.detail.code == "ACCOUNT_MISMATCH"

            # Changed sources cannot reuse continuation handle
            accounts.binding = snap.binding
            with pytest.raises(ContractError) as changed_err:
                await service.collect(
                    cancellation=_NeverCancelled(),
                    sources=("likes",),
                    continuation_ref=result.continuation_ref,
                )
            assert changed_err.value.detail.code == "INVALID_INPUT"

            # Expired continuation handle fails cleanly
            clock.advance(700.0)
            with pytest.raises(ContractError) as exp_err:
                await service.collect(
                    cancellation=_NeverCancelled(),
                    continuation_ref=result.continuation_ref,
                )
            assert exp_err.value.detail.code == "CONTENT_UNAVAILABLE"

    anyio.run(_run)


def test_denied_and_subset_sources_degrade_gracefully(tmp_path: Path) -> None:
    async def _run() -> None:
        clock = _MutableClock(NOW)
        db = Database(tmp_path / "denied.sqlite3")
        db.migrate()
        profile = QuotaProfile.load(PROFILE_PATH)
        ledger = SqliteQuotaLedger(db, profile, clock=clock)
        snapshot_repo = SqliteSnapshotRepository(db, clock=clock)
        dataset = FixtureDataset.from_json_file(CATALOG_PATH)
        accounts = _StaticAccountService(_binding())

        # Likes returns 403 insufficientPermissions -> denied, while subscriptions & playlists succeed
        async with FixtureYouTubeProvider(
            dataset,
            quota_ledger=ledger,
            clock=clock,
            faults=(
                FixtureFault(
                    endpoint="videos.list",
                    kind="http",
                    status_code=403,
                    body={"error": {"errors": [{"reason": "insufficientPermissions"}]}},
                ),
            ),
        ) as provider:
            service = LibraryService(
                provider=provider,
                account_service=accounts,
                quota_ledger=ledger,
                snapshot_repo=snapshot_repo,
                clock=clock,
                bounds=LibraryBounds(initial_pages_per_source=1),
            )
            result = await service.collect(cancellation=_NeverCancelled())
            assert result.snapshot.sources["likes"].state == "denied"
            assert result.snapshot.sources["subscriptions"].state == "retrieved"
            assert result.snapshot.sources["playlists"].state == "retrieved"
            assert any("denied" in w for w in result.summary.warnings)

            # Subset request marks unrequested sources as not_requested
            subset = await service.collect(
                cancellation=_NeverCancelled(), sources=("subscriptions",)
            )
            assert subset.snapshot.sources["likes"].state == "not_requested"
            assert subset.snapshot.sources["playlists"].state == "not_requested"
            assert subset.snapshot.sources["subscriptions"].state == "retrieved"

    anyio.run(_run)


def test_library_account_and_get_video_tools_over_fixture_stdio(
    tmp_path: Path,
) -> None:
    async def _run() -> None:
        db_file = tmp_path / "stdio-lib.sqlite3"
        params = StdioServerParameters(
            command=sys.executable,
            args=[
                "-m",
                "yt_intel",
                "serve",
                "--provider",
                "fixture",
                "--project-root",
                str(ROOT),
                "--fixture-db",
                str(db_file),
            ],
        )
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer, read_timeout_seconds=15) as client:
                await client.initialize()
                tools = {tool.name for tool in (await client.list_tools()).tools}
                assert {
                    "get_video",
                    "get_library",
                    "get_account_status",
                    "disconnect_account",
                }.issubset(tools)

                # 1. get_video
                vid_res = await client.call_tool("get_video", {"video": "libVid00001"})
                assert not vid_res.is_error
                assert vid_res.structured_content is not None
                assert vid_res.structured_content["data"]["video_id"] == "libVid00001"

                # 2. get_library
                lib_res = await client.call_tool("get_library", {})
                assert not lib_res.is_error
                assert lib_res.structured_content is not None
                lib_data = lib_res.structured_content["data"]
                assert lib_data["snapshot_id"].startswith("snap-")
                assert lib_data["unique_videos_count"] >= 3
                assert "raw-google-likes-page-2" not in str(lib_data)

                # 3. get_account_status
                acct_res = await client.call_tool("get_account_status", {})
                assert not acct_res.is_error
                assert acct_res.structured_content is not None
                assert acct_res.structured_content["status"] == "ok"

                # 4. disconnect_account -> subsequent get_account_status is empty
                disc_res = await client.call_tool("disconnect_account", {})
                assert not disc_res.is_error
                assert disc_res.structured_content is not None
                assert disc_res.structured_content["data"]["local_data_removed"] is True

                after_res = await client.call_tool("get_account_status", {})
                assert after_res.structured_content is not None
                assert after_res.structured_content["status"] == "empty"

    anyio.run(_run)
