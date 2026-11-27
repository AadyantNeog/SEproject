from datetime import UTC, date, datetime, time, timedelta
from hashlib import sha256
from json import dumps
from pathlib import Path
from secrets import token_urlsafe
from sqlite3 import Connection
from typing import Self
from zoneinfo import ZoneInfo

from pydantic import field_serializer, model_validator

from yt_intel.contracts.common import Contract, FrozenMap, Label, OpaqueId, Positive
from yt_intel.contracts.errors import ContractError, ErrorCode, ErrorDetail
from yt_intel.contracts.workflow import (
    BucketVector,
    Clock,
    Endpoint,
    QuotaReservation,
    RequestContext,
    WorkflowPlan,
)
from yt_intel.infrastructure.clock import SystemClock
from yt_intel.infrastructure.database import Database
from yt_intel.infrastructure.repositories import _binding_key, _ensure_account

_PACIFIC = ZoneInfo("America/Los_Angeles")


class QuotaProfile(Contract):
    profile_id: OpaqueId
    reference_date: date
    reference_url: Label
    limits: FrozenMap[OpaqueId, Positive]
    costs: FrozenMap[Endpoint, FrozenMap[OpaqueId, Positive]]

    @field_serializer("costs")
    def serialize_costs(
        self, costs: FrozenMap[Endpoint, FrozenMap[OpaqueId, Positive]]
    ) -> dict[Endpoint, dict[OpaqueId, Positive]]:
        return {endpoint: dict(buckets) for endpoint, buckets in costs.items()}

    @model_validator(mode="after")
    def validate_cost_buckets(self) -> Self:
        if not self.limits or not self.costs:
            raise ValueError("quota profiles require limits and endpoint costs")
        if any(
            not cost or cost.keys() - self.limits.keys() for cost in self.costs.values()
        ):
            raise ValueError("every endpoint cost must use configured buckets")
        return self

    @classmethod
    def load(cls, path: Path) -> Self:
        return cls.model_validate_json(path.read_bytes())

    def required_buckets(self, plan: WorkflowPlan) -> BucketVector:
        """Calculate the worst case from endpoint ceilings, including recovery reads."""
        if plan.quota_profile_id != self.profile_id:
            raise ValueError("workflow plan uses a different quota profile")
        if plan.reconciliation_allowance.keys() - plan.endpoint_ceilings.keys():
            raise ValueError("reconciliation endpoints require a call ceiling")
        if plan.endpoint_ceilings.keys() - self.costs.keys():
            raise ValueError("workflow endpoint has no configured quota cost")
        required: dict[str, int] = {}
        for endpoint, ceiling in plan.endpoint_ceilings.items():
            calls = ceiling.calls + plan.reconciliation_allowance.get(endpoint, 0)
            for bucket, units in self.costs[endpoint].items():
                required[bucket] = required.get(bucket, 0) + (
                    calls * ceiling.attempts_per_call * units
                )
        return required


def quota_period(now: datetime) -> tuple[date, datetime]:
    """Return the Pacific quota date and the next Pacific midnight in UTC."""
    if now.utcoffset() is None:
        raise ValueError("quota accounting requires an aware timestamp")
    day = now.astimezone(_PACIFIC).date()
    reset = datetime.combine(day + timedelta(days=1), time.min, tzinfo=_PACIFIC)
    return day, reset.astimezone(UTC)


def _blocked(code: ErrorCode, message: str) -> ContractError:
    return ContractError(
        ErrorDetail(
            code=code,
            message=message,
            retryable=False,
            safe_next_action="Start a new workflow with a current quota plan.",
        )
    )


def _require_available_buckets(
    connection: Connection, project: str, day: str, buckets: BucketVector
) -> None:
    exhausted = connection.execute(
        "SELECT bucket FROM quota_exhausted_buckets WHERE project_id = ? AND quota_day = ?",
        (project, day),
    )
    if any(row["bucket"] in buckets for row in exhausted):
        raise _blocked(
            "QUOTA_EXHAUSTED", "YouTube reported quota exhaustion for this bucket."
        )


