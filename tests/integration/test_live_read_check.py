"""Offline tests for the J2-07 live read-only check gates and fixed budget.

Google endpoints are replaced by httpx mock transports and the vault is in
memory. No network, real token or live quota is used.
"""

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from urllib.request import urlopen

import anyio
import httpx

from yt_intel.auth.oauth import YOUTUBE_READONLY_SCOPE
from yt_intel.cli import run_cli_auth, run_cli_disconnect
from yt_intel.contracts.account import TokenVault
from yt_intel.contracts.common import OpaqueId
from yt_intel.infrastructure.database import Database
from yt_intel.infrastructure.quota import QuotaProfile, SqliteQuotaLedger
from yt_intel.live_read_check import (
    DEFAULT_POLICY,
    DEFAULT_PROFILE,
    ENABLE_ENV,
    SECRETS_ENV,
    VIDEO_ENV,
    policy_resolved,
    run_check,
)

CHANNEL = "UCaaaaaaaaaaaaaaaaaaaaaa"
VIDEO = "dQw4w9WgXcQ"


class _Clock:
    def __init__(self) -> None:
        self._now = datetime.now(UTC)

    def now(self) -> datetime:
        return self._now


class _InMemoryVault(TokenVault):
    def __init__(self) -> None:
        self.data: dict[str, bytes] = {}

    async def read(self, reference: OpaqueId) -> bytes | None:
        return self.data.get(reference)

    async def store(self, reference: OpaqueId, sealed_payload: bytes) -> None:
        self.data[reference] = sealed_payload

    async def delete(self, reference: OpaqueId) -> None:
        self.data.pop(reference, None)


def _oauth(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "access_token": "ya29.check",
            "refresh_token": "1//check_ref",
            "expires_in": 3600,
            "scope": YOUTUBE_READONLY_SCOPE,
        },
    )


def _api(seen: list[str], channel: str = CHANNEL) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        seen.append(request.url.path)
        if request.url.path == "/youtube/v3/channels":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": channel,
                            "snippet": {"title": "Test Channel"},
                            "contentDetails": {"relatedPlaylists": {"uploads": "UU1"}},
                        }
                    ]
                },
            )
        assert request.url.path == "/youtube/v3/videos"
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": VIDEO,
                        "snippet": {
                            "title": "Public test video",
                            "liveBroadcastContent": "none",
                            "defaultAudioLanguage": "en",
                        },
                        "contentDetails": {"duration": "PT3M33S"},
                        "status": {"privacyStatus": "public"},
                    }
                ]
            },
        )

    return httpx.MockTransport(handler)


def _browser(url: str) -> bool:
    query = parse_qs(urlsplit(url).query)
    callback = f"{query['redirect_uri'][0]}?state={query['state'][0]}&code=c"

    def hit() -> None:
        with urlopen(callback, timeout=5) as response:
            assert response.status == 200

    threading.Thread(target=hit, daemon=True).start()
    return True


class _Setup:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp = tmp_path
        self.db = tmp_path / "live.sqlite3"
        self.state = tmp_path / "account-live.json"
        self.secrets = tmp_path / "client_secret.json"
        self.secrets.write_text(
            json.dumps({"installed": {"client_id": "cid-check"}}), encoding="utf-8"
        )
        self.policy = tmp_path / "d02.json"
        self.policy.write_text(
            json.dumps(
                {
                    "state": "resolved",
                    "evidence_url": "https://example.edu/d02-direction",
                    "recorded_by": "Test operator",
                }
            ),
            encoding="utf-8",
        )
        self.vault = _InMemoryVault()
        self.clock = _Clock()
        self.env = {
            ENABLE_ENV: "1",
            VIDEO_ENV: VIDEO,
            SECRETS_ENV: str(self.secrets),
        }

    async def sign_in(self) -> None:
        profile = QuotaProfile.load(
            Path(__file__).resolve().parents[2]
            / "config/quota-profiles/youtube-2026-11-16.json"
        )
        database = Database(self.db)
        database.migrate()
        await run_cli_auth(
            client_secrets_path=self.secrets,
            enable_writes=False,
            vault=self.vault,
            open_browser=_browser,
            database_path=self.db,
            account_state_path=self.state,
            quota_ledger=SqliteQuotaLedger(database, profile, clock=self.clock),
            quota_costs=profile.required_buckets,
            quota_profile_id=profile.profile_id,
            clock=self.clock,
            oauth_transport=httpx.MockTransport(_oauth),
            api_transport=_api([]),
        )

    async def check(self, seen: list[str], **changes: object):
        arguments: dict[str, object] = {
            "environ": self.env,
            "policy_path": self.policy,
            "profile_path": DEFAULT_PROFILE,
            "database_path": self.db,
            "account_state_path": self.state,
            "vault": self.vault,
            "clock": self.clock,
            "oauth_transport": httpx.MockTransport(_oauth),
            "api_transport": _api(seen),
        }
        arguments.update(changes)
        return await run_check(**arguments)  # type: ignore[arg-type]


