from datetime import UTC, datetime, timedelta

import anyio
import httpx
import pytest

from yt_intel.contracts.approval import ApprovedWriteContext
from yt_intel.contracts.common import AccountBinding
from yt_intel.contracts.errors import ContractError
from yt_intel.contracts.proposals import ProposalRef
from yt_intel.contracts.workflow import (
    Endpoint,
    QuotaReservation,
    RequestContext,
    WorkflowPlan,
)
from yt_intel.infrastructure.http import (
    AccountedHttpExecutor,
    AttemptRecord,
    compute_write_request_digest,
    validate_allowlisted_url,
)
from yt_intel.infrastructure.redaction import (
    REDACTED,
    redact_headers,
    redact_mapping,
    redact_text,
    redact_url,
)


class _NeverCancelled:
    def is_cancelled(self) -> bool:
        return False

    async def wait(self) -> None:
        await anyio.sleep_forever()


class _FakeClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class _RecordingLedger:
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


def _binding() -> AccountBinding:
    return AccountBinding(
        installation_id="inst-1",
        credential_binding_id="cred-1",
        channel_id="UC_x5XG1OV2P6uZZ5FSM9Ttw",
        mode="fixture",
    )


def _ctx(now: datetime) -> RequestContext:
    return RequestContext(
        request_id="req-sec-1",
        binding=_binding(),
        reservation_id="res-sec-1",
        deadline=now + timedelta(seconds=60),
        cancellation=_NeverCancelled(),
    )


@pytest.mark.parametrize(
    ("url", "method"),
    [
        ("https://www.googleapis.com/youtube/v3/videos", "GET"),
        ("https://www.googleapis.com/youtube/v3/channels", "GET"),
        ("https://www.googleapis.com/youtube/v3/search", "GET"),
        ("https://www.googleapis.com/youtube/v3/subscriptions", "GET"),
        ("https://www.googleapis.com/youtube/v3/playlists", "GET"),
        ("https://www.googleapis.com/youtube/v3/playlistItems", "GET"),
        ("https://www.googleapis.com/youtube/v3/videoCategories", "GET"),
        ("https://www.googleapis.com/youtube/v3/playlists", "POST"),
        ("https://www.googleapis.com/youtube/v3/playlistItems", "POST"),
        ("https://oauth2.googleapis.com/token", "POST"),
        ("https://oauth2.googleapis.com/revoke", "POST"),
    ],
)
def test_allowlist_accepts_official_routes(url: str, method: str) -> None:
    parsed = validate_allowlisted_url(url, method)
    assert parsed.scheme == "https"


@pytest.mark.parametrize(
    ("url", "method"),
    [
        ("http://www.googleapis.com/youtube/v3/videos", "GET"),
        ("https://example.com/youtube/v3/videos", "GET"),
        ("https://www.googleapis.com.evil.com/youtube/v3/videos", "GET"),
        ("https://user:pass@www.googleapis.com/youtube/v3/videos", "GET"),
        ("https://www.googleapis.com:8443/youtube/v3/videos", "GET"),
        ("https://www.googleapis.com/youtube/v3/videos", "POST"),
        ("https://www.googleapis.com/youtube/v3/playlists", "DELETE"),
        ("https://www.googleapis.com/youtube/v3/comments", "GET"),
        ("https://www.googleapis.com/oauth2/v2/userinfo", "GET"),
        ("https://oauth2.googleapis.com/token", "GET"),
    ],
)
def test_allowlist_rejects_disallowed_destinations(url: str, method: str) -> None:
    with pytest.raises(ContractError) as exc:
        validate_allowlisted_url(url, method)
    assert exc.value.detail.code == "UNSUPPORTED_IDENTIFIER"


def test_redaction_strips_tokens_headers_and_query_secrets() -> None:
    secret_access = "ya29.a0AfH6SM_secret_token_value"
    secret_refresh = "1//0g_refresh_secret_value"
    secret_key = "demo-k"
    secret_client = "GOCSPX-supersecretclient"

    raw = (
        f"Authorization: Bearer {secret_access}\n"
        f"refresh={secret_refresh} key={secret_key} client={secret_client}"
    )
    cleaned = redact_text(raw)
    for secret in (secret_access, secret_refresh, secret_key, secret_client):
        assert secret not in cleaned
    assert REDACTED in cleaned

    safe_url = redact_url(
        f"https://user:pw@www.googleapis.com/youtube/v3/videos?id=abc&key={secret_key}&access_token={secret_access}"
    )
    assert "user:pw" not in safe_url
    assert secret_key not in safe_url
    assert secret_access not in safe_url
    assert "id=abc" in safe_url

    safe_headers = redact_headers(
        {
            "Authorization": f"Bearer {secret_access}",
            "X-Goog-Api-Key": secret_key,
            "Accept": "application/json",
        }
    )
    assert safe_headers["Authorization"] == REDACTED
    assert safe_headers["X-Goog-Api-Key"] == REDACTED
    assert safe_headers["Accept"] == "application/json"

    safe_map = redact_mapping(
        {
            "access_token": secret_access,
            "nested": {"client_secret": secret_client, "ok": "v"},
        }
    )
    assert safe_map["access_token"] == REDACTED
    assert safe_map["nested"] == {"client_secret": REDACTED, "ok": "v"}