class SqliteQuotaLedger:
    """Persist debits before dispatch and release only unused capacity."""

    def __init__(
        self, database: Database, profile: QuotaProfile, clock: Clock | None = None
    ) -> None:
        self._database = database
        self._profile = profile
        self._clock = clock or SystemClock()
        encoded = dumps(profile.model_dump(mode="json"), sort_keys=True).encode()
        self._profile_digest = sha256(encoded).hexdigest()

    async def reserve(self, plan: WorkflowPlan) -> QuotaReservation:
        try:
            required = self._profile.required_buckets(plan)
        except ValueError as error:
            raise _blocked("INVALID_INPUT", str(error)) from error
        if not required or required != plan.buckets:
            raise _blocked(
                "INVALID_INPUT", "Workflow quota must match its endpoint ceilings."
            )
        reservation_id = token_urlsafe(24)
        with self._database.transaction() as connection:
            now = self._clock.now().astimezone(UTC)
            day, reset = quota_period(now)
            _require_available_buckets(
                connection, plan.project_id, day.isoformat(), required
            )
            if plan.deadline <= now:
                raise _blocked("WORKFLOW_TIMEOUT", "Workflow deadline has elapsed.")
            deadline = min(reset, plan.deadline)
            profile_date = self._profile.reference_date.isoformat()
            active = connection.execute(
                "SELECT reference_date, profile_digest FROM quota_project_profiles "
                "WHERE project_id = ?",
                (plan.project_id,),
            ).fetchone()
            if active is not None and active["profile_digest"] != self._profile_digest:
                if active["reference_date"] >= profile_date:
                    raise _blocked(
                        "QUOTA_INSUFFICIENT", "A newer dated quota profile is required."
                    )
                connection.execute(
                    "UPDATE quota_reservations SET released = 1 WHERE project_id = ?",
                    (plan.project_id,),
                )
            connection.execute(
                "INSERT INTO quota_project_profiles VALUES (?, ?, ?) "
                "ON CONFLICT(project_id) DO UPDATE SET "
                "reference_date = excluded.reference_date, profile_digest = excluded.profile_digest",
                (plan.project_id, profile_date, self._profile_digest),
            )
            usage = connection.execute(
                """
                SELECT bucket, SUM(spent + CASE WHEN released = 0
                    AND binding_key IS NOT NULL AND deadline > ?
                    THEN remaining ELSE 0 END) AS committed
                FROM quota_reservation_buckets JOIN quota_reservations USING (reservation_id)
                WHERE project_id = ? AND quota_day = ? GROUP BY bucket
                """,
                (now.isoformat(), plan.project_id, day.isoformat()),
            )
            committed = {row["bucket"]: row["committed"] for row in usage}
            for bucket, units in required.items():
                if committed.get(bucket, 0) + units > self._profile.limits[bucket]:
                    raise _blocked(
                        "QUOTA_INSUFFICIENT",
                        "The complete workflow exceeds available quota.",
                    )
            binding_key = _ensure_account(connection, plan.binding, now)
            connection.execute(
                "INSERT INTO quota_reservations "
                "(reservation_id, project_id, quota_day, deadline, profile_digest, binding_key) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    reservation_id,
                    plan.project_id,
                    day.isoformat(),
                    deadline.isoformat(),
                    self._profile_digest,
                    binding_key,
                ),
            )
            connection.executemany(
                "INSERT INTO quota_endpoint_ceilings "
                "(reservation_id, endpoint, attempts, calls, attempts_per_call) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    (
                        reservation_id,
                        endpoint,
                        (ceiling.calls + plan.reconciliation_allowance.get(endpoint, 0))
                        * ceiling.attempts_per_call,
                        ceiling.calls + plan.reconciliation_allowance.get(endpoint, 0),
                        ceiling.attempts_per_call,
                    )
                    for endpoint, ceiling in plan.endpoint_ceilings.items()
                ),
            )
            connection.executemany(
                "INSERT INTO quota_reservation_buckets (reservation_id, bucket, remaining) "
                "VALUES (?, ?, ?)",
                ((reservation_id, bucket, units) for bucket, units in required.items()),
            )
        return QuotaReservation(
            reservation_id=reservation_id,
            plan_id=plan.plan_id,
            project_id=plan.project_id,
            quota_profile_id=plan.quota_profile_id,
            reset_at=reset,
            reserved=required,
        )

    async def debit_attempt(
        self, ctx: RequestContext, endpoint: Endpoint, attempt_id: OpaqueId
    ) -> None:
        await self.debit_call_attempt(
            ctx, endpoint, attempt_id, call_id=attempt_id, attempt_number=1
        )

    async def debit_call_attempt(
        self,
        ctx: RequestContext,
        endpoint: Endpoint,
        attempt_id: OpaqueId,
        *,
        call_id: OpaqueId,
        attempt_number: int,
    ) -> int:
        with self._database.transaction() as connection:
            now = self._clock.now().astimezone(UTC)
            row = connection.execute(
                "SELECT * FROM quota_reservations WHERE reservation_id = ?",
                (ctx.reservation_id,),
            ).fetchone()
            if (
                row is None
                or row["released"]
                or row["profile_digest"] != self._profile_digest
            ):
                raise _blocked(
                    "QUOTA_INSUFFICIENT", "A current quota reservation is required."
                )
            if row["binding_key"] != _binding_key(ctx.binding):
                raise _blocked(
                    "ACCOUNT_MISMATCH", "Reservation belongs to another account."
                )
            if (
                row["deadline"] <= now.isoformat()
                or row["quota_day"] != quota_period(now)[0].isoformat()
                or ctx.deadline <= now
                or ctx.cancellation.is_cancelled()
            ):
                raise _blocked(
                    "WORKFLOW_TIMEOUT",
                    "The quota reservation expired or was cancelled.",
                )
            ceiling = connection.execute(
                "SELECT calls, attempts_per_call FROM quota_endpoint_ceilings "
                "WHERE reservation_id = ? AND endpoint = ?",
                (ctx.reservation_id, endpoint),
            ).fetchone()
            if (
                ceiling is None
                or not 1 <= attempt_number <= ceiling["attempts_per_call"]
            ):
                raise _blocked(
                    "QUOTA_INSUFFICIENT", "Call attempt budget is exhausted."
                )
            costs = self._profile.costs[endpoint]
            _require_available_buckets(
                connection, row["project_id"], row["quota_day"], costs
            )
            inserted = connection.execute(
                "INSERT INTO quota_attempts VALUES (?, ?, ?) ON CONFLICT DO NOTHING",
                (ctx.reservation_id, attempt_id, endpoint),
            )
            if inserted.rowcount != 1:
                raise _blocked(
                    "QUOTA_INSUFFICIENT", "Attempt has already been charged."
                )
            if attempt_number == 1:
                calls = connection.execute(
                    "SELECT COUNT(*) FROM quota_calls WHERE reservation_id = ? AND endpoint = ?",
                    (ctx.reservation_id, endpoint),
                ).fetchone()[0]
                if calls >= ceiling["calls"]:
                    raise _blocked(
                        "QUOTA_INSUFFICIENT", "Endpoint call budget is exhausted."
                    )
                call = connection.execute(
                    "INSERT INTO quota_calls VALUES (?, ?, ?, 1) ON CONFLICT DO NOTHING",
                    (ctx.reservation_id, call_id, endpoint),
                )
            else:
                call = connection.execute(
                    "UPDATE quota_calls SET attempts = ? WHERE reservation_id = ? "
                    "AND call_id = ? AND endpoint = ? AND attempts = ?",
                    (
                        attempt_number,
                        ctx.reservation_id,
                        call_id,
                        endpoint,
                        attempt_number - 1,
                    ),
                )
            if call.rowcount != 1:
                raise _blocked("QUOTA_INSUFFICIENT", "Call attempt is out of sequence.")
            for bucket, units in costs.items():
                debited = connection.execute(
                    "UPDATE quota_reservation_buckets SET remaining = remaining - ?, "
                    "spent = spent + ? WHERE reservation_id = ? AND bucket = ? AND remaining >= ?",
                    (units, units, ctx.reservation_id, bucket, units),
                )
                if debited.rowcount != 1:
                    raise _blocked(
                        "QUOTA_INSUFFICIENT", "Reserved bucket is exhausted."
                    )
            return int(ceiling["attempts_per_call"])

    async def mark_exhausted(
        self, ctx: RequestContext, endpoint: Endpoint, attempt_id: OpaqueId
    ) -> None:
        with self._database.transaction() as connection:
            charged = connection.execute(
                "SELECT project_id, quota_day FROM quota_reservations "
                "JOIN quota_attempts USING (reservation_id) "
                "WHERE reservation_id = ? AND attempt_id = ? AND endpoint = ? "
                "AND profile_digest = ?",
                (ctx.reservation_id, attempt_id, endpoint, self._profile_digest),
            ).fetchone()
            if charged is None:
                raise _blocked(
                    "QUOTA_INSUFFICIENT", "No charged attempt matches the response."
                )
            connection.executemany(
                "INSERT INTO quota_exhausted_buckets VALUES (?, ?, ?) ON CONFLICT DO NOTHING",
                (
                    (charged["project_id"], charged["quota_day"], bucket)
                    for bucket in self._profile.costs[endpoint]
                ),
            )

    async def release(self, reservation_id: OpaqueId) -> None:
        with self._database.transaction() as connection:
            connection.execute(
                "UPDATE quota_reservations SET released = 1 WHERE reservation_id = ?",
                (reservation_id,),
            )
