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
    BucketVector,
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
                        "access_token": "mock-a",
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


def test_account_stays_inactive_during_channel_verification_and_handles_cancellation(
    tmp_path: Path,
) -> None:
    async def _run() -> None:
        clock = _MutableClock(NOW)
        vault = _InMemoryVault()
        db = Database(tmp_path / "inactive.sqlite3")
        db.migrate()
        account_repo = SqliteAccountDataRepository(db, clock=clock)

        probe_started = anyio.Event()
        allow_probe_finish = anyio.Event()
        observed_during_probe: dict[str, object] = {}

        class _SlowChannelProvider(_StubChannelProvider):
            async def get_my_channels(self, ctx: RequestContext) -> tuple[Channel, ...]:
                probe_started.set()
                await allow_probe_finish.wait()
                return self.channels

        class _CancellableToken:
            def __init__(self) -> None:
                self._ev = anyio.Event()

            def cancel(self) -> None:
                self._ev.set()

            def is_cancelled(self) -> bool:
                return self._ev.is_set()

            async def wait(self) -> None:
                await self._ev.wait()

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "access_token": "mock-b",
                    "refresh_token": "1//probe_ref",
                    "expires_in": 3600,
                    "scope": YOUTUBE_READONLY_SCOPE,
                },
            )

        ch = _channel("UCaaaaaaaaaaaaaaaaaaaaaa", "Verified Channel")
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

            # Explicit desktop scopes: include_granted_scopes must be false by default
            pending = oauth.build_authorization_request(
                scopes=(YOUTUBE_READONLY_SCOPE,),
                redirect_uri=build_loopback_redirect_uri(51020),
            )
            assert "include_granted_scopes=false" in pending.authorization_url

            cancel_tok = _CancellableToken()

            async def _run_auth() -> None:
                with pytest.raises(ContractError) as exc:
                    await service.complete_authorization(
                        pending,
                        {"state": pending.state, "code": "code-cancel"},
                        read_provider=_SlowChannelProvider((ch,)),
                        reservation_id="res-probe",
                        cancellation=cancel_tok,
                    )
                observed_during_probe["error_code"] = exc.value.detail.code

            async def _inspect_while_verifying() -> None:
                await probe_started.wait()
                # Account must remain inactive and vault empty until channel verification finishes!
                observed_during_probe["current"] = await service.current()
                observed_during_probe["vault_keys"] = list(vault.data.keys())
                try:
                    await service.require_binding()
                    observed_during_probe["require_error"] = None
                except ContractError as exc:
                    observed_during_probe["require_error"] = exc.detail.code
                cancel_tok.cancel()
                allow_probe_finish.set()

            async with anyio.create_task_group() as tg:
                tg.start_soon(_run_auth)
                tg.start_soon(_inspect_while_verifying)

            assert observed_during_probe["current"] is None
            assert observed_during_probe["vault_keys"] == []
            assert observed_during_probe["require_error"] == "AUTH_REQUIRED"
            assert observed_during_probe["error_code"] == "WORKFLOW_TIMEOUT"
            assert await service.current() is None
            assert vault.data == {}

    anyio.run(_run)


