from datetime import UTC, datetime, timedelta

import anyio
import httpx
import pytest

from yt_intel.contracts.approval import ApprovedWriteContext
from yt_intel.contracts.common import AccountBinding
from yt_intel.contracts.errors import ContractError, ErrorDetail
from yt_intel.contracts.proposals import ProposalRef
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


class _ControllableCancellation:
    def __init__(self, *, initially_cancelled: bool = False) -> None:
        self._event = anyio.Event()
        if initially_cancelled:
            self._event.set()

    def cancel(self) -> None:
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()

    async def wait(self) -> None:
        await self._event.wait()


class _MutableClock:
    def __init__(self, now: datetime) -> None:
        self.current = now

    def now(self) -> datetime:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current = self.current + timedelta(seconds=seconds)


class _FakeQuotaLedger:
    def __init__(
        self,
        *,
        fail_after: int | None = None,
        events: list[str] | None = None,
    ) -> None:
        self.debits: list[tuple[Endpoint, str]] = []
        self._fail_after = fail_after
        self._events = events

    async def reserve(self, plan: WorkflowPlan) -> QuotaReservation:
        raise NotImplementedError

    async def debit_attempt(
        self, ctx: RequestContext, endpoint: Endpoint, attempt_id: str
    ) -> None:
        if self._fail_after is not None and len(self.debits) >= self._fail_after:
            raise ContractError(
                ErrorDetail(
                    code="QUOTA_INSUFFICIENT",
                    message="Insufficient quota balance for attempt.",
                    retryable=False,
                    safe_next_action="Wait for quota reset.",
                )
            )
        self.debits.append((endpoint, attempt_id))
        if self._events is not None:
            self._events.append(f"debit:{endpoint}:{attempt_id}")

    async def release(self, reservation_id: str) -> None:
        raise NotImplementedError


def _make_ctx(
    now: datetime,
    *,
    deadline_seconds: float = 60.0,
    cancellation: _ControllableCancellation | None = None,
) -> RequestContext:
    return RequestContext(
        request_id="req-int-1",
        binding=AccountBinding(
            installation_id="inst-1",
            credential_binding_id="cred-1",
            channel_id="UC_x5XG1OV2P6uZZ5FSM9Ttw",
            mode="fixture",
        ),
        reservation_id="res-int-1",
        deadline=now + timedelta(seconds=deadline_seconds),
        cancellation=cancellation or _ControllableCancellation(),
    )


def test_debit_occurs_before_dispatch_and_blocks_on_insufficient_quota() -> None:
    async def _run() -> None:
        now = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)
        events: list[str] = []
        ledger = _FakeQuotaLedger(events=events)

        def handler(request: httpx.Request) -> httpx.Response:
            events.append("http_dispatch")
            return httpx.Response(200, json={"items": []})

        async with AccountedHttpExecutor(
            quota_ledger=ledger,
            transport=httpx.MockTransport(handler),
            clock=_MutableClock(now),
            attempt_id_factory=lambda: "att-1",
        ) as executor:
            resp = await executor.execute_youtube(
                _make_ctx(now), "videos.list", params={"id": "dQw4w9WgXcQ"}
            )
            assert resp.status_code == 200
            assert events == ["debit:videos.list:att-1", "http_dispatch"]

        # When ledger refuses debit, zero HTTP calls are made.
        zero_budget_ledger = _FakeQuotaLedger(fail_after=0)
        called = False

        def blocked_handler(request: httpx.Request) -> httpx.Response:
            nonlocal called
            called = True
            return httpx.Response(200, json={})

        async with AccountedHttpExecutor(
            quota_ledger=zero_budget_ledger,
            transport=httpx.MockTransport(blocked_handler),
            clock=_MutableClock(now),
        ) as executor:
            with pytest.raises(ContractError) as exc:
                await executor.execute_youtube(_make_ctx(now), "videos.list")
            assert exc.value.detail.code == "QUOTA_INSUFFICIENT"
            assert called is False

    anyio.run(_run)


