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

        # Case 2: 5xx / redirect / malformed 2xx on write -> OPERATION_UNKNOWN (must reconcile), 1 attempt only.
        for bad_response in (
            httpx.Response(500, json={}),
            httpx.Response(502, json={}),
            httpx.Response(503, json={}),
            httpx.Response(504, json={}),
            httpx.Response(302, headers={"Location": "https://evil.example.com/"}),
            httpx.Response(200, content=b"not-valid-json"),
            httpx.Response(200, json=["unexpected-list"]),
        ):
            ledger_unclear = _FakeQuotaLedger()
            calls_unclear = 0

            def unclear_handler(
                request: httpx.Request, resp: httpx.Response = bad_response
            ) -> httpx.Response:
                nonlocal calls_unclear
                calls_unclear += 1
                return resp

            async with AccountedHttpExecutor(
                quota_ledger=ledger_unclear,
                transport=httpx.MockTransport(unclear_handler),
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
                assert "reconcil" in exc.value.detail.safe_next_action.casefold()
                assert calls_unclear == 1
                assert len(ledger_unclear.debits) == 1

        # Case 3: Network drop on write -> OPERATION_UNKNOWN (must reconcile), 1 attempt only.
        ledger_net = _FakeQuotaLedger()
        calls_net = 0

        def net_err_handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls_net
            calls_net += 1
            raise httpx.ConnectError("connection reset", request=request)

        async with AccountedHttpExecutor(
            quota_ledger=ledger_net,
            transport=httpx.MockTransport(net_err_handler),
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
            assert "reconcil" in exc.value.detail.safe_next_action.casefold()
            assert calls_net == 1
            assert len(ledger_net.debits) == 1

    anyio.run(_run)


def test_request_cannot_start_when_deadline_expires_during_auth_or_debit() -> None:
    async def _run() -> None:
        now = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)

        # Case 1: Deadline expires while resolving auth headers -> 0 debits, 0 HTTP calls.
        clock_auth = _MutableClock(now)
        ledger_auth = _FakeQuotaLedger()
        calls_auth = 0

        class _SlowAuth:
            async def get_headers(self, binding: AccountBinding) -> dict[str, str]:
                clock_auth.advance(65.0)
                return {"Authorization": "Bearer ya29.test"}

        def handler_auth(request: httpx.Request) -> httpx.Response:
            nonlocal calls_auth
            calls_auth += 1
            return httpx.Response(200, json={"items": []})

        async with AccountedHttpExecutor(
            quota_ledger=ledger_auth,
            auth_headers=_SlowAuth(),
            transport=httpx.MockTransport(handler_auth),
            clock=clock_auth,
        ) as executor:
            with pytest.raises(ContractError) as exc:
                await executor.execute_youtube(
                    _make_ctx(now, deadline_seconds=60.0), "videos.list"
                )
            assert exc.value.detail.code == "WORKFLOW_TIMEOUT"
            assert ledger_auth.debits == []
            assert calls_auth == 0

        # Case 2: Deadline expires during debit_attempt -> 0 HTTP calls.
        clock_debit = _MutableClock(now)
        calls_debit = 0

        class _SlowLedger(_FakeQuotaLedger):
            async def debit_attempt(
                self, ctx: RequestContext, endpoint: Endpoint, attempt_id: str
            ) -> None:
                await super().debit_attempt(ctx, endpoint, attempt_id)
                clock_debit.advance(65.0)

        ledger_debit = _SlowLedger()

        def handler_debit(request: httpx.Request) -> httpx.Response:
            nonlocal calls_debit
            calls_debit += 1
            return httpx.Response(200, json={"items": []})

        async with AccountedHttpExecutor(
            quota_ledger=ledger_debit,
            transport=httpx.MockTransport(handler_debit),
            clock=clock_debit,
        ) as executor:
            with pytest.raises(ContractError) as exc:
                await executor.execute_youtube(
                    _make_ctx(now, deadline_seconds=60.0), "videos.list"
                )
            assert exc.value.detail.code == "WORKFLOW_TIMEOUT"
            assert len(ledger_debit.debits) == 1
            assert calls_debit == 0

    anyio.run(_run)


def test_write_wire_payload_is_frozen_and_matches_approved_digest() -> None:
    async def _run() -> None:
        now = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)
        ctx = _make_ctx(now)
        params: dict[str, str] = {"part": "snippet,status"}
        body: dict[str, object] = {
            "snippet": {"title": "Approved Study"},
            "status": {"privacyStatus": "private"},
        }
        approved_digest = compute_write_request_digest(
            "playlists.insert", params=params, json_body=body
        )
        authority = ApprovedWriteContext(
            operation_id="op-freeze-1",
            reservation_id=ctx.reservation_id,
            binding=ctx.binding,
            proposal=ProposalRef(proposal_id="prop-1", version=1),
            proposal_digest="c" * 64,
            request_digest=approved_digest,
        )

        # Mutate caller-owned params and body during async auth lookup to ensure
        # the executor sends only the exact frozen approved payload.
        class _MutatingAuth:
            async def get_headers(self, binding: AccountBinding) -> dict[str, str]:
                params["part"] = "tampered"
                body["status"] = {"privacyStatus": "public"}
                return {
                    "Authorization": "Bearer ya29.approved",
                    "Content-Type": "text/plain",
                }

        captured: list[tuple[dict[str, str], bytes, str]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(
                (
                    dict(request.url.params.multi_items()),
                    request.content,
                    request.headers.get("Content-Type", ""),
                )
            )
            return httpx.Response(200, json={"id": "PL-approved"})

        async with AccountedHttpExecutor(
            quota_ledger=_FakeQuotaLedger(),
            auth_headers=_MutatingAuth(),
            transport=httpx.MockTransport(handler),
            clock=_MutableClock(now),
        ) as executor:
            resp = await executor.execute_youtube(
                ctx,
                "playlists.insert",
                params=params,
                json_body=body,
                authority=authority,
            )
            assert resp.status_code == 200
            assert len(captured) == 1
            sent_params, sent_bytes, sent_ct = captured[0]
            assert sent_params == {"part": "snippet,status"}
            assert sent_ct == "application/json"
            assert (
                sent_bytes
                == b'{"snippet":{"title":"Approved Study"},"status":{"privacyStatus":"private"}}'
            )

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
