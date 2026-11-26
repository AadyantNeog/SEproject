from datetime import UTC, datetime, timedelta
from pathlib import Path

import anyio
import httpx
import pytest

from yt_intel.auth.account import LocalAccountService
from yt_intel.auth.oauth import (
    YOUTUBE_READONLY_SCOPE,
    YOUTUBE_WRITE_SCOPE,
    OAuthClient,
    OAuthClientConfig,
    build_loopback_redirect_uri,
)
from yt_intel.contracts.account import TokenVault
from yt_intel.contracts.common import OpaqueId
from yt_intel.contracts.errors import ContractError
from yt_intel.contracts.models import Channel, LibrarySnapshot
from yt_intel.contracts.provider import YouTubeReadProvider
from yt_intel.contracts.workflow import (
    Endpoint,
    QuotaReservation,
    RequestContext,
    WorkflowPlan,
)
from yt_intel.infrastructure.database import Database
from yt_intel.infrastructure.http import AccountedHttpExecutor
from yt_intel.infrastructure.repositories import (
    SqliteAccountDataRepository,
    SqliteSnapshotRepository,
)

NOW = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)
FIXTURE_SNAPSHOT = (
    Path(__file__).resolve().parents[1] / "fixtures/contracts/library_snapshot.json"
)


class _MutableClock:
    def __init__(self, now: datetime = NOW) -> None:
        self.current = now

    def now(self) -> datetime:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current = self.current + timedelta(seconds=seconds)


class _FakeLedger:
    async def reserve(self, plan: WorkflowPlan) -> QuotaReservation:
        raise NotImplementedError

    async def debit_attempt(
        self, ctx: RequestContext, endpoint: Endpoint, attempt_id: str
    ) -> None:
        return None

    async def release(self, reservation_id: str) -> None:
        raise NotImplementedError


class _InMemoryVault(TokenVault):
    def __init__(self) -> None:
        self.data: dict[str, bytes] = {}

    async def read(self, reference: OpaqueId) -> bytes | None:
        return self.data.get(reference)

    async def store(self, reference: OpaqueId, sealed_payload: bytes) -> None:
        self.data[reference] = sealed_payload

    async def delete(self, reference: OpaqueId) -> None:
        self.data.pop(reference, None)


class _StubChannelProvider(YouTubeReadProvider):
    def __init__(self, channels: tuple[Channel, ...]) -> None:
        self.channels = channels

    async def get_my_channels(self, ctx: RequestContext) -> tuple[Channel, ...]:
        return self.channels

    async def get_videos(self, ctx: RequestContext, video_ids: tuple[str, ...]):  # type: ignore[override]
        raise NotImplementedError

    async def resolve_channel(self, ctx: RequestContext, channel):  # type: ignore[override]
        raise NotImplementedError

    async def get_channels(self, ctx: RequestContext, channel_ids: tuple[str, ...]):  # type: ignore[override]
        raise NotImplementedError

    async def search_videos(
        self, ctx, query, page_size, page_token=None, language_hint=None
    ):  # type: ignore[override]
        raise NotImplementedError

    async def list_likes(self, ctx, page_size, page_token=None):  # type: ignore[override]
        raise NotImplementedError

    async def list_subscriptions(self, ctx, page_size, page_token=None):  # type: ignore[override]
        raise NotImplementedError

    async def list_my_playlists(self, ctx, page_size, page_token=None):  # type: ignore[override]
        raise NotImplementedError

    async def list_playlist_items(self, ctx, playlist_id, page_size, page_token=None):  # type: ignore[override]
        raise NotImplementedError

    async def get_category_labels(self, ctx, region_code):  # type: ignore[override]
        raise NotImplementedError


def _channel(channel_id: str, title: str) -> Channel:
    return Channel(
        channel_id=channel_id,
        title=title,
        canonical_url=f"https://www.youtube.com/channel/{channel_id}",
        handle="@study",
        description=None,
        uploads_playlist_id=None,
        fetched_at=NOW,
    )