def test_disconnect_blocks_access_during_in_flight_refresh_and_prevents_token_writeback(
    tmp_path: Path,
) -> None:
    async def _run() -> None:
        clock = _MutableClock(NOW)
        vault = _InMemoryVault()
        db = Database(tmp_path / "race.sqlite3")
        db.migrate()
        account_repo = SqliteAccountDataRepository(db, clock=clock)

        refresh_started = anyio.Event()
        allow_refresh_finish = anyio.Event()
        refresh_error: list[str] = []
        mid_disconnect_blocked: list[bool] = []

        async def _async_oauth_handler(request: httpx.Request) -> httpx.Response:
            body = request.content.decode("utf-8")
            if request.url.path == "/revoke":
                return httpx.Response(200, json={})
            if "grant_type=refresh_token" in body:
                refresh_started.set()
                await allow_refresh_finish.wait()
                return httpx.Response(
                    200,
                    json={
                        "access_token": "ya29.refreshed_too_late",
                        "expires_in": 3600,
                        "scope": YOUTUBE_READONLY_SCOPE,
                    },
                )
            return httpx.Response(
                200,
                json={
                    "access_token": "ya29.initial_expiring",
                    "refresh_token": "1//initial_refresh",
                    "expires_in": 30,
                    "scope": YOUTUBE_READONLY_SCOPE,
                },
            )

        ch = _channel("UCaaaaaaaaaaaaaaaaaaaaaa", "Race Channel")
        async with AccountedHttpExecutor(
            quota_ledger=_FakeLedger(),
            transport=httpx.MockTransport(_async_oauth_handler),
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
            pending = oauth.build_authorization_request(
                scopes=(YOUTUBE_READONLY_SCOPE,),
                redirect_uri=build_loopback_redirect_uri(51030),
            )
            status = await service.complete_authorization(
                pending,
                {"state": pending.state, "code": "code-init"},
                read_provider=_StubChannelProvider((ch,)),
                reservation_id="res-init",
            )
            bound = status.binding

            async def _do_refresh() -> None:
                try:
                    await service.get_headers(bound)
                except ContractError as exc:
                    refresh_error.append(exc.detail.code)

            async def _do_disconnect() -> None:
                await refresh_started.wait()
                async with anyio.create_task_group() as inner:
                    inner.start_soon(service.disconnect, bound)
                    # Yield so disconnect starts and sets immediate block before refresh finishes
                    await anyio.sleep(0.02)
                    mid_disconnect_blocked.append(await service.current() is None)
                    try:
                        await service.require_binding()
                        mid_disconnect_blocked.append(False)
                    except ContractError as exc:
                        mid_disconnect_blocked.append(
                            exc.detail.code == "AUTH_REQUIRED"
                        )
                    allow_refresh_finish.set()

            async with anyio.create_task_group() as tg:
                tg.start_soon(_do_refresh)
                tg.start_soon(_do_disconnect)

            assert mid_disconnect_blocked == [True, True]
            assert refresh_error == ["AUTH_REQUIRED"]
            # In-flight refresh must NOT have written refreshed tokens back into the vault
            assert vault.data == {}
            assert await service.current() is None

    anyio.run(_run)


def test_browser_loopback_flow_and_cli_auth_subcommand(tmp_path: Path) -> None:
    import threading
    from urllib.parse import parse_qs, urlsplit
    from urllib.request import urlopen

    from yt_intel.cli import main as cli_main

    # CLI requires --client-secrets (or env var) and exits cleanly without traceback
    assert cli_main(["auth", "--read"]) == 2

    async def _run() -> None:
        clock = _MutableClock(NOW)
        vault = _InMemoryVault()
        db = Database(tmp_path / "browser.sqlite3")
        db.migrate()
        account_repo = SqliteAccountDataRepository(db, clock=clock)

        def oauth_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "access_token": "ya29.browser_tok",
                    "refresh_token": "1//browser_ref",
                    "expires_in": 3600,
                    "scope": YOUTUBE_READONLY_SCOPE,
                },
            )

        ch = _channel("UCaaaaaaaaaaaaaaaaaaaaaa", "Browser Channel")
        opened_urls: list[str] = []

        def fake_open_browser(url: str) -> bool:
            opened_urls.append(url)
            parsed = urlsplit(url)
            qs = parse_qs(parsed.query)
            redirect_uri = qs["redirect_uri"][0]
            state = qs["state"][0]
            callback_url = f"{redirect_uri}?state={state}&code=browser-auth-code"

            def _hit_callback() -> None:
                with urlopen(callback_url, timeout=5) as resp:
                    assert resp.status == 200

            threading.Thread(target=_hit_callback, daemon=True).start()
            return True

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
            status = await service.authorize_via_browser(
                enable_writes=False,
                read_provider=_StubChannelProvider((ch,)),
                reservation_id="res-browser",
                timeout_seconds=10.0,
                open_browser=fake_open_browser,
            )
            assert status.binding.channel_id == ch.channel_id
            assert status.scopes == (YOUTUBE_READONLY_SCOPE,)
            assert len(opened_urls) == 1
            assert "include_granted_scopes=false" in opened_urls[0]
            assert "127.0.0.1" in opened_urls[0]

    anyio.run(_run)


