import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from yt_intel.contracts.common import AccountBinding
from yt_intel.contracts.errors import ContractError
from yt_intel.contracts.workflow import CallCeiling, RequestContext, WorkflowPlan
from yt_intel.infrastructure.database import Database
from yt_intel.infrastructure.http import AccountedHttpExecutor
from yt_intel.infrastructure.quota import QuotaProfile, SqliteQuotaLedger, quota_period

PROFILE_PATH = (
    Path(__file__).resolve().parents[2]
    / "config/quota-profiles/youtube-2026-11-16.json"
)
NOW = datetime(2026, 3, 8, 8, tzinfo=UTC)


class Clock:
    def __init__(self, now=NOW):
        self.current = now

    def now(self):
        return self.current


class Cancellation:
    def is_cancelled(self):
        return False

    async def wait(self):
        await asyncio.Future()


def make_plan(profile):
    return WorkflowPlan(
        plan_id="fixture-plan",
        binding=AccountBinding(
            installation_id="fixture-installation",
            credential_binding_id="fixture-account",
            channel_id="UCfixture000000000000001",
            mode="fixture",
        ),
        project_id="fixture-project",
        quota_profile_id=profile.profile_id,
        endpoint_ceilings={"search.list": CallCeiling(calls=2, attempts_per_call=1)},
        buckets={"search": 2},
        candidate_cap=10,
        page_cap=2,
        sample_cap=0,
        cancellation_policy="stop",
        deadline=NOW + timedelta(minutes=5),
        reconciliation_allowance={},
    )


def test_pacific_reset_uses_dst():
    _, spring_reset = quota_period(NOW)
    assert spring_reset == datetime(2026, 3, 9, 7, tzinfo=UTC)
    _, autumn_reset = quota_period(datetime(2026, 11, 1, 7, tzinfo=UTC))
    assert autumn_reset == datetime(2026, 11, 2, 8, tzinfo=UTC)


@pytest.mark.anyio
async def test_release_after_restart_keeps_spent_units(tmp_path):
    profile = QuotaProfile.load(PROFILE_PATH).model_copy(
        update={"limits": {"search": 2, "general": 10}}
    )
    plan = make_plan(profile)
    path = tmp_path / "quota.sqlite3"
    ledger = SqliteQuotaLedger(Database(path), profile, Clock())
    reservation = await ledger.reserve(plan)
    ctx = RequestContext(
        request_id="fixture-request",
        binding=plan.binding,
        reservation_id=reservation.reservation_id,
        deadline=plan.deadline,
        cancellation=Cancellation(),
    )
    await ledger.debit_attempt(ctx, "search.list", "fixture-attempt")
    restarted = SqliteQuotaLedger(Database(path), profile, Clock())
    with pytest.raises(ContractError, match="already been charged"):
        await restarted.debit_attempt(ctx, "search.list", "fixture-attempt")
    await restarted.release(reservation.reservation_id)
    with pytest.raises(ContractError) as denied:
        await restarted.reserve(plan)
    assert denied.value.detail.code == "QUOTA_INSUFFICIENT"
    smaller = plan.model_copy(
        update={
            "endpoint_ceilings": {
                "search.list": CallCeiling(calls=1, attempts_per_call=1)
            },
            "buckets": {"search": 1},
        }
    )
    assert (await restarted.reserve(smaller)).reserved == {"search": 1}


@pytest.mark.anyio
async def test_concurrent_ledgers_cannot_reserve_same_capacity(tmp_path):
    profile = QuotaProfile.load(PROFILE_PATH).model_copy(
        update={"limits": {"search": 2, "general": 10}}
    )
    plan = make_plan(profile)
    path = tmp_path / "quota.sqlite3"
    ledgers = [SqliteQuotaLedger(Database(path), profile, Clock()) for _ in range(2)]

    def reserve(ledger):
        return asyncio.run(ledger.reserve(plan))

    results = await asyncio.gather(
        *(asyncio.to_thread(reserve, ledger) for ledger in ledgers),
        return_exceptions=True,
    )
    denied = [result for result in results if isinstance(result, ContractError)]
    assert len(denied) == 1
    assert denied[0].detail.code == "QUOTA_INSUFFICIENT"
    assert sum(not isinstance(result, BaseException) for result in results) == 1


