from datetime import UTC, datetime, timedelta
from pathlib import Path

import anyio
import httpx
import pytest

from yt_intel.auth.account import AccountRecord, LocalAccountService
from yt_intel.auth.oauth import (
    YOUTUBE_READONLY_SCOPE,
    OAuthClient,
    OAuthClientConfig,
    OAuthTokenSet,
    build_loopback_redirect_uri,
    validate_loopback_redirect_uri,
    verify_oauth_callback,
)
from yt_intel.auth.vault import (
    KeyringTokenVault,
    VaultBackendError,
    verify_protected_keyring_backend,
)
from yt_intel.contracts.account import TokenVault
from yt_intel.contracts.common import OpaqueId
from yt_intel.contracts.errors import ContractError
from yt_intel.contracts.models import LibrarySnapshot
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


class _FixedClock:
    def now(self) -> datetime:
        return NOW


class _FakeLedger:
    async def reserve(self, plan: WorkflowPlan) -> QuotaReservation:
        raise NotImplementedError

    async def debit_attempt(
        self, ctx: RequestContext, endpoint: Endpoint, attempt_id: str
    ) -> None:
        return None

    async def release(self, reservation_id: str) -> None:
        raise NotImplementedError


class _InMemoryTestVault(TokenVault):
    def __init__(self, *, fail_delete: bool = False) -> None:
        self.items: dict[str, bytes] = {}
        self._fail_delete = fail_delete

    async def read(self, reference: OpaqueId) -> bytes | None:
        return self.items.get(reference)

    async def store(self, reference: OpaqueId, sealed_payload: bytes) -> None:
        self.items[reference] = sealed_payload

    async def delete(self, reference: OpaqueId) -> None:
        if self._fail_delete:
            raise RuntimeError("simulated vault delete failure")
        self.items.pop(reference, None)


def test_vault_rejects_plaintext_fail_null_and_untrusted_backends() -> None:
    class PlaintextKeyring:
        __module__ = "keyrings.alt.file"

    class FailKeyring:
        __module__ = "keyring.backends.fail"

    class NullKeyring:
        __module__ = "keyring.backends.null"

    class ChainerBackend:
        __module__ = "keyring.backends.chainer"

        def __init__(self, backends: list[object]) -> None:
            self.backends = backends

    for bad in (
        None,
        PlaintextKeyring(),
        FailKeyring(),
        NullKeyring(),
        ChainerBackend([]),
        ChainerBackend([PlaintextKeyring()]),
    ):
        with pytest.raises(VaultBackendError) as exc:
            verify_protected_keyring_backend(bad)
        assert exc.value.detail.code == "AUTH_REQUIRED"


def test_vault_accepts_verified_windows_backend_and_round_trips_bytes() -> None:
    class WinVaultKeyring:
        __module__ = "keyring.backends.Windows"

        def __init__(self) -> None:
            self.store: dict[tuple[str, str], str] = {}

        def get_password(self, service: str, username: str) -> str | None:
            return self.store.get((service, username))

        def set_password(self, service: str, username: str, password: str) -> None:
            self.store[(service, username)] = password

        def delete_password(self, service: str, username: str) -> None:
            self.store.pop((service, username), None)

    async def _run() -> None:
        backend = WinVaultKeyring()
        vault = KeyringTokenVault(backend=backend)
        await vault.store("ref-1", b"secret-bytes")
        assert await vault.read("ref-1") == b"secret-bytes"
        await vault.delete("ref-1")
        assert await vault.read("ref-1") is None

    anyio.run(_run)


@pytest.mark.parametrize(
    "bad_uri",
    [
        "urn:ietf:wg:oauth:2.0:oob",
        "http://0.0.0.0:8080/oauth2callback",
        "http://localhost:8080/oauth2callback",
        "https://evil.example.com/oauth2callback",
        "http://127.0.0.1:80/oauth2callback",
        "http://127.0.0.1:8080/wrongpath",
        "http://user:pass@127.0.0.1:8080/oauth2callback",
    ],
)
def test_loopback_redirect_uri_rejects_non_loopback_and_oob(bad_uri: str) -> None:
    with pytest.raises(ContractError) as exc:
        validate_loopback_redirect_uri(bad_uri)
    assert exc.value.detail.code == "UNSUPPORTED_IDENTIFIER"