def test_cli_auth_reloads_active_account_across_separate_invocations_and_uses_quota_ledger(
    tmp_path: Path,
) -> None:
    import json
    import threading
    from urllib.parse import parse_qs, urlsplit
    from urllib.request import urlopen

    from yt_intel.cli import run_cli_auth

    secrets_file = tmp_path / "client_secret.json"
    secrets_file.write_text(
        json.dumps({"installed": {"client_id": "cid-desktop-cli"}}),
        encoding="utf-8",
    )
    db_path = tmp_path / "live.sqlite3"
    state_path = tmp_path / "account-live.json"
    clock = _MutableClock(NOW)
    vault = _InMemoryVault()

    class _TrackingQuotaLedger:
        def __init__(self) -> None:
            self.reservations: dict[str, WorkflowPlan] = {}
            self.debits: list[tuple[str, Endpoint, str]] = []
            self.released: list[str] = []

        async def reserve(self, plan: WorkflowPlan) -> QuotaReservation:
            res_id = f"res-{len(self.reservations) + 1}"
            self.reservations[res_id] = plan
            return QuotaReservation(
                reservation_id=res_id,
                plan_id=plan.plan_id,
                project_id=plan.project_id,
                quota_profile_id=plan.quota_profile_id,
                reset_at=NOW + timedelta(days=1),
                reserved=plan.buckets,
            )

        async def debit_attempt(
            self, ctx: RequestContext, endpoint: Endpoint, attempt_id: str
        ) -> None:
            plan = self.reservations.get(ctx.reservation_id)
            assert plan is not None
            assert plan.binding == ctx.binding
            assert endpoint in plan.endpoint_ceilings
            self.debits.append((ctx.reservation_id, endpoint, attempt_id))

        async def release(self, reservation_id: str) -> None:
            self.released.append(reservation_id)

    ledger = _TrackingQuotaLedger()

    def configured_costs(plan: WorkflowPlan) -> BucketVector:
        ceiling = plan.endpoint_ceilings["channels.list"]
        return {"general": ceiling.calls * ceiling.attempts_per_call * 2}

    def make_browser(auth_code: str):
        def _open(url: str) -> bool:
            parsed = urlsplit(url)
            qs = parse_qs(parsed.query)
            callback_url = (
                f"{qs['redirect_uri'][0]}?state={qs['state'][0]}&code={auth_code}"
            )

            def _hit() -> None:
                with urlopen(callback_url, timeout=5) as resp:
                    assert resp.status == 200

            threading.Thread(target=_hit, daemon=True).start()
            return True

        return _open

    def oauth_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/revoke":
            return httpx.Response(200, json={})
        body = request.content.decode("utf-8")
        if "code=code-read" in body:
            return httpx.Response(
                200,
                json={
                    "access_token": "ya29.cli_read",
                    "refresh_token": "1//cli_read_ref",
                    "expires_in": 3600,
                    "scope": YOUTUBE_READONLY_SCOPE,
                },
            )
        return httpx.Response(
            200,
            json={
                "access_token": "ya29.cli_write",
                "refresh_token": "1//cli_write_ref",
                "expires_in": 3600,
                "scope": f"{YOUTUBE_READONLY_SCOPE} {YOUTUBE_WRITE_SCOPE}",
            },
        )

    def make_api_transport(channel_id: str, title: str) -> httpx.MockTransport:
        def _handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/youtube/v3/channels"
            assert request.url.params.get("mine") == "true"
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": channel_id,
                            "snippet": {"title": title, "customUrl": "@study"},
                            "contentDetails": {
                                "relatedPlaylists": {"uploads": "UU123"}
                            },
                        }
                    ]
                },
            )

        return httpx.MockTransport(_handler)

    async def _run() -> None:
        # Invocation 1: `yt-intel auth --read`
        read_status = await run_cli_auth(
            client_secrets_path=secrets_file,
            enable_writes=False,
            vault=vault,
            open_browser=make_browser("code-read"),
            database_path=db_path,
            account_state_path=state_path,
            quota_ledger=ledger,
            quota_costs=configured_costs,
            clock=clock,
            oauth_transport=httpx.MockTransport(oauth_handler),
            api_transport=make_api_transport(
                "UCaaaaaaaaaaaaaaaaaaaaaa", "Primary Channel"
            ),
        )
        assert read_status.binding.channel_id == "UCaaaaaaaaaaaaaaaaaaaaaa"
        assert read_status.scopes == (YOUTUBE_READONLY_SCOPE,)
        # State file exists and contains NO OAuth tokens
        state_text = state_path.read_text(encoding="utf-8")
        assert "ya29.cli_read" not in state_text
        assert "1//cli_read_ref" not in state_text

        # Invocation 2 (separate run): `yt-intel auth --enable-writes` with WRONG channel fails closed
        with pytest.raises(ContractError) as mismatch:
            await run_cli_auth(
                client_secrets_path=secrets_file,
                enable_writes=True,
                vault=vault,
                open_browser=make_browser("code-write-wrong"),
                database_path=db_path,
                account_state_path=state_path,
                quota_ledger=ledger,
                quota_costs=configured_costs,
                clock=clock,
                oauth_transport=httpx.MockTransport(oauth_handler),
                api_transport=make_api_transport(
                    "UCbbbbbbbbbbbbbbbbbbbbbb", "Wrong Channel"
                ),
            )
        assert mismatch.value.detail.code == "ACCOUNT_MISMATCH"

        # Invocation 3 (separate run): `yt-intel auth --enable-writes` with SAME channel succeeds
        # and keeps the exact same AccountBinding (credential_binding_id + channel_id).
        write_status = await run_cli_auth(
            client_secrets_path=secrets_file,
            enable_writes=True,
            vault=vault,
            open_browser=make_browser("code-write-same"),
            database_path=db_path,
            account_state_path=state_path,
            quota_ledger=ledger,
            quota_costs=configured_costs,
            clock=clock,
            oauth_transport=httpx.MockTransport(oauth_handler),
            api_transport=make_api_transport(
                "UCaaaaaaaaaaaaaaaaaaaaaa", "Primary Channel"
            ),
        )
        assert write_status.binding == read_status.binding
        assert write_status.scopes == (YOUTUBE_READONLY_SCOPE, YOUTUBE_WRITE_SCOPE)

        # Every channel lookup reserved, debited `channels.list`, and released through QuotaLedger
        assert len(ledger.reservations) == 3
        assert all(
            plan.buckets == {"general": 6} for plan in ledger.reservations.values()
        )
        assert [ep for _, ep, _ in ledger.debits] == [
            "channels.list",
            "channels.list",
            "channels.list",
        ]
        assert ledger.released == ["res-1", "res-2", "res-3"]

    anyio.run(_run)
