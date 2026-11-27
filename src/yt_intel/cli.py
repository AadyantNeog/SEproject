from __future__ import annotations

import argparse
import importlib
import os
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import cast

import anyio
import httpx

from .auth.account import JsonAccountStateStore, LocalAccountService, QuotaCosts
from .auth.oauth import (
    OAuthClient,
    load_oauth_client_config,
    open_system_browser,
)
from .auth.vault import KeyringTokenVault
from .bootstrap import create_fixture_server
from .client_skills import sync_claude_skills
from .contracts.account import AccountStatus, TokenVault
from .contracts.common import OpaqueId
from .contracts.errors import ContractError, ErrorDetail
from .contracts.workflow import Clock, QuotaLedger
from .infrastructure.database import Database, default_database_path
from .infrastructure.http import AccountedHttpExecutor
from .infrastructure.repositories import SqliteAccountDataRepository
from .providers.youtube import LiveYouTubeReadProvider

_OAUTH_SECRETS_ENV = "YT_INTEL_OAUTH_CLIENT_SECRETS"
_DEFAULT_QUOTA_PROFILE_ID = "youtube-2026-11-16"


def _default_quota_profile_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "config"
        / "quota-profiles"
        / f"{_DEFAULT_QUOTA_PROFILE_ID}.json"
    )


def _load_sqlite_quota_ledger(
    database: Database,
    *,
    quota_profile_path: Path | None = None,
    clock: Clock | None = None,
) -> tuple[QuotaLedger, OpaqueId, QuotaCosts]:
    """Load Paul's P2-02 SqliteQuotaLedger; fail closed if P2-02 is not yet installed."""
    try:
        quota_module = importlib.import_module("yt_intel.infrastructure.quota")
        profile_cls = getattr(quota_module, "QuotaProfile")
        ledger_cls = getattr(quota_module, "SqliteQuotaLedger")
    except (ImportError, AttributeError):
        raise ContractError(
            ErrorDetail(
                code="PROVIDER_UNAVAILABLE",
                message="SQLite quota ledger (P2-02) is not available in this build.",
                retryable=False,
                safe_next_action="Install or merge P2-02 quota accounting before running live CLI sign-in.",
            )
        ) from None

    profile_path = (
        quota_profile_path
        if quota_profile_path is not None
        else _default_quota_profile_path()
    )
    if not profile_path.is_file():
        raise ContractError(
            ErrorDetail(
                code="PROVIDER_UNAVAILABLE",
                message="Quota profile configuration file is missing.",
                retryable=False,
                safe_next_action="Supply a valid --quota-profile JSON path.",
            )
        )
    try:
        profile = profile_cls.load(profile_path)
    except (OSError, ValueError):
        raise ContractError(
            ErrorDetail(
                code="INVALID_INPUT",
                message="The configured quota profile could not be read or validated.",
                retryable=False,
                safe_next_action="Supply a valid --quota-profile JSON path.",
            )
        ) from None
    ledger = cast(QuotaLedger, ledger_cls(database, profile, clock=clock))
    return ledger, str(profile.profile_id), cast(QuotaCosts, profile.required_buckets)