def test_repository_d02_record_is_unresolved() -> None:
    assert policy_resolved(DEFAULT_POLICY) is False
    record = json.loads(DEFAULT_POLICY.read_text(encoding="utf-8"))
    assert record["state"] == "unresolved" and record["evidence_url"] is None


def test_gates_block_before_any_provider_call(tmp_path: Path) -> None:
    setup = _Setup(tmp_path)
    seen: list[str] = []

    async def run() -> None:
        cases = [
            ({"environ": {}}, "LIVE_CHECK_NOT_ENABLED"),
            ({"policy_path": DEFAULT_POLICY}, "POLICY_UNRESOLVED"),
            ({"environ": {**setup.env, VIDEO_ENV: "not a video"}}, "INVALID_INPUT"),
            ({"environ": {**setup.env, SECRETS_ENV: ""}}, "AUTH_REQUIRED"),
            ({}, "AUTH_REQUIRED"),  # no saved account yet
        ]
        for changes, code in cases:
            report = await setup.check(seen, **changes)
            assert (report.status, report.code) == ("blocked", code)
            assert report.provider_attempts == 0
        assert seen == []
        assert not setup.db.exists()

    anyio.run(run)


def test_read_only_check_succeeds_then_stops_at_fixed_budget(tmp_path: Path) -> None:
    setup = _Setup(tmp_path)

    async def run() -> None:
        await setup.sign_in()
        reports = []
        for _ in range(4):
            seen: list[str] = []
            reports.append((await setup.check(seen), seen))
        for report, seen in reports[:3]:
            assert (report.status, report.code) == ("ok", "OK"), report.message
            assert seen == ["/youtube/v3/channels", "/youtube/v3/videos"]
            assert report.provider_attempts == 2
            assert report.quota["reserved"] == {"general": 6}
            assert report.quota["daily_budget"] == {"general": 10}
            assert report.results == {
                "binding_matches": True,
                "video_id": VIDEO,
                "video_availability": "available",
                "audio_language_evidence": "audio",
            }
            text = json.dumps(report.to_dict())
            assert "ya29" not in text and "Test Channel" not in text
            assert "Public test video" not in text
        refused, seen = reports[3]
        assert (refused.status, refused.code) == ("blocked", "QUOTA_INSUFFICIENT")
        assert refused.provider_attempts == 0 and seen == []

    anyio.run(run)


def test_wrong_channel_is_a_failed_check(tmp_path: Path) -> None:
    setup = _Setup(tmp_path)

    async def run() -> None:
        await setup.sign_in()
        seen: list[str] = []
        report = await setup.check(
            seen, api_transport=_api(seen, channel="UCbbbbbbbbbbbbbbbbbbbbbb")
        )
        assert (report.status, report.code) == ("failed", "ACCOUNT_OR_CONTENT_MISMATCH")
        assert report.results["binding_matches"] is False

    anyio.run(run)


def _revoke(status: int) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/revoke":
            return httpx.Response(status, json={})
        return _oauth(request)

    return httpx.MockTransport(handler)


def test_cli_disconnect_revokes_deletes_and_blocks_the_live_check(
    tmp_path: Path,
) -> None:
    setup = _Setup(tmp_path)

    async def run() -> None:
        await setup.sign_in()
        assert setup.vault.data
        result = await run_cli_disconnect(
            client_secrets_path=setup.secrets,
            vault=setup.vault,
            database_path=setup.db,
            account_state_path=setup.state,
            clock=setup.clock,
            oauth_transport=_revoke(200),
        )
        assert result is not None
        assert (result.revoked, result.tokens_removed, result.local_data_removed) == (
            True,
            True,
            True,
        )
        assert setup.vault.data == {}
        assert not setup.state.exists()
        seen: list[str] = []
        report = await setup.check(seen)
        assert (report.status, report.code) == ("blocked", "AUTH_REQUIRED")
        assert seen == [] and report.provider_attempts == 0
        again = await run_cli_disconnect(
            client_secrets_path=setup.secrets,
            vault=setup.vault,
            database_path=setup.db,
            account_state_path=setup.state,
            clock=setup.clock,
            oauth_transport=_revoke(200),
        )
        assert again is None

    anyio.run(run)


def test_cli_disconnect_reports_failed_revocation_but_still_deletes(
    tmp_path: Path,
) -> None:
    setup = _Setup(tmp_path)

    async def run() -> None:
        await setup.sign_in()
        result = await run_cli_disconnect(
            client_secrets_path=setup.secrets,
            vault=setup.vault,
            database_path=setup.db,
            account_state_path=setup.state,
            clock=setup.clock,
            oauth_transport=_revoke(503),
        )
        assert result is not None
        assert result.revoked is False
        assert result.tokens_removed and result.local_data_removed
        assert [warning.code for warning in result.warnings] == ["PROVIDER_UNAVAILABLE"]
        assert setup.vault.data == {}

    anyio.run(run)