def test_full_oauth_lifecycle_refresh_upgrade_and_sqlite_disconnect(
    tmp_path: Path,
) -> None:
    async def _run() -> None:
        clock = _MutableClock(NOW)
        vault = _InMemoryVault()
        db = Database(tmp_path / "lifecycle.sqlite3")
        db.migrate()
        account_repo = SqliteAccountDataRepository(db, clock=clock)
        snapshot_repo = SqliteSnapshotRepository(db, clock=clock)

        token_calls: list[str] = []
        revoke_calls: list[str] = []

        def oauth_handler(request: httpx.Request) -> httpx.Response:
            body = request.content.decode("utf-8")
            if request.url.path == "/revoke":
                revoke_calls.append(body)
                return httpx.Response(200, json={})
            token_calls.append(body)
            if "grant_type=authorization_code" in body and "code=code-read" in body:
                return httpx.Response(
                    200,
                    json={
                        "access_token": "ya29.read_v1",
                        "refresh_token": "1//refresh_v1",
                        "expires_in": 120,
                        "scope": YOUTUBE_READONLY_SCOPE,
                        "token_type": "Bearer",
                    },
                )
            if "grant_type=refresh_token" in body:
                return httpx.Response(
                    200,
                    json={
                        "access_token": "ya29.read_v2",
                        "expires_in": 3600,
                        "scope": YOUTUBE_READONLY_SCOPE,
                        "token_type": "Bearer",
                    },
                )
            if "code=code-write-wrong-ch" in body:
                return httpx.Response(
                    200,
                    json={
                        "access_token": "ya29.other_ch",
                        "refresh_token": "1//other_ch",
                        "expires_in": 3600,
                        "scope": f"{YOUTUBE_READONLY_SCOPE} {YOUTUBE_WRITE_SCOPE}",
                        "token_type": "Bearer",
                    },
                )
            if "code=code-write-ok" in body:
                return httpx.Response(
                    200,
                    json={
                        "access_token": "ya29.write_v1",
                        "refresh_token": "1//refresh_write_v1",
                        "expires_in": 3600,
                        "scope": f"{YOUTUBE_READONLY_SCOPE} {YOUTUBE_WRITE_SCOPE}",
                        "token_type": "Bearer",
                    },
                )
            return httpx.Response(400, json={"error": "invalid_grant"})

        ch_primary = _channel("UCaaaaaaaaaaaaaaaaaaaaaa", "Primary Study")
        ch_other = _channel("UCbbbbbbbbbbbbbbbbbbbbbb", "Other Channel")

        async with AccountedHttpExecutor(
            quota_ledger=_FakeLedger(),
            transport=httpx.MockTransport(oauth_handler),
            clock=clock,
        ) as executor:
            oauth = OAuthClient(
                OAuthClientConfig(client_id="cid-desktop"), executor, clock=clock
            )
            service = LocalAccountService(
                installation_id="inst-1",
                mode="live",
                vault=vault,
                oauth_client=oauth,
                account_data=account_repo,
                clock=clock,
            )

            # 1. Read authorization
            pending_read = oauth.build_authorization_request(
                scopes=(YOUTUBE_READONLY_SCOPE,),
                redirect_uri=build_loopback_redirect_uri(51001),
            )
            status = await service.complete_authorization(
                pending_read,
                {"state": pending_read.state, "code": "code-read"},
                read_provider=_StubChannelProvider((ch_primary,)),
                reservation_id="res-auth-1",
            )
            assert status.binding.channel_id == ch_primary.channel_id
            assert status.scopes == (YOUTUBE_READONLY_SCOPE,)

            # Read scope passes; write scope is rejected with SCOPE_REQUIRED
            bound = await service.require_binding(
                required_scopes=(YOUTUBE_READONLY_SCOPE,)
            )
            assert bound == status.binding
            with pytest.raises(ContractError) as scope_err:
                await service.require_binding(required_scopes=(YOUTUBE_WRITE_SCOPE,))
            assert scope_err.value.detail.code == "SCOPE_REQUIRED"

            # 2. Access token near expiry triggers automatic serialized refresh
            assert await service.get_headers(bound) == {
                "Authorization": "Bearer ya29.read_v1"
            }
            clock.advance(90.0)  # within 60s refresh skew of 120s expiry
            assert await service.get_headers(bound) == {
                "Authorization": "Bearer ya29.read_v2"
            }

            # 3. Scope upgrade signing into a DIFFERENT channel fails closed & preserves original binding/token
            pending_wrong = oauth.build_authorization_request(
                scopes=(YOUTUBE_READONLY_SCOPE, YOUTUBE_WRITE_SCOPE),
                redirect_uri=build_loopback_redirect_uri(51002),
            )
            with pytest.raises(ContractError) as mismatch:
                await service.complete_authorization(
                    pending_wrong,
                    {"state": pending_wrong.state, "code": "code-write-wrong-ch"},
                    read_provider=_StubChannelProvider((ch_other,)),
                    reservation_id="res-auth-2",
                    required_scopes=(YOUTUBE_READONLY_SCOPE, YOUTUBE_WRITE_SCOPE),
                    require_same_channel=True,
                )
            assert mismatch.value.detail.code == "ACCOUNT_MISMATCH"
            # Original token and binding remain intact!
            assert await service.get_headers(bound) == {
                "Authorization": "Bearer ya29.read_v2"
            }
            assert len(revoke_calls) == 1

            # 4. Same-channel write-scope upgrade succeeds and preserves credential_binding_id
            pending_upgrade = oauth.build_authorization_request(
                scopes=(YOUTUBE_READONLY_SCOPE, YOUTUBE_WRITE_SCOPE),
                redirect_uri=build_loopback_redirect_uri(51003),
            )
            upgraded = await service.complete_authorization(
                pending_upgrade,
                {"state": pending_upgrade.state, "code": "code-write-ok"},
                read_provider=_StubChannelProvider((ch_primary,)),
                reservation_id="res-auth-3",
                required_scopes=(YOUTUBE_READONLY_SCOPE, YOUTUBE_WRITE_SCOPE),
                require_same_channel=True,
            )
            assert upgraded.binding == bound
            assert YOUTUBE_WRITE_SCOPE in upgraded.scopes
            assert (
                await service.require_binding(required_scopes=(YOUTUBE_WRITE_SCOPE,))
                == bound
            )

            # 5. Save SQLite snapshot for this account, then disconnect cleanly
            snap = LibrarySnapshot.model_validate_json(
                FIXTURE_SNAPSHOT.read_bytes()
            ).model_copy(update={"binding": bound})
            await snapshot_repo.save_snapshot(snap)
            disc = await service.disconnect(bound)
            assert disc.revoked is True
            assert disc.tokens_removed is True
            assert disc.local_data_removed is True
            assert disc.warnings == ()
            assert await service.current() is None
            assert vault.data == {}
            assert (
                await snapshot_repo.get_snapshot(
                    bound, snap.snapshot_id, now=clock.now()
                )
                is None
            )

    anyio.run(_run)