async def run_cli_auth(
    *,
    client_secrets_path: Path,
    enable_writes: bool,
    channel_id: str | None = None,
    timeout_seconds: float = 120.0,
    vault: TokenVault | None = None,
    open_browser: Callable[[str], bool] = open_system_browser,
    database_path: Path | None = None,
    account_state_path: Path | None = None,
    quota_ledger: QuotaLedger | None = None,
    quota_costs: QuotaCosts | None = None,
    quota_profile_path: Path | None = None,
    quota_profile_id: OpaqueId = _DEFAULT_QUOTA_PROFILE_ID,
    clock: Clock | None = None,
    oauth_transport: httpx.AsyncBaseTransport | None = None,
    api_transport: httpx.AsyncBaseTransport | None = None,
) -> AccountStatus:
    """Execute the operator CLI browser OAuth sign-in flow for read or write scopes.

    Reloads any previously saved non-secret active account record so enabling writes
    in a separate CLI invocation enforces same-channel verification, and routes the
    channel lookup through the persistent QuotaLedger (Paul's P2-02).
    """
    config = load_oauth_client_config(client_secrets_path)
    resolved_vault = vault if vault is not None else KeyringTokenVault()
    db_path = (
        database_path if database_path is not None else default_database_path("live")
    )
    db = Database(db_path)
    db.migrate()
    account_data = SqliteAccountDataRepository(db, clock=clock)
    state_path = (
        account_state_path
        if account_state_path is not None
        else db_path.with_name("account-live.json")
    )
    state_store = JsonAccountStateStore(state_path)

    if quota_ledger is None:
        ledger, resolved_profile_id, quota_costs = _load_sqlite_quota_ledger(
            db, quota_profile_path=quota_profile_path, clock=clock
        )
    else:
        ledger = quota_ledger
        resolved_profile_id = quota_profile_id

    oauth_executor = AccountedHttpExecutor(
        quota_ledger=ledger,
        transport=oauth_transport,
        clock=clock,
    )
    oauth_client = OAuthClient(config, oauth_executor, clock=clock)
    service = LocalAccountService(
        installation_id="local-cli",
        mode="live",
        vault=resolved_vault,
        oauth_client=oauth_client,
        account_data=account_data,
        clock=clock,
        state_store=state_store,
    )
    read_executor = AccountedHttpExecutor(
        quota_ledger=ledger,
        auth_headers=service,
        transport=api_transport,
        clock=clock,
    )
    read_provider = LiveYouTubeReadProvider(read_executor, clock=clock)
    try:
        return await service.authorize_via_browser(
            enable_writes=enable_writes,
            read_provider=read_provider,
            quota_ledger=ledger,
            quota_costs=quota_costs,
            quota_profile_id=resolved_profile_id,
            selected_channel_id=channel_id,
            timeout_seconds=timeout_seconds,
            open_browser=open_browser,
        )
    finally:
        await read_executor.aclose()
        await oauth_executor.aclose()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="yt-intel")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="Run the local MCP server over stdio")
    serve.add_argument("--provider", choices=("fixture",), default="fixture")
    serve.add_argument(
        "--project-root", type=Path, help="Checkout for fixture previews and skills"
    )
    serve.add_argument(
        "--fixture-db", type=Path, help="Override the local fixture database path"
    )
    skills = commands.add_parser(
        "sync-claude-skills", help="Copy canonical skills to Claude Code"
    )
    skills.add_argument("--project-root", type=Path, default=Path.cwd())
    skills.add_argument(
        "--check", action="store_true", help="Verify the copies without writing"
    )
    auth = commands.add_parser(
        "auth", help="Authorise a local YouTube account through Google browser OAuth"
    )
    mode_group = auth.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--read",
        action="store_true",
        help="Request explicit read-only scope (youtube.readonly)",
    )
    mode_group.add_argument(
        "--enable-writes",
        action="store_true",
        help="Request explicit read + write scopes (youtube.readonly, youtube.force-ssl)",
    )
    auth.add_argument(
        "--client-secrets",
        type=Path,
        default=None,
        help=f"Path to local Google Desktop OAuth JSON (or set {_OAUTH_SECRETS_ENV})",
    )
    auth.add_argument(
        "--channel-id",
        type=str,
        default=None,
        help="Optional UC... channel ID when the Google account owns multiple channels",
    )
    auth.add_argument(
        "--quota-profile",
        type=Path,
        default=None,
        help="Optional path to a dated YouTube quota profile JSON file",
    )
    auth.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="Browser callback timeout in seconds (default: 120)",
    )
    args = parser.parse_args(argv)

    if args.command == "auth":
        secrets_path: Path | None = args.client_secrets
        if secrets_path is None:
            env_path = os.environ.get(_OAUTH_SECRETS_ENV, "").strip()
            if env_path:
                secrets_path = Path(env_path)
        if secrets_path is None:
            print(
                f"AUTH_REQUIRED: Supply --client-secrets <path> or set {_OAUTH_SECRETS_ENV}.",
                file=sys.stderr,
            )
            return 2
        try:
            status = anyio.run(
                lambda: run_cli_auth(
                    client_secrets_path=secrets_path,
                    enable_writes=bool(args.enable_writes),
                    channel_id=args.channel_id,
                    timeout_seconds=args.timeout,
                    quota_profile_path=args.quota_profile,
                )
            )
        except ContractError as exc:
            print(
                f"{exc.detail.code}: {exc.detail.message} Next: {exc.detail.safe_next_action}",
                file=sys.stderr,
            )
            return 1
        print(
            f"Authorised channel {status.channel_title} ({status.binding.channel_id}) "
            f"with scopes: {', '.join(status.scopes)}"
        )
        return 0

    try:
        root = (
            args.project_root.resolve(strict=True)
            if args.project_root is not None
            else None
        )
        if root is not None and not root.is_dir():
            raise ValueError("project root must be a directory")
        if args.command == "sync-claude-skills":
            assert root is not None
            for name, digest in sync_claude_skills(root, check=args.check).items():
                print(f"{name} {digest}")
            return 0
        server = create_fixture_server(root, fixture_db=args.fixture_db)
    except (OSError, ValueError) as error:
        parser.error(str(error))

    server.run(transport="stdio")
    return 0