def test_redirects_fail_closed_without_following_or_retrying() -> None:
    async def _run() -> None:
        now = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)
        ledger = _RecordingLedger()
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(
                302, headers={"Location": "https://evil.example.com/steal"}
            )

        async with AccountedHttpExecutor(
            quota_ledger=ledger,
            transport=httpx.MockTransport(handler),
            clock=_FakeClock(now),
        ) as executor:
            with pytest.raises(ContractError) as exc:
                await executor.execute_youtube(
                    _ctx(now), "videos.list", params={"id": "dQw4w9WgXcQ"}
                )
            assert exc.value.detail.code == "PROVIDER_UNAVAILABLE"
            assert exc.value.detail.retryable is False
            assert calls == 1
            assert len(ledger.debits) == 1

    anyio.run(_run)


def test_write_requests_require_exact_bound_authority_before_debit_or_dispatch() -> (
    None
):
    async def _run() -> None:
        now = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)
        ctx = _ctx(now)
        ledger = _RecordingLedger()
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json={"id": "PL123"})

        body: dict[str, object] = {
            "snippet": {"title": "Study"},
            "status": {"privacyStatus": "private"},
        }
        params = {"part": "snippet,status"}
        good_digest = compute_write_request_digest(
            "playlists.insert", params=params, json_body=body
        )

        async with AccountedHttpExecutor(
            quota_ledger=ledger,
            transport=httpx.MockTransport(handler),
            clock=_FakeClock(now),
        ) as executor:
            # 1. Missing authority
            with pytest.raises(ContractError) as exc:
                await executor.execute_youtube(
                    ctx, "playlists.insert", params=params, json_body=body
                )
            assert exc.value.detail.code == "APPROVAL_REQUIRED"

            # 2. Wrong account binding
            wrong_account = ApprovedWriteContext(
                operation_id="op-1",
                reservation_id=ctx.reservation_id,
                binding=ctx.binding.model_copy(
                    update={"credential_binding_id": "cred-other"}
                ),
                proposal=ProposalRef(proposal_id="prop-1", version=1),
                proposal_digest="a" * 64,
                request_digest=good_digest,
            )
            with pytest.raises(ContractError) as exc:
                await executor.execute_youtube(
                    ctx,
                    "playlists.insert",
                    params=params,
                    json_body=body,
                    authority=wrong_account,
                )
            assert exc.value.detail.code == "ACCOUNT_MISMATCH"

            # 3. Tampered payload digest
            tampered_auth = ApprovedWriteContext(
                operation_id="op-1",
                reservation_id=ctx.reservation_id,
                binding=ctx.binding,
                proposal=ProposalRef(proposal_id="prop-1", version=1),
                proposal_digest="a" * 64,
                request_digest=good_digest,
            )
            tampered_body = {
                "snippet": {"title": "Tampered"},
                "status": {"privacyStatus": "public"},
            }
            with pytest.raises(ContractError) as exc:
                await executor.execute_youtube(
                    ctx,
                    "playlists.insert",
                    params=params,
                    json_body=tampered_body,
                    authority=tampered_auth,
                )
            assert exc.value.detail.code == "PROPOSAL_CHANGED"

            assert calls == 0
            assert ledger.debits == []

    anyio.run(_run)


def test_auth_headers_are_injected_internally_and_never_leaked() -> None:
    async def _run() -> None:
        now = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)
        secret_token = "ya29.internal_secret_bearer_token"
        seen_auth_header: list[str] = []
        records: list[AttemptRecord] = []

        class _AuthProvider:
            async def get_headers(self, binding: AccountBinding) -> dict[str, str]:
                return {"Authorization": f"Bearer {secret_token}"}

        def handler(request: httpx.Request) -> httpx.Response:
            seen_auth_header.append(request.headers.get("Authorization", ""))
            return httpx.Response(200, json={"items": []})

        async with AccountedHttpExecutor(
            quota_ledger=_RecordingLedger(),
            auth_headers=_AuthProvider(),
            transport=httpx.MockTransport(handler),
            clock=_FakeClock(now),
            on_attempt=records.append,
        ) as executor:
            result = await executor.execute_youtube(
                _ctx(now), "videos.list", params={"id": "dQw4w9WgXcQ"}
            )
            assert seen_auth_header == [f"Bearer {secret_token}"]
            assert secret_token not in repr(result)
            assert secret_token not in repr(records)

    anyio.run(_run)
