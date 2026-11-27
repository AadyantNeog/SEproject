"""J2-07 scheduled live read-only check with a fixed quota budget.

The check is meant for a protected runner that an operator has provisioned.
It sends at most two official read requests, `channels.list?mine=true` and
`videos.list`, inside one reservation drawn from a dedicated daily budget.
Every gate is evaluated before the vault, the network or the quota ledger is
touched: an explicit enable flag, a recorded D-02 resolution, a valid
operator-chosen public video, the OAuth client configuration and a saved
read-only account. A failing gate reports `blocked` with zero provider calls.

The report holds statuses, counts and identifiers the operator supplied. It
never includes tokens, channel titles or retrieved metadata text. This module
has no write path.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal
from uuid import uuid4

import anyio
import httpx

from yt_intel.auth.account import JsonAccountStateStore, LocalAccountService
from yt_intel.auth.oauth import (
    YOUTUBE_READONLY_SCOPE,
    OAuthClient,
    load_oauth_client_config,
)
from yt_intel.auth.vault import KeyringTokenVault
from yt_intel.contracts.account import TokenVault
from yt_intel.contracts.errors import ContractError
from yt_intel.contracts.workflow import (
    CallCeiling,
    Clock,
    Endpoint,
    RequestContext,
    WorkflowPlan,
)
from yt_intel.domain.identifiers import parse_video_id
from yt_intel.infrastructure.database import Database, default_database_path
from yt_intel.infrastructure.http import AccountedHttpExecutor
from yt_intel.infrastructure.quota import QuotaProfile, SqliteQuotaLedger
from yt_intel.infrastructure.repositories import SqliteAccountDataRepository
from yt_intel.providers.youtube import LiveYouTubeReadProvider

ENABLE_ENV = "YT_INTEL_LIVE_READ_CHECK"
VIDEO_ENV = "YT_INTEL_LIVE_CHECK_VIDEO"
SECRETS_ENV = "YT_INTEL_OAUTH_CLIENT_SECRETS"
PROJECT_ID = "live-read-check"
_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY = _ROOT / "docs/evidence/policy-and-consent/d02-status.json"
DEFAULT_PROFILE = _ROOT / "config/quota-profiles/live-read-check-2026-11-28.json"
_ENDPOINTS: tuple[Endpoint, ...] = ("channels.list", "videos.list")

type Status = Literal["ok", "blocked", "failed"]


class _NotCancelled:
    def is_cancelled(self) -> bool:
        return False

    async def wait(self) -> None:
        await anyio.sleep_forever()


@dataclass
class CheckReport:
    status: Status
    code: str
    message: str
    gates: dict[str, bool] = field(default_factory=dict)
    provider_attempts: int = 0
    quota: dict[str, object] = field(default_factory=dict)
    results: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "task": "J2-07",
            "mode": "live",
            "read_only": True,
            "status": self.status,
            "code": self.code,
            "message": self.message,
            "gates": self.gates,
            "provider_attempts": self.provider_attempts,
            "quota": self.quota,
            "results": self.results,
        }


def policy_resolved(path: Path) -> bool:
    """Accept only a human-recorded D-02 resolution with an evidence link."""
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(record, Mapping):
        return False
    evidence = record.get("evidence_url")
    recorded_by = record.get("recorded_by")
    return (
        record.get("state") == "resolved"
        and isinstance(evidence, str)
        and evidence.startswith("https://")
        and isinstance(recorded_by, str)
        and bool(recorded_by.strip())
    )


def _blocked(report: CheckReport, code: str, message: str) -> CheckReport:
    report.status, report.code, report.message = "blocked", code, message
    return report


def _attempts(database: Database, reservation_id: str) -> int:
    with database.transaction(immediate=False) as connection:
        row = connection.execute(
            "SELECT COUNT(*) FROM quota_attempts WHERE reservation_id = ?",
            (reservation_id,),
        ).fetchone()
    return int(row[0])


async def run_check(
    *,
    environ: Mapping[str, str],
    policy_path: Path = DEFAULT_POLICY,
    profile_path: Path = DEFAULT_PROFILE,
    database_path: Path | None = None,
    account_state_path: Path | None = None,
    vault: TokenVault | None = None,
    clock: Clock | None = None,
    oauth_transport: httpx.AsyncBaseTransport | None = None,
    api_transport: httpx.AsyncBaseTransport | None = None,
) -> CheckReport:
    report = CheckReport(status="blocked", code="", message="")
    gates = report.gates
    gates["enabled"] = environ.get(ENABLE_ENV) == "1"
    if not gates["enabled"]:
        return _blocked(
            report, "LIVE_CHECK_NOT_ENABLED", f"Set {ENABLE_ENV}=1 on the runner."
        )
    gates["d02_resolved"] = policy_resolved(policy_path)
    if not gates["d02_resolved"]:
        return _blocked(
            report,
            "POLICY_UNRESOLVED",
            "D-02 has no recorded resolution. Live-derived processing stays disabled.",
        )
    try:
        video_id = parse_video_id(environ.get(VIDEO_ENV, ""))
        gates["video_configured"] = True
    except ContractError:
        gates["video_configured"] = False
        return _blocked(
            report,
            "INVALID_INPUT",
            f"Set {VIDEO_ENV} to an authorised public test video ID.",
        )
    secrets = environ.get(SECRETS_ENV, "").strip()
    gates["oauth_client_configured"] = bool(secrets) and Path(secrets).is_file()
    if not gates["oauth_client_configured"]:
        return _blocked(
            report,
            "AUTH_REQUIRED",
            f"Set {SECRETS_ENV} to the runner's OAuth client file.",
        )
    db_path = database_path or default_database_path("live")
    state_path = account_state_path or db_path.with_name("account-live.json")
    record = JsonAccountStateStore(state_path).load() if state_path.is_file() else None
    gates["account_connected"] = (
        record is not None
        and not record.disconnect_pending
        and YOUTUBE_READONLY_SCOPE in record.granted_scopes
    )
    if record is None or not gates["account_connected"]:
        return _blocked(
            report,
            "AUTH_REQUIRED",
            "Run `yt-intel auth --read` on the runner with the authorised test account.",
        )
    try:
        profile = QuotaProfile.load(profile_path)
    except (OSError, ValueError):
        gates["budget_profile"] = False
        return _blocked(report, "INVALID_INPUT", "The live check budget is missing.")
    gates["budget_profile"] = set(_ENDPOINTS) <= set(profile.costs)
    if not gates["budget_profile"]:
        return _blocked(report, "INVALID_INPUT", "The budget lacks read endpoints.")

    database = Database(db_path)
    database.migrate()
    ledger = SqliteQuotaLedger(database, profile, clock=clock)
    binding = record.binding
    deadline = datetime.now(UTC) + timedelta(seconds=60)
    plan = WorkflowPlan(
        plan_id=f"live-read-check-{uuid4().hex[:12]}",
        binding=binding,
        project_id=PROJECT_ID,
        quota_profile_id=profile.profile_id,
        endpoint_ceilings={
            endpoint: CallCeiling(calls=1, attempts_per_call=3)
            for endpoint in _ENDPOINTS
        },
        buckets={},
        candidate_cap=1,
        page_cap=1,
        sample_cap=0,
        deadline=deadline,
        cancellation_policy="cooperative",
        reconciliation_allowance={},
    )
    plan = plan.model_copy(update={"buckets": profile.required_buckets(plan)})
    report.quota = {
        "profile_id": profile.profile_id,
        "project_id": PROJECT_ID,
        "daily_budget": dict(profile.limits),
        "reserved": dict(plan.buckets),
    }
    try:
        reservation = await ledger.reserve(plan)
    except ContractError as error:
        return _blocked(report, error.detail.code, error.detail.message)

    resolved_vault = vault if vault is not None else KeyringTokenVault()
    oauth_executor = AccountedHttpExecutor(
        quota_ledger=ledger, transport=oauth_transport, clock=clock
    )
    service = LocalAccountService(
        installation_id="live-read-check",
        mode="live",
        vault=resolved_vault,
        oauth_client=OAuthClient(
            load_oauth_client_config(Path(secrets)), oauth_executor, clock=clock
        ),
        account_data=SqliteAccountDataRepository(database, clock=clock),
        clock=clock,
        initial_record=record,
    )
    read_executor = AccountedHttpExecutor(
        quota_ledger=ledger, auth_headers=service, transport=api_transport, clock=clock
    )
    provider = LiveYouTubeReadProvider(read_executor, clock=clock)
    context = RequestContext(
        request_id=uuid4().hex,
        binding=binding,
        reservation_id=reservation.reservation_id,
        deadline=deadline,
        cancellation=_NotCancelled(),
    )
    try:
        channels = await provider.get_my_channels(context)
        report.results["binding_matches"] = any(
            channel.channel_id == binding.channel_id for channel in channels
        )
        batch = await provider.get_videos(context, (video_id,))
        video = batch.videos.get(video_id)
        report.results["video_id"] = video_id
        report.results["video_availability"] = (
            "omitted" if video is None else video.availability
        )
        report.results["audio_language_evidence"] = (
            None if video is None else video.language_evidence
        )
        if report.results["binding_matches"] and video is not None:
            report.status, report.code = "ok", "OK"
            report.message = "Both read-only calls succeeded within budget."
        else:
            report.status, report.code = "failed", "ACCOUNT_OR_CONTENT_MISMATCH"
            report.message = "The bound channel or the test video was not returned."
    except ContractError as error:
        report.status, report.code = "failed", error.detail.code
        report.message = error.detail.message
    finally:
        await ledger.release(reservation.reservation_id)
        await read_executor.aclose()
        await oauth_executor.aclose()
        report.provider_attempts = _attempts(database, reservation.reservation_id)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the fixed-budget live read-only check (J2-07)."
    )
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--budget-profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--output", type=Path, help="Also write the JSON report.")
    args = parser.parse_args(argv)
    report = anyio.run(
        lambda: run_check(
            environ=os.environ,
            policy_path=args.policy,
            profile_path=args.budget_profile,
        )
    )
    text = json.dumps(report.to_dict(), indent=2)
    if args.output is not None:
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    # A blocked prerequisite is reported, not hidden, but it is not a failure
    # of the product. A failed live read is.
    return {"ok": 0, "blocked": 3, "failed": 1}[report.status]


if __name__ == "__main__":
    sys.exit(main())