def test_missing_channel_and_denied_scope_fail_closed_without_storing_tokens(
    tmp_path: Path,
) -> None:
    async def _run() -> None:
        clock = _MutableClock(NOW)
        vault = _InMemoryVault()
        db = Database(tmp_path / "missing.sqlite3")
        db.migrate()
        account_repo = SqliteAccountDataRepository(db, clock=clock)

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/revoke":
                return httpx.Response(200, json={})
            body = request.content.decode("utf-8")
            if "code=code-no-scope" in body:
                return httpx.Response(
                    200,
                    json={
                        "access_token": "ya29.noscope",
                        "refresh_token": "1//noscope",
                        "expires_in": 3600,
                        "scope": "openid",
                    },
                )
            return httpx.Response(
                200,
                json={
                    "access_token": "ya29.nochannel",
                    "refresh_token": "1//nochannel",
                    "expires_in": 3600,
                    "scope": YOUTUBE_READONLY_SCOPE,
                },
            )

        async with AccountedHttpExecutor(
            quota_ledger=_FakeLedger(),
            transport=httpx.MockTransport(handler),
            clock=clock,
        ) as executor:
            oauth = OAuthClient(
                OAuthClientConfig(client_id="cid-desktop"), executor, clock=clock
            )
            service = LocalAccountService(
                installation_id="inst-1",
                mode="live",
                vault=vault,
                oauth_client=oauth,
                account_data=account_repo,
                clock=clock,
            )

            # Denied/insufficient granted scope
            p1 = oauth.build_authorization_request(
                scopes=(YOUTUBE_READONLY_SCOPE,),
                redirect_uri=build_loopback_redirect_uri(51010),
            )
            with pytest.raises(ContractError) as exc_scope:
                await service.complete_authorization(
                    p1,
                    {"state": p1.state, "code": "code-no-scope"},
                    read_provider=_StubChannelProvider(()),
                    reservation_id="res-1",
                )
            assert exc_scope.value.detail.code == "SCOPE_REQUIRED"
            assert vault.data == {}

            # Missing YouTube channel (youtubeSignupRequired equivalent)
            p2 = oauth.build_authorization_request(
                scopes=(YOUTUBE_READONLY_SCOPE,),
                redirect_uri=build_loopback_redirect_uri(51011),
            )
            with pytest.raises(ContractError) as exc_ch:
                await service.complete_authorization(
                    p2,
                    {"state": p2.state, "code": "code-no-channel"},
                    read_provider=_StubChannelProvider(()),
                    reservation_id="res-2",
                )
            assert exc_ch.value.detail.code == "CHANNEL_REQUIRED"
            assert vault.data == {}
            assert await service.current() is None

    anyio.run(_run)