def test_safe_read_retries_succeed_within_three_attempts_and_honour_retry_after() -> (
    None
):
    async def _run() -> None:
        now = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)
        clock = _MutableClock(now)
        ledger = _FakeQuotaLedger()
        sleeps: list[float] = []

        async def fake_sleep(delay: float) -> None:
            sleeps.append(delay)
            clock.advance(delay)

        responses = iter(
            [
                httpx.Response(429, headers={"Retry-After": "2"}, json={}),
                httpx.Response(503, json={}),
                httpx.Response(200, json={"items": [{"id": "dQw4w9WgXcQ"}]}),
            ]
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return next(responses)

        async with AccountedHttpExecutor(
            quota_ledger=ledger,
            transport=httpx.MockTransport(handler),
            clock=clock,
            sleep=fake_sleep,
            jitter=lambda: 1.0,
            base_backoff_seconds=0.5,
            max_backoff_seconds=5.0,
        ) as executor:
            resp = await executor.execute_youtube(
                _make_ctx(now), "videos.list", params={"id": "dQw4w9WgXcQ"}
            )
            assert resp.attempts == 3
            assert resp.payload == {"items": [{"id": "dQw4w9WgXcQ"}]}
            assert len(ledger.debits) == 3
            assert sleeps == [2.0, 1.0]

    anyio.run(_run)


def test_read_timeout_retries_at_most_three_times_then_fails() -> None:
    async def _run() -> None:
        now = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)
        clock = _MutableClock(now)
        ledger = _FakeQuotaLedger()
        attempts = 0

        async def fake_sleep(delay: float) -> None:
            clock.advance(delay)

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            raise httpx.ReadTimeout("simulated timeout", request=request)

        async with AccountedHttpExecutor(
            quota_ledger=ledger,
            transport=httpx.MockTransport(handler),
            clock=clock,
            sleep=fake_sleep,
            jitter=lambda: 0.5,
        ) as executor:
            with pytest.raises(ContractError) as exc:
                await executor.execute_youtube(_make_ctx(now), "search.list")
            assert exc.value.detail.code == "WORKFLOW_TIMEOUT"
            assert attempts == 3
            assert len(ledger.debits) == 3

    anyio.run(_run)


@pytest.mark.parametrize(
    ("status_code", "body", "expected_code"),
    [
        (
            403,
            {"error": {"errors": [{"reason": "quotaExceeded"}]}},
            "QUOTA_EXHAUSTED",
        ),
        (
            403,
            {"error": {"errors": [{"reason": "youtubeSignupRequired"}]}},
            "CHANNEL_REQUIRED",
        ),
        (
            403,
            {"error": {"errors": [{"reason": "insufficientPermissions"}]}},
            "SCOPE_REQUIRED",
        ),
        (401, {"error": {"message": "Invalid Credentials"}}, "AUTH_REVOKED"),
        (404, {"error": {"message": "Not Found"}}, "CONTENT_UNAVAILABLE"),
        (400, {"error": {"message": "Bad Request"}}, "INVALID_INPUT"),
    ],
)
def test_non_retryable_read_errors_do_not_retry(
    status_code: int, body: dict[str, object], expected_code: str
) -> None:
    async def _run() -> None:
        now = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)
        ledger = _FakeQuotaLedger()
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(status_code, json=body)

        async with AccountedHttpExecutor(
            quota_ledger=ledger,
            transport=httpx.MockTransport(handler),
            clock=_MutableClock(now),
        ) as executor:
            with pytest.raises(ContractError) as exc:
                await executor.execute_youtube(_make_ctx(now), "videos.list")
            assert exc.value.detail.code == expected_code
            assert exc.value.detail.retryable is False
            assert calls == 1
            assert len(ledger.debits) == 1

    anyio.run(_run)


