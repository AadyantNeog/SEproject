import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from yt_intel.contracts.common import AccountBinding
from yt_intel.contracts.errors import ContractError
from yt_intel.contracts.workflow import CallCeiling, RequestContext, WorkflowPlan
from yt_intel.infrastructure.database import Database
from yt_intel.infrastructure.quota import QuotaProfile, SqliteQuotaLedger, quota_period

PROFILE_PATH = (
    Path(__file__).resolve().parents[2]
    / "config/quota-profiles/youtube-2026-11-16.json"
)
NOW = datetime(2026, 3, 8, 8, tzinfo=UTC)


class Clock:
    def now(self):
        return NOW


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