def test_oauth_callback_rejects_mismatched_state_and_redacts_secrets_in_repr() -> None:
    async def _run() -> None:
        async with AccountedHttpExecutor(
            quota_ledger=_FakeLedger(),
            transport=httpx.MockTransport(lambda req: httpx.Response(200, json={})),
            clock=_FixedClock(),
        ) as executor:
            client = OAuthClient(
                OAuthClientConfig(client_id="cid-1", client_secret="GOCSPX-secretval"),
                executor,
                clock=_FixedClock(),
            )
            pending = client.build_authorization_request(
                scopes=(YOUTUBE_READONLY_SCOPE,),
                redirect_uri=build_loopback_redirect_uri(54321),
            )
            assert "GOCSPX-secretval" not in repr(client._config)
            assert pending.code_verifier not in repr(pending)
            assert pending.state not in repr(pending)

            with pytest.raises(ContractError) as state_err:
                verify_oauth_callback(
                    pending, {"state": "wrong-state", "code": "auth-code"}
                )
            assert state_err.value.detail.code == "AUTH_REQUIRED"

            with pytest.raises(ContractError) as denied_err:
                verify_oauth_callback(pending, {"error": "access_denied"})
            assert denied_err.value.detail.code == "SCOPE_REQUIRED"

            tokens = OAuthTokenSet(
                access_token="ya29.supersecretaccess",
                refresh_token="1//supersecretrefresh",
                expires_at=NOW + timedelta(hours=1),
                granted_scopes=(YOUTUBE_READONLY_SCOPE,),
            )
            assert "ya29.supersecretaccess" not in repr(tokens)
            assert "1//supersecretrefresh" not in repr(tokens)

    anyio.run(_run)


def test_account_isolation_and_partial_disconnect_failure_reporting(
    tmp_path: Path,
) -> None:
    async def _run() -> None:
        db = Database(tmp_path / "runtime.sqlite3")
        db.migrate()
        account_repo = SqliteAccountDataRepository(db, clock=_FixedClock())
        snapshot_repo = SqliteSnapshotRepository(db, clock=_FixedClock())

        snapshot = LibrarySnapshot.model_validate_json(FIXTURE_SNAPSHOT.read_bytes())
        active_binding = snapshot.binding
        foreign_binding = active_binding.model_copy(
            update={"credential_binding_id": "foreign-cred"}
        )
        await snapshot_repo.save_snapshot(snapshot)

        vault = _InMemoryTestVault(fail_delete=True)
        vault_ref = (
            f"yt-intel-{active_binding.mode}-{active_binding.credential_binding_id}"
        )
        tokens = OAuthTokenSet(
            access_token="ya29.active_token",
            refresh_token="1//active_refresh",
            expires_at=NOW + timedelta(hours=1),
            granted_scopes=(YOUTUBE_READONLY_SCOPE,),
        )
        await vault.store(vault_ref, tokens.to_vault_bytes())

        async with AccountedHttpExecutor(
            quota_ledger=_FakeLedger(),
            transport=httpx.MockTransport(lambda req: httpx.Response(503, json={})),
            clock=_FixedClock(),
        ) as executor:
            oauth = OAuthClient(
                OAuthClientConfig(client_id="cid-1"), executor, clock=_FixedClock()
            )
            service = LocalAccountService(
                installation_id=active_binding.installation_id,
                mode=active_binding.mode,
                vault=vault,
                oauth_client=oauth,
                account_data=account_repo,
                clock=_FixedClock(),
                initial_record=AccountRecord(
                    binding=active_binding,
                    channel_title="Fixture Channel",
                    vault_reference=vault_ref,
                    granted_scopes=(YOUTUBE_READONLY_SCOPE,),
                ),
            )

            # Foreign binding cannot read auth headers or disconnect the active account
            with pytest.raises(ContractError) as hdr_err:
                await service.get_headers(foreign_binding)
            assert hdr_err.value.detail.code == "ACCOUNT_MISMATCH"

            with pytest.raises(ContractError) as disc_err:
                await service.disconnect(foreign_binding)
            assert disc_err.value.detail.code == "ACCOUNT_MISMATCH"

            # Disconnect reports failed revocation and failed vault deletion honestly
            result = await service.disconnect(active_binding)
            assert result.revoked is False
            assert result.tokens_removed is False
            assert result.local_data_removed is True
            assert any(w.code == "LOCAL_DELETION_FAILED" for w in result.warnings)
            # Even after partial cleanup failure, further access remains blocked
            assert await service.current() is None
            with pytest.raises(ContractError) as blocked_req:
                await service.require_binding()
            assert blocked_req.value.detail.code == "AUTH_REQUIRED"
            with pytest.raises(ContractError) as blocked_hdr:
                await service.get_headers(active_binding)
            assert blocked_hdr.value.detail.code == "AUTH_REQUIRED"
            # SQLite snapshot for active_binding was deleted by Paul's repository
            assert (
                await snapshot_repo.get_snapshot(
                    active_binding, snapshot.snapshot_id, now=NOW
                )
                is None
            )

    anyio.run(_run)