@pytest.mark.anyio
@pytest.mark.parametrize("search_limit", [1, 2])
async def test_real_executor_starts_only_after_full_budget_is_reserved(
    tmp_path, search_limit
):
    profile = QuotaProfile.load(PROFILE_PATH).model_copy(
        update={"limits": {"search": search_limit, "general": 10}}
    )
    plan = make_plan(profile).model_copy(
        update={
            "endpoint_ceilings": {
                "videos.list": CallCeiling(calls=1, attempts_per_call=1),
                "search.list": CallCeiling(calls=2, attempts_per_call=1),
            },
            "buckets": {"general": 1, "search": 2},
        }
    )
    database = Database(tmp_path / "quota.sqlite3")
    ledger = SqliteQuotaLedger(database, profile, Clock())
    dispatched = []

    def handler(request):
        with database.transaction(immediate=False) as connection:
            assert (
                connection.execute(
                    "SELECT SUM(spent) FROM quota_reservation_buckets"
                ).fetchone()[0]
                == 1
            )
        dispatched.append(request)
        return httpx.Response(200, json={"items": []})

    async with AccountedHttpExecutor(
        quota_ledger=ledger, transport=httpx.MockTransport(handler), clock=Clock()
    ) as executor:

        async def fetch_seed():
            reservation = await ledger.reserve(plan)
            ctx = RequestContext(
                request_id="fixture-request",
                binding=plan.binding,
                reservation_id=reservation.reservation_id,
                deadline=plan.deadline,
                cancellation=Cancellation(),
            )
            try:
                await executor.execute_youtube(
                    ctx, "videos.list", params={"id": "dQw4w9WgXcQ"}
                )
            finally:
                await ledger.release(reservation.reservation_id)

        if search_limit == 1:
            with pytest.raises(ContractError) as denied:
                await fetch_seed()
            assert denied.value.detail.code == "QUOTA_INSUFFICIENT"
            assert dispatched == []
        else:
            await fetch_seed()
            assert len(dispatched) == 1


@pytest.mark.anyio
async def test_retry_cannot_consume_the_next_logical_calls_budget(tmp_path):
    profile = QuotaProfile.load(PROFILE_PATH)
    plan = make_plan(profile)
    clock = Clock()
    ledger = SqliteQuotaLedger(Database(tmp_path / "quota.sqlite3"), profile, clock)
    reservation = await ledger.reserve(plan)
    ctx = RequestContext(
        request_id="fixture-request",
        binding=plan.binding,
        reservation_id=reservation.reservation_id,
        deadline=plan.deadline,
        cancellation=Cancellation(),
    )
    sent = 0

    def handler(request):
        nonlocal sent
        sent += 1
        return httpx.Response(503 if sent == 1 else 200, json={"items": []})

    async with AccountedHttpExecutor(
        quota_ledger=ledger, transport=httpx.MockTransport(handler), clock=clock
    ) as executor:
        with pytest.raises(ContractError) as failed:
            await executor.execute_youtube(ctx, "search.list", params={"q": "first"})
        assert failed.value.detail.code == "PROVIDER_UNAVAILABLE"
        assert sent == 1
        await executor.execute_youtube(ctx, "search.list", params={"q": "second"})
        assert sent == 2
        with pytest.raises(ContractError, match="Endpoint call budget"):
            await executor.execute_youtube(ctx, "search.list", params={"q": "third"})
        assert sent == 2


@pytest.mark.anyio
async def test_youtube_exhaustion_blocks_existing_and_new_reservations_until_reset(
    tmp_path,
):
    profile = QuotaProfile.load(PROFILE_PATH)
    plan = make_plan(profile).model_copy(
        update={
            "endpoint_ceilings": {
                "search.list": CallCeiling(calls=2, attempts_per_call=1),
                "videos.list": CallCeiling(calls=1, attempts_per_call=1),
            },
            "buckets": {"search": 2, "general": 1},
        }
    )
    clock = Clock()
    path = tmp_path / "quota.sqlite3"
    ledger = SqliteQuotaLedger(Database(path), profile, clock)
    reservation = await ledger.reserve(plan)
    ctx = RequestContext(
        request_id="fixture-request",
        binding=plan.binding,
        reservation_id=reservation.reservation_id,
        deadline=plan.deadline,
        cancellation=Cancellation(),
    )
    sent = []

    def handler(request):
        sent.append(request.url.path)
        if request.url.path.endswith("/search"):
            return httpx.Response(
                403, json={"error": {"errors": [{"reason": "quotaExceeded"}]}}
            )
        return httpx.Response(200, json={"items": []})

    transport = httpx.MockTransport(handler)
    async with AccountedHttpExecutor(
        quota_ledger=ledger, transport=transport, clock=clock
    ) as executor:
        with pytest.raises(ContractError) as upstream:
            await executor.execute_youtube(ctx, "search.list", params={"q": "fixture"})
        assert upstream.value.detail.code == "QUOTA_EXHAUSTED"
    assert len(sent) == 1

    restarted = SqliteQuotaLedger(Database(path), profile, clock)
    async with AccountedHttpExecutor(
        quota_ledger=restarted, transport=transport, clock=clock
    ) as executor:
        with pytest.raises(ContractError) as blocked:
            await executor.execute_youtube(ctx, "search.list", params={"q": "fixture"})
        assert blocked.value.detail.code == "QUOTA_EXHAUSTED"
        assert len(sent) == 1
        await executor.execute_youtube(ctx, "videos.list", params={"id": "dQw4w9WgXcQ"})
        assert len(sent) == 2
    with pytest.raises(ContractError) as preflight:
        await restarted.reserve(plan)
    assert preflight.value.detail.code == "QUOTA_EXHAUSTED"
    clock.current = reservation.reset_at
    tomorrow = plan.model_copy(update={"deadline": clock.now() + timedelta(minutes=5)})
    assert (await restarted.reserve(tomorrow)).reserved == plan.buckets