def test_writes_never_retry_and_timeout_returns_operation_unknown() -> None:
    async def _run() -> None:
        now = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)
        ctx = _make_ctx(now)
        params = {"part": "snippet,status"}
        body: dict[str, object] = {
            "snippet": {"title": "Study"},
            "status": {"privacyStatus": "private"},
        }
        authority = ApprovedWriteContext(
            operation_id="op-write-1",
            reservation_id=ctx.reservation_id,
            binding=ctx.binding,
            proposal=ProposalRef(proposal_id="prop-1", version=1),
            proposal_digest="b" * 64,
            request_digest=compute_write_request_digest(
                "playlists.insert", params=params, json_body=body
            ),
        )

        # Case 1: Timeout after dispatch -> OPERATION_UNKNOWN, 1 attempt only.
        ledger_timeout = _FakeQuotaLedger()
        calls = 0

        def timeout_handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            raise httpx.ReadTimeout("write timed out", request=request)

        async with AccountedHttpExecutor(
            quota_ledger=ledger_timeout,
            transport=httpx.MockTransport(timeout_handler),
            clock=_MutableClock(now),
        ) as executor:
            with pytest.raises(ContractError) as exc:
                await executor.execute_youtube(
                    ctx,
                    "playlists.insert",
                    params=params,
                    json_body=body,
                    authority=authority,
                )
            assert exc.value.detail.code == "OPERATION_UNKNOWN"
            assert exc.value.detail.retryable is False
            assert calls == 1
            assert len(ledger_timeout.debits) == 1

        # Case 2: 503 on write -> PROVIDER_UNAVAILABLE, retryable=False, 1 attempt only.
        ledger_503 = _FakeQuotaLedger()
        calls_503 = 0

        def err_handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls_503
            calls_503 += 1
            return httpx.Response(503, json={})

        async with AccountedHttpExecutor(
            quota_ledger=ledger_503,
            transport=httpx.MockTransport(err_handler),
            clock=_MutableClock(now),
        ) as executor:
            with pytest.raises(ContractError) as exc:
                await executor.execute_youtube(
                    ctx,
                    "playlists.insert",
                    params=params,
                    json_body=body,
                    authority=authority,
                )
            assert exc.value.detail.code == "PROVIDER_UNAVAILABLE"
            assert exc.value.detail.retryable is False
            assert calls_503 == 1
            assert len(ledger_503.debits) == 1

    anyio.run(_run)


def test_expired_deadline_and_precancellation_perform_zero_debits_or_calls() -> None:
    async def _run() -> None:
        now = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)
        ledger = _FakeQuotaLedger()
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json={})

        async with AccountedHttpExecutor(
            quota_ledger=ledger,
            transport=httpx.MockTransport(handler),
            clock=_MutableClock(now),
        ) as executor:
            with pytest.raises(ContractError) as exc:
                await executor.execute_youtube(
                    _make_ctx(now, deadline_seconds=0), "videos.list"
                )
            assert exc.value.detail.code == "WORKFLOW_TIMEOUT"

            cancelled = _ControllableCancellation(initially_cancelled=True)
            with pytest.raises(ContractError) as exc:
                await executor.execute_youtube(
                    _make_ctx(now, cancellation=cancelled), "videos.list"
                )
            assert exc.value.detail.code == "WORKFLOW_TIMEOUT"

            assert calls == 0
            assert ledger.debits == []

    anyio.run(_run)


def test_oauth_requests_use_allowlist_without_touching_youtube_quota() -> None:
    async def _run() -> None:
        now = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)
        ledger = _FakeQuotaLedger()

        def handler(request: httpx.Request) -> httpx.Response:
            assert str(request.url) == "https://oauth2.googleapis.com/token"
            return httpx.Response(
                200, json={"token_type": "Bearer", "expires_in": 3600}
            )

        async with AccountedHttpExecutor(
            quota_ledger=ledger,
            transport=httpx.MockTransport(handler),
            clock=_MutableClock(now),
        ) as executor:
            resp = await executor.execute_oauth(
                "oauth.token",
                form_data={"grant_type": "refresh_token", "refresh_token": "1//secret"},
                deadline=now + timedelta(seconds=30),
                cancellation=_ControllableCancellation(),
            )
            assert resp.status_code == 200
            assert resp.payload["token_type"] == "Bearer"
            assert ledger.debits == []

    anyio.run(_run)
